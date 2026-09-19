import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import Engine, delete, event, select
from sqlalchemy.orm import Session

from evidence_engine.correlation.service import correlate_exact
from evidence_engine.errors import EvidenceError
from evidence_engine.models.entities import (
    DeviceObservation,
    NetworkObservation,
    NormalizationRun,
    NormalizedEvent,
)
from evidence_engine.normalization.service import normalize_events
from evidence_engine.query.incident import query_incident_window
from evidence_engine.query.timeline import query_timeline
from evidence_engine.storage.database import open_database
from tests.test_correlation_schema import v4_catalog
from tests.test_correlation_service import seeded
from tests.test_technical_queries import (
    DEVICE_FIELDS,
    NETWORK_FIELDS,
    assert_memberships,
    assert_origin,
    clone,
    command,
    read_rows,
)
from tests.test_technical_queries import (
    technical_case as technical_case,
)
from tests.test_timeline import FIELDS, database_bytes

START = "2026-01-02T03:04:05Z"
END = "2026-01-02T03:04:07Z"


@pytest.fixture
def incident_case(technical_case):
    root = technical_case
    engine = open_database(root / "database/evidence.db")
    with Session(engine) as s:
        events = list(s.scalars(select(NormalizedEvent).order_by(NormalizedEvent.id)))
        for row, instant, kind in zip(
            events,
            [START, START, "2026-01-02T03:04:06Z", END],
            [
                "account.profile_activity",
                "account.profile_activity",
                "content.activity",
                "content.activity",
            ],
            strict=True,
        ):
            row.occurred_at_utc = instant.replace("Z", ".000000Z")
            row.time_status = "normalized"
            row.time_basis = "explicit_utc"
            row.event_kind = kind
        clone(
            s,
            events[0],
            event_ordinal=99,
            occurred_at_utc=None,
            time_status="missing",
            time_basis="unknown",
        )
        for version in ("1.0.0", "1.2.0"):
            run = NormalizationRun(
                case_id=events[0].case_id,
                normalizer_id="google.event_normalizer",
                normalizer_version=version,
                status="COMPLETED",
            )
            s.add(run)
            s.flush()
            clone(
                s,
                events[0],
                normalization_run_id=run.id,
                normalizer_id="google.event_normalizer",
                normalizer_version=version,
                platform="google",
            )
        s.commit()
    engine.dispose()
    return root


def query(root, **options):
    return query_incident_window(root, **({"start": START, "end": END} | options))


def context_expected(root, kind, parsed_record_id):
    rows = read_rows(root, kind + "_observations")
    return sorted(
        (
            r
            for r in rows
            if r["parsed_record_id"] == parsed_record_id
            and r["observer_id"] == kind + ".observer"
            and r["observer_version"] == "1.0.0"
        ),
        key=lambda r: (r["observation_ordinal"], r["id"]),
    )


def check_items(root, result):
    for item in result["items"]:
        assert set(item) == FIELDS | {"provenance", "device_context", "network_context"}
        assert_origin(root, item["provenance"])
        for kind, fields in [("device", DEVICE_FIELDS), ("network", NETWORK_FIELDS)]:
            context = item[kind + "_context"]
            expected = context_expected(root, kind, item["parsed_record_id"])
            assert [r["observation_id"] for r in context] == [r["id"] for r in expected]
            assert all(set(r) == fields - {"platform", "parsed_record_id"} for r in context)
            assert_memberships(root, context, kind)
            for row, source in zip(context, expected, strict=True):
                assert all(
                    row[f] == source[f] for f in row if f not in {"observation_id", "candidate_ids"}
                )
    text = json.dumps(result)
    for forbidden in (
        "value_raw",
        "ip_raw",
        "ip_canonical",
        "payload_json",
        "annotations_json",
        "timestamp_raw",
        "SYNTHETIC-DEVICE-X",
        "203.0.113.10",
        "2001:db8::1",
    ):
        assert forbidden not in text


