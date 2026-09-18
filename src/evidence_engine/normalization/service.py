"""Atomic per-normalizer derivation from cataloged ParsedRecords only."""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.paths import CasePaths
from evidence_engine.ingest.parsing.framework import JSONValue, json_text
from evidence_engine.models.entities import (
    Case,
    NormalizationRun,
    NormalizedEvent,
    ParsedRecord,
    new_id,
    utc_now,
)
from evidence_engine.normalization.framework import Normalizer, NormalizerContext
from evidence_engine.normalization.normalizers import NORMALIZERS
from evidence_engine.storage.database import open_database


@dataclass
class NormalizationSummary:
    records_inspected: int = 0
    records_supported: int = 0
    events_normalized: int = 0
    events_existing: int = 0
    records_skipped: int = 0
    warnings: int = 0
    errors: int = 0


def raw_text(value: JSONValue) -> str | None:
    return None if value is None else json_text(value)


def normalize_events(
    case_root: Path, normalizers: tuple[Normalizer, ...] = NORMALIZERS
) -> NormalizationSummary:
    paths = CasePaths.load(case_root)
    engine = open_database(paths.db_file)
    summary = NormalizationSummary()
    try:
        with Session(engine) as session:
            case_id = session.scalars(select(Case.id)).one()
            catalog = list(
                session.scalars(
                    select(ParsedRecord)
                    .where(ParsedRecord.case_id == case_id)
                    .order_by(ParsedRecord.id)
                )
            )
            summary.records_inspected = len(catalog)
            for record in catalog:
                candidates = [
                    n
                    for n in normalizers
                    if n.supports(record.parser_id, record.parser_version, record.record_type)
                ]
                if len(candidates) > 1:
                    raise EvidenceError("Ambiguous normalizer registration")
                summary.records_supported += bool(candidates)
            summary.records_skipped = summary.records_inspected - summary.records_supported
        for normalizer in normalizers:
            with Session(engine) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                run = NormalizationRun(
                    id=new_id(),
                    case_id=case_id,
                    normalizer_id=normalizer.normalizer_id,
                    normalizer_version=normalizer.normalizer_version,
                    status="RUNNING",
                )
                session.add(run)
                session.flush()
                run_id = run.id
                added = existing = 0
                warnings: Counter[str] = Counter()
                try:
                    with session.begin_nested():
                        for record in session.scalars(
                            select(ParsedRecord)
                            .where(ParsedRecord.case_id == case_id)
                            .order_by(ParsedRecord.id)
                        ):
                            if not normalizer.supports(
                                record.parser_id, record.parser_version, record.record_type
                            ):
                                continue
                            prior = session.scalar(
                                select(NormalizedEvent.id).where(
                                    NormalizedEvent.parsed_record_id == record.id,
                                    NormalizedEvent.normalizer_id == normalizer.normalizer_id,
                                    NormalizedEvent.normalizer_version
                                    == normalizer.normalizer_version,
                                    NormalizedEvent.event_ordinal == 0,
                                )
                            )
                            if prior is not None:
                                existing += 1
                                continue
                            payload = json.loads(record.payload_json)
                            annotations = json.loads(record.annotations_json)
                            if (
                                not isinstance(payload, dict)
                                or not isinstance(annotations, list)
                                or any(not isinstance(a, dict) for a in annotations)
                            ):
                                raise ValueError("INVALID_PARSED_RECORD")
                            context = NormalizerContext(
                                record.parser_id,
                                record.parser_version,
                                record.record_type,
                                json.loads(record.timestamp_raw)
                                if record.timestamp_raw is not None
                                else None,
                                payload,
                                annotations,
                            )
                            result = normalizer.normalize(context)
                            draft = result.event
                            session.add(
                                NormalizedEvent(
                                    case_id=case_id,
                                    normalization_run_id=run.id,
                                    parsed_record_id=record.id,
                                    normalizer_id=normalizer.normalizer_id,
                                    normalizer_version=normalizer.normalizer_version,
                                    event_ordinal=0,
                                    platform=draft.platform,
                                    event_kind=draft.event_kind,
                                    timestamp_raw=record.timestamp_raw,
                                    occurred_at_utc=draft.occurred_at_utc,
                                    time_status=draft.time_status,
                                    time_basis=draft.time_basis,
                                    ip_raw=raw_text(draft.ip_raw),
                                    device_identifier_raw=raw_text(draft.device_identifier_raw),
                                    device_model_raw=raw_text(draft.device_model_raw),
                                    action_raw=raw_text(draft.action_raw),
                                    status_raw=raw_text(draft.status_raw),
                                )
                            )
                            session.flush()
                            added += 1
                            warnings.update(result.warnings)
                    run.status = "COMPLETED"
                    run.events_normalized = added
                    run.events_existing = existing
                    run.diagnostics_json = json_text(dict(warnings))
                except Exception as error:
                    run.status = "FAILED"
                    run.error_code = (
                        "PERSISTENCE_ERROR"
                        if isinstance(error, SQLAlchemyError)
                        else "NORMALIZATION_ERROR"
                    )
                    added = existing = 0
                    warnings.clear()
                run.completed_at = utc_now()
                failed = run.status == "FAILED"
                try:
                    session.commit()
                except Exception as error:
                    session.close()
                    with Session(engine) as inspection:
                        if inspection.get(NormalizationRun, run_id) is not None:
                            raise EvidenceError(
                                "Normalization commit may already be durable; results preserved; "
                                "manual review required"
                            ) from error
                        inspection.add(
                            NormalizationRun(
                                id=run_id,
                                case_id=case_id,
                                normalizer_id=normalizer.normalizer_id,
                                normalizer_version=normalizer.normalizer_version,
                                status="FAILED",
                                error_code="COMMIT_FAILED",
                                completed_at=utc_now(),
                            )
                        )
                        inspection.commit()
                    added = existing = 0
                    warnings.clear()
                    failed = True
                summary.events_normalized += added
                summary.events_existing += existing
                summary.warnings += sum(warnings.values())
                summary.errors += failed
        return summary
    finally:
        engine.dispose()
