import json
import sqlite3

import pytest
from sqlalchemy import Engine, event
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.storage.database import V4_TABLES, open_database
from tests.test_correlation_service import seeded, snapshot
from tests.test_normalization_schema import v2_catalog
from tests.test_observation_schema import v3_catalog
from tests.test_parsing_service import legacy_catalog


def v4_catalog(root):
    seeded(root)
    before = snapshot(root, V4_TABLES)
    with sqlite3.connect(root / "database/evidence.db") as c:
        assert c.execute("PRAGMA user_version").fetchone() == (5,)
        for table in ("correlation_supports", "correlation_candidates", "correlation_runs"):
            c.execute(f"DROP TABLE {table}")
        c.execute("PRAGMA user_version=4")
    return before


def test_v4_readers_and_writers_require_explicit_v5_migration(case_root):
    before = v4_catalog(case_root)
    path = case_root / "database/evidence.db"
    data = path.read_bytes()
    for command, status in [
        (["correlate", "exact"], 2),
        (["observe", "device-network"], 2),
        (["normalize", "events"], 2),
        (["parse", "instagram"], 2),
        (["evidence", "ingest"], 2),
        (["evidence", "verify"], 0),
        (["evidence", "manifest"], 0),
    ]:
        result = CliRunner().invoke(app, [*command, "--case-root", str(case_root)])
        assert result.exit_code == status, result.output
        assert path.read_bytes() == data
    result = CliRunner().invoke(app, ["evidence", "migrate", "--case-root", str(case_root)])
    assert result.exit_code == 0 and json.loads(result.stdout)["schema_version"] == 5
    assert snapshot(case_root, V4_TABLES) == before
    assert CliRunner().invoke(app, ["correlate", "--help"]).exit_code == 0
    assert (
        CliRunner().invoke(app, ["correlate", "exact", "--case-root", str(case_root)]).exit_code
        == 0
    )


@pytest.mark.parametrize(
    "version,setup", [(1, legacy_catalog), (2, v2_catalog), (3, v3_catalog), (4, v4_catalog)]
)
def test_v5_migration_rollback_and_explicit_chain(case_root, version, setup):
    setup(case_root)
    path = case_root / "database/evidence.db"
    with sqlite3.connect(path) as c:
        before = list(c.iterdump())
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    rows = snapshot(case_root, tables)

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement == "PRAGMA user_version = 5":
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
    open_database(path, migrate=True).dispose()
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone() == (5,)
    assert snapshot(case_root, tables) == rows
