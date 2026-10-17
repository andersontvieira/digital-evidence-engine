import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session
from typer._click.utils import strip_ansi
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.correlation import overlap
from evidence_engine.correlation.exact import DEVICE_RULE, NETWORK_RULE
from evidence_engine.correlation.temporal import (
    temporal_candidates,
    temporal_candidates_in_snapshot,
)
from evidence_engine.errors import EvidenceError
from evidence_engine.models.entities import CorrelationCandidate, CorrelationRun, CorrelationSupport
from evidence_engine.normalization.service import normalize_events
from evidence_engine.query.catalog import read_catalog
from evidence_engine.query.incident import same_record_context
from evidence_engine.storage.database import open_database
from tests.test_correlation_service import seeded
from tests.test_media_inventory import tree_state

START = "2026-01-01T00:00:00Z"
END = "2026-01-01T00:01:00Z"


@pytest.fixture
def catalog(case_root):
    seeded(case_root, count=5)
    assert normalize_events(case_root).errors == 0
    with sqlite3.connect(case_root / "database/evidence.db") as c:
        rows = c.execute(
            "SELECT e.id,e.parsed_record_id FROM normalized_events e "
            "JOIN parsed_records p ON e.parsed_record_id=p.id ORDER BY p.record_index"
        ).fetchall()
        for index, (event_id, _) in enumerate(rows):
            instant = (
                (datetime.fromisoformat(START) + timedelta(seconds=index))
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
            c.execute(
                "UPDATE normalized_events SET occurred_at_utc=?,time_status='normalized',"
                "time_basis='explicit_utc' WHERE id=?",
                (instant, event_id),
            )
    return SimpleNamespace(
        root=case_root, events=[r[0] for r in rows], records=[r[1] for r in rows]
    )


def execute(catalog, sql, args=()):
    with sqlite3.connect(catalog.root / "database/evidence.db") as c:
        c.execute("PRAGMA foreign_keys=OFF")
        c.execute("PRAGMA ignore_check_constraints=ON")
        return c.execute(sql, args).fetchall()


def group(catalog, kind, indices, name):
    ids = []
    for index in indices:
        ids.extend(
            r[0]
            for r in execute(
                catalog,
                f"SELECT id FROM {kind}_observations "
                "WHERE parsed_record_id=? ORDER BY observation_ordinal",
                (catalog.records[index],),
            )
        )
    engine = open_database(catalog.root / "database/evidence.db")
    with Session(engine) as session:
        case_id = execute(catalog, "SELECT id FROM cases")[0][0]
        run = CorrelationRun(
            case_id=case_id,
            correlator_id="exact_match.correlator",
            correlator_version="1.0.0",
            status="COMPLETED",
        )
        session.add(run)
        session.flush()
        candidate = CorrelationCandidate(
            id="synthetic-candidate-" + name,
            case_id=case_id,
            correlation_run_id=run.id,
            correlator_id="exact_match.correlator",
            correlator_version="1.0.0",
            candidate_kind=kind,
            rule_id=DEVICE_RULE if kind == "device" else NETWORK_RULE,
            rule_version="1.0.0",
            support_count=len(ids),
            key_digest=hashlib.sha256(name.encode()).hexdigest(),
        )
        session.add(candidate)
        session.flush()
        for ordinal, observation_id in enumerate(ids):
            session.add(
                CorrelationSupport(
                    candidate_id=candidate.id,
                    candidate_kind=kind,
                    support_ordinal=ordinal,
                    device_observation_id=observation_id if kind == "device" else None,
                    network_observation_id=observation_id if kind == "network" else None,
                )
            )
        session.commit()
    engine.dispose()
    return "synthetic-candidate-" + name


def query(catalog, **changes):
    return overlap.temporal_exact_overlap(
        catalog.root, **({"start": START, "end": END, "max_delta_seconds": 10} | changes)
    )


def args(catalog, command="temporal-exact-overlap", **changes):
    options = {
        "case-root": str(catalog.root),
        "start": START,
        "end": END,
        "max-delta-seconds": "10",
    } | changes
    return ["correlate", command] + [
        part for k, v in options.items() for part in ("--" + k, str(v))
    ]


def test_6a_snapshot_refactor_and_fixed_json_contract(catalog):
    wrapper = temporal_candidates(catalog.root, start=START, end=END, max_delta_seconds=10)
    with read_catalog(catalog.root) as connection:
        with patch(
            "evidence_engine.correlation.temporal.read_catalog",
            side_effect=AssertionError("second opener"),
        ):
            inner = temporal_candidates_in_snapshot(
                connection,
                start_utc="2026-01-01T00:00:00.000000Z",
                end_utc="2026-01-01T00:01:00.000000Z",
                max_delta_seconds=10,
                platform=None,
                event_kind=None,
                limit=1000,
            )
    assert wrapper == inner
    expected = (
        json.dumps(asdict(inner), sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n"
    ).encode("ascii")
    assert CliRunner().invoke(app, args(catalog, "temporal-candidates")).stdout_bytes == expected


@pytest.mark.parametrize("kinds", [(), ("device",), ("network",), ("device", "network")])
def test_basic_overlap_and_read_only(catalog, kinds):
    expected = {kind: group(catalog, kind, [0, 1], kind) for kind in kinds}
    before = tree_state(catalog.root)
    result = query(catalog)
    assert result.eligible_events == 5 and result.matched_pairs == result.returned_pairs == 10
    first = result.items[0]
    for kind in ("device", "network"):
        assert getattr(first.shared_exact_candidates, kind + "_candidate_ids") == (
            (expected[kind],) if kind in expected else ()
        )
    assert not first.same_parsed_record
    assert tree_state(catalog.root) == before
    assert not isinstance(first, CorrelationCandidate)


def test_different_and_unrelated_candidates_do_not_propagate(catalog):
    group(catalog, "device", [0, 2], "a-only")
    group(catalog, "device", [1, 3], "b-only")
    assert not query(catalog, limit=1).items[0].shared_exact_candidates.device_candidate_ids
    shared = group(catalog, "device", [0, 1], "shared")
    assert query(catalog, limit=1).items[0].shared_exact_candidates.device_candidate_ids == (
        shared,
    )


def test_multiplicity_lexical_order_and_same_record(catalog):
    # Clone an atomic observation from record A with a distinct ordinal, no new source.
    execute(
        catalog,
        "INSERT INTO device_observations SELECT 'synthetic-extra-observation',case_id,"
        "observation_run_id,parsed_record_id,observer_id,observer_version,9,platform,"
        "fact_kind,namespace,value_raw,source_field_locator,source_field_name,created_at "
        "FROM device_observations WHERE parsed_record_id=?",
        (catalog.records[0],),
    )
    z = group(catalog, "device", [0, 1], "z")
    a = group(catalog, "device", [0, 1], "a")
    assert query(catalog, limit=1).items[0].shared_exact_candidates.device_candidate_ids == (a, z)
    execute(
        catalog,
        "UPDATE normalized_events SET parsed_record_id=?,event_ordinal=1 WHERE id=?",
        (catalog.records[0], catalog.events[1]),
    )
    pair = query(catalog, limit=1).items[0]
    assert pair.same_parsed_record and pair.shared_exact_candidates.device_candidate_ids == (a, z)


@pytest.mark.parametrize("component", ["observer", "correlator", "rule"])
@pytest.mark.parametrize("version", ["0.9.0", "1.2.0"])
def test_noneligible_versions_are_normal_exclusions(catalog, component, version):
    group(catalog, "device", [0, 1], "versioned")
    if component == "observer":
        execute(catalog, "UPDATE device_observations SET observer_version=?", (version,))
        execute(
            catalog,
            "UPDATE observation_runs SET observer_version=? WHERE observer_id='device.observer'",
            (version,),
        )
    elif component == "correlator":
        execute(catalog, "UPDATE correlation_candidates SET correlator_version=?", (version,))
        execute(catalog, "UPDATE correlation_runs SET correlator_version=?", (version,))
    else:
        execute(catalog, "UPDATE correlation_candidates SET rule_version=?", (version,))
    assert not query(catalog, limit=1).items[0].shared_exact_candidates.device_candidate_ids


@pytest.mark.parametrize(
    "damage",
    [
        "candidate_missing",
        "observation_missing",
        "wrong_branch",
        "kind_mismatch",
        "rule_kind",
        "run_missing",
        "run_version",
        "run_case",
        "candidate_case",
        "record_case",
        "observation_case",
        "observation_run_missing",
        "observation_run_version",
        "support_count",
        "one_support",
        "support_missing",
        "support_ordinal",
        "outside_observer_version",
        "event_case",
    ],
)
def test_reached_integrity_failure_is_global_exit_2(catalog, damage):
    candidate = group(catalog, "device", [0, 1, 4], "damaged")
    statements = {
        "candidate_missing": ("DELETE FROM correlation_candidates", ()),
        "observation_missing": (
            "DELETE FROM device_observations WHERE parsed_record_id=?",
            (catalog.records[4],),
        ),
        "wrong_branch": (
            "UPDATE correlation_supports SET network_observation_id=device_observation_id,"
            "device_observation_id=NULL WHERE support_ordinal=0",
            (),
        ),
        "kind_mismatch": (
            "UPDATE correlation_supports SET candidate_kind='network' WHERE support_ordinal=0",
            (),
        ),
        "rule_kind": ("UPDATE correlation_candidates SET rule_id=?", (NETWORK_RULE,)),
        "run_missing": ("DELETE FROM correlation_runs", ()),
        "run_version": ("UPDATE correlation_runs SET correlator_version='1.2.0'", ()),
        "run_case": ("UPDATE correlation_runs SET case_id='synthetic-other-case'", ()),
        "candidate_case": ("UPDATE correlation_candidates SET case_id='synthetic-other-case'", ()),
        "record_case": (
            "UPDATE parsed_records SET case_id='synthetic-other-case' WHERE id=?",
            (catalog.records[4],),
        ),
        "observation_case": (
            "UPDATE device_observations SET case_id='synthetic-other-case' "
            "WHERE parsed_record_id=?",
            (catalog.records[4],),
        ),
        "observation_run_missing": (
            "DELETE FROM observation_runs WHERE observer_id='device.observer'",
            (),
        ),
        "observation_run_version": (
            "UPDATE observation_runs SET observer_version='1.2.0' "
            "WHERE observer_id='device.observer'",
            (),
        ),
        "support_count": ("UPDATE correlation_candidates SET support_count=99", ()),
        "one_support": ("DELETE FROM correlation_supports WHERE support_ordinal>0", ()),
        "support_missing": ("DELETE FROM correlation_supports WHERE support_ordinal=2", ()),
        "support_ordinal": (
            "UPDATE correlation_supports SET support_ordinal=8 WHERE support_ordinal=2",
            (),
        ),
        "outside_observer_version": (
            "UPDATE device_observations SET observer_version='1.2.0' WHERE parsed_record_id=?",
            (catalog.records[4],),
        ),
        "event_case": (
            "UPDATE normalized_events SET case_id='synthetic-other-case' WHERE id=?",
            (catalog.events[0],),
        ),
    }
    execute(catalog, *statements[damage])
    if damage == "one_support":
        execute(catalog, "UPDATE correlation_candidates SET support_count=1")
    before = tree_state(catalog.root)
    with pytest.raises(EvidenceError, match="TEMPORAL_OVERLAP_INTEGRITY_ERROR"):
        query(catalog, limit=1)
    result = CliRunner().invoke(app, args(catalog, limit=1))
    assert result.exit_code == 2 and "TEMPORAL_OVERLAP_INTEGRITY_ERROR" in result.output
    assert '"items"' not in result.output and candidate not in result.output
    assert tree_state(catalog.root) == before


def test_prefix_is_authoritative_and_empty_skips_bulk(catalog, monkeypatch):
    group(catalog, "device", [3, 4], "late")
    complete = query(catalog)
    limited = query(catalog, limit=2)
    assert limited.items == complete.items[:2] and limited.matched_pairs == 10 and limited.truncated
    assert not any(p.shared_exact_candidates.device_candidate_ids for p in limited.items)
    assert complete.items[-1].shared_exact_candidates.device_candidate_ids
    statements = []

    def inspect(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", inspect)
    try:
        empty = query(catalog, platform="nonexistent")
    finally:
        event.remove(Engine, "before_cursor_execute", inspect)
    assert empty.items == () and empty.matched_pairs == 0
    assert not any("correlation_" in s or "observations" in s for s in statements)


def test_single_snapshot_bulk_query_count_chunks_and_shared_association(catalog, monkeypatch):
    for kind in ("device", "network"):
        group(catalog, kind, list(range(5)), kind)
    original = overlap.read_catalog
    opened = []
    connections = set()
    statements = []

    @contextmanager
    def counted(root):
        with original(root) as c:
            opened.append(c)
            yield c

    def inspect(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith("select"):
            connections.add(id(cursor.connection))
            assert cursor.connection.in_transaction
            assert cursor.connection.execute("PRAGMA query_only").fetchone()[0] == 1
            assert not any(
                s in statement
                for s in (
                    "value_raw",
                    "ip_raw",
                    "ip_canonical",
                    "key_digest",
                    "payload_json",
                    "annotations_json",
                )
            )
            statements.append(statement)

    monkeypatch.setattr(overlap, "read_catalog", counted)
    event.listen(Engine, "before_cursor_execute", inspect)
    try:
        small = query(catalog, limit=1)
        small_count = len(statements)
        assert len(opened) == len(connections) == 1
        statements.clear()
        connections.clear()
        opened.clear()
        large = query(catalog)
        large_count = len(statements)
        assert len(opened) == len(connections) == 1 and small_count == large_count
        monkeypatch.setattr(overlap, "BATCH_SIZE", 2)
        chunked = query(catalog)
        assert chunked == large and small.items == large.items[:1]
    finally:
        event.remove(Engine, "before_cursor_execute", inspect)
    with read_catalog(catalog.root) as connection:
        for kind in ("device", "network"):
            ids = {
                cid
                for o in same_record_context(connection, kind, catalog.records[0])
                for cid in o["candidate_ids"]
            }
            assert (
                set(getattr(large.items[0].shared_exact_candidates, kind + "_candidate_ids")) == ids
            )


@pytest.mark.parametrize(
    "filters",
    [
        {"platform": "meta"},
        {"platform": "META"},
        {"event_kind": "account.activity"},
        {"platform": "meta", "event_kind": "nonexistent"},
    ],
)
def test_filters_identical_to_temporal(catalog, filters):
    temporal = temporal_candidates(
        catalog.root, start=START, end=END, max_delta_seconds=10, **filters
    )
    enriched = query(catalog, **filters)
    assert enriched.matched_pairs == temporal.matched_pairs
    assert [(p.event_a, p.event_b, p.delta_microseconds) for p in enriched.items] == [
        (p.event_a, p.event_b, p.delta_microseconds) for p in temporal.items
    ]


@pytest.mark.parametrize(
    "options",
    [
        {"max-delta-seconds": "0"},
        {"max-delta-seconds": "86401"},
        {"max-delta-seconds": "1.5"},
        {"limit": "0"},
        {"limit": "10001"},
        {"start": "2026-01-01T00:00:00"},
        {"start": "2026-01-01T00:00:00+00:00"},
        {"start": END},
        {"end": START},
    ],
)
def test_cli_invalid_arguments(catalog, options):
    assert CliRunner().invoke(app, args(catalog, **options)).exit_code == 2


@pytest.mark.parametrize("option", ["--case-root", "--start", "--end", "--max-delta-seconds"])
def test_required_options(catalog, option, monkeypatch):
    monkeypatch.delenv("CASE_ROOT", raising=False)
    command = args(catalog)
    index = command.index(option)
    del command[index : index + 2]
    assert CliRunner().invoke(app, command).exit_code == 2


def test_cli_policy_privacy_determinism_help(catalog):
    group(catalog, "device", [0, 1], "cli")
    one = CliRunner().invoke(app, args(catalog))
    two = CliRunner().invoke(app, args(catalog))
    assert one.exit_code == two.exit_code == 0 and one.stdout_bytes == two.stdout_bytes
    result = json.loads(one.stdout)
    assert result == json.loads(json.dumps(asdict(query(catalog))))
    assert result["policy"] == {
        "max_delta_seconds": 10,
        "relation_kind": "temporal.exact_signal_overlap_candidate",
        "policy_id": "temporal_exact_overlap",
        "policy_version": "1.0.0",
        "feature_class": "DERIVED",
        "temporal_policy_id": "temporal.proximity",
        "temporal_policy_version": "1.0.0",
        "exact_correlator_id": "exact_match.correlator",
        "exact_correlator_version": "1.0.0",
    }
    for p in result["items"]:
        assert set(p) == {
            "event_a",
            "event_b",
            "delta_microseconds",
            "same_parsed_record",
            "shared_exact_candidates",
        }
        assert set(p["shared_exact_candidates"]) == {
            "device_candidate_ids",
            "network_candidate_ids",
        }
    for forbidden in (
        "SYNTHETIC-ID",
        "203.0.113",
        "key_digest",
        "payload",
        "annotation",
        "path",
        "filename",
        "message",
        "caption",
        "score",
        "confidence",
        "support_count",
        "same_actor",
        "correlated",
    ):
        assert forbidden not in one.stdout
    help_result = CliRunner().invoke(
        app, ["correlate", "temporal-exact-overlap", "--help"], color=False
    )
    assert help_result.exit_code == 0 and "--max-delta-seconds" in strip_ansi(help_result.output)
    for forbidden in (
        "--require-shared-exact",
        "--candidate-kind",
        "--score",
        "--rank",
        "--threshold",
    ):
        assert forbidden not in help_result.output


def test_observation_ids_are_scoped_by_typed_table(catalog):
    device = group(catalog, "device", [0, 1], "typed-device")
    network = group(catalog, "network", [0, 1], "typed-network")
    device_id = execute(
        catalog,
        "SELECT id FROM device_observations WHERE parsed_record_id=?",
        (catalog.records[0],),
    )[0][0]
    network_id = execute(
        catalog,
        "SELECT id FROM network_observations WHERE parsed_record_id=?",
        (catalog.records[0],),
    )[0][0]
    execute(catalog, "UPDATE network_observations SET id=? WHERE id=?", (device_id, network_id))
    execute(
        catalog,
        "UPDATE correlation_supports SET network_observation_id=? WHERE network_observation_id=?",
        (device_id, network_id),
    )
    shared = query(catalog, limit=1).items[0].shared_exact_candidates
    assert shared.device_candidate_ids == (device,)
    assert shared.network_candidate_ids == (network,)
