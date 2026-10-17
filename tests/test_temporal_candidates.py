import json
import sqlite3
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from itertools import combinations
from unittest.mock import Mock

import pytest
from sqlalchemy import Engine, delete, event, select
from sqlalchemy.orm import Session
from typer._click.utils import strip_ansi
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.correlation.service import correlate_exact
from evidence_engine.correlation.temporal import (
    TemporalPairCandidate,
    _sweep_pairs,
    temporal_candidates,
)
from evidence_engine.errors import EvidenceError
from evidence_engine.models.entities import (
    CorrelationCandidate,
    DeviceObservation,
    NetworkObservation,
    NormalizedEvent,
)
from evidence_engine.normalization.service import normalize_events
from evidence_engine.query.timeline import TimelineItem
from evidence_engine.storage.database import open_database
from tests.test_correlation_schema import v4_catalog
from tests.test_correlation_service import seeded
from tests.test_media_inventory import tree_state
from tests.test_timeline import FIELDS, INSTANTS, ordered
from tests.test_timeline import timeline_case as timeline_case

START = "2026-01-02T03:04:05Z"
END = "2026-01-02T03:04:07Z"


def item(index, microseconds=0, platform="meta"):
    instant = datetime.fromisoformat(START) + timedelta(microseconds=microseconds)
    return TimelineItem(
        f"synthetic-event-{index:03}",
        f"synthetic-record-{index:03}",
        instant.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        platform,
        "content.activity",
        platform + ".event_normalizer",
        "1.1.0" if platform == "google" else "1.0.0",
        "normalized",
        "explicit_utc",
    )


def key(row):
    return row.occurred_at_utc, row.platform, row.event_kind, row.event_id


def oracle(rows, radius):
    pairs = []
    # Cartesian baseline belongs only to this synthetic test, never to production.
    for a, b in combinations(sorted(rows, key=key), 2):
        delta = datetime.fromisoformat(b.occurred_at_utc) - datetime.fromisoformat(
            a.occurred_at_utc
        )
        us = delta // timedelta(microseconds=1)
        if us <= radius * 1_000_000:
            pairs.append(TemporalPairCandidate(us, a, b))
    return tuple(pairs)


def query(root, **changes):
    return temporal_candidates(
        root, **({"start": START, "end": END, "max_delta_seconds": 1} | changes)
    )


@pytest.mark.parametrize(
    "us,expected", [(1, 1), (999999, 1), (1000000, 1), (1000001, 0), (86400000000, 0)]
)
def test_integer_microsecond_boundary(us, expected):
    count, pairs = _sweep_pairs((item(0), item(1, us)), 1, 1000)
    assert count == len(pairs) == expected
    if pairs:
        assert type(pairs[0].delta_microseconds) is int and pairs[0].delta_microseconds == us


def test_day_boundary_and_maximum_radius():
    rows = (item(0), item(1, 86_400_000_000), item(2, 86_400_000_001))
    assert _sweep_pairs(rows, 86400, 1000)[1] == oracle(rows, 86400)


@pytest.mark.parametrize("count", [0, 1, 3])
def test_unique_unordered_pairs_and_no_self(count):
    rows = tuple(item(i) for i in range(count))
    matched, pairs = _sweep_pairs(rows, 1, 1000)
    assert matched == count * (count - 1) // 2
    assert len({frozenset((p.event_a.event_id, p.event_b.event_id)) for p in pairs}) == matched
    assert all(p.event_a.event_id != p.event_b.event_id for p in pairs)


def test_timestamp_ties_and_same_record_are_not_excluded():
    rows = [
        replace(item(i, platform=platform), parsed_record_id="synthetic-shared-record")
        for i, platform in enumerate(("meta", "apple", "google", "meta"))
    ]
    rows[0] = replace(rows[0], event_kind="account.activity")
    rows = tuple(sorted(rows, key=key))
    matched, pairs = _sweep_pairs(rows, 1, 1000)
    assert matched == 6 and pairs == oracle(rows, 1)
    assert all(p.delta_microseconds == 0 for p in pairs)
    assert any(p.event_a.platform != p.event_b.platform for p in pairs)
    assert any(p.event_a.platform == p.event_b.platform for p in pairs)


