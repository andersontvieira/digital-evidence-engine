"""Exact source references from persisted parser contracts; no action inference."""

import re
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, cast

from sqlalchemy import Connection, select

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.archives import validate_name
from evidence_engine.ingest.generic.hashing import original_reader, sha256_stream
from evidence_engine.ingest.generic.paths import CasePaths, discover
from evidence_engine.ingest.parsing.framework import ParseError, child_locator, strict_json
from evidence_engine.media.contents import ExactMediaContent, project_contents
from evidence_engine.media.inventory import inventory_in_snapshot
from evidence_engine.models.entities import ArchiveMember, EvidenceFile, ParsedRecord
from evidence_engine.query.catalog import read_catalog, validate_limit
from evidence_engine.query.policy import POLICY_ID as CURRENT_POLICY_ID
from evidence_engine.query.policy import POLICY_VERSION as CURRENT_POLICY_VERSION
from evidence_engine.query.provenance import record_origin
from evidence_engine.query.search import Projection
from evidence_engine.query.timeline import timeline_in_snapshot, utc_bound

POLICY_ID = "source_media.provenance_link"
POLICY_VERSION = "1.0.0"
LIMITATIONS = (
    "SOURCE_REFERENCE_DOES_NOT_ESTABLISH_ACTION_SEMANTICS",
    "NO_IDENTITY_AUTHORSHIP_SESSION_OR_CAUSALITY",
    "EXACT_MEMBER_PATH_EQUALITY_ONLY",
    "EXACT_MEDIA_CONTENT_LIMITED_TO_CURRENT_MEDIA_POLICY",
    "ABSENCE_LIMITED_TO_CATALOG_AND_QUERY_SCOPE",
    "NO_MESSAGE_ATTACHMENT_INFERENCE",
)


@dataclass(frozen=True)
class SourceMediaReference:
    parsed_record_id: str
    platform: str
    parser_id: str
    parser_version: str
    source_field_locator: str
    reference_value: str
    classification: str = "OBSERVED"


@dataclass(frozen=True)
class ParsedMediaSource:
    id: str
    parser_id: str
    parser_version: str
    record_type: str
    source_locator: str
    payload_json: str


def extract_meta_references(record: ParsedMediaSource) -> tuple[SourceMediaReference, ...] | None:
    """None means no approved adapter; an empty tuple means no contracted reference.

    Only the 1.1.0 array item's named Mídia/media list is contracted. Other URI
    fields, legacy object shapes and annotations are never searched as fallback.
    """
    if (record.parser_id, record.parser_version, record.record_type) != (
        "meta.recently_deleted_content",
        "1.1.0",
        "recently_deleted_content",
    ):
        return None
    try:
        payload = strict_json(record.payload_json.encode("utf-8"))
    except (ParseError, UnicodeError) as error:
        raise EvidenceError("INVALID_SOURCE_MEDIA_PAYLOAD") from error
    if not isinstance(payload, dict):
        raise EvidenceError("INVALID_SOURCE_MEDIA_PAYLOAD")
    entries = payload.get("label_values")
    if entries is None:
        return ()
    if not isinstance(entries, list) or not re.fullmatch(
        r"\$/(?:0|[1-9][0-9]*)", record.source_locator
    ):
        raise EvidenceError("INVALID_SOURCE_MEDIA_STRUCTURE")
    references = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or entry.get("label") not in ("Mídia", "M\u00c3\u00addia"):
            continue
        media = entry.get("media", [])
        if not isinstance(media, list):
            raise EvidenceError("INVALID_SOURCE_MEDIA_STRUCTURE")
        parent = child_locator(child_locator(record.source_locator, "label_values"), index)
        for ordinal, item in enumerate(media):
            if not isinstance(item, dict):
                raise EvidenceError("INVALID_SOURCE_MEDIA_STRUCTURE")
            value = item.get("uri")
            if value is None or value == "":
                continue
            if not isinstance(value, str):
                raise EvidenceError("INVALID_SOURCE_MEDIA_REFERENCE")
            locator = child_locator(child_locator(child_locator(parent, "media"), ordinal), "uri")
            references.append(
                SourceMediaReference(
                    record.id, "meta", record.parser_id, record.parser_version, locator, value
                )
            )
    return tuple(sorted(references, key=lambda r: (r.source_field_locator, r.reference_value)))


@dataclass(frozen=True)
class CatalogMember:
    id: str
    evidence_file_id: str
    member_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class CatalogContainer:
    id: str
    relative_path: str
    size_bytes: int
    sha256: str
    is_archive: bool


