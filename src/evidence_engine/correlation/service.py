"""Atomic candidate/support persistence with immutable support-set validation."""

from dataclasses import dataclass
from itertools import chain
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from evidence_engine.correlation.exact import CORRELATOR_ID, CORRELATOR_VERSION, exact_groups
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.paths import CasePaths
from evidence_engine.models.entities import (
    Case,
    CorrelationCandidate,
    CorrelationRun,
    CorrelationSupport,
    DeviceObservation,
    NetworkObservation,
    new_id,
    utc_now,
)
from evidence_engine.storage.database import open_database


class SupportSetDivergence(Exception):
    """An existing candidate cannot be silently extended, reduced or rewritten."""


@dataclass
class CorrelationSummary:
    device_observations_inspected: int = 0
    network_observations_inspected: int = 0
    candidates_created: int = 0
    candidates_existing: int = 0
    supports_created: int = 0
    supports_existing: int = 0
    device_candidates: int = 0
    network_candidates: int = 0
    warnings: int = 0
    errors: int = 0


def correlate_exact(case_root: Path) -> CorrelationSummary:
    paths = CasePaths.load(case_root)
    engine = open_database(paths.db_file)
    summary = CorrelationSummary()
    try:
        with Session(engine) as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            case_id = session.scalars(select(Case.id)).one()
            run = CorrelationRun(
                id=new_id(),
                case_id=case_id,
                correlator_id=CORRELATOR_ID,
                correlator_version=CORRELATOR_VERSION,
                status="RUNNING",
            )
            session.add(run)
            session.flush()
            run_id = run.id
            try:
                with session.begin_nested():
                    devices = list(
                        session.scalars(
                            select(DeviceObservation).where(DeviceObservation.case_id == case_id)
                        )
                    )
                    networks = list(
                        session.scalars(
                            select(NetworkObservation).where(NetworkObservation.case_id == case_id)
                        )
                    )
                    summary.device_observations_inspected = len(devices)
                    summary.network_observations_inspected = len(networks)
                    groups = exact_groups(chain(devices, networks))
                    existing = {
                        (c.rule_id, c.rule_version, c.key_digest): c
                        for c in session.scalars(
                            select(CorrelationCandidate).where(
                                CorrelationCandidate.case_id == case_id,
                                CorrelationCandidate.correlator_id == CORRELATOR_ID,
                                CorrelationCandidate.correlator_version == CORRELATOR_VERSION,
                            )
                        )
                    }
                    expected_keys = {(g.rule_id, g.rule_version, g.key_digest) for g in groups}
                    # Detect vanished groups too (including groups reduced to singletons).
                    if existing.keys() - expected_keys:
                        raise SupportSetDivergence()
                    for group in groups:
                        expected_supports = [
                            (
                                ordinal,
                                group.candidate_kind,
                                observation.id if group.candidate_kind == "device" else None,
                                observation.id if group.candidate_kind == "network" else None,
                            )
                            for ordinal, observation in enumerate(group.observations)
                        ]
                        prior = existing.get((group.rule_id, group.rule_version, group.key_digest))
                        if prior is not None:
                            supports = list(
                                session.scalars(
                                    select(CorrelationSupport)
                                    .where(CorrelationSupport.candidate_id == prior.id)
                                    .order_by(CorrelationSupport.support_ordinal)
                                )
                            )
                            actual_supports = [
                                (
                                    s.support_ordinal,
                                    s.candidate_kind,
                                    s.device_observation_id,
                                    s.network_observation_id,
                                )
                                for s in supports
                            ]
                            if (
                                prior.candidate_kind != group.candidate_kind
                                or prior.support_count != len(expected_supports)
                                or actual_supports != expected_supports
                            ):
                                raise SupportSetDivergence()
                            summary.candidates_existing += 1
                            summary.supports_existing += len(supports)
                        else:
                            candidate = CorrelationCandidate(
                                case_id=case_id,
                                correlation_run_id=run.id,
                                correlator_id=CORRELATOR_ID,
                                correlator_version=CORRELATOR_VERSION,
                                rule_id=group.rule_id,
                                rule_version=group.rule_version,
                                candidate_kind=group.candidate_kind,
                                key_digest=group.key_digest,
                                support_count=len(expected_supports),
                            )
                            session.add(candidate)
                            session.flush()
                            for ordinal, kind, device_id, network_id in expected_supports:
                                session.add(
                                    CorrelationSupport(
                                        candidate_id=candidate.id,
                                        candidate_kind=kind,
                                        support_ordinal=ordinal,
                                        device_observation_id=device_id,
                                        network_observation_id=network_id,
                                    )
                                )
                            session.flush()
                            summary.candidates_created += 1
                            summary.supports_created += len(expected_supports)
                        if group.candidate_kind == "device":
                            summary.device_candidates += 1
                        else:
                            summary.network_candidates += 1
                run.status = "COMPLETED"
                run.candidates_created = summary.candidates_created
                run.candidates_existing = summary.candidates_existing
                run.supports_created = summary.supports_created
                run.supports_existing = summary.supports_existing
            except Exception as error:
                run.status = "FAILED"
                run.error_code = (
                    "SUPPORT_SET_DIVERGENCE"
                    if isinstance(error, SupportSetDivergence)
                    else "PERSISTENCE_ERROR"
                    if isinstance(error, SQLAlchemyError)
                    else "CORRELATION_ERROR"
                )
                summary = CorrelationSummary(
                    device_observations_inspected=summary.device_observations_inspected,
                    network_observations_inspected=summary.network_observations_inspected,
                    errors=1,
                )
            run.device_observations_inspected = summary.device_observations_inspected
            run.network_observations_inspected = summary.network_observations_inspected
            run.finished_at = utc_now()
            try:
                session.commit()
            except Exception as error:
                session.close()
                with Session(engine) as inspection:
                    if inspection.get(CorrelationRun, run_id) is not None:
                        raise EvidenceError(
                            "Correlation commit may already be durable; results preserved; "
                            "manual review required"
                        ) from error
                    inspection.add(
                        CorrelationRun(
                            id=run_id,
                            case_id=case_id,
                            correlator_id=CORRELATOR_ID,
                            correlator_version=CORRELATOR_VERSION,
                            status="FAILED",
                            error_code="COMMIT_FAILED",
                            finished_at=utc_now(),
                            device_observations_inspected=summary.device_observations_inspected,
                            network_observations_inspected=summary.network_observations_inspected,
                        )
                    )
                    inspection.commit()
                summary = CorrelationSummary(
                    device_observations_inspected=summary.device_observations_inspected,
                    network_observations_inspected=summary.network_observations_inspected,
                    errors=1,
                )
        return summary
    finally:
        engine.dispose()
