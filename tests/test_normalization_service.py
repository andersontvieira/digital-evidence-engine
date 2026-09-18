import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.ingest.parsing.service import parse_apple, parse_google, parse_instagram
from evidence_engine.models.entities import (
    ArchiveMember,
    EvidenceFile,
    NormalizationRun,
    NormalizedEvent,
    ParsedRecord,
    SourceRecord,
)
from evidence_engine.normalization.normalizers import NORMALIZERS
from evidence_engine.normalization.service import normalize_events
from evidence_engine.storage.database import open_database
from tests.test_apple_service import archive as apple_archive
from tests.test_google_service import archive as google_archive
from tests.test_parsing_service import synthetic_zip


def populated(root):
    synthetic_zip(root)
    google_archive(root)
    apple_archive(root)
    ingest(root)
    for parse in (parse_instagram, parse_google, parse_apple):
        assert parse(root).errors == 0


def test_all_platforms_provenance_raw_preservation_and_idempotence(case_root):
    populated(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        before = [
            (r.id, r.payload_json, r.timestamp_raw, r.annotations_json)
            for r in s.scalars(select(ParsedRecord).order_by(ParsedRecord.id))
        ]
    result = CliRunner().invoke(app, ["normalize", "events", "--case-root", str(case_root)])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary["errors"] == 0 and summary["records_skipped"] == 2
    assert summary["events_normalized"] == len(before) - 2
    assert all(isinstance(v, int) for v in summary.values())
    assert "SYNTHETIC" not in result.output and "203.0.113" not in result.output
    with Session(engine) as s:
        events = list(s.scalars(select(NormalizedEvent)))
        ids = {e.id for e in events}
        assert {e.platform for e in events} == {"meta", "google", "apple"}
        assert len({e.event_kind for e in events}) == 7
        for e in events:
            record = s.get(ParsedRecord, e.parsed_record_id)
            source = s.get(SourceRecord, record.source_record_id)
            member = s.get(ArchiveMember, source.archive_member_id)
            evidence = s.get(EvidenceFile, member.evidence_file_id)
            assert (
                hashlib.sha256(
                    (case_root / "originals" / evidence.relative_path).read_bytes()
                ).hexdigest()
                == evidence.sha256
            )
            assert e.timestamp_raw == record.timestamp_raw
            assert e.normalizer_version == ("1.1.0" if e.platform == "google" else "1.0.0")
            assert e.event_ordinal == 0
    again = normalize_events(case_root)
    assert again.events_normalized == 0 and again.events_existing == len(ids)
    with Session(engine) as s:
        assert {e.id for e in s.scalars(select(NormalizedEvent))} == ids
        assert [
            (r.id, r.payload_json, r.timestamp_raw, r.annotations_json)
            for r in s.scalars(select(ParsedRecord).order_by(ParsedRecord.id))
        ] == before
    engine.dispose()


def test_failure_rolls_back_entire_normalizer_and_other_platforms_continue(case_root):
    populated(case_root)
    original = NORMALIZERS[0]

    class Broken:
        normalizer_id = original.normalizer_id
        normalizer_version = original.normalizer_version
        supports = original.supports
        calls = 0

        def normalize(self, context):
            self.calls += 1
            if self.calls == 2:
                raise ValueError("SYNTHETIC_PRIVATE_ERROR")
            return original.normalize(context)

    result = normalize_events(case_root, (Broken(), *NORMALIZERS[1:]))
    assert result.errors == 1 and result.events_normalized > 0
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        assert (
            list(s.scalars(select(NormalizedEvent).where(NormalizedEvent.platform == "meta"))) == []
        )
        run = s.scalars(
            select(NormalizationRun).where(NormalizationRun.normalizer_id == original.normalizer_id)
        ).one()
        assert run.status == "FAILED" and run.events_normalized == 0
        assert run.error_code == "NORMALIZATION_ERROR"
        assert "PRIVATE" not in run.diagnostics_json
        prior_ids = set(s.scalars(select(NormalizedEvent.id)))
    assert normalize_events(case_root).errors == 0
    with Session(engine) as s:
        assert prior_ids <= set(s.scalars(select(NormalizedEvent.id)))
    engine.dispose()


def test_multiple_exports_and_direct_sources_remain_independent(case_root):
    for name in ("synthetic-a.zip", "synthetic-b.zip"):
        synthetic_zip(case_root, name)
    (case_root / "originals/profile_activity.json").write_text(
        '{"profile_account_insights":[{"timestamp":1700000000}]}'
    )
    ingest(case_root)
    parse_instagram(case_root)
    summary = normalize_events(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        events = list(s.scalars(select(NormalizedEvent)))
        assert len(events) == summary.events_normalized
        pairs = [
            (s.get(ParsedRecord, e.parsed_record_id).payload_json, e.occurred_at_utc)
            for e in events
        ]
        assert len(set(pairs)) < len(pairs)
        direct = [
            s.get(SourceRecord, s.get(ParsedRecord, e.parsed_record_id).source_record_id)
            for e in events
        ]
        assert any(r.evidence_file_id is not None and r.archive_member_id is None for r in direct)
    engine.dispose()
