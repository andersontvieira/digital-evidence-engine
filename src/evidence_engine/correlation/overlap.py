"""Read-only composition of temporal pairs and persisted exact memberships."""

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, RowMapping, select

from evidence_engine.correlation.exact import (
    CORRELATOR_ID,
    CORRELATOR_VERSION,
    DEVICE_RULE,
    NETWORK_RULE,
    RULE_VERSION,
)
from evidence_engine.correlation.temporal import (
    TemporalCandidates,
    TemporalWindow,
    temporal_bounds,
    temporal_candidates_in_snapshot,
)
from evidence_engine.errors import EvidenceError
from evidence_engine.models.entities import Base
from evidence_engine.query.catalog import read_catalog
from evidence_engine.query.incident import same_record_predicate
from evidence_engine.query.search import ObservationKind
from evidence_engine.query.timeline import TimelineItem

BATCH_SIZE = 400
KINDS: tuple[ObservationKind, ...] = ("device", "network")
RULES = {"device": DEVICE_RULE, "network": NETWORK_RULE}
OBSERVATION_COLUMNS = (
    "id",
    "case_id",
    "parsed_record_id",
    "observation_run_id",
    "observer_id",
    "observer_version",
)
SUPPORT_COLUMNS = (
    "id",
    "candidate_id",
    "candidate_kind",
    "support_ordinal",
    "device_observation_id",
    "network_observation_id",
)
CANDIDATE_COLUMNS = (
    "id",
    "case_id",
    "correlation_run_id",
    "correlator_id",
    "correlator_version",
    "candidate_kind",
    "rule_id",
    "rule_version",
    "support_count",
)


@dataclass(frozen=True)
class TemporalExactOverlapPolicy:
    max_delta_seconds: int
    relation_kind: str = "temporal.exact_signal_overlap_candidate"
    policy_id: str = "temporal_exact_overlap"
    policy_version: str = "1.0.0"
    feature_class: str = "DERIVED"
    temporal_policy_id: str = "temporal.proximity"
    temporal_policy_version: str = "1.0.0"
    exact_correlator_id: str = CORRELATOR_ID
    exact_correlator_version: str = CORRELATOR_VERSION


@dataclass(frozen=True)
class SharedExactCandidates:
    device_candidate_ids: tuple[str, ...]
    network_candidate_ids: tuple[str, ...]


@dataclass(frozen=True)
class TemporalExactOverlapCandidate:
    delta_microseconds: int
    event_a: TimelineItem
    event_b: TimelineItem
    same_parsed_record: bool
    shared_exact_candidates: SharedExactCandidates


@dataclass(frozen=True)
class TemporalExactOverlapResult:
    policy: TemporalExactOverlapPolicy
    window: TemporalWindow
    eligible_events: int
    matched_pairs: int
    returned_pairs: int
    truncated: bool
    items: tuple[TemporalExactOverlapCandidate, ...]


def _require(condition: bool) -> None:
    if not condition:
        raise EvidenceError("TEMPORAL_OVERLAP_INTEGRITY_ERROR")


def _batches(ids: set[str]) -> Iterator[list[str]]:
    ordered = sorted(ids)
    for start in range(0, len(ordered), BATCH_SIZE):
        yield ordered[start : start + BATCH_SIZE]


def _load(
    connection: Connection,
    table_name: str,
    columns: tuple[str, ...],
    reference: str,
    ids: set[str],
) -> dict[str, RowMapping]:
    """Explicit projections, no joins: missing references remain detectable."""
    table = Base.metadata.tables[table_name]
    result: dict[str, RowMapping] = {}
    for batch in _batches(ids):
        rows = connection.execute(
            select(*(table.c[name] for name in columns)).where(table.c[reference].in_(batch))
        ).mappings()
        result.update((row["id"], row) for row in rows)
    return result


