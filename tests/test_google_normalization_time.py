import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from evidence_engine.ingest.generic.service import ingest
from evidence_engine.ingest.parsing.service import parse_google
from evidence_engine.models.entities import NormalizedEvent, ParsedRecord
from evidence_engine.normalization.normalizers import NORMALIZERS, PlatformNormalizer
from evidence_engine.normalization.service import normalize_events
from evidence_engine.normalization.time import normalize_time
from evidence_engine.storage.database import open_database
from tests.test_google_service import FIXTURES
from tests.test_normalization import context


@pytest.mark.parametrize("parser", ["google.subscriber_info", "google.change_history"])
def test_exact_google_source_declared_utc(parser):
    raw = "2026-01-02 03:04:05 Z"
    c = context(parser, timestamp=raw)
    result = NORMALIZERS[1].normalize(c)
    assert NORMALIZERS[1].normalizer_version == "1.1.0"
    assert result.event.occurred_at_utc == "2026-01-02T03:04:05.000000Z"
    assert (result.event.time_status, result.event.time_basis) == ("normalized", "explicit_utc")
    assert c.timestamp_raw == raw
    assert PlatformNormalizer("google", "1.0.0").normalize(c).event.time_status == "raw_only"


@pytest.mark.parametrize(
    "raw",
    [
        "2026-01-02 03:04:05",
        "2026-01-02 03:04:05 UTCX",
        "2026/01/02 03:04:05 Z",
        "2026-01-02 25:04:05 Z",
        "2026-13-02 03:04:05 Z",
        "2026-01-32 03:04:05 Z",
        "2026-01-02T03:04:05 Z",
        "2026-02-29 03:04:05 Z",
        "2026-01-02 03:60:05 Z",
        "2026-01-02 03:04:60 Z",
        "2026-01-02 03:04:05 Z extra",
        "2026-01-02 03:04:05 Z\n",
        "2026-01-02 03:04:05  Z",
        "2026-1-02 03:04:05 Z",
        "2026-01-02 03:04:05 z",
        "2026-01-02 03:04:05.123 Z",
    ],
)
def test_google_variant_is_exact_and_calendar_validated(raw):
    result = NORMALIZERS[1].normalize(context("google.subscriber_info", timestamp=raw))
    assert result.event.time_status == "raw_only"
    assert result.event.occurred_at_utc is None


@pytest.mark.parametrize(
    "parser,index", [("meta.profile_activity", 0), ("apple.sign_on_activity", 2)]
)
def test_variant_is_not_enabled_for_other_platforms(parser, index):
    raw = "2026-01-02 03:04:05 Z"
    assert (
        NORMALIZERS[index].normalize(context(parser, timestamp=raw)).event.time_status == "raw_only"
    )
    assert NORMALIZERS[index].normalizer_version == "1.0.0"
    assert normalize_time(raw).status == "raw_only"


def test_existing_google_contracts_unchanged():
    for raw in (
        None,
        "",
        "2026-01-02T03:04:05Z",
        "2026-01-02T03:04:05+02:00",
        "2026-01-02 03:04:05 UTC",
    ):
        c = context("google.change_history", timestamp=raw)
        assert NORMALIZERS[1].normalize(c) == PlatformNormalizer("google", "1.0.0").normalize(c)


def test_versions_coexist_without_rewriting_observations_or_old_events(case_root):
    data = (
        (FIXTURES / "SubscriberInfo.html")
        .read_bytes()
        .replace(b"2024-01-02T03:04:05Z", b"2026-01-02 03:04:05 Z")
    )
    (case_root / "originals/SubscriberInfo.html").write_bytes(data)
    ingest(case_root)
    parse_google(case_root)
    old = PlatformNormalizer("google", "1.0.0")
    assert normalize_events(case_root, (old,)).events_normalized == 4
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        before = [
            (
                e.id,
                e.parsed_record_id,
                e.timestamp_raw,
                e.occurred_at_utc,
                e.time_status,
                e.time_basis,
            )
            for e in s.scalars(select(NormalizedEvent).order_by(NormalizedEvent.id))
        ]
        observations = [
            (r.id, r.payload_json, r.timestamp_raw, r.annotations_json)
            for r in s.scalars(select(ParsedRecord).order_by(ParsedRecord.id))
        ]
    assert normalize_events(case_root).events_normalized == 4
    assert normalize_events(case_root).events_normalized == 0
    with Session(engine) as s:
        historic = list(
            s.scalars(
                select(NormalizedEvent)
                .where(NormalizedEvent.normalizer_version == "1.0.0")
                .order_by(NormalizedEvent.id)
            )
        )
        assert [
            (
                e.id,
                e.parsed_record_id,
                e.timestamp_raw,
                e.occurred_at_utc,
                e.time_status,
                e.time_basis,
            )
            for e in historic
        ] == before
        current = list(
            s.scalars(select(NormalizedEvent).where(NormalizedEvent.normalizer_version == "1.1.0"))
        )
        assert {e.parsed_record_id for e in historic} == {e.parsed_record_id for e in current}
        assert sum(e.time_status == "normalized" for e in current) == 2
        assert all(
            json.loads(e.timestamp_raw) == "2026-01-02 03:04:05 Z"
            for e in current
            if e.time_status == "normalized"
        )
        assert [
            (r.id, r.payload_json, r.timestamp_raw, r.annotations_json)
            for r in s.scalars(select(ParsedRecord).order_by(ParsedRecord.id))
        ] == observations
    engine.dispose()
