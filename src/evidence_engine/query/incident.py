"""Current events with explicit same-ParsedRecord context, never temporal correlation."""

from dataclasses import asdict
from pathlib import Path

from sqlalchemy import Connection, select

from evidence_engine.errors import EvidenceError
from evidence_engine.models.entities import DeviceObservation, NetworkObservation
from evidence_engine.query.catalog import read_catalog, validate_limit
from evidence_engine.query.provenance import record_origin
from evidence_engine.query.search import (
    DEVICE_COLUMNS,
    NETWORK_COLUMNS,
    ObservationKind,
    Projection,
    candidate_ids,
)
from evidence_engine.query.timeline import timeline_in_snapshot, utc_bound


def same_record_context(
    connection: Connection,
    kind: ObservationKind,
    parsed_record_id: str,
) -> list[Projection]:
    model = DeviceObservation if kind == "device" else NetworkObservation
    columns = DEVICE_COLUMNS if kind == "device" else NETWORK_COLUMNS
    rows = (
        connection.execute(
            select(*columns)
            .where(
                model.parsed_record_id == parsed_record_id,
                model.observer_id == f"{kind}.observer",
                model.observer_version == "1.0.0",
            )
            .order_by(model.observation_ordinal, model.id)
        )
        .mappings()
        .all()
    )
    items = []
    for row in rows:
        item = {
            key: value for key, value in row.items() if key not in {"platform", "parsed_record_id"}
        }
        item["candidate_ids"] = candidate_ids(connection, kind, row["observation_id"])
        items.append(item)
    return items


def query_incident_window(
    case_root: Path,
    *,
    start: str,
    end: str,
    platform: str | None = None,
    event_kind: str | None = None,
    limit: int = 500,
) -> Projection:
    validate_limit(limit, 5000)
    start_utc, end_utc = utc_bound(start), utc_bound(end)
    if start_utc is None or end_utc is None:
        raise EvidenceError("Incident window requires start and end UTC bounds")
    if start_utc >= end_utc:
        raise EvidenceError("Incident window start must precede end")
    with read_catalog(case_root) as connection:
        timeline = timeline_in_snapshot(
            connection,
            start_utc=start_utc,
            end_utc=end_utc,
            platform=platform,
            event_kind=event_kind,
            limit=limit,
        )
        items = []
        for event in timeline.items:
            item = asdict(event)
            item["provenance"] = record_origin(connection, event.parsed_record_id)
            item["device_context"] = same_record_context(
                connection, "device", event.parsed_record_id
            )
            item["network_context"] = same_record_context(
                connection, "network", event.parsed_record_id
            )
            items.append(item)
        return {
            "policy_id": timeline.policy_id,
            "policy_version": timeline.policy_version,
            "matched_total": timeline.matched_total,
            "returned": timeline.returned,
            "truncated": timeline.truncated,
            "undated_current_events": timeline.undated_current_events,
            "items": items,
        }
