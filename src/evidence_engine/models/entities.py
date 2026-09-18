"""Initial schema: immutable catalog baselines and explicit source references."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid4())


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=utc_now)
    case_root: Mapped[str]
    inventory_updated_at: Mapped[str] = mapped_column(default=utc_now)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    started_at: Mapped[str] = mapped_column(default=utc_now)
    finished_at: Mapped[str | None]
    engine_version: Mapped[str]
    status: Mapped[str]
    files_seen: Mapped[int] = mapped_column(default=0)
    files_added: Mapped[int] = mapped_column(default=0)
    errors: Mapped[str] = mapped_column(default="[]")
    zip_limits: Mapped[str]


class EvidenceFile(Base):
    __tablename__ = "evidence_files"
    __table_args__ = (
        UniqueConstraint("case_id", "relative_path"),
        CheckConstraint("size_bytes >= 0"),
        CheckConstraint("length(sha256) = 64"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    ingestion_run_id: Mapped[str] = mapped_column(ForeignKey("ingestion_runs.id"))
    relative_path: Mapped[str]
    filename: Mapped[str]
    extension: Mapped[str]
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str | None]
    is_archive: Mapped[bool]
    created_at: Mapped[str] = mapped_column(default=utc_now)
    first_seen_at: Mapped[str] = mapped_column(default=utc_now)


class ArchiveMember(Base):
    __tablename__ = "archive_members"
    __table_args__ = (
        UniqueConstraint("evidence_file_id", "member_path"),
        UniqueConstraint("working_relative_path"),
        CheckConstraint("size_bytes >= 0 AND compressed_size >= 0"),
        CheckConstraint("length(sha256) = 64"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evidence_file_id: Mapped[str] = mapped_column(ForeignKey("evidence_files.id"), index=True)
    ingestion_run_id: Mapped[str] = mapped_column(ForeignKey("ingestion_runs.id"))
    member_path: Mapped[str]
    filename: Mapped[str]
    extension: Mapped[str]
    size_bytes: Mapped[int]
    compressed_size: Mapped[int]
    crc32: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    working_relative_path: Mapped[str]


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (
        CheckConstraint(
            "(evidence_file_id IS NOT NULL AND archive_member_id IS NULL) OR "
            "(evidence_file_id IS NULL AND archive_member_id IS NOT NULL)",
            name="exactly_one_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ingestion_run_id: Mapped[str] = mapped_column(ForeignKey("ingestion_runs.id"))
    evidence_file_id: Mapped[str | None] = mapped_column(ForeignKey("evidence_files.id"))
    archive_member_id: Mapped[str | None] = mapped_column(ForeignKey("archive_members.id"))
    location: Mapped[str]
    parser_id: Mapped[str]
    parser_version: Mapped[str]


class ParserRun(Base):
    """One source/parser attempt; failed attempts retain only technical diagnostics."""

    __tablename__ = "parser_runs"
    __table_args__ = (
        CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED', 'UNSUPPORTED')"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_record_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"))
    parser_id: Mapped[str]
    parser_version: Mapped[str]
    status: Mapped[str]
    records_parsed: Mapped[int] = mapped_column(default=0)
    warnings_json: Mapped[str] = mapped_column(default="[]")
    error_code: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=utc_now)
    finished_at: Mapped[str | None]


Index(
    "uq_completed_source_parser",
    ParserRun.source_record_id,
    ParserRun.parser_id,
    ParserRun.parser_version,
    unique=True,
    sqlite_where=ParserRun.status == "COMPLETED",
)


class ParsedRecord(Base):
    """An observation at a precise source locator, never a normalized event."""

    __tablename__ = "parsed_records"
    __table_args__ = (
        UniqueConstraint("parser_run_id", "source_locator"),
        CheckConstraint("record_index IS NULL OR record_index >= 0"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    source_record_id: Mapped[str] = mapped_column(ForeignKey("source_records.id"), unique=True)
    parser_run_id: Mapped[str] = mapped_column(ForeignKey("parser_runs.id"))
    parser_id: Mapped[str]
    parser_version: Mapped[str]
    record_type: Mapped[str]
    source_locator: Mapped[str]
    record_index: Mapped[int | None]
    # JSON scalar encoded as text, preserving string vs number vs boolean.
    timestamp_raw: Mapped[str | None]
    payload_json: Mapped[str]
    annotations_json: Mapped[str] = mapped_column(default="[]")
    created_at: Mapped[str] = mapped_column(default=utc_now)


class NormalizationRun(Base):
    """One atomic normalizer execution; diagnostics contain fixed codes only."""

    __tablename__ = "normalization_runs"
    __table_args__ = (CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    normalizer_id: Mapped[str]
    normalizer_version: Mapped[str]
    status: Mapped[str]
    started_at: Mapped[str] = mapped_column(default=utc_now)
    completed_at: Mapped[str | None]
    error_code: Mapped[str | None]
    diagnostics_json: Mapped[str] = mapped_column(default="[]")
    events_normalized: Mapped[int] = mapped_column(default=0)
    events_existing: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(default=utc_now)


class NormalizedEvent(Base):
    """DERIVED representation of one observation; never an identity correlation."""

    __tablename__ = "normalized_events"
    __table_args__ = (
        UniqueConstraint(
            "parsed_record_id", "normalizer_id", "normalizer_version", "event_ordinal"
        ),
        CheckConstraint("event_ordinal >= 0"),
        CheckConstraint("time_status IN ('normalized', 'raw_only', 'missing')"),
        CheckConstraint("(time_status = 'normalized') = (occurred_at_utc IS NOT NULL)"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    normalization_run_id: Mapped[str] = mapped_column(ForeignKey("normalization_runs.id"))
    parsed_record_id: Mapped[str] = mapped_column(ForeignKey("parsed_records.id"), index=True)
    normalizer_id: Mapped[str]
    normalizer_version: Mapped[str]
    event_ordinal: Mapped[int] = mapped_column(default=0)
    platform: Mapped[str]
    event_kind: Mapped[str]
    # Raw fields are JSON scalars, preserving original types and empty strings.
    timestamp_raw: Mapped[str | None]
    occurred_at_utc: Mapped[str | None]
    time_status: Mapped[str]
    time_basis: Mapped[str]
    ip_raw: Mapped[str | None]
    device_identifier_raw: Mapped[str | None]
    device_model_raw: Mapped[str | None]
    action_raw: Mapped[str | None]
    status_raw: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=utc_now)


class ObservationRun(Base):
    """One atomic observer execution; warnings contain technical counts only."""

    __tablename__ = "observation_runs"
    __table_args__ = (CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    observer_id: Mapped[str]
    observer_version: Mapped[str]
    status: Mapped[str]
    started_at: Mapped[str] = mapped_column(default=utc_now)
    finished_at: Mapped[str | None]
    records_inspected: Mapped[int] = mapped_column(default=0)
    records_supported: Mapped[int] = mapped_column(default=0)
    records_skipped: Mapped[int] = mapped_column(default=0)
    observations_created: Mapped[int] = mapped_column(default=0)
    observations_existing: Mapped[int] = mapped_column(default=0)
    warnings_json: Mapped[str] = mapped_column(default="{}")
    error_code: Mapped[str | None]


class DeviceObservation(Base):
    """DERIVED atomic fact, not an entity or assertion of device identity."""

    __tablename__ = "device_observations"
    __table_args__ = (
        UniqueConstraint(
            "parsed_record_id", "observer_id", "observer_version", "observation_ordinal"
        ),
        CheckConstraint("observation_ordinal >= 0"),
        CheckConstraint("fact_kind IN ('identifier', 'model')"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    observation_run_id: Mapped[str] = mapped_column(ForeignKey("observation_runs.id"))
    parsed_record_id: Mapped[str] = mapped_column(ForeignKey("parsed_records.id"), index=True)
    observer_id: Mapped[str]
    observer_version: Mapped[str]
    observation_ordinal: Mapped[int]
    platform: Mapped[str]
    fact_kind: Mapped[str]
    namespace: Mapped[str]
    # JSON scalar encoding preserves the source type, spelling and leading zeros.
    value_raw: Mapped[str]
    source_field_locator: Mapped[str]
    source_field_name: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=utc_now)


class NetworkObservation(Base):
    """DERIVED occurrence of an explicit IP field; no network identity."""

    __tablename__ = "network_observations"
    __table_args__ = (
        UniqueConstraint(
            "parsed_record_id", "observer_id", "observer_version", "observation_ordinal"
        ),
        CheckConstraint("observation_ordinal >= 0"),
        CheckConstraint("ip_version IS NULL OR ip_version IN (4, 6)"),
        CheckConstraint("(ip_canonical IS NULL) = (ip_version IS NULL)"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    observation_run_id: Mapped[str] = mapped_column(ForeignKey("observation_runs.id"))
    parsed_record_id: Mapped[str] = mapped_column(ForeignKey("parsed_records.id"), index=True)
    observer_id: Mapped[str]
    observer_version: Mapped[str]
    observation_ordinal: Mapped[int]
    platform: Mapped[str]
    source_role: Mapped[str]
    # JSON scalar, just like other raw catalog fields; canonical is plain text.
    ip_raw: Mapped[str]
    ip_canonical: Mapped[str | None]
    ip_version: Mapped[int | None]
    source_field_locator: Mapped[str]
    source_field_name: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=utc_now)


class CorrelationRun(Base):
    """One atomic exact-match execution; diagnostics contain no source values."""

    __tablename__ = "correlation_runs"
    __table_args__ = (CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    correlator_id: Mapped[str]
    correlator_version: Mapped[str]
    status: Mapped[str]
    started_at: Mapped[str] = mapped_column(default=utc_now)
    finished_at: Mapped[str | None]
    device_observations_inspected: Mapped[int] = mapped_column(default=0)
    network_observations_inspected: Mapped[int] = mapped_column(default=0)
    candidates_created: Mapped[int] = mapped_column(default=0)
    candidates_existing: Mapped[int] = mapped_column(default=0)
    supports_created: Mapped[int] = mapped_column(default=0)
    supports_existing: Mapped[int] = mapped_column(default=0)
    warnings_json: Mapped[str] = mapped_column(default="{}")
    error_code: Mapped[str | None]


class CorrelationCandidate(Base):
    """Group of exact technical matches, never a shared identity or pairwise edge."""

    __tablename__ = "correlation_candidates"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "correlator_id",
            "correlator_version",
            "rule_id",
            "rule_version",
            "key_digest",
        ),
        UniqueConstraint("id", "candidate_kind"),
        CheckConstraint("candidate_kind IN ('device', 'network')"),
        CheckConstraint("support_count >= 2"),
        CheckConstraint("length(key_digest) = 64"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    correlation_run_id: Mapped[str] = mapped_column(ForeignKey("correlation_runs.id"))
    correlator_id: Mapped[str]
    correlator_version: Mapped[str]
    rule_id: Mapped[str]
    rule_version: Mapped[str]
    candidate_kind: Mapped[str]
    key_digest: Mapped[str] = mapped_column(String(64))
    support_count: Mapped[int]
    created_at: Mapped[str] = mapped_column(default=utc_now)


class CorrelationSupport(Base):
    """One typed observation reference; raw values stay in their source table."""

    __tablename__ = "correlation_supports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["candidate_id", "candidate_kind"],
            ["correlation_candidates.id", "correlation_candidates.candidate_kind"],
        ),
        UniqueConstraint("candidate_id", "support_ordinal"),
        UniqueConstraint("candidate_id", "device_observation_id"),
        UniqueConstraint("candidate_id", "network_observation_id"),
        CheckConstraint("support_ordinal >= 0"),
        CheckConstraint(
            "(candidate_kind = 'device' AND device_observation_id IS NOT NULL "
            "AND network_observation_id IS NULL) OR "
            "(candidate_kind = 'network' AND network_observation_id IS NOT NULL "
            "AND device_observation_id IS NULL)"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str]
    candidate_kind: Mapped[str]
    support_ordinal: Mapped[int]
    device_observation_id: Mapped[str | None] = mapped_column(ForeignKey("device_observations.id"))
    network_observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("network_observations.id")
    )
