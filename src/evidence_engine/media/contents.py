"""Exact content projection of verified 5A occurrences; no additional byte access."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from evidence_engine.errors import EvidenceError
from evidence_engine.media.inventory import MediaItem, inventory_media
from evidence_engine.media.signatures import MediaFormat


@dataclass(frozen=True)
class ContentOccurrence:
    source_kind: Literal["evidence_file", "archive_member"]
    evidence_file_id: str
    archive_member_id: str | None
    evidence_relative_path: str
    member_path: str | None


@dataclass(frozen=True)
class ExactMediaContent:
    content_sha256: str
    media_kind: Literal["image", "video"]
    media_format: MediaFormat
    size_bytes: int
    occurrence_count: int
    representative: ContentOccurrence
    occurrences: tuple[ContentOccurrence, ...]


@dataclass(frozen=True)
class MediaContentSet:
    verified_media_occurrences: int
    exact_content_count: int
    singleton_content_count: int
    duplicate_content_count: int
    occurrences_in_duplicate_contents: int
    format_counts_by_content: dict[str, int]
    kind_counts_by_content: dict[str, int]
    contents: tuple[ExactMediaContent, ...]


def project_contents(items: tuple[MediaItem, ...]) -> MediaContentSet:
    """Project already verified inventory items; representative has no evidentiary priority."""
    by_hash: dict[str, list[MediaItem]] = defaultdict(list)
    for item in items:
        by_hash[item.cataloged_sha256].append(item)
    contents = []
    for digest, members in by_hash.items():
        first = members[0]
        if any(
            (item.media_kind, item.media_format, item.size_bytes)
            != (first.media_kind, first.media_format, first.size_bytes)
            for item in members
        ):
            raise EvidenceError("INCONSISTENT_EXACT_MEDIA_CONTENT")
        members.sort(
            key=lambda item: (
                item.source_kind,
                item.evidence_relative_path,
                item.member_path or "",
                item.evidence_file_id,
                item.archive_member_id or "",
            )
        )
        occurrences = tuple(
            ContentOccurrence(
                item.source_kind,
                item.evidence_file_id,
                item.archive_member_id,
                item.evidence_relative_path,
                item.member_path,
            )
            for item in members
        )
        contents.append(
            ExactMediaContent(
                digest,
                first.media_kind,
                first.media_format,
                first.size_bytes,
                len(occurrences),
                occurrences[0],
                occurrences,
            )
        )
    contents.sort(
        key=lambda content: (content.media_kind, content.media_format, content.content_sha256)
    )
    singleton_count = sum(content.occurrence_count == 1 for content in contents)
    return MediaContentSet(
        len(items),
        len(contents),
        singleton_count,
        len(contents) - singleton_count,
        sum(content.occurrence_count for content in contents if content.occurrence_count >= 2),
        dict(sorted(Counter(content.media_format for content in contents).items())),
        dict(sorted(Counter(content.media_kind for content in contents).items())),
        tuple(contents),
    )


def media_contents(case_root: Path) -> MediaContentSet:
    return project_contents(inventory_media(case_root).items)
