"""Exact persisted technical facts, without identity or new candidate inference."""

from ipaddress import ip_address
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import Connection, func, select

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.parsing.framework import json_text
from evidence_engine.models.entities import (
    CorrelationSupport,
    DeviceObservation,
    NetworkObservation,
)
from evidence_engine.query.catalog import read_catalog, validate_limit

# Only explicit column projections enter these JSON dictionaries; raw fields are predicates only.
type Projection = dict[str, Any]
type ObservationKind = Literal["device", "network"]

DEVICE_COLUMNS = (
    DeviceObservation.id.label("observation_id"),
    DeviceObservation.parsed_record_id,
    DeviceObservation.platform,
    DeviceObservation.fact_kind,
    DeviceObservation.namespace,
    DeviceObservation.source_field_locator,
    DeviceObservation.source_field_name,
    DeviceObservation.observation_ordinal,
)
NETWORK_COLUMNS = (
    NetworkObservation.id.label("observation_id"),
    NetworkObservation.parsed_record_id,
    NetworkObservation.platform,
    NetworkObservation.source_role,
    NetworkObservation.ip_version,
    NetworkObservation.source_field_locator,
    NetworkObservation.source_field_name,
    NetworkObservation.observation_ordinal,
)


def candidate_ids(connection: Connection, kind: ObservationKind, observation_id: str) -> list[str]:
    foreign_key = (
        CorrelationSupport.device_observation_id
        if kind == "device"
        else CorrelationSupport.network_observation_id
    )
    return list(
        connection.scalars(
            select(CorrelationSupport.candidate_id)
            .where(CorrelationSupport.candidate_kind == kind, foreign_key == observation_id)
            .order_by(CorrelationSupport.candidate_id)
        )
    )


def query_device(
    case_root: Path,
    *,
    namespace: str,
    value: str,
    platform: str | None = None,
    fact_kind: str | None = None,
    limit: int = 100,
) -> Projection:
    validate_limit(limit, 10000)
    if not isinstance(namespace, str) or not isinstance(value, str):
        raise EvidenceError("Device namespace and value must be strings")
    if fact_kind is not None and fact_kind not in {"identifier", "model"}:
        raise EvidenceError("Device fact kind must be identifier or model")
    filters = [
        DeviceObservation.observer_id == "device.observer",
        DeviceObservation.observer_version == "1.0.0",
        DeviceObservation.namespace == namespace,
        DeviceObservation.value_raw == json_text(value),
    ]
    if platform is not None:
        filters.append(DeviceObservation.platform == platform)
    if fact_kind is not None:
        filters.append(DeviceObservation.fact_kind == fact_kind)
    with read_catalog(case_root) as connection:
        matched = connection.execute(
            select(func.count()).select_from(DeviceObservation).where(*filters)
        ).scalar_one()
        rows = connection.execute(
            select(*DEVICE_COLUMNS)
            .where(*filters)
            .order_by(
                DeviceObservation.platform,
                DeviceObservation.parsed_record_id,
                DeviceObservation.observation_ordinal,
                DeviceObservation.id,
            )
            .limit(limit)
        ).mappings()
        items = [dict(row) for row in rows]
        for item in items:
            item["candidate_ids"] = candidate_ids(connection, "device", item["observation_id"])
        return {
            "matched_total": matched,
            "returned": len(items),
            "truncated": matched > len(items),
            "items": items,
        }


def query_network(
    case_root: Path,
    *,
    ip: str,
    platform: str | None = None,
    source_role: str | None = None,
    limit: int = 100,
) -> Projection:
    validate_limit(limit, 10000)
    try:
        address = ip_address(ip)
    except ValueError:
        raise EvidenceError("Invalid IP address") from None
    filters = [
        NetworkObservation.observer_id == "network.observer",
        NetworkObservation.observer_version == "1.0.0",
        NetworkObservation.ip_version == address.version,
        NetworkObservation.ip_canonical == str(address),
    ]
    if platform is not None:
        filters.append(NetworkObservation.platform == platform)
    if source_role is not None:
        filters.append(NetworkObservation.source_role == source_role)
    with read_catalog(case_root) as connection:
        matched = connection.execute(
            select(func.count()).select_from(NetworkObservation).where(*filters)
        ).scalar_one()
        rows = connection.execute(
            select(*NETWORK_COLUMNS)
            .where(*filters)
            .order_by(
                NetworkObservation.platform,
                NetworkObservation.parsed_record_id,
                NetworkObservation.observation_ordinal,
                NetworkObservation.id,
            )
            .limit(limit)
        ).mappings()
        items = [dict(row) for row in rows]
        for item in items:
            item["candidate_ids"] = candidate_ids(connection, "network", item["observation_id"])
        return {
            "matched_total": matched,
            "returned": len(items),
            "truncated": matched > len(items),
            "items": items,
        }
