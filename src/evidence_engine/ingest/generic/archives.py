"""Validate the entire ZIP inventory before controlled, first-level extraction."""

import hashlib
import io
import os
import stat
import struct
import unicodedata
import zipfile
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO

from evidence_engine.config import ZipLimits
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.hashing import CHUNK_SIZE
from evidence_engine.ingest.generic.paths import check_path, sync_directory

MAX_METADATA_BYTES = 32 * 1024 * 1024


class MetadataReader(io.BufferedIOBase):
    """Bound metadata reads and count central entries before ZipInfo allocation."""

    def __init__(self, stream: BinaryIO, max_members: int) -> None:
        self.stream = stream
        self.max_members = max_members
        self.size = stream.seek(0, os.SEEK_END)

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        return self.stream.seek(offset, whence)

    def tell(self) -> int:
        return self.stream.tell()

    def read(self, size: int | None = -1) -> bytes:
        requested = self.size - self.tell() if size is None or size < 0 else size
        if requested > MAX_METADATA_BYTES:
            raise EvidenceError("ZIP metadata size limit exceeded")
        data = self.stream.read(requested)
        # zipfile requests the central directory as one sized block. Its other
        # reads are end records and local headers, never decompressed payloads.
        if size is not None and size >= 0 and data.startswith(b"PK\x01\x02"):
            offset = 0
            count = 0
            while offset < len(data):
                if data[offset : offset + 4] != b"PK\x01\x02" or offset + 46 > len(data):
                    raise EvidenceError("Invalid ZIP central directory")
                count += 1
                if count > self.max_members:
                    raise EvidenceError("ZIP member count limit exceeded")
                lengths = struct.unpack_from("<HHH", data, offset + 28)
                offset += 46 + sum(lengths)
            if offset != len(data):
                raise EvidenceError("Truncated ZIP central directory")
        return data


def member_chunks(
    stream: BinaryIO, archive: zipfile.ZipFile, info: zipfile.ZipInfo
) -> Iterator[bytes]:
    """Decode the full compressed range; never truncate to the declared size.

    ZipExtFile truncates output at file_size. A forged size and prefix CRC can
    therefore appear valid. Use zipfile for header/overlap checks, and bounded
    raw DEFLATE decoding to independently measure all bytes and require EOF.
    """
    with archive.open(info):
        pass
    stream.seek(info.header_offset)
    header = stream.read(30)
    if len(header) != 30 or header[:4] != b"PK\x03\x04":
        raise EvidenceError("Invalid ZIP local header")
    flags, method = struct.unpack_from("<HH", header, 6)
    if flags != info.flag_bits or method != info.compress_type:
        raise EvidenceError("ZIP local and central headers disagree")
    name_size, extra_size = struct.unpack_from("<HH", header, 26)
    stream.seek(info.header_offset + 30 + name_size + extra_size)
    remaining = info.compress_size
    decoder = zlib.decompressobj(-15) if method == zipfile.ZIP_DEFLATED else None
    while remaining:
        raw = stream.read(min(remaining, CHUNK_SIZE))
        if not raw:
            raise EvidenceError("Truncated ZIP compressed data")
        remaining -= len(raw)
        if decoder is None:
            yield raw
            continue
        pending = raw
        while True:
            chunk = decoder.decompress(pending, CHUNK_SIZE)
            pending = decoder.unconsumed_tail
            if decoder.unused_data:
                raise EvidenceError("ZIP contains trailing compressed data")
            if chunk:
                yield chunk
            if not pending and len(chunk) < CHUNK_SIZE:
                break
        if decoder.eof and remaining:
            raise EvidenceError("ZIP compressed size exceeds stream boundary")
    if decoder is not None and not decoder.eof:
        raise EvidenceError("Truncated ZIP DEFLATE stream")


@dataclass(frozen=True)
class ExtractedMember:
    member_path: str
    size_bytes: int
    compressed_size: int
    crc32: int
    sha256: str
    path: Path


def validate_name(info: zipfile.ZipInfo) -> str:
    name = info.orig_filename
    if name != info.filename or not name or "\\" in name:
        raise EvidenceError("ZIP contains an invalid member name")
    try:
        name.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise EvidenceError("ZIP member name is not valid Unicode") from error
    if (
        PurePosixPath(name).is_absolute()
        or PureWindowsPath(name).drive
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
        or unicodedata.normalize("NFC", name) != name
    ):
        raise EvidenceError("ZIP contains an unsafe or noncanonical member name")
    parts = name.removesuffix("/").split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    reserved |= {f"{prefix}{digit}" for prefix in ("COM", "LPT") for digit in "123456789¹²³"}
    for part in parts:
        if (
            part in ("", ".", "..")
            or part.endswith((".", " "))
            # Colon is logical metadata only; extract_zip generates every destination.
            # Absolute paths and leading Windows drive designators are rejected above.
            or any(char in part for char in '<>"|?*')
            or part.split(".")[0].upper() in reserved
        ):
            raise EvidenceError("ZIP contains a nonportable or traversal member name")
    return name.removesuffix("/")