def resolve_member(
    connection: Connection, evidence_id: str, reference: str
) -> CatalogMember | None:
    # Equality in SQLite's BINARY collation, never a filesystem/path operation.
    rows = (
        connection.execute(
            select(
                ArchiveMember.id,
                ArchiveMember.evidence_file_id,
                ArchiveMember.member_path,
                ArchiveMember.size_bytes,
                ArchiveMember.sha256,
            ).where(
                ArchiveMember.evidence_file_id == evidence_id,
                ArchiveMember.member_path.collate("BINARY") == reference,
            )
        )
        .mappings()
        .all()
    )
    if len(rows) > 1:
        raise EvidenceError("SOURCE_MEDIA_CATALOG_MEMBER_CARDINALITY")
    return CatalogMember(**rows[0]) if rows else None


def verify_member(path: Path, container: CatalogContainer, member: CatalogMember) -> None:
    """Verify the exact ZIP entry and the original container on one stable handle."""
    name = member.member_path
    try:
        # Foundation validates logical ZIP identity, including safe colons (ADR 0014).
        # Its directory-suffix projection must not change a cataloged file identity.
        if validate_name(zipfile.ZipInfo(name)) != name:
            raise EvidenceError("Non-file logical member identity")
    except (EvidenceError, ValueError) as error:
        raise EvidenceError("UNSAFE_CATALOG_MEDIA_MEMBER_PATH") from error
    if not container.is_archive or member.evidence_file_id != container.id:
        raise EvidenceError("SOURCE_MEDIA_CONTAINER_INTEGRITY_ERROR")
    try:
        with original_reader(path) as stream:
            with zipfile.ZipFile(stream) as archive:
                matches = [i for i in archive.infolist() if i.filename == name]
                if len(matches) != 1:
                    raise EvidenceError("SOURCE_MEDIA_ZIP_MEMBER_CARDINALITY")
                info = matches[0]
                if validate_name(info) != name:
                    raise EvidenceError("UNSAFE_CATALOG_MEDIA_MEMBER_PATH")
                if info.is_dir() or info.file_size != member.size_bytes:
                    raise EvidenceError("CATALOG_MEMBER_INTEGRITY_MISMATCH")
                with archive.open(info) as source:
                    digest, size = sha256_stream(cast(BinaryIO, source))
                if (digest, size) != (member.sha256, member.size_bytes):
                    raise EvidenceError("CATALOG_MEMBER_INTEGRITY_MISMATCH")
            stream.seek(0)
            digest, size = sha256_stream(stream)
            if (digest, size) != (container.sha256, container.size_bytes):
                raise EvidenceError("SOURCE_MEDIA_CONTAINER_INTEGRITY_MISMATCH")
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, ValueError) as error:
        raise EvidenceError("SOURCE_MEDIA_ZIP_READ_ERROR") from error


def content_projection(
    member: CatalogMember, contents: tuple[ExactMediaContent, ...]
) -> Projection:
    matches = [
        c
        for c in contents
        if any(
            o.source_kind == "archive_member"
            and o.archive_member_id == member.id
            and o.evidence_file_id == member.evidence_file_id
            and o.member_path == member.member_path
            for o in c.occurrences
        )
    ]
    if len(matches) > 1:
        raise EvidenceError("SOURCE_MEDIA_CONTENT_CARDINALITY")
    result: Projection = {
        "classification": "DERIVED",
        "status": "LINK_ARCHIVE_MEMBER_ONLY",
        "archive_member_id": member.id,
        "evidence_file_id": member.evidence_file_id,
        "member_path": member.member_path,
        "size_bytes": member.size_bytes,
        "archive_member_sha256": member.sha256,
        "bytes_verified": True,
        "exact_media_content": None,
    }
    if matches:
        content = matches[0]
        if (content.content_sha256, content.size_bytes) != (member.sha256, member.size_bytes):
            raise EvidenceError("SOURCE_MEDIA_CONTENT_INTEGRITY_MISMATCH")
        result["status"] = "LINK_EXACT_MEDIA_CONTENT"
        result["exact_media_content"] = asdict(content)
    return result


