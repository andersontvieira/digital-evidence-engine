"""Bounded signature hints, not validation of a complete image bitstream."""

from dataclasses import dataclass
from typing import Literal

PREFIX_LIMIT = 4096
type MediaFormat = Literal[
    "jpeg", "png", "gif", "webp", "heif", "heic", "avif", "iso-bmff", "unknown"
]


@dataclass(frozen=True)
class Signature:
    media_kind: Literal["image", "video"] | None
    media_format: MediaFormat


UNKNOWN = Signature(None, "unknown")
UNSUPPORTED_BMFF = Signature(None, "iso-bmff")


def identify(prefix: bytes) -> Signature:
    data = prefix[:PREFIX_LIMIT]
    if data.startswith(b"\xff\xd8\xff"):
        return Signature("image", "jpeg")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return Signature("image", "png")
    if data.startswith((b"GIF87a", b"GIF89a")):
        return Signature("image", "gif")
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        size = int.from_bytes(data[4:8], "little")
        return Signature("image", "webp") if size >= 4 and size % 2 == 0 else UNKNOWN
    # Only a complete, bounded ftyp box, optionally after free/skip/wide padding.
    offset = 0
    for _ in range(16):
        if len(data) - offset < 8:
            return UNKNOWN
        size = int.from_bytes(data[offset : offset + 4], "big")
        box_type = data[offset + 4 : offset + 8]
        header = 8
        if size == 1:
            if len(data) - offset < 16:
                return UNKNOWN
            size = int.from_bytes(data[offset + 8 : offset + 16], "big")
            header = 16
        if size < header or size > len(data) - offset:
            return UNKNOWN
        if box_type == b"ftyp":
            payload = data[offset + header : offset + size]
            if len(payload) < 8 or (len(payload) - 8) % 4:
                return UNKNOWN
            brands = {payload[:4], *(payload[i : i + 4] for i in range(8, len(payload), 4))}
            avif = bool(brands & {b"avif", b"avis"})
            heic = bool(brands & {b"heic", b"heix", b"hevc", b"hevx"})
            # Mixed codec families or non-image major brands stay unsupported.
            if (
                avif
                and heic
                or payload[:4]
                not in {
                    b"avif",
                    b"avis",
                    b"heic",
                    b"heix",
                    b"hevc",
                    b"hevx",
                    b"mif1",
                    b"msf1",
                }
            ):
                return UNSUPPORTED_BMFF
            if avif:
                return Signature("image", "avif")
            if heic:
                return Signature("image", "heic")
            return Signature("image", "heif")
        if box_type not in {b"free", b"skip", b"wide"}:
            return UNKNOWN
        offset += size
    return UNKNOWN
