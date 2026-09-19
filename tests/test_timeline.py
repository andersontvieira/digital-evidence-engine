import json
import sqlite3
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.models.entities import NormalizationRun, NormalizedEvent
from evidence_engine.normalization.normalizers import PlatformNormalizer
from evidence_engine.normalization.service import normalize_events
from evidence_engine.query.policy import CURRENT_NORMALIZERS, POLICY_ID, POLICY_VERSION
from evidence_engine.query.timeline import query_timeline
from evidence_engine.storage.database import open_database
from tests.test_correlation_schema import v4_catalog
from tests.test_normalization_service import populated

FIELDS = {
    "event_id",
    "parsed_record_id",
    "occurred_at_utc",
    "platform",
    "event_kind",
    "normalizer_id",
    "normalizer_version",
    "time_status",
    "time_basis",
}
INSTANTS = [
    "2026-01-02T03:04:05.000000Z",
    "2026-01-02T03:04:05.123456Z",
    "2026-01-02T03:04:05.999999Z",
    "2026-01-02T03:04:06.000000Z",
]


@pytest.fixture
def timeline_case(case_root):
    populated(case_root)
    normalize_events(case_root)
    normalize_events(case_root, (PlatformNormalizer("google", "1.0.0"),))
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(NormalizedEvent).order_by(NormalizedEvent.platform, NormalizedEvent.id)
            )
        )
        current = [
            r
            for r in rows
            if r.normalizer_version == ("1.1.0" if r.platform == "google" else "1.0.0")
        ]
        for index, row in enumerate(current):
            row.occurred_at_utc = INSTANTS[index % len(INSTANTS)]
            row.time_status = "normalized"
            row.time_basis = "explicit_utc"
        for row, status in zip(current[:2], ("raw_only", "missing"), strict=True):
            row.occurred_at_utc = None
            row.time_status = status
            row.time_basis = "unknown"
        for row in rows:
            if row not in current:
                row.occurred_at_utc = None
                row.time_status = "raw_only"
                row.time_basis = "unknown"
        google = next(r for r in current if r.platform == "google")
        future_run = NormalizationRun(
            case_id=google.case_id,
            normalizer_id="google.event_normalizer",
            normalizer_version="1.2.0",
            status="COMPLETED",
        )
        session.add(future_run)
        session.flush()
        values = {
            column.name: getattr(google, column.name)
            for column in NormalizedEvent.__table__.columns
            if column.name not in {"id", "created_at"}
        }
        session.add(
            NormalizedEvent(
                **(values | {"normalization_run_id": future_run.id, "normalizer_version": "1.2.0"})
            )
        )
        # An additional future undated event must not inflate the current undated count.
        session.add(
            NormalizedEvent(
                **(
                    values
                    | {
                        "normalization_run_id": future_run.id,
                        "normalizer_version": "1.2.0",
                        "event_ordinal": 1,
                        "occurred_at_utc": None,
                        "time_status": "missing",
                    }
                )
            )
        )
        session.commit()
        expected = [
            {field: getattr(row, "id" if field == "event_id" else field) for field in FIELDS}
            for row in current
        ]
    engine.dispose()
    return case_root, expected


def ordered(rows):
    return sorted(
        rows, key=lambda r: (r["occurred_at_utc"], r["platform"], r["event_kind"], r["event_id"])
    )


def database_bytes(root):
    return {p.name: p.read_bytes() for p in (root / "database").iterdir() if p.is_file()}


def test_explicit_policy_current_versions_only_and_deterministic_json(timeline_case):
    root, expected = timeline_case
    assert POLICY_ID == "current_event_policy" and POLICY_VERSION == "1.0.0"
    assert CURRENT_NORMALIZERS == (
        ("meta.event_normalizer", "1.0.0"),
        ("google.event_normalizer", "1.1.0"),
        ("apple.event_normalizer", "1.0.0"),
    )
    args = ["query", "timeline", "--case-root", str(root)]
    before = database_bytes(root)
    first = CliRunner().invoke(app, args)
    second = CliRunner().invoke(app, args)
    assert first.exit_code == second.exit_code == 0, first.output
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    dated = ordered([r for r in expected if r["occurred_at_utc"] is not None])
    assert result["items"] == dated
    assert result["matched_total"] == result["returned"] == len(dated)
    assert not result["truncated"] and result["undated_current_events"] == 2
    assert {r["platform"] for r in result["items"]} == {"meta", "google", "apple"}
    assert all(set(row) == FIELDS for row in result["items"])
    assert all(
        row["normalizer_version"] == "1.1.0"
        for row in result["items"]
        if row["platform"] == "google"
    )
    assert "SYNTHETIC" not in first.stdout and "203.0.113" not in first.stdout
    assert database_bytes(root) == before


@pytest.mark.parametrize(
    "filters",
    [
        {"platform": "meta"},
        {"platform": "google"},
        {"platform": "apple"},
        {"event_kind": "communication.message"},
        {"event_kind": "account.change"},
        {"platform": "google", "event_kind": "account.change"},
        {"platform": "nonexistent"},
        {"event_kind": "nonexistent"},
        {"platform": "google", "start": INSTANTS[1], "end": INSTANTS[3]},
        {"start": "2026-01-02T03:04:05Z", "end": "2026-01-02T03:04:06Z"},
        {"start": INSTANTS[1]},
        {"end": INSTANTS[1]},
    ],
)
def test_filters_and_half_open_time_window(timeline_case, filters):
    root, rows = timeline_case
    subset = [
        r
        for r in rows
        if all(r[k] == filters[k] for k in ("platform", "event_kind") if k in filters)
    ]
    dated = [r for r in subset if r["occurred_at_utc"] is not None]
    # Independent datetime comparisons also check normalization of no-fraction input.
    from datetime import datetime

    for bound, predicate in (("start", lambda a, b: a >= b), ("end", lambda a, b: a < b)):
        if bound in filters:
            dated = [
                r
                for r in dated
                if predicate(
                    datetime.fromisoformat(r["occurred_at_utc"]),
                    datetime.fromisoformat(filters[bound]),
                )
            ]
    result = query_timeline(root, **filters)
    assert [asdict(item) for item in result.items] == ordered(dated)
    assert result.matched_total == result.returned == len(dated)
    assert result.undated_current_events == sum(r["occurred_at_utc"] is None for r in subset)


