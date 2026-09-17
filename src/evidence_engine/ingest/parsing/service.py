"""Parse cataloged sources with hash checks and one transaction per source/parser."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.hashing import original_reader, sha256_file
from evidence_engine.ingest.generic.paths import CasePaths, check_path, discover
from evidence_engine.ingest.google.html import table_document
from evidence_engine.ingest.google.parsers import PARSERS as GOOGLE_PARSERS
from evidence_engine.ingest.instagram.parsers import PARSERS
from evidence_engine.ingest.parsing.framework import (
    MAX_SOURCE_BYTES,
    Diagnostic,
    JSONValue,
    ParseError,
    Parser,
    ParserContext,
    json_text,
    resolve_locator,
    strict_json,
)
from evidence_engine.models.entities import (
    ArchiveMember,
    Case,
    EvidenceFile,
    ParsedRecord,
    ParserRun,
    SourceRecord,
    new_id,
    utc_now,
)
from evidence_engine.storage.database import open_database


@dataclass(frozen=True)
class CatalogSource:
    inventory_id: str
    ingestion_run_id: str
    case_id: str
    evidence_id: str
    member_id: str | None
    relative_path: str
    original_path: str
    original_hash: str
    working_path: str | None
    sha256: str
    size_bytes: int


@dataclass
class ParseSummary:
    sources_inspected: int = 0
    sources_supported: int = 0
    sources_skipped: int = 0
    records_parsed: int = 0
    records_existing: int = 0
    warnings: int = 0
    errors: int = 0


def catalog_sources(session: Session) -> list[CatalogSource]:
    case = session.scalars(select(Case)).one_or_none()
    if case is None:
        raise EvidenceError("Catalog has no case")
    results: list[CatalogSource] = []
    inventory = (
        SourceRecord.parser_id == "evidence_engine.inventory",
        SourceRecord.location == "whole-file",
    )
    direct = session.execute(
        select(SourceRecord, EvidenceFile)
        .join(EvidenceFile, SourceRecord.evidence_file_id == EvidenceFile.id)
        .where(*inventory, EvidenceFile.case_id == case.id, EvidenceFile.is_archive.is_(False))
    )
    for source, evidence in direct:
        results.append(
            CatalogSource(
                source.id,
                source.ingestion_run_id,
                case.id,
                evidence.id,
                None,
                evidence.relative_path,
                evidence.relative_path,
                evidence.sha256,
                None,
                evidence.sha256,
                evidence.size_bytes,
            )
        )
    members = session.execute(
        select(SourceRecord, ArchiveMember, EvidenceFile)
        .join(ArchiveMember, SourceRecord.archive_member_id == ArchiveMember.id)
        .join(EvidenceFile, ArchiveMember.evidence_file_id == EvidenceFile.id)
        .where(*inventory, EvidenceFile.case_id == case.id)
    )
    for source, member, evidence in members:
        results.append(
            CatalogSource(
                source.id,
                source.ingestion_run_id,
                case.id,
                evidence.id,
                member.id,
                member.member_path,
                evidence.relative_path,
                evidence.sha256,
                member.working_relative_path,
                member.sha256,
                member.size_bytes,
            )
        )
    return sorted(
        results, key=lambda item: (item.original_path, item.relative_path, item.inventory_id)
    )


def source_bytes(
    source: CatalogSource, paths: CasePaths, originals: dict[str, Path], checked_archives: set[str]
) -> bytes:
    original = originals.get(source.original_path)
    if original is None:
        raise ParseError("MISSING_ORIGINAL")
    path = original
    if source.member_id is not None:
        if source.evidence_id not in checked_archives:
            if sha256_file(original) != source.original_hash:
                raise ParseError("MODIFIED_CONTAINER")
            checked_archives.add(source.evidence_id)
        assert source.working_path is not None
        relative = PurePosixPath(source.working_path)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in source.working_path
            or PureWindowsPath(source.working_path).drive
            or relative.as_posix() != source.working_path
        ):
            raise ParseError("UNSAFE_CATALOG_PATH")
        path = paths.working.joinpath(*relative.parts)
        check_path(path)
        if not path.resolve().is_relative_to(paths.working):
            raise ParseError("UNSAFE_CATALOG_PATH")
    if source.size_bytes > MAX_SOURCE_BYTES:
        raise ParseError("SOURCE_SIZE_LIMIT")
    with original_reader(path) as stream:
        data = stream.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise ParseError("SOURCE_SIZE_LIMIT")
    if len(data) != source.size_bytes or hashlib.sha256(data).hexdigest() != source.sha256:
        raise ParseError("MODIFIED_SOURCE")
    return data


def parse_instagram(case_root: Path, parsers: tuple[Parser, ...] = PARSERS) -> ParseSummary:
    return parse_catalog(case_root, parsers, strict_json)


def parse_google(case_root: Path, parsers: tuple[Parser, ...] = GOOGLE_PARSERS) -> ParseSummary:
    return parse_catalog(case_root, parsers, table_document)


def parse_catalog(
    case_root: Path, parsers: tuple[Parser, ...], decode: Callable[[bytes], JSONValue]
) -> ParseSummary:
    paths = CasePaths.load(case_root)
    engine = open_database(paths.db_file)
    summary = ParseSummary()
    try:
        with Session(engine) as session:
            sources = catalog_sources(session)
        originals = {
            path.relative_to(paths.originals).as_posix(): path for path in discover(paths.originals)
        }
        checked_archives: set[str] = set()
        summary.sources_inspected = len(sources)
        for source in sources:
            context = ParserContext(source.relative_path)
            candidates = [parser for parser in parsers if parser.matches_path(context)]
            if not candidates:
                summary.sources_skipped += 1
                continue
            if len(candidates) != 1:
                raise EvidenceError("Ambiguous parser registration")
            parser = candidates[0]
            before_source = replace(summary)
            with Session(engine) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                completed = session.scalars(
                    select(ParserRun).where(
                        ParserRun.source_record_id == source.inventory_id,
                        ParserRun.parser_id == parser.parser_id,
                        ParserRun.parser_version == parser.parser_version,
                        ParserRun.status == "COMPLETED",
                    )
                ).one_or_none()
                attempt_id = new_id()
                run = ParserRun(
                    id=attempt_id,
                    source_record_id=source.inventory_id,
                    parser_id=parser.parser_id,
                    parser_version=parser.parser_version,
                    status="RUNNING",
                )
                session.add(run)
                session.flush()
                try:
                    # Roll back all observations and their SourceRecords together on failure.
                    with session.begin_nested():
                        data = source_bytes(source, paths, originals, checked_archives)
                        if completed is not None:
                            session.delete(run)
                            summary.sources_supported += 1
                            summary.sources_skipped += 1
                            summary.records_existing += completed.records_parsed
                            summary.warnings += len(json.loads(completed.warnings_json))
                        else:
                            document = decode(data)
                            if not parser.supports(context, document):
                                run.status = "UNSUPPORTED"
                                run.warnings_json = json_text(
                                    [asdict(Diagnostic("UNSUPPORTED_SCHEMA", "$"))]
                                )
                                summary.sources_skipped += 1
                            else:
                                result = parser.parse(context, document)
                                locators: set[str] = set()
                                for record in result.records:
                                    if record.source_locator in locators:
                                        raise ParseError("DUPLICATE_SOURCE_LOCATOR")
                                    locators.add(record.source_locator)
                                    raw = resolve_locator(document, record.source_locator)
                                    if not isinstance(raw, dict) or any(
                                        key not in raw or json_text(raw[key]) != json_text(value)
                                        for key, value in record.payload.items()
                                    ):
                                        raise ParseError("PAYLOAD_NOT_FROM_LOCATOR")
                                    origin = SourceRecord(
                                        id=new_id(),
                                        ingestion_run_id=source.ingestion_run_id,
                                        evidence_file_id=source.evidence_id
                                        if source.member_id is None
                                        else None,
                                        archive_member_id=source.member_id,
                                        location=record.source_locator,
                                        parser_id=parser.parser_id,
                                        parser_version=parser.parser_version,
                                    )
                                    session.add(origin)
                                    session.flush()
                                    session.add(
                                        ParsedRecord(
                                            case_id=source.case_id,
                                            source_record_id=origin.id,
                                            parser_run_id=run.id,
                                            parser_id=parser.parser_id,
                                            parser_version=parser.parser_version,
                                            record_type=record.record_type,
                                            source_locator=record.source_locator,
                                            record_index=record.record_index,
                                            timestamp_raw=None
                                            if record.timestamp_raw is None
                                            else json_text(record.timestamp_raw),
                                            payload_json=json_text(record.payload),
                                            annotations_json=json_text(record.annotations),
                                        )
                                    )
                                session.flush()
                                run.status = "COMPLETED"
                                run.records_parsed = len(result.records)
                                run.warnings_json = json_text(
                                    [asdict(item) for item in result.warnings]
                                )
                    if completed is None:
                        summary.warnings += len(json.loads(run.warnings_json))
                        if run.status == "COMPLETED":
                            summary.sources_supported += 1
                            summary.records_parsed += run.records_parsed
                except Exception as error:
                    run.status = "FAILED"
                    run.records_parsed = 0
                    run.warnings_json = "[]"
                    if isinstance(error, ParseError):
                        run.error_code = str(error)
                    elif isinstance(error, SQLAlchemyError):
                        run.error_code = "PERSISTENCE_ERROR"
                    elif isinstance(error, OSError):
                        run.error_code = "SOURCE_IO_ERROR"
                    elif isinstance(error, EvidenceError):
                        run.error_code = "SOURCE_PATH_OR_INTEGRITY_ERROR"
                    else:
                        run.error_code = "INTERNAL_PARSER_ERROR"
                    summary.errors += 1
                run.finished_at = utc_now()
                try:
                    session.commit()
                except Exception as error:
                    # Closing rolls back an uncommitted transaction, but must
                    # never relabel an acknowledged-or-not durable success.
                    session.close()
                    with Session(engine) as inspection:
                        persisted = inspection.get(ParserRun, attempt_id)
                        if persisted is not None:
                            raise EvidenceError(
                                "Parser commit may already be durable; results preserved; "
                                "manual review required"
                            ) from error
                        inspection.add(
                            ParserRun(
                                id=attempt_id,
                                source_record_id=source.inventory_id,
                                parser_id=parser.parser_id,
                                parser_version=parser.parser_version,
                                status="FAILED",
                                error_code="COMMIT_FAILED",
                                finished_at=utc_now(),
                            )
                        )
                        inspection.commit()
                    summary = before_source
                    summary.errors += 1
        return summary
    finally:
        engine.dispose()
