import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import Engine, delete, event, select
from sqlalchemy.orm import Session

from evidence_engine.correlation.service import correlate_exact
from evidence_engine.models.entities import (
    CorrelationCandidate,
    CorrelationSupport,
    DeviceObservation,
    NetworkObservation,
    NormalizationRun,
    NormalizedEvent,
)
from evidence_engine.normalization.service import normalize_events
from evidence_engine.query.incident import query_incident_window
from evidence_engine.query.incident_candidates import query_incident_candidates
from evidence_engine.storage.database import open_database
from tests.test_correlation_schema import v4_catalog
from tests.test_correlation_service import seeded
from tests.test_technical_queries import clone, command, read_rows
from tests.test_timeline import database_bytes

START = "2026-01-02T03:04:05Z"
END = "2026-01-02T03:04:07Z"
ENTRY_FIELDS = {
    "candidate_id",
    "candidate_kind",
    "correlator_id",
    "correlator_version",
    "rule_id",
    "rule_version",
    "candidate_support_count",
    "window_event_count",
    "window_support_occurrences",
    "window_platforms",
    "window_event_kinds",
    "events",
}
EVENT_FIELDS = {
    "event_id",
    "parsed_record_id",
    "occurred_at_utc",
    "platform",
    "event_kind",
    "observation_links",
}


def query(root, **kwargs):
    return query_incident_candidates(root, **({"start": START, "end": END} | kwargs))


