"""Restricted catalog projections following persisted foreign keys only."""

from pathlib import Path
from uuid import UUID

from sqlalchemy import Connection, func, select

from evidence_engine.errors import EvidenceError
from evidence_engine.models.entities import (
    ArchiveMember,
    CorrelationCandidate,
    CorrelationSupport,
    DeviceObservation,
    EvidenceFile,
    NetworkObservation,
    NormalizedEvent,
    ParsedRecord,
    SourceRecord,
)
from evidence_engine.query.catalog import read_catalog, validate_limit
from evidence_engine.query.policy import CURRENT_NORMALIZERS
from evidence_engine.query.search import (
    DEVICE_COLUMNS,
    NETWORK_COLUMNS,
    ObservationKind,
    Projection,
    candidate_ids,
)

KINDS = {"event", "parsed-record", "device-observation", "network-observation", "candidate"}


def record_origin(connection: Connection, parsed_record_id: str) -> Projection:
    record = (
        connection.execute(
            select(
                ParsedRecord.source_record_id,
                ParsedRecord.source_locator,
            ).where(ParsedRecord.id == parsed_record_id)
        )
        .mappings()
        .one_or_none()
    )
    if record is None:
        raise EvidenceError("PROVENANCE_INTEGRITY_ERROR")
    source = (
        connection.execute(
            select(SourceRecord.evidence_file_id, SourceRecord.archive_member_id).where(
                SourceRecord.id == record["source_record_id"]
            )
        )
        .mappings()
        .one_or_none()
    )
    if source is None or (source["evidence_file_id"] is None) == (
        source["archive_member_id"] is None
    ):
        raise EvidenceError("PROVENANCE_INTEGRITY_ERROR")
    evidence_id = source["evidence_file_id"]
    member_path = member_sha256 = None
    if source["archive_member_id"] is not None:
        member = (
            connection.execute(
                select(
                    ArchiveMember.evidence_file_id,
                    ArchiveMember.member_path,
                    ArchiveMember.sha256,
                ).where(ArchiveMember.id == source["archive_member_id"])
            )
            .mappings()
            .one_or_none()
        )
        if member is None:
            raise EvidenceError("PROVENANCE_INTEGRITY_ERROR")
        evidence_id = member["evidence_file_id"]
        member_path, member_sha256 = member["member_path"], member["sha256"]
    evidence = (
        connection.execute(
            select(EvidenceFile.relative_path, EvidenceFile.sha256).where(
                EvidenceFile.id == evidence_id
            )
        )
        .mappings()
        .one_or_none()
    )
    if evidence is None:
        raise EvidenceError("PROVENANCE_INTEGRITY_ERROR")
    return {
        "parsed_record_id": parsed_record_id,
        "source_record_id": record["source_record_id"],
        "source_locator": record["source_locator"],
        "origin_kind": "archive_member"
        if source["archive_member_id"] is not None
        else "evidence_file",
        "evidence_file_id": evidence_id,
        "evidence_relative_path": evidence["relative_path"],
        "evidence_sha256": evidence["sha256"],
        "archive_member_id": source["archive_member_id"],
        "member_path": member_path,
        "archive_member_sha256": member_sha256,
    }


