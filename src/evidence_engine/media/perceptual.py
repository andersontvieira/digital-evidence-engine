"""Read-only pHash of verified representatives, once per exact content."""

import re
import warnings
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import BinaryIO, Literal

import imagehash
from PIL import Image, ImageOps
from sqlalchemy import Connection, select

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.hashing import original_reader, sha256_stream
from evidence_engine.ingest.generic.paths import CasePaths
from evidence_engine.media.contents import ContentOccurrence, ExactMediaContent, media_contents
from evidence_engine.media.inventory import materialized_path
from evidence_engine.media.signatures import MediaFormat
from evidence_engine.models.entities import ArchiveMember, EvidenceFile
from evidence_engine.query.catalog import read_catalog

ALGORITHM_ID = "image.phash"
ALGORITHM_VERSION = "1.0.0"
type Status = Literal["SUCCESS", "FAILED", "UNSUPPORTED"]
type ErrorCode = Literal[
    "DECODE_ERROR",
    "FORMAT_MISMATCH",
    "INVALID_EXIF_ORIENTATION",
    "DECOMPRESSION_BOMB",
    "ANIMATED_IMAGE_UNSUPPORTED",
    "UNSUPPORTED_FORMAT",
    "NORMALIZATION_ERROR",
]


@dataclass(frozen=True)
class PerceptualPolicy:
    algorithm_id: str = ALGORITHM_ID
    algorithm_version: str = ALGORITHM_VERSION
    hash_size: int = 8
    highfreq_factor: int = 4
    hash_bits: int = 64
    exif_orientation: bool = True
    alpha_background_rgb: tuple[int, int, int] = (255, 255, 255)
    icc_transform: str = "none"
    supported_formats: tuple[str, ...] = ("jpeg", "png")
    pillow_version: str = version("Pillow")
    imagehash_version: str = version("ImageHash")
    numpy_version: str = version("numpy")
    scipy_version: str = version("scipy")


@dataclass(frozen=True)
class DecodedHash:
    status: Status
    width: int | None = None
    height: int | None = None
    phash_hex: str | None = None
    error_code: ErrorCode | None = None


@dataclass(frozen=True)
class PerceptualItem:
    content_sha256: str
    media_kind: Literal["image", "video"]
    media_format: MediaFormat
    size_bytes: int
    occurrence_count: int
    representative: ContentOccurrence
    occurrences: tuple[ContentOccurrence, ...]
    status: Status
    width: int | None
    height: int | None
    algorithm_id: str
    algorithm_version: str
    phash_hex: str | None
    error_code: ErrorCode | None
    feature_class: Literal["DERIVED"] = "DERIVED"


@dataclass(frozen=True)
class PerceptualInventory:
    policy: PerceptualPolicy
    exact_content_count: int
    success_count: int
    failed_count: int
    unsupported_count: int
    projected_occurrences: int
    items: tuple[PerceptualItem, ...]


def normalize_rgb(image: Image.Image) -> Image.Image:
    """Compose transparency on white without ICC transforms; return owned RGB pixels."""
    if "A" in image.getbands() or "transparency" in image.info:
        with image.convert("RGBA") as rgba:
            with Image.new("RGBA", rgba.size, (255, 255, 255, 255)) as background:
                with Image.alpha_composite(background, rgba) as composed:
                    return composed.convert("RGB")
    return image.convert("RGB")


