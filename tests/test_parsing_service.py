import hashlib
import json
import sqlite3
import subprocess
import sys
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.ingest.generic.verification import verify
from evidence_engine.ingest.instagram.parsers import PARSERS
from evidence_engine.ingest.parsing.framework import ExtractedRecord, ParserResult
from evidence_engine.ingest.parsing.service import parse_instagram
from evidence_engine.models.entities import (
    ArchiveMember,
    EvidenceFile,
    ParsedRecord,
    ParserRun,
    SourceRecord,
)
from evidence_engine.reports.manifest import manifest_json
from evidence_engine.storage.database import V1_TABLES, open_database

FIXTURES = Path(__file__).parent / "fixtures/synthetic/meta"


def write_source(root: Path, name: str, data: object) -> Path:
    path = root / "originals" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def synthetic_zip(root: Path, name: str = "synthetic-export.zip") -> Path:
    path = root / "originals" / name
    with zipfile.ZipFile(path, "w") as archive:
        for fixture in sorted(FIXTURES.rglob("*.json")):
            archive.writestr(fixture.relative_to(FIXTURES).as_posix(), fixture.read_bytes())
    return path


def counts(root: Path) -> dict[str, int]:
    engine = open_database(root / "database/evidence.db")
    try:
        with Session(engine) as session:
            return {
                model.__tablename__: session.scalar(select(func.count()).select_from(model))
                for model in (SourceRecord, ParserRun, ParsedRecord)
            }
    finally:
        engine.dispose()


def test_full_provenance_direct_and_archive_idempotency(case_root: Path) -> None:
    archive = synthetic_zip(case_root)
    direct = case_root / "originals/profile_activity.json"
    direct.write_bytes((FIXTURES / direct.name).read_bytes())
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (archive, direct)}
    ingest(case_root)
    baseline = manifest_json(case_root)
    first = parse_instagram(case_root)
    assert first.sources_inspected == first.sources_supported == 4
    assert first.records_parsed == 12 and first.errors == 0
    initial_counts = counts(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        ids = set(session.scalars(select(ParsedRecord.id)))
        records = session.scalars(select(ParsedRecord)).all()
        for record in records:
            source = session.get(SourceRecord, record.source_record_id)
            run = session.get(ParserRun, record.parser_run_id)
            inventory = session.get(SourceRecord, run.source_record_id)
            assert source.parser_id == record.parser_id == run.parser_id
            expected_version = "1.0.0" if record.parser_id == "meta.instagram_messages" else "1.1.0"
            assert source.parser_version == record.parser_version == expected_version
            assert source.location == record.source_locator
            assert inventory.parser_id == "evidence_engine.inventory"
            if source.archive_member_id:
                member = session.get(ArchiveMember, source.archive_member_id)
                evidence = session.get(EvidenceFile, member.evidence_file_id)
                assert evidence.sha256 == hashlib.sha256(archive.read_bytes()).hexdigest()
            else:
                evidence = session.get(EvidenceFile, source.evidence_file_id)
                assert evidence.relative_path == direct.name
    second = parse_instagram(case_root)
    assert second.records_parsed == 0 and second.records_existing == 12
    assert second.errors == 0 and counts(case_root) == initial_counts
    with Session(engine) as session:
        assert set(session.scalars(select(ParsedRecord.id))) == ids
    engine.dispose()
    assert manifest_json(case_root) == baseline
    assert all(item.status == "OK" for item in verify(case_root))
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (archive, direct)} == before


def test_equal_observations_in_two_exports_remain_separate(case_root: Path) -> None:
    synthetic_zip(case_root, "synthetic-export-a.zip")
    synthetic_zip(case_root, "synthetic-export-b.zip")
    ingest(case_root)
    assert parse_instagram(case_root).records_parsed == 18
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        records = session.scalars(
            select(ParsedRecord).where(
                ParsedRecord.source_locator == "$/profile_account_insights/0"
            )
        ).all()
        assert len(records) == 2
        assert records[0].payload_json == records[1].payload_json
        assert records[0].source_record_id != records[1].source_record_id
        origins = [session.get(SourceRecord, record.source_record_id) for record in records]
        assert origins[0].archive_member_id != origins[1].archive_member_id
    engine.dispose()