def validated_inventory(archive: zipfile.ZipFile, limits: ZipLimits) -> list[zipfile.ZipInfo]:
    entries = archive.infolist()
    if len(entries) > limits.max_members:
        raise EvidenceError("ZIP member count limit exceeded")
    names: dict[str, bool] = {}
    spellings: dict[str, str] = {}
    total = 0
    for info in entries:
        name = validate_name(info)
        key = name.casefold()
        parts = name.split("/")
        for depth in range(1, len(parts) + 1):
            prefix = "/".join(parts[:depth])
            canonical = prefix.casefold()
            if canonical in spellings and spellings[canonical] != prefix:
                raise EvidenceError("ZIP case-colliding directory or member name")
            spellings[canonical] = prefix
        if key in names:
            raise EvidenceError("ZIP duplicate or case-colliding member name")
        names[key] = info.is_dir()
        mode = info.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise EvidenceError("ZIP links and special files are forbidden")
        if kind == stat.S_IFDIR and not info.is_dir():
            raise EvidenceError("ZIP inconsistent directory metadata")
        if info.flag_bits & 1:
            raise EvidenceError("Encrypted ZIP members are unsupported")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise EvidenceError("Unsupported ZIP compression method")
        if info.compress_type == zipfile.ZIP_STORED and info.compress_size != info.file_size:
            raise EvidenceError("ZIP stored member sizes disagree")
        if info.is_dir() and info.file_size:
            raise EvidenceError("ZIP directory contains unexpected data")
        if info.file_size > limits.max_file_bytes:
            raise EvidenceError("ZIP per-file size limit exceeded")
        total += info.file_size
        if total > limits.max_total_bytes:
            raise EvidenceError("ZIP total size limit exceeded")
        if info.file_size / max(info.compress_size, 1) > limits.max_ratio:
            raise EvidenceError("ZIP compression ratio limit exceeded")
    for name in names:
        for parent in PurePosixPath(name).parents:
            if str(parent) in names and not names[str(parent)]:
                raise EvidenceError("ZIP file/directory name collision")
    return entries


def extract_zip(stream: BinaryIO, destination: Path, limits: ZipLimits) -> list[ExtractedMember]:
    """Destination must be a fresh owned staging directory, never an original path."""
    check_path(destination)
    if destination.exists():
        raise EvidenceError("Extraction destination already exists")
    try:
        with zipfile.ZipFile(MetadataReader(stream, limits.max_members)) as archive:
            entries = validated_inventory(archive, limits)
            destination.mkdir()
            results: list[ExtractedMember] = []
            total = 0
            for index, info in enumerate(entries):
                if info.is_dir():
                    if any(member_chunks(stream, archive, info)) or info.CRC != 0:
                        raise EvidenceError("ZIP directory contains unexpected data")
                    continue
                # Generated names avoid all host-filesystem interpretation of ZIP names.
                target = destination / f"{index:08d}.bin"
                digest = hashlib.sha256()
                size = 0
                crc = 0
                with target.open("xb") as output:
                    for chunk in member_chunks(stream, archive, info):
                        size += len(chunk)
                        total += len(chunk)
                        if size > limits.max_file_bytes or total > limits.max_total_bytes:
                            raise EvidenceError("ZIP actual decompressed size limit exceeded")
                        if size / max(info.compress_size, 1) > limits.max_ratio:
                            raise EvidenceError("ZIP actual compression ratio limit exceeded")
                        if size > info.file_size:
                            raise EvidenceError("ZIP actual size exceeds declared member size")
                        digest.update(chunk)
                        crc = zlib.crc32(chunk, crc)
                        output.write(chunk)
                    if size != info.file_size or crc != info.CRC:
                        raise EvidenceError("ZIP member size or CRC differs from inventory")
                    output.flush()
                    os.fsync(output.fileno())
                results.append(
                    ExtractedMember(
                        info.filename,
                        size,
                        info.compress_size,
                        info.CRC,
                        digest.hexdigest(),
                        target,
                    )
                )
            sync_directory(destination)
            return results
    except (
        zipfile.BadZipFile,
        NotImplementedError,
        UnicodeError,
        RuntimeError,
        zlib.error,
    ) as error:
        raise EvidenceError("Invalid, damaged or unsupported ZIP") from error