def test_limit_total_and_tie_order(timeline_case):
    root, _ = timeline_case
    full = query_timeline(root)
    small = query_timeline(root, limit=3)
    assert small.matched_total == full.matched_total and small.returned == 3 and small.truncated
    assert small.items == full.items[:3]
    assert len({i.occurred_at_utc for i in full.items}) < len(full.items)
    assert list(full.items) == sorted(
        full.items, key=lambda i: (i.occurred_at_utc, i.platform, i.event_kind, i.event_id)
    )


@pytest.mark.parametrize(
    "value",
    [
        "2026-01-02T03:04:05",
        "2026-01-02T03:04:05+00:00",
        "2026-01-02 03:04:05Z",
        "2026-02-30T03:04:05Z",
        "2026-01-02T03:04:60Z",
        "2026-01-02T03:04:05.1234567Z",
        "2026-01-02T03:04:05z",
        "2026-01-02T03:04:05Z ",
        "invalid",
    ],
)
def test_invalid_utc_input_rejected_without_database_creation(case_root, value):
    result = CliRunner().invoke(
        app, ["query", "timeline", "--case-root", str(case_root), "--start", value]
    )
    assert result.exit_code == 2
    assert not (case_root / "database").exists()


@pytest.mark.parametrize(
    "start,end",
    [(INSTANTS[1], INSTANTS[0]), (INSTANTS[0], INSTANTS[0]), ("2026-01-02T03:04:05Z", INSTANTS[0])],
)
def test_reversed_or_equal_bounds(case_root, start, end):
    with pytest.raises(EvidenceError, match="precede"):
        query_timeline(case_root, start=start, end=end)


@pytest.mark.parametrize("limit", [0, -1, 10001, True])
def test_invalid_limit(case_root, limit):
    with pytest.raises(EvidenceError, match="limit"):
        query_timeline(case_root, limit=limit)


def test_empty_catalog_missing_catalog_and_cli_help(case_root):
    result = CliRunner().invoke(app, ["query", "timeline", "--case-root", str(case_root)])
    assert result.exit_code == 2 and not (case_root / "database/evidence.db").exists()
    ingest(case_root)
    empty = query_timeline(case_root)
    assert empty.matched_total == empty.returned == empty.undated_current_events == 0
    assert empty.items == () and not empty.truncated
    assert CliRunner().invoke(app, ["query", "--help"]).exit_code == 0
    assert CliRunner().invoke(app, ["query", "timeline", "--help"]).exit_code == 0


def test_schema_v4_is_not_migrated(case_root):
    v4_catalog(case_root)
    before = database_bytes(case_root)
    with pytest.raises(EvidenceError, match="schema v5"):
        query_timeline(case_root)
    assert database_bytes(case_root) == before


def test_query_only_mode_and_no_raw_or_other_entity_reads(timeline_case, monkeypatch):
    root, _ = timeline_case
    original_open = Path.open
    checked = []

    def no_raw(path, *args, **kwargs):
        assert "originals" not in path.parts and "working" not in path.parts
        return original_open(path, *args, **kwargs)

    def inspect_query(connection, cursor, statement, parameters, context, executemany):
        if (
            statement.lstrip().upper().startswith("SELECT")
            and "FROM normalized_events" in statement
        ):
            assert connection.engine.url.query["mode"] == "ro"
            assert connection.connection.driver_connection.execute(
                "PRAGMA query_only"
            ).fetchone() == (1,)
            assert all(
                name not in statement
                for name in (
                    "timestamp_raw",
                    "ip_raw",
                    "device_identifier_raw",
                    "parsed_records",
                    "correlation_candidates",
                )
            )
            checked.append(True)

    before = database_bytes(root)
    event.listen(Engine, "before_cursor_execute", inspect_query)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(Path, "open", no_raw)
            query_timeline(root)
    finally:
        event.remove(Engine, "before_cursor_execute", inspect_query)
    assert len(checked) == 3 and database_bytes(root) == before


@pytest.mark.parametrize("mode", ["wal", "hot_journal"])
def test_no_wal_or_journal_recovery(case_root, mode):
    ingest(case_root)
    path = case_root / "database/evidence.db"
    if mode == "wal":
        with sqlite3.connect(path) as c:
            c.execute("PRAGMA journal_mode=WAL")
    else:
        code = """
import os, sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.execute('PRAGMA cache_size=1')
c.execute('BEGIN IMMEDIATE')
c.execute('UPDATE ingestion_runs SET errors=?', ('x' * 1000000,))
os._exit(0)
"""
        subprocess.run([sys.executable, "-c", code, str(path)], check=True, timeout=30)
        assert path.with_name("evidence.db-journal").exists()
    before = database_bytes(case_root)
    result = CliRunner().invoke(app, ["query", "timeline", "--case-root", str(case_root)])
    assert result.exit_code == 2
    assert database_bytes(case_root) == before