def test_new_parser_version_is_separate_observation_set(case_root: Path) -> None:
    source = case_root / "originals/profile_activity.json"
    source.write_bytes((FIXTURES / source.name).read_bytes())
    ingest(case_root)
    legacy = replace(PARSERS[0], parser_version="1.0.0")
    assert parse_instagram(case_root, (legacy,)).records_parsed == 3
    parser = PARSERS[0]
    assert parse_instagram(case_root, (parser,)).records_parsed == 3
    assert parse_instagram(case_root, (parser,)).records_existing == 3
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        assert set(session.scalars(select(ParsedRecord.parser_version))) == {"1.0.0", "1.1.0"}
    engine.dispose()


@pytest.mark.parametrize(
    "bad",
    [
        b"{",
        b'{"profile_account_insights":[{"timestamp":1},null]}',
        b'{"profile_account_insights":[{"timestamp":1},{}]}',
    ],
)
def test_bad_source_does_not_leave_partial_records_or_stop_other_sources(
    case_root: Path, bad: bytes
) -> None:
    (case_root / "originals/profile_activity.json").write_bytes(bad)
    (case_root / "originals/recently_deleted_content.json").write_bytes(
        (FIXTURES / "recently_deleted_content.json").read_bytes()
    )
    ingest(case_root)
    result = CliRunner().invoke(app, ["parse", "instagram", "--case-root", str(case_root)])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["records_parsed"] == 2
    assert "SYNTHETIC-DEVICE" not in result.output and str(case_root) not in result.output
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        assert set(session.scalars(select(ParsedRecord.parser_id))) == {
            "meta.recently_deleted_content"
        }
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceRecord)
                .where(SourceRecord.parser_id == "meta.profile_activity")
            )
            == 0
        )
        failed = session.scalars(select(ParserRun).where(ParserRun.status == "FAILED")).one()
        assert failed.error_code and failed.records_parsed == 0
    engine.dispose()


@pytest.mark.parametrize(
    "shape",
    [
        {"other": [{"timestamp": 1}]},
        {"profile_account_insights": {}},
        {"messages": [], "title": "synthetic"},
    ],
)
def test_meta_filename_with_unrelated_schema_is_not_selected(
    case_root: Path, shape: object
) -> None:
    write_source(case_root, "profile_activity.json", shape)
    ingest(case_root)
    result = parse_instagram(case_root)
    assert result.sources_supported == result.records_parsed == 0
    assert result.warnings == 1
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        run = session.scalars(select(ParserRun)).one()
        assert run.status == "UNSUPPORTED"
        assert "UNSUPPORTED_SCHEMA" in run.warnings_json
    engine.dispose()


@pytest.mark.parametrize("mode", ["duplicate", "locator", "invented", "database"])
def test_failure_after_first_record_rolls_back_source_and_observations(
    case_root: Path, mode: str
) -> None:
    write_source(
        case_root,
        "profile_activity.json",
        {"profile_account_insights": [{"timestamp": 1}, {"timestamp": 2}]},
    )
    ingest(case_root)
    baseline = counts(case_root)

    class BrokenParser:
        parser_id = "meta.profile_activity"
        parser_version = "synthetic-test"
        matches_path = PARSERS[0].matches_path
        supports = PARSERS[0].supports

        def parse(self, context, document):
            first = ExtractedRecord(
                "profile_activity", "$/profile_account_insights/0", 0, 1, {"timestamp": 1}
            )
            locator = (
                first.source_locator if mode == "duplicate" else "$/profile_account_insights/1"
            )
            if mode == "locator":
                locator = "$/profile_account_insights/999"
            second = ExtractedRecord(
                "profile_activity",
                locator,
                -1 if mode == "database" else 1,
                2,
                {"timestamp": 99 if mode == "invented" else 2},
            )
            return ParserResult([first, second], [])

    result = parse_instagram(case_root, (BrokenParser(),))
    assert result.errors == 1 and result.records_parsed == 0
    after = counts(case_root)
    assert after["source_records"] == baseline["source_records"]
    assert after["parsed_records"] == 0 and after["parser_runs"] == 1


def test_multiple_message_files_and_optional_fields(case_root: Path) -> None:
    for index in (1, 2):
        write_source(
            case_root,
            f"messages/inbox/synthetic_thread/message_{index}.json",
            {"participants": [], "messages": [{"content": f"synthetic {index}"}]},
        )
    ingest(case_root)
    result = parse_instagram(case_root)
    assert result.sources_supported == 2 and result.records_parsed == 4
    assert parse_instagram(case_root).records_existing == 4


