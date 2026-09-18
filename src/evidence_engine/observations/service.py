"""Atomic observer runs over catalog rows; no evidence-file reads or correlations."""

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.paths import CasePaths
from evidence_engine.ingest.parsing.framework import json_text
from evidence_engine.models.entities import (
    Case,
    DeviceObservation,
    NetworkObservation,
    ObservationRun,
    ParsedRecord,
    new_id,
    utc_now,
)
from evidence_engine.observations.framework import DeviceDraft, ObservationContext, Observer
from evidence_engine.observations.observers import OBSERVERS
from evidence_engine.storage.database import open_database


@dataclass
class ObservationSummary:
    records_inspected: int = 0
    records_supported: int = 0
    device_observations_created: int = 0
    device_observations_existing: int = 0
    network_observations_created: int = 0
    network_observations_existing: int = 0
    records_skipped: int = 0
    warnings: int = 0
    errors: int = 0


def observe_device_network(
    case_root: Path, observers: tuple[Observer, ...] = OBSERVERS
) -> ObservationSummary:
    paths = CasePaths.load(case_root)
    engine = open_database(paths.db_file)
    summary = ObservationSummary()
    try:
        if len({o.observer_id for o in observers}) != len(observers) or any(
            o.observer_id not in {"device.observer", "network.observer"} for o in observers
        ):
            raise EvidenceError("Invalid observer registration")
        with Session(engine) as session:
            case_id = session.scalars(select(Case.id)).one()
            for record in session.scalars(
                select(ParsedRecord).where(ParsedRecord.case_id == case_id)
            ):
                summary.records_inspected += 1
                summary.records_supported += any(
                    o.supports(record.parser_id, record.parser_version, record.record_type)
                    for o in observers
                )
            summary.records_skipped = summary.records_inspected - summary.records_supported
        for observer in observers:
            model: type[DeviceObservation] | type[NetworkObservation]
            model = (
                DeviceObservation
                if observer.observer_id == "device.observer"
                else NetworkObservation
            )
            with Session(engine) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                run = ObservationRun(
                    id=new_id(),
                    case_id=case_id,
                    observer_id=observer.observer_id,
                    observer_version=observer.observer_version,
                    status="RUNNING",
                )
                session.add(run)
                session.flush()
                run_id = run.id
                added = existing = inspected = supported = 0
                warnings: Counter[str] = Counter()
                try:
                    with session.begin_nested():
                        for record in session.scalars(
                            select(ParsedRecord)
                            .where(ParsedRecord.case_id == case_id)
                            .order_by(ParsedRecord.id)
                        ):
                            inspected += 1
                            if not observer.supports(
                                record.parser_id, record.parser_version, record.record_type
                            ):
                                continue
                            supported += 1
                            payload, annotations = (
                                json.loads(record.payload_json),
                                json.loads(record.annotations_json),
                            )
                            if (
                                not isinstance(payload, dict)
                                or not isinstance(annotations, list)
                                or any(not isinstance(a, dict) for a in annotations)
                            ):
                                raise ValueError("INVALID_PARSED_RECORD")
                            result = observer.observe(
                                ObservationContext(
                                    record.parser_id,
                                    record.parser_version,
                                    record.record_type,
                                    record.source_locator,
                                    payload,
                                    annotations,
                                )
                            )
                            prior_rows = list(
                                session.scalars(
                                    select(model)
                                    .where(
                                        model.parsed_record_id == record.id,
                                        model.observer_id == observer.observer_id,
                                        model.observer_version == observer.observer_version,
                                    )
                                    .order_by(model.observation_ordinal)
                                )
                            )
                            prior = cast(list[DeviceObservation | NetworkObservation], prior_rows)
                            if prior and [p.observation_ordinal for p in prior] != list(
                                range(len(result.observations))
                            ):
                                raise ValueError("EXISTING_OBSERVATION_MISMATCH")
                            for ordinal, draft in enumerate(result.observations):
                                if isinstance(draft, DeviceDraft) != (model is DeviceObservation):
                                    raise ValueError("WRONG_OBSERVATION_KIND")
                                values = asdict(draft)
                                raw_key = (
                                    "value_raw" if isinstance(draft, DeviceDraft) else "ip_raw"
                                )
                                values[raw_key] = json_text(values[raw_key])
                                if prior:
                                    if any(
                                        getattr(prior[ordinal], key) != value
                                        for key, value in values.items()
                                    ):
                                        raise ValueError("EXISTING_OBSERVATION_MISMATCH")
                                    existing += 1
                                    continue
                                session.add(
                                    model(
                                        case_id=case_id,
                                        observation_run_id=run.id,
                                        parsed_record_id=record.id,
                                        observer_id=observer.observer_id,
                                        observer_version=observer.observer_version,
                                        observation_ordinal=ordinal,
                                        **values,
                                    )
                                )
                                session.flush()
                                added += 1
                            warnings.update(result.warnings)
                    run.status = "COMPLETED"
                    run.observations_created = added
                    run.observations_existing = existing
                    run.warnings_json = json_text(dict(warnings))
                except Exception as error:
                    run.status = "FAILED"
                    run.error_code = (
                        "PERSISTENCE_ERROR"
                        if isinstance(error, SQLAlchemyError)
                        else "OBSERVATION_ERROR"
                    )
                    added = existing = 0
                    warnings.clear()
                run.records_inspected = inspected
                run.records_supported = supported
                run.records_skipped = inspected - supported
                run.finished_at = utc_now()
                failed = run.status == "FAILED"
                try:
                    session.commit()
                except Exception as error:
                    session.close()
                    with Session(engine) as inspection:
                        if inspection.get(ObservationRun, run_id) is not None:
                            raise EvidenceError(
                                "Observation commit may already be durable; results preserved; "
                                "manual review required"
                            ) from error
                        inspection.add(
                            ObservationRun(
                                id=run_id,
                                case_id=case_id,
                                observer_id=observer.observer_id,
                                observer_version=observer.observer_version,
                                status="FAILED",
                                error_code="COMMIT_FAILED",
                                finished_at=utc_now(),
                                records_inspected=inspected,
                                records_supported=supported,
                                records_skipped=inspected - supported,
                            )
                        )
                        inspection.commit()
                    added = existing = 0
                    warnings.clear()
                    failed = True
                if model is DeviceObservation:
                    summary.device_observations_created += added
                    summary.device_observations_existing += existing
                else:
                    summary.network_observations_created += added
                    summary.network_observations_existing += existing
                summary.warnings += sum(warnings.values())
                summary.errors += failed
        return summary
    finally:
        engine.dispose()