def query_source_links(
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
    if start_utc is None or end_utc is None or start_utc >= end_utc:
        raise EvidenceError("Source media links require start before end in UTC")
    paths = CasePaths.load(case_root)
    with read_catalog(case_root) as connection:
        timeline = timeline_in_snapshot(
            connection,
            start_utc=start_utc,
            end_utc=end_utc,
            platform=platform,
            event_kind=event_kind,
            limit=None,
        )
        items: list[Projection] = []
        members: dict[str, CatalogMember] = {}
        containers: dict[str, CatalogContainer] = {}
        for event in timeline.items:
            row = (
                connection.execute(
                    select(
                        ParsedRecord.id,
                        ParsedRecord.parser_id,
                        ParsedRecord.parser_version,
                        ParsedRecord.record_type,
                        ParsedRecord.source_locator,
                        ParsedRecord.payload_json,
                    ).where(ParsedRecord.id == event.parsed_record_id)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise EvidenceError("SOURCE_MEDIA_RECORD_INTEGRITY_ERROR")
            references = extract_meta_references(ParsedMediaSource(**row))
            origin = record_origin(connection, event.parsed_record_id)
            for reference in references or (None,):
                resolution: Projection = {
                    "classification": "DERIVED",
                    "status": (
                        "UNSUPPORTED_SOURCE_REFERENCE_TYPE"
                        if references is None
                        else "NO_SOURCE_MEDIA_REFERENCE"
                        if reference is None
                        else "NO_CATALOG_MEMBER_MATCH"
                    ),
                }
                if reference is not None:
                    if event.platform != reference.platform:
                        raise EvidenceError("SOURCE_MEDIA_PLATFORM_INTEGRITY_ERROR")
                    member = resolve_member(
                        connection, origin["evidence_file_id"], reference.reference_value
                    )
                    if member is not None:
                        members[member.id] = member
                        parent = (
                            connection.execute(
                                select(
                                    EvidenceFile.id,
                                    EvidenceFile.relative_path,
                                    EvidenceFile.size_bytes,
                                    EvidenceFile.sha256,
                                    EvidenceFile.is_archive,
                                ).where(EvidenceFile.id == member.evidence_file_id)
                            )
                            .mappings()
                            .one_or_none()
                        )
                        if parent is None:
                            raise EvidenceError("SOURCE_MEDIA_CONTAINER_INTEGRITY_ERROR")
                        containers[member.evidence_file_id] = CatalogContainer(**parent)
                        resolution["archive_member_id"] = member.id
                items.append(
                    {
                        "event": asdict(event),
                        "source_reference": asdict(reference) if reference else None,
                        "provenance": origin,
                        "resolution": resolution,
                        "limitations": list(LIMITATIONS),
                    }
                )
        if members:
            originals = {
                p.relative_to(paths.originals).as_posix(): p for p in discover(paths.originals)
            }
            for member in members.values():
                container = containers[member.evidence_file_id]
                path = originals.get(container.relative_path)
                if path is None:
                    raise EvidenceError("MISSING_SOURCE_MEDIA_CONTAINER")
                verify_member(path, container, member)
            # Reuse the existing scanner and exact-content algorithm within THIS read snapshot.
            contents = project_contents(inventory_in_snapshot(paths, connection).items).contents
            for item in items:
                if "archive_member_id" in item["resolution"]:
                    item["resolution"] = content_projection(
                        members[item["resolution"]["archive_member_id"]], contents
                    )
        counts = dict(sorted(Counter(i["resolution"]["status"] for i in items).items()))
        return {
            "policy": {
                "policy_id": POLICY_ID,
                "policy_version": POLICY_VERSION,
                "feature_class": "DERIVED",
                "relation_kind": "source_media.exact_provenance_link",
                "current_event_policy_id": CURRENT_POLICY_ID,
                "current_event_policy_version": CURRENT_POLICY_VERSION,
            },
            "scope": {
                "start": start_utc,
                "end": end_utc,
                "platform": platform,
                "event_kind": event_kind,
                "limit": limit,
            },
            "consistency": {
                "database_consistency": "single_read_snapshot",
                "database_scope": "events_references_provenance_members_and_media_inventory",
                "filesystem_consistency": "verified_stable_reads",
                "atomic_database_filesystem": False,
                "exact_media_contents_consulted": bool(members),
            },
            "summary": {
                "unit": "event_source_reference_items",
                "eligible_events": timeline.matched_total,
                "source_references": sum(i["source_reference"] is not None for i in items),
                "undated_current_events": timeline.undated_current_events,
                "matched_total": len(items),
                "returned": min(limit, len(items)),
                "truncated": len(items) > limit,
                "status_counts_scope": "all_matched_items",
                "status_counts": counts,
            },
            "items": items[:limit],
        }