def test_current_boundary_order_provenance_and_exact_context(incident_case):
    root = incident_case
    result = query(root)
    assert result["matched_total"] == result["returned"] == 3 and not result["truncated"]
    assert result["undated_current_events"] == 1
    assert result["policy_id"] == "current_event_policy" and result["policy_version"] == "1.0.0"
    items = result["items"]
    assert all(
        i["normalizer_id"] == "meta.event_normalizer" and i["normalizer_version"] == "1.0.0"
        for i in items
    )
    assert sum(i["occurred_at_utc"] == START.replace("Z", ".000000Z") for i in items) == 2
    assert all(i["occurred_at_utc"] != END.replace("Z", ".000000Z") for i in items)
    assert items == sorted(
        items, key=lambda i: (i["occurred_at_utc"], i["platform"], i["event_kind"], i["event_id"])
    )
    check_items(root, result)
    timeline = query_timeline(root, start=START, end=END)
    assert [i["event_id"] for i in items] == [i.event_id for i in timeline.items]


@pytest.mark.parametrize(
    "filters,total,undated",
    [
        ({"platform": "meta"}, 3, 1),
        ({"platform": "google"}, 0, 0),
        ({"event_kind": "content.activity"}, 1, 0),
        ({"event_kind": "account.profile_activity"}, 2, 1),
        ({"platform": "meta", "event_kind": "content.activity"}, 1, 0),
        ({"event_kind": "absent"}, 0, 0),
    ],
)
def test_exact_filters_and_undated_semantics(incident_case, filters, total, undated):
    result = query(incident_case, **filters)
    assert result["matched_total"] == result["returned"] == total
    assert result["undated_current_events"] == undated
    outside = query(
        incident_case, start="2020-01-01T00:00:00Z", end="2020-01-02T00:00:00Z", **filters
    )
    assert outside["items"] == [] and outside["undated_current_events"] == undated


def test_limit_prefix_and_deterministic_cli(incident_case):
    root = incident_case
    full = query(root)
    short = query(root, limit=2)
    assert short["matched_total"] == 3 and short["returned"] == 2 and short["truncated"]
    assert short["items"] == full["items"][:2] and short["undated_current_events"] == 1
    a = command(root, "incident-window", "--start", START, "--end", END)
    b = command(root, "incident-window", "--start", START, "--end", END)
    assert a.exit_code == b.exit_code == 0 and a.stdout_bytes == b.stdout_bytes
    assert json.loads(a.stdout) == full


def test_six_synthetic_posts_no_network_propagation_via_shared_candidate(case_root):
    seeded(case_root, count=7)
    normalize_events(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        events = list(s.scalars(select(NormalizedEvent).order_by(NormalizedEvent.id)))
        post_record_ids = [e.parsed_record_id for e in events[:6]]
        for i, row in enumerate(events):
            row.event_kind = "content.activity" if i < 6 else "account.profile_activity"
            row.occurred_at_utc = f"2026-01-02T03:04:{i + 5:02d}.000000Z"
            row.time_status = "normalized"
            row.time_basis = "explicit_utc"
        s.execute(
            delete(NetworkObservation).where(
                NetworkObservation.parsed_record_id.in_(post_record_ids)
            )
        )
        s.commit()
    engine.dispose()
    assert correlate_exact(case_root).errors == 0
    posts = query(case_root, end="2026-01-02T03:04:20Z", event_kind="content.activity")
    assert posts["matched_total"] == posts["returned"] == 6
    check_items(case_root, posts)
    assert all(i["device_context"] and i["network_context"] == [] for i in posts["items"])
    profile = query(case_root, end="2026-01-02T03:04:20Z", event_kind="account.profile_activity")[
        "items"
    ][0]
    assert profile["network_context"] and profile["network_context"][0]["candidate_ids"] == []
    # Same candidate and neighboring time cannot propagate the profile's IP to a post.
    for post in posts["items"]:
        assert (
            post["device_context"][0]["candidate_ids"]
            == profile["device_context"][0]["candidate_ids"]
        )
        assert post["device_context"][0]["candidate_ids"]
        assert post["network_context"] == []


def test_no_device_or_network_context_copied_from_neighbor(case_root):
    seeded(case_root, count=2)
    normalize_events(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        rows = list(s.scalars(select(NormalizedEvent).order_by(NormalizedEvent.id)))
        empty_id = rows[0].id
        for row in rows:
            row.occurred_at_utc = START.replace("Z", ".000000Z")
            row.time_status = "normalized"
        for model in (DeviceObservation, NetworkObservation):
            s.execute(delete(model).where(model.parsed_record_id == rows[0].parsed_record_id))
        s.commit()
    engine.dispose()
    items = query(case_root)["items"]
    empty = next(i for i in items if i["event_id"] == empty_id)
    neighbor = next(i for i in items if i["event_id"] != empty_id)
    assert empty["device_context"] == empty["network_context"] == []
    assert neighbor["device_context"] and neighbor["network_context"]


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--start", START],
        ["--end", END],
        ["--start", START, "--end", START],
        ["--start", END, "--end", START],
        ["--start", "2026-01-02T03:04:05+00:00", "--end", END],
        ["--start", "invalid", "--end", END],
        ["--start", START, "--end", END, "--limit", "0"],
        ["--start", START, "--end", END, "--limit", "5001"],
    ],
)
def test_invalid_or_missing_bounds_limit_no_creation(case_root, args):
    before = set(case_root.rglob("*"))
    result = command(case_root, "incident-window", *args)
    assert result.exit_code == 2 and "Traceback" not in result.output
    assert set(case_root.rglob("*")) == before


