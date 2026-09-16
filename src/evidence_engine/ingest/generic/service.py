"""Transactional catalog ingestion with an immutable per-path baseline."""

import json
import logging
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from evidence_engine import __version__
from evidence_engine.config import ZipLimits
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.archives import extract_zip
from evidence_engine.ingest.generic.hashing import original_reader, sha256_file, sha256_stream
from evidence_engine.ingest.generic.paths import CasePaths, check_path, discover, sync_directory
from evidence_engine.models.entities import (
    ArchiveMember,
    Case,
    EvidenceFile,
    IngestionRun,
    SourceRecord,
    new_id,
    utc_now,
)
from evidence_engine.storage.database import open_database

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestResult:
    run_id: str
    files_seen: int
    files_added: int


def source_record(
    run_id: str, *, evidence_id: str | None = None, member_id: str | None = None
) -> SourceRecord:
    return SourceRecord(
        id=new_id(),
        ingestion_run_id=run_id,
        evidence_file_id=evidence_id,
        archive_member_id=member_id,
        location="whole-file",
        parser_id="evidence_engine.inventory",
        parser_version=__version__,
    )


def validate_materialized_members(session: Session, paths: CasePaths, case_id: str) -> None:
    """A successful run cannot endorse missing or changed cataloged extractions."""
    members = session.scalars(
        select(ArchiveMember).join(EvidenceFile).where(EvidenceFile.case_id == case_id)
    )
    for member in members:
        relative = PurePosixPath(member.working_relative_path)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or PureWindowsPath(member.working_relative_path).drive
            or "\\" in member.working_relative_path
            or relative.as_posix() != member.working_relative_path
        ):
            raise EvidenceError("Unsafe cataloged extraction path")
        path = paths.working.joinpath(*relative.parts)
        check_path(path)
        if not path.is_file() or not path.resolve().is_relative_to(paths.working):
            raise EvidenceError("MISSING cataloged extraction; manual review required")
        if path.stat().st_size != member.size_bytes or sha256_file(path) != member.sha256:
            raise EvidenceError("MODIFIED cataloged extraction; manual review required")