def _support_branch(support: RowMapping, kind: str) -> str:
    _require(kind in KINDS and support["candidate_kind"] == kind)
    other = "network" if kind == "device" else "device"
    reference = support[f"{kind}_observation_id"]
    _require(isinstance(reference, str) and support[f"{other}_observation_id"] is None)
    return str(reference)


def _memberships(
    connection: Connection,
    event_records: dict[str, str],
) -> dict[str, dict[str, set[str]]]:
    """Load prefix memberships; additional supports validate, never propagate."""
    record_ids = set(event_records.values())
    memberships: dict[str, dict[str, set[str]]] = {
        kind: {record: set() for record in record_ids} for kind in KINDS
    }
    if not record_ids:
        return memberships
    cases = connection.execute(select(Base.metadata.tables["cases"].c.id)).scalars().all()
    _require(len(cases) == 1)
    case_id = cases[0]
    events = _load(
        connection,
        "normalized_events",
        ("id", "case_id", "parsed_record_id"),
        "id",
        set(event_records),
    )
    _require(set(events) == set(event_records))
    for event_id, record_id in event_records.items():
        _require(
            events[event_id]["case_id"] == case_id
            and events[event_id]["parsed_record_id"] == record_id
        )

    seeds: dict[str, dict[str, RowMapping]] = {kind: {} for kind in KINDS}
    reached: dict[str, RowMapping] = {}
    support_table = Base.metadata.tables["correlation_supports"]
    for kind in KINDS:
        table = Base.metadata.tables[f"{kind}_observations"]
        for batch in _batches(record_ids):
            rows = connection.execute(
                select(*(table.c[n] for n in OBSERVATION_COLUMNS)).where(
                    same_record_predicate(kind, batch)
                )
            ).mappings()
            seeds[kind].update((row["id"], row) for row in rows)
        # IDs are scoped to their typed table; never match an ID against the other arm.
        for batch in _batches(set(seeds[kind])):
            rows = connection.execute(
                select(*(support_table.c[n] for n in SUPPORT_COLUMNS)).where(
                    support_table.c[f"{kind}_observation_id"].in_(batch)
                )
            ).mappings()
            for row in rows:
                _require(_support_branch(row, kind) in seeds[kind])
                reached[row["id"]] = row

    candidate_ids = {s["candidate_id"] for s in reached.values()}
    candidates = _load(connection, "correlation_candidates", CANDIDATE_COLUMNS, "id", candidate_ids)
    _require(set(candidates) == candidate_ids)
    runs = _load(
        connection,
        "correlation_runs",
        ("id", "case_id", "correlator_id", "correlator_version", "status"),
        "id",
        {c["correlation_run_id"] for c in candidates.values()},
    )
    eligible = {}
    for candidate_id, candidate in candidates.items():
        kind = candidate["candidate_kind"]
        run = runs.get(candidate["correlation_run_id"])
        _require(kind in KINDS and candidate["case_id"] == case_id and run is not None)
        assert run is not None
        _require(
            run["case_id"] == case_id
            and run["status"] == "COMPLETED"
            and run["correlator_id"] == candidate["correlator_id"]
            and run["correlator_version"] == candidate["correlator_version"]
        )
        if candidate["rule_id"] in RULES.values():
            _require(candidate["rule_id"] == RULES[kind])
        if (
            candidate["correlator_id"],
            candidate["correlator_version"],
            candidate["rule_id"],
            candidate["rule_version"],
        ) == (CORRELATOR_ID, CORRELATOR_VERSION, RULES[kind], RULE_VERSION):
            eligible[candidate_id] = candidate
    for support in reached.values():
        _support_branch(support, candidates[support["candidate_id"]]["candidate_kind"])

    supports = _load(
        connection, "correlation_supports", SUPPORT_COLUMNS, "candidate_id", set(eligible)
    )
    grouped: dict[str, list[RowMapping]] = defaultdict(list)
    references: dict[str, set[str]] = {kind: set() for kind in KINDS}
    for support in supports.values():
        kind = eligible[support["candidate_id"]]["candidate_kind"]
        references[kind].add(_support_branch(support, kind))
        grouped[support["candidate_id"]].append(support)
    observations = {kind: dict(seeds[kind]) for kind in KINDS}
    for kind in KINDS:
        loaded = _load(
            connection, f"{kind}_observations", OBSERVATION_COLUMNS, "id", references[kind]
        )
        _require(set(loaded) == references[kind])
        observations[kind].update(loaded)
    all_observations = [row for rows in observations.values() for row in rows.values()]
    records = _load(
        connection,
        "parsed_records",
        ("id", "case_id"),
        "id",
        record_ids | {o["parsed_record_id"] for o in all_observations},
    )
    _require(record_ids <= set(records))
    for record in records.values():
        _require(record["case_id"] == case_id)
    observation_runs = _load(
        connection,
        "observation_runs",
        ("id", "case_id", "observer_id", "observer_version", "status"),
        "id",
        {o["observation_run_id"] for o in all_observations},
    )
    for kind in KINDS:
        for observation in observations[kind].values():
            run = observation_runs.get(observation["observation_run_id"])
            _require(
                observation["parsed_record_id"] in records
                and observation["case_id"] == case_id
                and run is not None
            )
            assert run is not None
            _require(
                (observation["observer_id"], observation["observer_version"])
                == (f"{kind}.observer", "1.0.0")
            )
            _require(
                run["case_id"] == case_id
                and run["status"] == "COMPLETED"
                and run["observer_id"] == observation["observer_id"]
                and run["observer_version"] == observation["observer_version"]
            )

    for candidate_id, candidate in eligible.items():
        links = grouped[candidate_id]
        _require(len(links) >= 2 and len(links) == candidate["support_count"])
        _require(sorted(s["support_ordinal"] for s in links) == list(range(len(links))))
        kind = candidate["candidate_kind"]
        ids = [_support_branch(s, kind) for s in links]
        _require(len(set(ids)) == len(ids))
        for observation_id in ids:
            if observation_id in seeds[kind]:
                record_id = seeds[kind][observation_id]["parsed_record_id"]
                memberships[kind][record_id].add(candidate_id)
    return memberships