def test_sweep_matches_cartesian_baseline_order_and_limited_prefix():
    rows = tuple(
        sorted(
            (
                item(i, (i * 7919 % 23) * 1000000 + i, ("meta", "google", "apple")[i % 3])
                for i in range(80)
            ),
            key=key,
        )
    )
    expected = oracle(rows, 3)
    assert _sweep_pairs(rows, 3, 10000) == (len(expected), expected)
    assert _sweep_pairs(rows, 3, 2) == (len(expected), expected[:2])


def test_materializes_only_limited_prefix(monkeypatch):
    import evidence_engine.correlation.temporal as module

    constructor = Mock(wraps=TemporalPairCandidate)
    monkeypatch.setattr(module, "TemporalPairCandidate", constructor)
    count, pairs = module._sweep_pairs(tuple(item(i) for i in range(120)), 1, 2)
    assert count == 7140 and len(pairs) == constructor.call_count == 2


@pytest.mark.parametrize(
    "filters",
    [
        {},
        {"platform": "meta"},
        {"platform": "google"},
        {"platform": "apple"},
        {"event_kind": "account.change"},
        {"platform": "google", "event_kind": "account.change"},
        {"platform": "META"},
        {"event_kind": "nonexistent"},
    ],
)
def test_current_selection_filters_and_undated_exclusion(timeline_case, filters):
    root, rows = timeline_case
    with sqlite3.connect(root / "database/evidence.db") as connection:
        connection.execute(
            "UPDATE normalized_events SET occurred_at_utc=?,time_status='normalized' "
            "WHERE normalizer_id='google.event_normalizer' AND normalizer_version!='1.1.0'",
            (INSTANTS[0],),
        )
    expected = tuple(
        TimelineItem(**row)
        for row in ordered(
            [
                row
                for row in rows
                if row["occurred_at_utc"] is not None
                and all(row[k] == v for k, v in filters.items())
            ]
        )
    )
    result = query(root, **filters)
    assert result.eligible_events == len(expected)
    assert result.items == oracle(expected, 1)
    assert result.matched_pairs == result.returned_pairs == len(result.items)
    assert not result.truncated


def test_half_open_window_and_limit_does_not_limit_events(timeline_case):
    root, rows = timeline_case
    result = query(root, start=INSTANTS[0], end=INSTANTS[3], limit=2)
    eligible = tuple(
        TimelineItem(**row)
        for row in ordered(
            [
                row
                for row in rows
                if row["occurred_at_utc"] is not None
                and INSTANTS[0] <= row["occurred_at_utc"] < INSTANTS[3]
            ]
        )
    )
    expected = oracle(eligible, 1)
    assert result.eligible_events == len(eligible)
    assert result.matched_pairs == len(expected)
    assert result.items == expected[:2] and result.truncated == (len(expected) > 2)


@pytest.mark.parametrize(
    "changes",
    [
        {"max_delta_seconds": 0},
        {"max_delta_seconds": 86401},
        {"max_delta_seconds": True},
        {"max_delta_seconds": 1.5},
        {"limit": 0},
        {"limit": 10001},
        {"limit": True},
        {"start": None},
        {"end": None},
        {"start": END},
        {"end": START},
        {"start": "2026-01-02T03:04:05"},
        {"start": "2026-01-02T03:04:05+00:00"},
        {"start": "2026-01-02T03:04:05.1234567Z"},
    ],
)
def test_invalid_arguments_fail_before_catalog(tmp_path, changes):
    with pytest.raises(EvidenceError):
        query(tmp_path, **changes)