@pytest.mark.parametrize("mode", ["missing", "v4", "wal"])
def test_read_only_defenses(case_root, mode):
    if mode == "v4":
        v4_catalog(case_root)
    if mode == "wal":
        seeded(case_root)
        with sqlite3.connect(case_root / "database/evidence.db") as c:
            c.execute("PRAGMA journal_mode=WAL")
    before = database_bytes(case_root) if mode != "missing" else set(case_root.rglob("*"))
    result = command(case_root, "incident-window", "--start", START, "--end", END)
    assert result.exit_code == 2
    after = database_bytes(case_root) if mode != "missing" else set(case_root.rglob("*"))
    assert after == before


def test_single_opener_same_snapshot_no_originals_or_sensitive_selects(incident_case, monkeypatch):
    import evidence_engine.query.catalog as catalog

    root = incident_case
    before = database_bytes(root)
    original_open = Path.open
    database_open = catalog.open_database
    opens = []
    connections = set()

    def count_open(*args, **kwargs):
        assert kwargs == {"read_only": True}
        opens.append(True)
        return database_open(*args, **kwargs)

    def no_originals(path, *args, **kwargs):
        assert "originals" not in path.parts and "working" not in path.parts
        return original_open(path, *args, **kwargs)

    def inspect(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith("select") and "sqlite_master" not in statement:
            projection = statement.lower().split("from")[0]
            assert not any(
                k in projection
                for k in (
                    "value_raw",
                    "ip_raw",
                    "ip_canonical",
                    "payload_json",
                    "annotations_json",
                    "timestamp_raw",
                )
            )
            assert cursor.connection.in_transaction
            assert cursor.connection.execute("PRAGMA query_only").fetchone()[0] == 1
            assert connection.engine.url.query["mode"] == "ro"
            connections.add(id(cursor.connection))

    event.listen(Engine, "before_cursor_execute", inspect)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(catalog, "open_database", count_open)
            patch.setattr(Path, "open", no_originals)
            assert query(root)["returned"] == 3
    finally:
        event.remove(Engine, "before_cursor_execute", inspect)
    assert len(opens) == len(connections) == 1
    assert database_bytes(root) == before


def test_limit_validation_and_required_service_bounds(case_root):
    for limit in (0, 5001, True):
        with pytest.raises(EvidenceError, match="limit"):
            query(case_root, limit=limit)
    with pytest.raises(EvidenceError, match="requires start and end"):
        query(case_root, start=None)
