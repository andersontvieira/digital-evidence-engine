import json
import sqlite3

import pytest
from sqlalchemy import Engine, event
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.storage.database import V2_TABLES, open_database
from tests.test_parsing_service import legacy_catalog


def v2_catalog(root):
    (root / "originals/synthetic.txt").write_text("synthetic")
    ingest(root)
    with sqlite3.connect(root / "database/evidence.db") as c:
        assert c.execute("PRAGMA user_version").fetchone() == (5,)
        c.execute("DROP TABLE correlation_supports")
        c.execute("DROP TABLE correlation_candidates")
        c.execute("DROP TABLE correlation_runs")
        c.execute("DROP TABLE device_observations")
        c.execute("DROP TABLE network_observations")
        c.execute("DROP TABLE observation_runs")
        c.execute("DROP TABLE normalized_events")
        c.execute("DROP TABLE normalization_runs")
        c.execute("PRAGMA user_version=2")
        return {t: c.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in V2_TABLES}


def test_v2_requires_explicit_migration_and_readers_do_not_migrate(case_root):
    before = v2_catalog(case_root)
    path = case_root / "database/evidence.db"
    data = path.read_bytes()
    for command, status in [
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
    assert result.exit_code == 0 and json.loads(result.stdout)["schema_version"] == 5
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone() == (5,)
        assert {
            t: c.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in V2_TABLES
        } == before
    assert CliRunner().invoke(app, ["normalize", "--help"]).exit_code == 0


@pytest.mark.parametrize("version", [1, 2])
def test_migration_to_v3_failure_restores_starting_schema(case_root, version):
    (legacy_catalog if version == 1 else v2_catalog)(case_root)
    path = case_root / "database/evidence.db"
    with sqlite3.connect(path) as c:
        before = c.execute("SELECT * FROM sqlite_master ORDER BY name").fetchall()

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement == "PRAGMA user_version = 3":
            raise OSError("synthetic failure")

    event.listen(Engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(OSError):
            open_database(path, migrate=True)
    finally:
        event.remove(Engine, "before_cursor_execute", fail)
    with sqlite3.connect(path) as c:
        assert c.execute("PRAGMA user_version").fetchone() == (version,)
        assert c.execute("SELECT * FROM sqlite_master ORDER BY name").fetchall() == before