@pytest.fixture
def matrix_case(case_root):
    seeded(case_root, count=4)
    normalize_events(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        rows = list(s.scalars(select(NormalizedEvent).order_by(NormalizedEvent.id)))
        for row, instant, kind in zip(
            rows,
            [START, "2026-01-02T03:04:06Z", END, "2026-01-02T03:04:06Z"],
            [
                "content.activity",
                "account.profile_activity",
                "account.profile_activity",
                "media.activity",
            ],
            strict=True,
        ):
            row.occurred_at_utc = instant.replace("Z", ".000000Z")
            row.time_status = "normalized"
            row.time_basis = "explicit_utc"
            row.event_kind = kind
        d = s.scalars(
            select(DeviceObservation).where(
                DeviceObservation.parsed_record_id == rows[0].parsed_record_id
            )
        ).one()
        clone(s, d, observation_ordinal=7, source_field_locator="/synthetic/second")
        single_d = s.scalars(
            select(DeviceObservation).where(
                DeviceObservation.parsed_record_id == rows[3].parsed_record_id
            )
        ).one()
        single_n = s.scalars(
            select(NetworkObservation).where(
                NetworkObservation.parsed_record_id == rows[3].parsed_record_id
            )
        ).one()
        single_d.value_raw = json.dumps("SYNTHETIC-SINGLETON")
        single_n.ip_canonical = "198.51.100.20"
        single_n.ip_raw = json.dumps("198.51.100.20")
        # A global platform outside the window must not leak into window_platforms.
        for model in (DeviceObservation, NetworkObservation):
            s.scalars(
                select(model).where(model.parsed_record_id == rows[2].parsed_record_id)
            ).one().platform = "apple"
        for version in ("1.0.0", "1.2.0"):
            run = NormalizationRun(
                case_id=rows[0].case_id,
                normalizer_id="google.event_normalizer",
                normalizer_version=version,
                status="COMPLETED",
            )
            s.add(run)
            s.flush()
            clone(
                s,
                rows[0],
                normalizer_id="google.event_normalizer",
                normalizer_version=version,
                normalization_run_id=run.id,
                platform="google",
            )
        s.commit()
    engine.dispose()
    assert correlate_exact(case_root).errors == 0
    return case_root


def check_links(root, items):
    supports = {r["id"]: r for r in read_rows(root, "correlation_supports")}
    devices = {r["id"]: r for r in read_rows(root, "device_observations")}
    networks = {r["id"]: r for r in read_rows(root, "network_observations")}
    events = {r["id"]: r for r in read_rows(root, "normalized_events")}
    candidates = {r["id"]: r for r in read_rows(root, "correlation_candidates")}
    for item in items:
        assert set(item) == ENTRY_FIELDS
        assert item["candidate_support_count"] == candidates[item["candidate_id"]]["support_count"]
        assert item["window_event_count"] == len({e["event_id"] for e in item["events"]})
        assert item["window_support_occurrences"] == sum(
            len(e["observation_links"]) for e in item["events"]
        )
        assert item["window_platforms"] == sorted({e["platform"] for e in item["events"]})
        assert item["window_event_kinds"] == sorted({e["event_kind"] for e in item["events"]})
        assert item["events"] == sorted(
            item["events"],
            key=lambda e: (e["occurred_at_utc"], e["platform"], e["event_kind"], e["event_id"]),
        )
        for e in item["events"]:
            assert set(e) == EVENT_FIELDS
            assert all(
                e[k] == events[e["event_id"]][k]
                for k in EVENT_FIELDS - {"event_id", "observation_links"}
            )
            assert e["observation_links"] == sorted(
                e["observation_links"],
                key=lambda link: (link["support_ordinal"], link["observation_id"]),
            )
            kind = item["candidate_kind"]
            for link in e["observation_links"]:
                support = supports[link["support_id"]]
                observation = (devices if kind == "device" else networks)[link["observation_id"]]
                assert support["candidate_id"] == item["candidate_id"]
                assert support[kind + "_observation_id"] == observation["id"]
                assert observation["parsed_record_id"] == e["parsed_record_id"]
                assert link["support_ordinal"] == support["support_ordinal"]
                fields = (
                    {"fact_kind", "namespace"}
                    if kind == "device"
                    else {"source_role", "ip_version"}
                )
                assert set(link) == fields | {
                    "observation_id",
                    "support_id",
                    "support_ordinal",
                    "source_field_locator",
                }
                assert all(link[f] == observation[f] for f in fields | {"source_field_locator"})
    text = json.dumps(items)
    for forbidden in (
        "value_raw",
        "ip_raw",
        "ip_canonical",
        "payload_json",
        "annotations_json",
        "timestamp_raw",
        "SYNTHETIC-ID-001",
        "203.0.113.10",
        "198.51.100.20",
        "key_digest",
    ):
        assert forbidden not in text


def test_current_same_record_links_global_counts_order_and_projection(matrix_case):
    result = query(matrix_case)
    assert (
        result["matched_candidates"] == result["returned_candidates"] == 2
        and not result["truncated"]
    )
    assert result["policy_id"] == "current_event_policy" and result["policy_version"] == "1.0.0"
    device, network = result["items"]
    assert device["candidate_kind"] == "device" and network["candidate_kind"] == "network"
    assert (
        device["candidate_support_count"],
        device["window_event_count"],
        device["window_support_occurrences"],
    ) == (4, 2, 3)
    assert (
        network["candidate_support_count"],
        network["window_event_count"],
        network["window_support_occurrences"],
    ) == (3, 2, 2)
    assert all(i["window_platforms"] == ["meta"] for i in result["items"])
    assert all(len(i["events"]) == 2 for i in result["items"])
    assert all(
        i["events"][0]["occurred_at_utc"] == START.replace("Z", ".000000Z") for i in result["items"]
    )
    assert all(
        e["occurred_at_utc"] < END.replace("Z", ".000000Z")
        for i in result["items"]
        for e in i["events"]
    )
    check_links(matrix_case, result["items"])


@pytest.mark.parametrize(
    "filters,matched",
    [
        ({"platform": "meta"}, 2),
        ({"platform": "google"}, 0),
        ({"platform": "apple"}, 0),
        ({"candidate_kind": "device"}, 1),
        ({"candidate_kind": "network"}, 1),
        ({"event_kind": "content.activity"}, 2),
        ({"event_kind": "media.activity"}, 0),
        ({"platform": "meta", "event_kind": "content.activity", "candidate_kind": "device"}, 1),
        ({"start": END, "end": "2026-01-02T03:04:08Z"}, 2),
    ],
)
def test_filters_boundaries_and_no_singleton_candidate(matrix_case, filters, matched):
    result = query(matrix_case, **filters)
    assert result["matched_candidates"] == matched
    if filters.get("event_kind") == "content.activity":
        assert all(i["window_event_count"] == 1 for i in result["items"])
        device = next(i for i in result["items"] if i["candidate_kind"] == "device")
        assert device["window_support_occurrences"] == 2
    if filters.get("event_kind") == "media.activity":
        original = query_incident_window(
            matrix_case, start=START, end=END, event_kind="media.activity"
        )
        assert original["returned"] == 1
    check_links(matrix_case, result["items"])


def test_limit_is_candidate_only_and_json_bytes_stable(matrix_case):
    full = query(matrix_case)
    limited = query(matrix_case, limit=1)
    assert (
        limited["matched_candidates"] == 2
        and limited["returned_candidates"] == 1
        and limited["truncated"]
    )
    assert limited["items"] == full["items"][:1]
    a = command(matrix_case, "incident-candidates", "--start", START, "--end", END)
    b = command(matrix_case, "incident-candidates", "--start", START, "--end", END)
    assert a.exit_code == b.exit_code == 0 and a.stdout_bytes == b.stdout_bytes
    assert json.loads(a.stdout) == full


def test_no_propagation_from_neighboring_record(case_root):
    seeded(case_root, count=3)
    normalize_events(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        rows = list(s.scalars(select(NormalizedEvent).order_by(NormalizedEvent.id)))
        for i, row in enumerate(rows):
            row.occurred_at_utc = START.replace("Z", ".000000Z")
            row.time_status = "normalized"
            row.event_kind = "content.activity" if i == 0 else "account.profile_activity"
        for model in (DeviceObservation, NetworkObservation):
            s.execute(delete(model).where(model.parsed_record_id == rows[0].parsed_record_id))
        s.commit()
    engine.dispose()
    correlate_exact(case_root)
    assert query(case_root, event_kind="content.activity")["items"] == []
    assert query(case_root, event_kind="account.profile_activity")["matched_candidates"] == 2


def test_six_events_twenty_global_supports_no_network(case_root):
    seeded(case_root, count=20)
    normalize_events(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        rows = list(s.scalars(select(NormalizedEvent).order_by(NormalizedEvent.id)))
        for i, row in enumerate(rows):
            row.occurred_at_utc = (START if i < 6 else END).replace("Z", ".000000Z")
            row.time_status = "normalized"
            row.event_kind = "content.activity"
        s.execute(
            delete(NetworkObservation).where(
                NetworkObservation.parsed_record_id.in_([r.parsed_record_id for r in rows[:6]])
            )
        )
        s.commit()
    engine.dispose()
    correlate_exact(case_root)
    result = query(case_root)
    assert result["matched_candidates"] == result["returned_candidates"] == 1
    item = result["items"][0]
    assert item["candidate_kind"] == "device"
    assert (
        item["candidate_support_count"],
        item["window_event_count"],
        item["window_support_occurrences"],
    ) == (20, 6, 6)
    assert len(item["events"]) == 6
    assert query(case_root, candidate_kind="network")["items"] == []
    check_links(case_root, result["items"])


def test_shared_parsed_record_counts_event_support_occurrences(matrix_case):
    engine = open_database(matrix_case / "database/evidence.db")
    with Session(engine) as s:
        row = s.scalars(
            select(NormalizedEvent).where(
                NormalizedEvent.platform == "meta", NormalizedEvent.event_kind == "content.activity"
            )
        ).one()
        clone(s, row, event_ordinal=15)
        s.commit()
    engine.dispose()
    item = query(matrix_case, candidate_kind="device")["items"][0]
    assert item["window_event_count"] == 3 and item["window_support_occurrences"] == 5
    assert item["candidate_support_count"] == 4


def test_future_observers_with_persisted_supports_excluded(matrix_case):
    engine = open_database(matrix_case / "database/evidence.db")
    extra_ids = []
    with Session(engine) as s:
        for kind, model in [("device", DeviceObservation), ("network", NetworkObservation)]:
            original = s.scalars(
                select(CorrelationCandidate).where(CorrelationCandidate.candidate_kind == kind)
            ).one()
            extra = clone(s, original, rule_version="synthetic-future", support_count=2)
            source = s.scalars(select(model)).first()
            observations = [
                clone(s, source, observer_version="1.1.0", observation_ordinal=i) for i in (80, 81)
            ]
            s.flush()
            extra_ids.append(extra.id)
            for ordinal, obs in enumerate(observations):
                s.add(
                    CorrelationSupport(
                        candidate_id=extra.id,
                        candidate_kind=kind,
                        support_ordinal=ordinal,
                        device_observation_id=obs.id if kind == "device" else None,
                        network_observation_id=obs.id if kind == "network" else None,
                    )
                )
        s.commit()
    engine.dispose()
    assert not set(extra_ids).intersection(i["candidate_id"] for i in query(matrix_case)["items"])


def test_more_than_incident_default_events_are_not_cut_off(case_root):
    seeded(case_root, count=2)
    normalize_events(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        rows = list(s.scalars(select(NormalizedEvent)))
        for row in rows:
            row.occurred_at_utc = START.replace("Z", ".000000Z")
            row.time_status = "normalized"
        for ordinal in range(1, 500):
            clone(s, rows[0], event_ordinal=ordinal)
        s.commit()
    engine.dispose()
    correlate_exact(case_root)
    result = query(case_root, limit=1)
    assert result["matched_candidates"] == 2 and result["returned_candidates"] == 1
    assert result["items"][0]["window_event_count"] == 501
    assert len(result["items"][0]["events"]) == 501


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
        ["--start", START, "--end", END, "--limit", "1001"],
        ["--start", START, "--end", END, "--candidate-kind", "invalid"],
    ],
)
def test_invalid_arguments_do_not_create_database(case_root, args):
    before = set(case_root.rglob("*"))
    result = command(case_root, "incident-candidates", *args)
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
    result = command(case_root, "incident-candidates", "--start", START, "--end", END)
    assert result.exit_code == 2
    assert (database_bytes(case_root) if mode != "missing" else set(case_root.rglob("*"))) == before


def test_single_snapshot_no_raw_reads_or_originals_and_db_unchanged(matrix_case, monkeypatch):
    import evidence_engine.query.catalog as catalog

    root = matrix_case
    before = database_bytes(root)
    path_open = Path.open
    db_open = catalog.open_database
    opens = []
    connections = set()

    def count_open(*args, **kwargs):
        assert kwargs == {"read_only": True}
        opens.append(True)
        return db_open(*args, **kwargs)

    def no_originals(path, *args, **kwargs):
        assert "originals" not in path.parts and "working" not in path.parts
        return path_open(path, *args, **kwargs)

    def inspect(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith("select") and "sqlite_master" not in statement:
            assert cursor.connection.in_transaction
            assert cursor.connection.execute("PRAGMA query_only").fetchone()[0] == 1
            assert connection.engine.url.query["mode"] == "ro"
            assert not any(
                k in statement
                for k in (
                    "value_raw",
                    "ip_raw",
                    "ip_canonical",
                    "payload_json",
                    "timestamp_raw",
                    "annotations_json",
                )
            )
            connections.add(id(cursor.connection))

    event.listen(Engine, "before_cursor_execute", inspect)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(catalog, "open_database", count_open)
            patch.setattr(Path, "open", no_originals)
            assert query(root)["returned_candidates"] == 2
    finally:
        event.remove(Engine, "before_cursor_execute", inspect)
    assert len(opens) == len(connections) == 1 and database_bytes(root) == before