def observation(connection: Connection, kind: ObservationKind, object_id: str) -> Projection | None:
    model = DeviceObservation if kind == "device" else NetworkObservation
    columns = DEVICE_COLUMNS if kind == "device" else NETWORK_COLUMNS
    row = (
        connection.execute(
            select(*columns, model.observer_id, model.observer_version).where(model.id == object_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    result = dict(row)
    result["candidate_ids"] = candidate_ids(connection, kind, object_id)
    result["provenance"] = record_origin(connection, result["parsed_record_id"])
    return result


def candidate(connection: Connection, object_id: str, limit: int) -> Projection | None:
    row = (
        connection.execute(
            select(
                CorrelationCandidate.id.label("candidate_id"),
                CorrelationCandidate.candidate_kind,
                CorrelationCandidate.correlator_id,
                CorrelationCandidate.correlator_version,
                CorrelationCandidate.rule_id,
                CorrelationCandidate.rule_version,
                CorrelationCandidate.support_count,
                CorrelationCandidate.key_digest,
            ).where(CorrelationCandidate.id == object_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    result = dict(row)
    count = connection.execute(
        select(func.count())
        .select_from(CorrelationSupport)
        .where(CorrelationSupport.candidate_id == object_id)
    ).scalar_one()
    if count != result["support_count"]:
        raise EvidenceError("PROVENANCE_INTEGRITY_ERROR")
    rows = (
        connection.execute(
            select(
                CorrelationSupport.id.label("support_id"),
                CorrelationSupport.support_ordinal,
                CorrelationSupport.candidate_kind,
                CorrelationSupport.device_observation_id,
                CorrelationSupport.network_observation_id,
            )
            .where(CorrelationSupport.candidate_id == object_id)
            .order_by(CorrelationSupport.support_ordinal)
            .limit(limit)
        )
        .mappings()
        .all()
    )
    supports = []
    for support in rows:
        kind = support["candidate_kind"]
        device_id, network_id = support["device_observation_id"], support["network_observation_id"]
        if kind != result["candidate_kind"] or not (
            kind == "device"
            and device_id is not None
            and network_id is None
            or kind == "network"
            and network_id is not None
            and device_id is None
        ):
            raise EvidenceError("PROVENANCE_INTEGRITY_ERROR")
        observation_id = device_id if kind == "device" else network_id
        if not isinstance(observation_id, str):
            raise EvidenceError("PROVENANCE_INTEGRITY_ERROR")
        item = observation(connection, kind, observation_id)
        if item is None:
            raise EvidenceError("PROVENANCE_INTEGRITY_ERROR")
        fields = ("fact_kind", "namespace") if kind == "device" else ("source_role", "ip_version")
        supports.append(
            {
                "support_id": support["support_id"],
                "support_ordinal": support["support_ordinal"],
                "observation_kind": kind,
                "observation_id": item["observation_id"],
                "parsed_record_id": item["parsed_record_id"],
                "platform": item["platform"],
                **{field: item[field] for field in fields},
                "provenance": item["provenance"],
            }
        )
    result.update(
        returned_supports=len(supports), supports_truncated=count > len(supports), supports=supports
    )
    return result


def query_provenance(
    case_root: Path, *, kind: str, object_id: str, limit: int = 100
) -> Projection | None:
    """None means NOT_FOUND; invalid chains fail without returning a partial projection."""
    if kind not in KINDS:
        raise EvidenceError("Unsupported provenance kind")
    validate_limit(limit, 1000)
    try:
        object_id = str(UUID(object_id))
    except ValueError:
        raise EvidenceError("Provenance ID must be a valid UUID") from None
    with read_catalog(case_root) as connection:
        if kind == "candidate":
            return candidate(connection, object_id, limit)
        if kind in {"device-observation", "network-observation"}:
            return observation(
                connection, "device" if kind == "device-observation" else "network", object_id
            )
        if kind == "event":
            row = (
                connection.execute(
                    select(
                        NormalizedEvent.id.label("event_id"),
                        NormalizedEvent.parsed_record_id,
                        NormalizedEvent.platform,
                        NormalizedEvent.event_kind,
                        NormalizedEvent.normalizer_id,
                        NormalizedEvent.normalizer_version,
                        NormalizedEvent.occurred_at_utc,
                        NormalizedEvent.time_status,
                        NormalizedEvent.time_basis,
                    ).where(NormalizedEvent.id == object_id)
                )
                .mappings()
                .one_or_none()
            )
        else:
            row = (
                connection.execute(
                    select(
                        ParsedRecord.id.label("parsed_record_id"),
                        ParsedRecord.parser_id,
                        ParsedRecord.parser_version,
                        ParsedRecord.record_type,
                        ParsedRecord.source_locator,
                    ).where(ParsedRecord.id == object_id)
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        result = dict(row)
        if kind == "event":
            result["current_policy_match"] = (
                result["normalizer_id"],
                result["normalizer_version"],
            ) in CURRENT_NORMALIZERS
        result["provenance"] = record_origin(connection, result["parsed_record_id"])
        return result