@pytest.mark.parametrize("target", ["direct", "member", "container"])
def test_modified_cataloged_content_is_not_parsed_even_after_success(
    case_root: Path, target: str
) -> None:
    if target == "direct":
        path = case_root / "originals/profile_activity.json"
        path.write_bytes((FIXTURES / path.name).read_bytes())
    else:
        path = synthetic_zip(case_root)
    ingest(case_root)
    first = parse_instagram(case_root)
    before = counts(case_root)["parsed_records"]
    if target == "member":
        engine = open_database(case_root / "database/evidence.db")
        with Session(engine) as session:
            relative = session.scalar(
                select(ArchiveMember.working_relative_path).where(
                    ArchiveMember.member_path == "profile_activity.json"
                )
            )
        engine.dispose()
        path = case_root / "working" / relative
    path.write_bytes(b"synthetic tampering")
    second = parse_instagram(case_root)
    assert first.errors == 0 and second.errors >= 1 and second.records_parsed == 0
    assert counts(case_root)["parsed_records"] == before


def test_empty_supported_source_is_also_idempotent(case_root: Path) -> None:
    write_source(case_root, "profile_activity.json", {"profile_account_insights": []})
    ingest(case_root)
    first = parse_instagram(case_root)
    assert first.sources_supported == 1 and first.records_parsed == 0
    before = counts(case_root)
    assert parse_instagram(case_root).sources_skipped == 1
    assert counts(case_root) == before


def test_untracked_source_is_not_processed_and_missing_catalog_is_not_created(
    case_root: Path,
) -> None:
    result = CliRunner().invoke(app, ["parse", "instagram", "--case-root", str(case_root)])
    assert result.exit_code == 2 and not (case_root / "database").exists()
    ingest(case_root)
    write_source(
        case_root, "profile_activity.json", {"profile_account_insights": [{"timestamp": 1}]}
    )
    assert parse_instagram(case_root).sources_inspected == 0
    assert CliRunner().invoke(app, ["parse", "--help"]).exit_code == 0


def legacy_catalog(root: Path) -> dict[str, list[tuple]]:
    write_source(root, "profile_activity.json", {"profile_account_insights": [{"timestamp": 1}]})
    ingest(root)
    with sqlite3.connect(root / "database/evidence.db") as connection:
        connection.execute("DROP TABLE correlation_supports")
        connection.execute("DROP TABLE correlation_candidates")
        connection.execute("DROP TABLE correlation_runs")
        connection.execute("DROP TABLE device_observations")
        connection.execute("DROP TABLE network_observations")
        connection.execute("DROP TABLE observation_runs")
        connection.execute("DROP TABLE normalized_events")
        connection.execute("DROP TABLE normalization_runs")
        connection.execute("DROP TABLE parsed_records")
        connection.execute("DROP TABLE parser_runs")
        connection.execute("PRAGMA user_version=1")
        return {
            table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in V1_TABLES
        }


def test_v1_requires_explicit_migration_preserving_existing_rows(case_root: Path) -> None:
    before = legacy_catalog(case_root)
    database = case_root / "database/evidence.db"
    original_bytes = database.read_bytes()
    for command in (["parse", "instagram"], ["evidence", "ingest"], ["evidence", "verify"]):
        result = CliRunner().invoke(app, [*command, "--case-root", str(case_root)])
        assert result.exit_code == 2 and "migration" in result.output
        assert database.read_bytes() == original_bytes
    for _ in range(2):
        result = CliRunner().invoke(app, ["evidence", "migrate", "--case-root", str(case_root)])
        assert result.exit_code == 0 and json.loads(result.stdout)["schema_version"] == 5
    with sqlite3.connect(database) as connection:
        assert {
            table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in V1_TABLES
        } == before
    assert parse_instagram(case_root).records_parsed == 1


def test_migration_failure_rolls_back_schema(case_root: Path) -> None:
    from sqlalchemy import Engine

    legacy_catalog(case_root)

    def fail_version(connection, cursor, statement, parameters, context, executemany):
        if statement == "PRAGMA user_version = 2":
            raise OSError("synthetic migration interruption")

    event.listen(Engine, "before_cursor_execute", fail_version)
    try:
        with pytest.raises(OSError):
            open_database(case_root / "database/evidence.db", migrate=True)
    finally:
        event.remove(Engine, "before_cursor_execute", fail_version)
    with sqlite3.connect(case_root / "database/evidence.db") as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        } == V1_TABLES