def temporal_exact_overlap(
    case_root: Path,
    *,
    start: str,
    end: str,
    max_delta_seconds: int,
    platform: str | None = None,
    event_kind: str | None = None,
    limit: int = 1000,
) -> TemporalExactOverlapResult:
    start_utc, end_utc = temporal_bounds(start, end, max_delta_seconds, limit)
    with read_catalog(case_root) as connection:
        temporal = temporal_candidates_in_snapshot(
            connection,
            start_utc=start_utc,
            end_utc=end_utc,
            max_delta_seconds=max_delta_seconds,
            platform=platform,
            event_kind=event_kind,
            limit=limit,
        )
        return overlap_in_snapshot(connection, temporal)


def overlap_in_snapshot(
    connection: Connection, temporal: TemporalCandidates
) -> TemporalExactOverlapResult:
    """Project memberships onto the already computed 6A prefix in the same snapshot."""
    memberships = _memberships(
        connection,
        {
            event.event_id: event.parsed_record_id
            for pair in temporal.items
            for event in (pair.event_a, pair.event_b)
        },
    )
    items = []
    for pair in temporal.items:
        a, b = pair.event_a.parsed_record_id, pair.event_b.parsed_record_id
        items.append(
            TemporalExactOverlapCandidate(
                pair.delta_microseconds,
                pair.event_a,
                pair.event_b,
                a == b,
                SharedExactCandidates(
                    tuple(sorted(memberships["device"][a] & memberships["device"][b])),
                    tuple(sorted(memberships["network"][a] & memberships["network"][b])),
                ),
            )
        )
    return TemporalExactOverlapResult(
        TemporalExactOverlapPolicy(temporal.policy.max_delta_seconds),
        temporal.window,
        temporal.eligible_events,
        temporal.matched_pairs,
        temporal.returned_pairs,
        temporal.truncated,
        tuple(items),
    )
