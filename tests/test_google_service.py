import hashlib
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.ingest.google.html import table_document
from evidence_engine.ingest.google.parsers import PARSERS
from evidence_engine.ingest.parsing.framework import ParserResult, resolve_locator
from evidence_engine.ingest.parsing.service import parse_google
from evidence_engine.models.entities import (
    ArchiveMember,
    EvidenceFile,
    ParsedRecord,
    ParserRun,
    SourceRecord,
)
from evidence_engine.storage.database import open_database

FIXTURES = Path(__file__).parent / "fixtures/synthetic/google"


def archive(root, filename="synthetic-takeout.zip"):
    path = root / "originals" / filename
    with zipfile.ZipFile(path, "w") as z:
        for fixture in sorted(FIXTURES.glob("*.html")):
            z.writestr("Takeout/Google Account/synthetic." + fixture.name, fixture.read_bytes())
    return path


def test_google_zip_provenance_idempotency_and_private_cli(case_root):
    original = archive(case_root)
    before = original.read_bytes()
    ingest(case_root)
    result = CliRunner().invoke(app, ["parse", "google", "--case-root", str(case_root)])
    assert result.exit_code == 0
    summary = json.loads(result.stdout)
    assert summary["records_parsed"] == 8 and summary["sources_supported"] == 2
    assert all(isinstance(v, int) for v in summary.values())
    for private in ["example.invalid", "203.0.113.10", "+55", "SyntheticAgent", str(case_root)]:
        assert private not in result.output
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session, zipfile.ZipFile(original) as z:
        records = list(session.scalars(select(ParsedRecord)))
        ids = {r.id for r in records}
        for r in records:
            source = session.get(SourceRecord, r.source_record_id)
            member = session.get(ArchiveMember, source.archive_member_id)
            evidence = session.get(EvidenceFile, member.evidence_file_id)
            run = session.get(ParserRun, r.parser_run_id)
            assert evidence.sha256 == hashlib.sha256(before).hexdigest()
            assert source.location == r.source_locator
            assert source.parser_id == r.parser_id == run.parser_id
            assert source.parser_version == r.parser_version == "1.0.0"
            data = z.read(member.member_path)
            assert hashlib.sha256(data).hexdigest() == member.sha256
            assert resolve_locator(table_document(data), r.source_locator) == json.loads(
                r.payload_json
            )
    again = parse_google(case_root)
    assert again.records_parsed == 0 and again.records_existing == 8
    with Session(engine) as session:
        assert set(session.scalars(select(ParsedRecord.id))) == ids
    engine.dispose()
    assert original.read_bytes() == before


def test_distinct_exports_preserve_all_occurrences(case_root):
    archive(case_root, "synthetic-a.zip")
    archive(case_root, "synthetic-b.zip")
    ingest(case_root)
    assert parse_google(case_root).records_parsed == 16


@pytest.mark.parametrize(
    "bad", [b"<table><tr><th>Wrong schema</th></tr></table>", b"<table><tr><td>synthetic malformed"]
)
def test_bad_source_is_audited_and_independent_source_continues(case_root, bad):
    (case_root / "originals/SubscriberInfo.html").write_bytes(bad)
    (case_root / "originals/ChangeHistory.html").write_bytes(
        (FIXTURES / "ChangeHistory.html").read_bytes()
    )
    ingest(case_root)
    summary = parse_google(case_root)
    assert summary.records_parsed == 4
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        run = session.scalars(
            select(ParserRun).where(ParserRun.parser_id == "google.subscriber_info")
        ).one()
        assert run.status == ("FAILED" if b"malformed" in bad else "UNSUPPORTED")
        assert run.records_parsed == 0
        assert set(session.scalars(select(ParsedRecord.parser_id))) == {"google.change_history"}
    engine.dispose()


def test_failure_after_first_record_rolls_back_all_source_observations(case_root):
    (case_root / "originals/SubscriberInfo.html").write_bytes(
        (FIXTURES / "SubscriberInfo.html").read_bytes()
    )
    ingest(case_root)
    original = PARSERS[0]

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

    summary = parse_google(case_root, (BrokenParser(),))
    assert summary.errors == 1 and summary.records_parsed == 0
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        assert list(session.scalars(select(ParsedRecord))) == []
        assert (
            list(
                session.scalars(
                    select(SourceRecord).where(SourceRecord.parser_id == original.parser_id)
                )
            )
            == []
        )
        assert session.scalars(select(ParserRun)).one().status == "FAILED"
    engine.dispose()


def test_complete_first_row_followed_by_malformed_html_never_persists(case_root):
    data = (
        (FIXTURES / "ChangeHistory.html")
        .read_bytes()
        .replace(b"</table>", b"<tr><td>broken</table>")
    )
    (case_root / "originals/ChangeHistory.html").write_bytes(data)
    ingest(case_root)
    assert parse_google(case_root).errors == 1
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        assert list(session.scalars(select(ParsedRecord))) == []
    engine.dispose()
