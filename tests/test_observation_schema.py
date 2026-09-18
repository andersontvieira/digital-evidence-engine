import json
import sqlite3

import pytest
from sqlalchemy import Engine, event
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.normalization.service import normalize_events
from evidence_engine.storage.database import V3_TABLES, open_database
from tests.test_normalization_schema import v2_catalog
from tests.test_normalization_service import populated
from tests.test_parsing_service import legacy_catalog


def v3_catalog(root):
    populated(root)
    normalize_events(root)
    with sqlite3.connect(root / "database/evidence.db") as c:
        assert c.execute("PRAGMA user_version").fetchone() == (4,)
        for table in ("device_observations", "network_observations", "observation_runs"):
            c.execute(f"DROP TABLE {table}")
        c.execute("PRAGMA user_version=3")
        return {t: c.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in V3_TABLES}


def test_v3_requires_explicit_migration_and_all_old_rows_survive(case_root):
    before = v3_catalog(case_root)
    path = case_root / "database/evidence.db"
    data = path.read_bytes()
    for command, status in [
        (["observe", "device-network"], 2),
        (["normalize", "events"], 2),
        (["parse", "apple"], 2),
        (["evidence", "ingest"], 2),
        (["evidence", "verify"], 0),
        (["evidence", "manifest"], 0),
    ]:
        result = CliRunner().invoke(app, [*command, "--case-root", str(case_root)])
        assert result.exit_code == status, result.output
        assert path.read_bytes() == data
    result = CliRunner().invoke(app, ["evidence", "migrate", "--case-root", str(case_root)])
    assert result.exit_code == 0 and json.loads(result.stdout)["schema_version"] == 4
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone() == (4,)
        assert {
            t: c.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in V3_TABLES
        } == before
        for table in ("device_observations", "network_observations", "observation_runs"):
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    assert CliRunner().invoke(app, ["observe", "--help"]).exit_code == 0


@pytest.mark.parametrize("version,setup", [(1, legacy_catalog), (2, v2_catalog), (3, v3_catalog)])
def test_v4_migration_failure_restores_schema_and_rows(case_root, version, setup):
    setup(case_root)
    path = case_root / "database/evidence.db"
    with sqlite3.connect(path) as c:
        before = list(c.iterdump())

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement == "PRAGMA user_version = 4":
            raise OSError("synthetic migration failure")

    event.listen(Engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(OSError):
            open_database(path, migrate=True)
    finally:
        event.remove(Engine, "before_cursor_execute", fail)
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone() == (version,)
        assert list(c.iterdump()) == before
