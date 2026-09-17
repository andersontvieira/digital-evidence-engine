import hashlib
import json
import zipfile
from dataclasses import replace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.ingest.apple.parsers import PARSERS
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.ingest.parsing.csv import csv_document
from evidence_engine.ingest.parsing.framework import ParserResult, resolve_locator
from evidence_engine.ingest.parsing.service import parse_apple
from evidence_engine.models.entities import (
    ArchiveMember,
    EvidenceFile,
    ParsedRecord,
    ParserRun,
    SourceRecord,
)
from evidence_engine.storage.database import open_database
from tests.test_apple_parsers import PATHS, fixture


def archive(root, filename="synthetic-apple.zip", bad=None):
    path = root / "originals" / filename
    with zipfile.ZipFile(path, "w") as z:
        for index, member in enumerate(PATHS):
            z.writestr(member, bad if index == 1 and bad is not None else fixture(index))
    return path


def test_three_zip_chains_idempotency_and_private_cli(case_root):
    original = archive(case_root)
    before = original.read_bytes()
    ingest(case_root)
    result = CliRunner().invoke(app, ["parse", "apple", "--case-root", str(case_root)])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary["records_parsed"] == 8 and summary["sources_supported"] == 3
    assert all(isinstance(value, int) for value in summary.values())
    for sensitive in ["SYNTHETIC", "203.0.113.20", "2001:db8", "000001", str(case_root)]:
        assert sensitive not in result.output
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session, zipfile.ZipFile(original) as z:
        records = list(session.scalars(select(ParsedRecord)))
        ids = {r.id for r in records}
        assert {r.parser_id for r in records} == {p.parser_id for p in PARSERS}
        for record in records:
            source = session.get(SourceRecord, record.source_record_id)
            member = session.get(ArchiveMember, source.archive_member_id)
            evidence = session.get(EvidenceFile, member.evidence_file_id)
            run = session.get(ParserRun, record.parser_run_id)
            assert evidence.sha256 == hashlib.sha256(before).hexdigest()
            assert source.location == record.source_locator
            assert source.parser_id == record.parser_id == run.parser_id
            assert source.parser_version == record.parser_version == "1.0.0"
            data = z.read(member.member_path)
            assert hashlib.sha256(data).hexdigest() == member.sha256
            raw = resolve_locator(csv_document(data), record.source_locator)
            assert all(raw[key] == value for key, value in json.loads(record.payload_json).items())
    again = parse_apple(case_root)
    assert again.records_parsed == 0 and again.records_existing == 8
    with Session(engine) as session:
        assert set(session.scalars(select(ParsedRecord.id))) == ids
    engine.dispose()
    assert original.read_bytes() == before


def test_distinct_exports_keep_duplicate_occurrences(case_root):
    archive(case_root, "synthetic-a.zip")
    archive(case_root, "synthetic-b.zip")
    ingest(case_root)
    assert parse_apple(case_root).records_parsed == 16


@pytest.mark.parametrize(
    "bad,status", [(b"Unrelated\nvalue\n", "UNSUPPORTED"), (fixture(1) + b'"unfinished', "FAILED")]
)
def test_bad_source_does_not_prevent_independent_sources(case_root, bad, status):
    archive(case_root, bad=bad)
    ingest(case_root)
    summary = parse_apple(case_root)
    assert summary.records_parsed == 3
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        run = session.scalars(
            select(ParserRun).where(ParserRun.parser_id == PARSERS[1].parser_id)
        ).one()
        assert run.status == status and run.records_parsed == 0
        assert set(session.scalars(select(ParsedRecord.parser_id))) == {
            PARSERS[0].parser_id,
            PARSERS[2].parser_id,
        }
        assert (
            list(
                session.scalars(
                    select(SourceRecord).where(SourceRecord.parser_id == PARSERS[1].parser_id)
                )
            )
            == []
        )
    engine.dispose()


def test_failure_after_first_persisted_record_rolls_back_source_and_continues(case_root):
    archive(case_root)
    ingest(case_root)
    original = PARSERS[1]

    class BrokenParser:
        parser_id = original.parser_id
        parser_version = original.parser_version
        matches_path = original.matches_path
        supports = original.supports

        def parse(self, context, document):
            result = original.parse(context, document)
            return ParserResult(
                [result.records[0], replace(result.records[1], source_locator="$/absent")]
            )

    summary = parse_apple(case_root, (PARSERS[0], BrokenParser(), PARSERS[2]))
    assert summary.errors == 1 and summary.records_parsed == 3
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        assert (
            list(
                session.scalars(
                    select(ParsedRecord).where(ParsedRecord.parser_id == original.parser_id)
                )
            )
            == []
        )
        assert (
            list(
                session.scalars(
                    select(SourceRecord).where(SourceRecord.parser_id == original.parser_id)
                )
            )
            == []
        )
        assert (
            session.scalars(select(ParserRun).where(ParserRun.parser_id == original.parser_id))
            .one()
            .status
            == "FAILED"
        )
    engine.dispose()