def test_read_only_one_snapshot_only_event_queries(timeline_case):
    root, _ = timeline_case
    before = tree_state(root)
    connections = set()

    def inspect(connection, cursor, statement, parameters, context, executemany):
        if statement.lower().startswith("select"):
            assert not any(
                name in statement.lower()
                for name in (
                    "device_observations",
                    "network_observations",
                    "correlation_candidates",
                    "correlation_supports",
                    "parsed_records",
                    "payload_json",
                    "annotations_json",
                )
            )
            assert cursor.connection.execute("PRAGMA query_only").fetchone()[0] == 1
            assert cursor.connection.in_transaction
            connections.add(id(cursor.connection))

    event.listen(Engine, "before_cursor_execute", inspect)
    try:
        query(root)
    finally:
        event.remove(Engine, "before_cursor_execute", inspect)
    assert len(connections) == 1 and tree_state(root) == before


def test_exact_candidate_does_not_control_temporal_pair(case_root):
    seeded(case_root, count=3)
    normalize_events(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        rows = list(session.scalars(select(NormalizedEvent).order_by(NormalizedEvent.id)))
        assert len(rows) == 3
        ids = [row.id for row in rows]
        for row, offset in zip(rows, (0, 1, 10), strict=True):
            row.occurred_at_utc = item(0, offset * 1000000).occurred_at_utc
            row.time_status = "normalized"
            row.time_basis = "explicit_utc"
        for model in (DeviceObservation, NetworkObservation):
            session.execute(delete(model).where(model.parsed_record_id == rows[1].parsed_record_id))
        session.commit()
    engine.dispose()
    assert correlate_exact(case_root).candidates_created == 2
    result = query(case_root, end="2026-01-02T03:04:20Z")
    assert [(p.event_a.event_id, p.event_b.event_id) for p in result.items] == [(ids[0], ids[1])]
    assert not isinstance(result.items[0], CorrelationCandidate)


def test_cli_policy_determinism_and_restricted_projection(timeline_case):
    root, _ = timeline_case
    args = [
        "correlate",
        "temporal-candidates",
        "--case-root",
        str(root),
        "--start",
        START,
        "--end",
        END,
        "--max-delta-seconds",
        "1",
        "--limit",
        "2",
    ]
    first, second = CliRunner().invoke(app, args), CliRunner().invoke(app, args)
    assert first.exit_code == second.exit_code == 0
    assert first.stdout_bytes == second.stdout_bytes
    result = json.loads(first.stdout)
    assert result["policy"] == {
        "relation_kind": "temporal.proximity_candidate",
        "policy_id": "temporal.proximity",
        "policy_version": "1.0.0",
        "feature_class": "DERIVED",
        "max_delta_seconds": 1,
    }
    assert result["window"]["start"] == INSTANTS[0]
    for pair in result["items"]:
        assert set(pair) == {"event_a", "event_b", "delta_microseconds"}
        assert set(pair["event_a"]) == set(pair["event_b"]) == FIELDS
    for forbidden in (
        "pair_id",
        "payload",
        "annotations",
        "SYNTHETIC",
        "203.0.113",
        str(root),
        "score",
        "confidence",
    ):
        assert forbidden not in first.stdout
    assert result == json.loads(json.dumps(asdict(query(root, limit=2))))


@pytest.mark.parametrize("option", ["--start", "--end", "--max-delta-seconds"])
def test_required_cli_arguments(tmp_path, option):
    args = [
        "correlate",
        "temporal-candidates",
        "--case-root",
        str(tmp_path),
        "--start",
        START,
        "--end",
        END,
        "--max-delta-seconds",
        "1",
    ]
    index = args.index(option)
    del args[index : index + 2]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2


@pytest.mark.parametrize("mode", ["missing", "v4"])
def test_catalog_guard(case_root, mode):
    if mode == "v4":
        v4_catalog(case_root)
    with pytest.raises(EvidenceError):
        query(case_root)


def test_help():
    result = CliRunner().invoke(app, ["correlate", "temporal-candidates", "--help"], color=False)
    assert result.exit_code == 0 and "--max-delta-seconds" in strip_ansi(result.output)