def ingest(case_root: Path, limits: ZipLimits | None = None) -> IngestResult:
    paths = CasePaths.load(case_root, create=True)
    limits = limits or ZipLimits()
    engine = open_database(paths.db_file, initialize=True)
    staging: Path | None = None
    run_id = new_id()
    seen = 0
    added = 0
    try:
        # Persist the run before work so a killed process leaves an auditable RUNNING row.
        with Session(engine) as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            case = session.scalars(select(Case)).one_or_none()
            if case is None:
                case = Case(id=new_id(), name=paths.root.name, case_root=str(paths.root))
                session.add(case)
                session.flush()
            case_id = case.id
            session.add(
                IngestionRun(
                    id=run_id,
                    case_id=case_id,
                    engine_version=__version__,
                    status="RUNNING",
                    zip_limits=limits.model_dump_json(),
                )
            )
            session.commit()
        logger.info("ingestion_started run_id=%s", run_id)
        try:
            with Session(engine) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                existing = {
                    item.relative_path: item
                    for item in session.scalars(
                        select(EvidenceFile).where(EvidenceFile.case_id == case_id)
                    )
                }
                files = discover(paths.originals)
                relative_names = {file.relative_to(paths.originals).as_posix() for file in files}
                seen = len(files)
                if set(existing) - relative_names:
                    raise EvidenceError("MISSING original; baseline preserved; run evidence verify")
                for file in files:
                    relative = file.relative_to(paths.originals).as_posix()
                    with original_reader(file) as stream:
                        digest, size = sha256_stream(stream)
                        if relative in existing:
                            baseline = existing[relative]
                            if digest != baseline.sha256 or size != baseline.size_bytes:
                                raise EvidenceError(
                                    "MODIFIED original; baseline preserved; run evidence verify"
                                )
                            continue
                        stream.seek(0)
                        is_archive = zipfile.is_zipfile(stream)
                        if file.suffix.lower() == ".zip" and not is_archive:
                            raise EvidenceError("File with ZIP extension is not a valid ZIP")
                        evidence_id = new_id()
                        evidence = EvidenceFile(
                            id=evidence_id,
                            case_id=case_id,
                            ingestion_run_id=run_id,
                            relative_path=relative,
                            filename=file.name,
                            extension=file.suffix.lower(),
                            size_bytes=size,
                            sha256=digest,
                            mime_type="application/zip" if is_archive else None,
                            is_archive=is_archive,
                        )
                        session.add(evidence)
                        session.flush()
                        session.add(source_record(run_id, evidence_id=evidence_id))
                        if is_archive:
                            if staging is None:
                                staging = Path(
                                    tempfile.mkdtemp(prefix=f"ingest-{run_id}-", dir=paths.working)
                                )
                            stream.seek(0)
                            extracted = extract_zip(stream, staging / evidence_id, limits)
                            for entry in extracted:
                                name = PurePosixPath(entry.member_path)
                                member = ArchiveMember(
                                    id=new_id(),
                                    evidence_file_id=evidence_id,
                                    ingestion_run_id=run_id,
                                    member_path=entry.member_path,
                                    filename=name.name,
                                    extension=name.suffix.lower(),
                                    size_bytes=entry.size_bytes,
                                    compressed_size=entry.compressed_size,
                                    crc32=entry.crc32,
                                    sha256=entry.sha256,
                                    working_relative_path=entry.path.relative_to(
                                        paths.working
                                    ).as_posix(),
                                )
                                session.add(member)
                                session.flush()
                                session.add(source_record(run_id, member_id=member.id))
                            stream.seek(0)
                            if sha256_stream(stream) != (digest, size):
                                raise EvidenceError("ZIP changed during extraction")
                    added += 1
                validate_materialized_members(session, paths, case_id)
                if staging is not None:
                    sync_directory(staging)
                    sync_directory(paths.working)
                    sync_directory(paths.root)
                run = session.get(IngestionRun, run_id)
                assert run is not None
                run.status = "COMPLETED"
                run.finished_at = utc_now()
                run.files_seen, run.files_added = seen, added
                if added:
                    case = session.get(Case, case_id)
                    assert case is not None
                    case.inventory_updated_at = run.finished_at
                session.commit()
        except Exception as error:
            message = (
                str(error)
                if isinstance(error, EvidenceError)
                else f"Technical failure: {type(error).__name__}"
            )
            # commit() can fail after SQLite has committed (e.g. an after_commit
            # hook or lost acknowledgement). Never delete possibly committed files.
            try:
                with Session(engine) as inspection:
                    state = inspection.scalar(
                        select(IngestionRun.status).where(IngestionRun.id == run_id)
                    )
            except SQLAlchemyError:
                raise EvidenceError(
                    f"Run {run_id}: commit outcome unknown; staging preserved for manual review"
                ) from error
            if state != "RUNNING":
                raise EvidenceError(
                    f"Run {run_id}: catalog may already be committed; staging preserved; "
                    "manual review required"
                ) from error
            if staging is not None:
                try:
                    check_path(staging)
                    if staging.parent != paths.working:
                        raise EvidenceError("Unsafe extraction cleanup path")
                    shutil.rmtree(staging)
                except (OSError, EvidenceError):
                    # A cleanup failure must not erase the audit of the original failure.
                    message += "; staging cleanup failed; manual review of working required"
            with Session(engine) as session:
                run = session.get(IngestionRun, run_id)
                assert run is not None
                run.status, run.finished_at = "FAILED", utc_now()
                run.files_seen, run.files_added = seen, 0
                run.errors = json.dumps([message])
                session.commit()
            logger.error("ingestion_failed run_id=%s error=%s", run_id, message)
            raise EvidenceError(f"Run {run_id} failed: {message}") from error
        logger.info(
            "ingestion_completed run_id=%s files_seen=%d files_added=%d", run_id, seen, added
        )
        return IngestResult(run_id, seen, added)
    finally:
        engine.dispose()