@pytest.mark.parametrize("command", [["parse", "instagram"], ["evidence", "ingest"]])
def test_v1_hot_journal_is_not_recovered_before_rejection(
    case_root: Path, command: list[str]
) -> None:
    legacy_catalog(case_root)
    database = case_root / "database/evidence.db"
    code = """
import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute('PRAGMA cache_size=1')
connection.execute('BEGIN IMMEDIATE')
connection.execute('UPDATE ingestion_runs SET errors=?', ('synthetic' * 200000,))
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", code, str(database)], check=True, timeout=30)
    before = {p.name: p.read_bytes() for p in database.parent.iterdir()}
    assert "evidence.db-journal" in before
    result = CliRunner().invoke(app, [*command, "--case-root", str(case_root)])
    assert result.exit_code == 2
    assert {p.name: p.read_bytes() for p in database.parent.iterdir()} == before


@pytest.mark.parametrize("when", ["before_commit", "after_commit"])
def test_outer_commit_failure_cannot_leave_false_success(case_root: Path, when: str) -> None:
    write_source(
        case_root, "profile_activity.json", {"profile_account_insights": [{"timestamp": 1}]}
    )
    ingest(case_root)
    fired = False

    def interrupt(session):
        nonlocal fired
        if (
            not fired
            and not session.in_nested_transaction()
            and any(
                isinstance(item, ParserRun) and item.status == "COMPLETED"
                for item in session.identity_map.values()
            )
        ):
            fired = True
            raise OSError("synthetic commit interruption")

    event.listen(Session, when, interrupt)
    try:
        if when == "before_commit":
            result = parse_instagram(case_root)
            assert result.errors == 1 and result.records_parsed == 0
        else:
            with pytest.raises(EvidenceError, match="commit"):
                parse_instagram(case_root)
    finally:
        event.remove(Session, when, interrupt)
    assert fired
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        run = session.scalars(select(ParserRun)).one()
        total = session.scalar(select(func.count()).select_from(ParsedRecord))
        sources = session.scalar(select(func.count()).select_from(SourceRecord))
        if when == "before_commit":
            assert run.status == "FAILED" and run.error_code == "COMMIT_FAILED"
            assert total == 0 and sources == 1
        else:
            assert run.status == "COMPLETED" and total == 1 and sources == 2
    engine.dispose()


def test_failure_immediately_after_source_record_insert_rolls_back(case_root: Path) -> None:
    write_source(
        case_root, "profile_activity.json", {"profile_account_insights": [{"timestamp": 1}]}
    )
    ingest(case_root)

    def fail_insert(mapper, connection, target):
        if target.parser_id == "meta.profile_activity":
            raise RuntimeError("synthetic insert interruption")

    event.listen(SourceRecord, "after_insert", fail_insert)
    try:
        assert parse_instagram(case_root).errors == 1
    finally:
        event.remove(SourceRecord, "after_insert", fail_insert)
    assert counts(case_root) == {"source_records": 1, "parser_runs": 1, "parsed_records": 0}


def test_missing_archive_member_is_explicit_failure(case_root: Path) -> None:
    synthetic_zip(case_root)
    ingest(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        relative = session.scalar(
            select(ArchiveMember.working_relative_path).where(
                ArchiveMember.member_path == "profile_activity.json"
            )
        )
    engine.dispose()
    (case_root / "working" / relative).unlink()
    result = parse_instagram(case_root)
    assert result.errors == 1 and result.sources_supported == 2 and result.records_parsed == 6


def test_source_byte_limit_without_large_fixture(case_root: Path, monkeypatch) -> None:
    write_source(
        case_root, "profile_activity.json", {"profile_account_insights": [{"timestamp": 1}]}
    )
    ingest(case_root)
    monkeypatch.setattr("evidence_engine.ingest.parsing.service.MAX_SOURCE_BYTES", 16)
    result = parse_instagram(case_root)
    assert result.errors == 1 and result.records_parsed == 0
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        assert session.scalar(select(ParserRun.error_code)) == "SOURCE_SIZE_LIMIT"
    engine.dispose()


def test_unknown_schema_cannot_be_migrated(case_root: Path) -> None:
    legacy_catalog(case_root)
    database = case_root / "database/evidence.db"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version=99")
    before = database.read_bytes()
    result = CliRunner().invoke(app, ["evidence", "migrate", "--case-root", str(case_root)])
    assert result.exit_code == 2 and database.read_bytes() == before
