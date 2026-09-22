"""Validate cataloged physical occurrences, preserving all exact duplicate sources."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

from sqlalchemy import Connection, select

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.hashing import original_reader, sha256_stream
from evidence_engine.ingest.generic.paths import CasePaths, check_path, discover
from evidence_engine.media.signatures import PREFIX_LIMIT, MediaFormat, identify
from evidence_engine.models.entities import ArchiveMember, EvidenceFile
from evidence_engine.query.catalog import read_catalog


@dataclass(frozen=True)
class MediaItem:
    source_kind: Literal["evidence_file", "archive_member"]
    evidence_file_id: str
    archive_member_id: str | None
    evidence_relative_path: str
    member_path: str | None
    size_bytes: int
    cataloged_sha256: str
    media_kind: Literal["image", "video"]
    media_format: MediaFormat
    extension_hint: str | None


@dataclass(frozen=True)
class DuplicateGroup:
    sha256: str
    occurrence_count: int
    occurrences: tuple[MediaItem, ...]


@dataclass(frozen=True)
class MediaInventory:
    scanned_occurrences: int
    recognized_media: int
    verified_media: int
    unrecognized_occurrences: int
    format_counts: dict[str, int]
    kind_counts: dict[str, int]
    exact_duplicate_groups: int
    exact_duplicate_occurrences: int
    items: tuple[MediaItem, ...]
    duplicate_groups: tuple[DuplicateGroup, ...]


def materialized_path(working: Path, stored: str) -> Path:
    relative = PurePosixPath(stored)
    if (
        not stored
        or relative.is_absolute()
        or ".." in relative.parts
        or PureWindowsPath(stored).drive
        or any(c in stored for c in ("\\", ":", "\x00"))
        or relative.as_posix() != stored
    ):
        raise EvidenceError("UNSAFE_CATALOG_MEDIA_PATH")
    path = working.joinpath(*relative.parts)
    check_path(path)
    if not path.resolve().is_relative_to(working):
        raise EvidenceError("UNSAFE_CATALOG_MEDIA_PATH")
    return path


def inventory_media(case_root: Path) -> MediaInventory:
    paths = CasePaths.load(case_root)
    with read_catalog(case_root) as connection:
        return inventory_in_snapshot(paths, connection)


def inventory_in_snapshot(paths: CasePaths, connection: Connection) -> MediaInventory:
    """Existing inventory algorithm within a caller-owned read-only catalog snapshot."""
    originals = {p.relative_to(paths.originals).as_posix(): p for p in discover(paths.originals)}
    items: list[MediaItem] = []
    evidence = (
        connection.execute(
            select(
                EvidenceFile.id,
                EvidenceFile.relative_path,
                EvidenceFile.size_bytes,
                EvidenceFile.sha256,
                EvidenceFile.extension,
            )
        )
        .mappings()
        .all()
    )
    members = (
        connection.execute(
            select(
                ArchiveMember.id,
                ArchiveMember.evidence_file_id,
                ArchiveMember.member_path,
                ArchiveMember.working_relative_path,
                ArchiveMember.size_bytes,
                ArchiveMember.sha256,
                ArchiveMember.extension,
            )
        )
        .mappings()
        .all()
    )
    evidence_by_id = {row["id"]: row for row in evidence}
    # Validate every cataloged occurrence, including unrecognized prefixes, so a changed
    # signature cannot hide previously cataloged media as an apparently harmless unknown.
    for source_kind, rows in (("evidence_file", evidence), ("archive_member", members)):
        for row in rows:
            member = source_kind == "archive_member"
            parent = evidence_by_id.get(row["evidence_file_id"]) if member else row
            if parent is None:
                raise EvidenceError("MEDIA_PROVENANCE_INTEGRITY_ERROR")
            original = originals.get(parent["relative_path"])
            if original is None:
                raise EvidenceError("MISSING_CATALOGED_MEDIA_SOURCE")
            path = (
                materialized_path(paths.working, row["working_relative_path"])
                if member
                else original
            )
            try:
                with original_reader(path) as stream:
                    prefix = stream.read(PREFIX_LIMIT)
                    stream.seek(0)
                    digest, size = sha256_stream(stream)
            except FileNotFoundError:
                raise EvidenceError("MISSING_CATALOGED_MEDIA_SOURCE") from None
            if size != row["size_bytes"] or digest != row["sha256"]:
                raise EvidenceError("MEDIA_SIZE_OR_SHA256_MISMATCH")
            signature = identify(prefix)
            if signature.media_kind is None:
                continue
            items.append(
                MediaItem(
                    "archive_member" if member else "evidence_file",
                    parent["id"],
                    row["id"] if member else None,
                    parent["relative_path"],
                    row["member_path"] if member else None,
                    row["size_bytes"],
                    row["sha256"],
                    signature.media_kind,
                    signature.media_format,
                    row["extension"] or None,
                )
            )
    items.sort(
        key=lambda item: (
            item.source_kind,
            item.evidence_relative_path,
            item.member_path or "",
            item.evidence_file_id,
            item.archive_member_id or "",
        )
    )
    by_hash: dict[str, list[MediaItem]] = defaultdict(list)
    for item in items:
        by_hash[item.cataloged_sha256].append(item)
    groups = [
        DuplicateGroup(digest, len(occurrences), tuple(occurrences))
        for digest, occurrences in by_hash.items()
        if len(occurrences) >= 2
    ]
    groups.sort(key=lambda group: (-group.occurrence_count, group.sha256))
    scanned = len(evidence) + len(members)
    return MediaInventory(
        scanned,
        len(items),
        len(items),
        scanned - len(items),
        dict(sorted(Counter(item.media_format for item in items).items())),
        dict(sorted(Counter(item.media_kind for item in items).items())),
        len(groups),
        sum(group.occurrence_count for group in groups),
        tuple(items),
        tuple(groups),
    )