def decode_hash(stream: BinaryIO, media_format: MediaFormat) -> DecodedHash:
    """Decode errors stay local; callers keep the stable Foundation reader open."""
    if media_format not in ("jpeg", "png"):
        return DecodedHash("UNSUPPORTED", error_code="UNSUPPORTED_FORMAT")
    phase: ErrorCode = "DECODE_ERROR"
    try:
        # Record unrelated library warnings instead of leaking embedded metadata/paths.
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream) as image:
                if image.format != {"jpeg": "JPEG", "png": "PNG"}[media_format]:
                    return DecodedHash("FAILED", error_code="FORMAT_MISMATCH")
                if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1:
                    return DecodedHash("UNSUPPORTED", error_code="ANIMATED_IMAGE_UNSUPPORTED")
                image.load()
                phase = "INVALID_EXIF_ORIENTATION"
                warning_count = len(recorded)
                orientation = image.getexif().get(274, 1)
                if (
                    len(recorded) != warning_count
                    or type(orientation) is not int
                    or orientation not in range(1, 9)
                ):
                    return DecodedHash("FAILED", error_code=phase)
                with ImageOps.exif_transpose(image) as oriented:
                    phase = "NORMALIZATION_ERROR"
                    with normalize_rgb(oriented) as normalized:
                        digest = str(imagehash.phash(normalized, hash_size=8, highfreq_factor=4))
                        if re.fullmatch(r"[0-9a-f]{16}", digest) is None:
                            raise EvidenceError("INVALID_PHASH_REPRESENTATION")
                        return DecodedHash("SUCCESS", oriented.width, oriented.height, digest)
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        return DecodedHash("FAILED", error_code="DECOMPRESSION_BOMB")
    except (OSError, ValueError, SyntaxError, TypeError, KeyError, OverflowError) as error:
        if isinstance(error, OSError) and error.errno is not None:
            raise
        return DecodedHash("FAILED", error_code=phase)


def representative_path(
    connection: Connection,
    paths: CasePaths,
    content: ExactMediaContent,
) -> Path:
    """Resolve the persisted occurrence using Foundation confinement and provenance."""
    representative = content.representative
    evidence = (
        connection.execute(
            select(EvidenceFile.__table__).where(EvidenceFile.id == representative.evidence_file_id)
        )
        .mappings()
        .one_or_none()
    )
    if evidence is None or evidence["relative_path"] != representative.evidence_relative_path:
        raise EvidenceError("PERCEPTUAL_PROVENANCE_MISMATCH")
    if representative.source_kind == "evidence_file":
        if representative.archive_member_id is not None or representative.member_path is not None:
            raise EvidenceError("PERCEPTUAL_PROVENANCE_MISMATCH")
        row = evidence
        path = materialized_path(paths.originals, row["relative_path"])
    else:
        member = (
            connection.execute(
                select(ArchiveMember.__table__).where(
                    ArchiveMember.id == representative.archive_member_id
                )
            )
            .mappings()
            .one_or_none()
        )
        if member is None or (member["evidence_file_id"], member["member_path"]) != (
            representative.evidence_file_id,
            representative.member_path,
        ):
            raise EvidenceError("PERCEPTUAL_PROVENANCE_MISMATCH")
        row = member
        path = materialized_path(paths.working, row["working_relative_path"])
    if (row["sha256"], row["size_bytes"]) != (content.content_sha256, content.size_bytes):
        raise EvidenceError("PERCEPTUAL_CATALOG_BASELINE_CHANGED")
    return path


def perceptual_hashes(case_root: Path) -> PerceptualInventory:
    contents = media_contents(case_root)
    paths = CasePaths.load(case_root)
    items = []
    with read_catalog(case_root) as connection:
        for content in contents.contents:
            if content.media_kind != "image" or content.media_format not in ("jpeg", "png"):
                decoded = DecodedHash("UNSUPPORTED", error_code="UNSUPPORTED_FORMAT")
            else:
                path = representative_path(connection, paths, content)
                with original_reader(path) as stream:
                    digest, size = sha256_stream(stream)
                    if (digest, size) != (content.content_sha256, content.size_bytes):
                        raise EvidenceError("PERCEPTUAL_SIZE_OR_SHA256_MISMATCH")
                    stream.seek(0)
                    decoded = decode_hash(stream, content.media_format)
                    # Reader stability is checked even after a controlled decode failure.
            items.append(
                PerceptualItem(
                    content.content_sha256,
                    content.media_kind,
                    content.media_format,
                    content.size_bytes,
                    content.occurrence_count,
                    content.representative,
                    content.occurrences,
                    decoded.status,
                    decoded.width,
                    decoded.height,
                    ALGORITHM_ID,
                    ALGORITHM_VERSION,
                    decoded.phash_hex,
                    decoded.error_code,
                )
            )
    return PerceptualInventory(
        PerceptualPolicy(),
        len(items),
        sum(i.status == "SUCCESS" for i in items),
        sum(i.status == "FAILED" for i in items),
        sum(i.status == "UNSUPPORTED" for i in items),
        sum(i.occurrence_count for i in items),
        tuple(items),
    )
