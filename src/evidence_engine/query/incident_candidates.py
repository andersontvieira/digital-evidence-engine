"""Window projection of persisted memberships; no new correlation or identity links."""

from pathlib import Path

from sqlalchemy import Connection, select

from evidence_engine.errors import EvidenceError
from evidence_engine.models.entities import CorrelationCandidate, CorrelationSupport
from evidence_engine.query.catalog import read_catalog, validate_limit
from evidence_engine.query.incident import same_record_context
from evidence_engine.query.search import ObservationKind, Projection
from evidence_engine.query.timeline import timeline_in_snapshot, utc_bound


def candidate_metadata(
    connection: Connection, candidate_id: str, kind: ObservationKind
) -> Projection:
    row = (
        connection.execute(
            select(
                CorrelationCandidate.id.label("candidate_id"),
                CorrelationCandidate.candidate_kind,
                CorrelationCandidate.correlator_id,
                CorrelationCandidate.correlator_version,
                CorrelationCandidate.rule_id,
                CorrelationCandidate.rule_version,
                CorrelationCandidate.support_count.label("candidate_support_count"),
            ).where(CorrelationCandidate.id == candidate_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None or row["candidate_kind"] != kind:
        raise EvidenceError("MATRIX_MEMBERSHIP_INTEGRITY_ERROR")
    return dict(row)


def support_link(
    connection: Connection,
    candidate_id: str,
    kind: ObservationKind,
    observation: Projection,
) -> Projection:
    reference = (
        CorrelationSupport.device_observation_id
        if kind == "device"
        else CorrelationSupport.network_observation_id
    )
    other = (
        CorrelationSupport.network_observation_id
        if kind == "device"
        else CorrelationSupport.device_observation_id
    )
    row = (
        connection.execute(
            select(
                CorrelationSupport.id.label("support_id"),
                CorrelationSupport.support_ordinal,
            ).where(
                CorrelationSupport.candidate_id == candidate_id,
                CorrelationSupport.candidate_kind == kind,
                reference == observation["observation_id"],
                other.is_(None),
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise EvidenceError("MATRIX_MEMBERSHIP_INTEGRITY_ERROR")
    domain = ("fact_kind", "namespace") if kind == "device" else ("source_role", "ip_version")
    return {
        "observation_id": observation["observation_id"],
        **dict(row),
        **{field: observation[field] for field in domain},
        "source_field_locator": observation["source_field_locator"],
    }


def query_incident_candidates(
    case_root: Path,
    *,
    start: str,
    end: str,
    platform: str | None = None,
    event_kind: str | None = None,
    candidate_kind: str | None = None,
    limit: int = 100,
) -> Projection:
    validate_limit(limit, 1000)
    if candidate_kind is not None and candidate_kind not in {"device", "network"}:
        raise EvidenceError("Candidate kind must be device or network")
    start_utc, end_utc = utc_bound(start), utc_bound(end)
    if start_utc is None or end_utc is None:
        raise EvidenceError("Incident candidates requires start and end UTC bounds")
    if start_utc >= end_utc:
        raise EvidenceError("Incident candidates start must precede end")
    with read_catalog(case_root) as connection:
        return incident_candidates_in_snapshot(
            connection,
            start_utc=start_utc,
            end_utc=end_utc,
            platform=platform,
            event_kind=event_kind,
            limit=limit,
            candidate_kind=candidate_kind,
        )


def incident_candidates_in_snapshot(
    connection: Connection,
    *,
    start_utc: str,
    end_utc: str,
    platform: str | None,
    event_kind: str | None,
    candidate_kind: str | None,
    limit: int,
) -> Projection:
    """Compose in the caller's read snapshot; arguments must already be validated."""
    timeline = timeline_in_snapshot(
        connection,
        start_utc=start_utc,
        end_utc=end_utc,
        platform=platform,
        event_kind=event_kind,
        limit=None,
    )
    entries: dict[str, Projection] = {}
    references: dict[tuple[str, str], Projection] = {}
    kinds: tuple[ObservationKind, ...] = ("device", "network")
    for event in timeline.items:
        for kind in kinds:
            if candidate_kind is not None and kind != candidate_kind:
                continue
            for observation in same_record_context(connection, kind, event.parsed_record_id):
                for candidate_id in observation["candidate_ids"]:
                    if candidate_id not in entries:
                        entries[candidate_id] = candidate_metadata(connection, candidate_id, kind)
                        entries[candidate_id]["events"] = []
                    link = support_link(connection, candidate_id, kind, observation)
                    key = candidate_id, event.event_id
                    if key not in references:
                        references[key] = {
                            "event_id": event.event_id,
                            "parsed_record_id": event.parsed_record_id,
                            "occurred_at_utc": event.occurred_at_utc,
                            "platform": event.platform,
                            "event_kind": event.event_kind,
                            "observation_links": [],
                        }
                        # Timeline order is preserved; each distinct event is appended once.
                        entries[candidate_id]["events"].append(references[key])
                    references[key]["observation_links"].append(link)
    items = list(entries.values())
    for item in items:
        events = item["events"]
        for reference in events:
            reference["observation_links"].sort(
                key=lambda link: (link["support_ordinal"], link["observation_id"])
            )
        item["window_event_count"] = len(events)
        # One occurrence per event/support link, even when events share a source record.
        item["window_support_occurrences"] = sum(len(e["observation_links"]) for e in events)
        item["window_platforms"] = sorted({e["platform"] for e in events})
        item["window_event_kinds"] = sorted({e["event_kind"] for e in events})
    items.sort(
        key=lambda item: (
            -item["window_event_count"],
            -item["window_support_occurrences"],
            item["candidate_kind"],
            item["candidate_id"],
        )
    )
    return {
        "policy_id": timeline.policy_id,
        "policy_version": timeline.policy_version,
        "matched_candidates": len(items),
        "returned_candidates": min(limit, len(items)),
        "truncated": len(items) > limit,
        "items": items[:limit],
    }
