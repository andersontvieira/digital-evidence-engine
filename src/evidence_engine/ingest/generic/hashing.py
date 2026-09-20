"""Streaming SHA-256 and read-only opening with mutation detection."""

import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.paths import check_path

CHUNK_SIZE = 1024 * 1024
_WINDOWS = os.name == "nt"


def file_identity(info: os.stat_result) -> tuple[int, int, int]:
    """Object identity shared by path stat and handle fstat, including file type."""
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))


def read_stability(info: os.stat_result) -> tuple[int, ...]:
    """Windows ctime/creation time is not a portable mutation invariant (ADR 0027)."""
    content = (info.st_size, info.st_mtime_ns)
    return content if _WINDOWS else (*content, info.st_ctime_ns)


def _unchanged(before: os.stat_result, after: os.stat_result) -> bool:
    return file_identity(before) == file_identity(after) and read_stability(
        before
    ) == read_stability(after)


@contextmanager
def original_reader(path: Path) -> Iterator[BinaryIO]:
    check_path(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise EvidenceError("Only regular files can be read as evidence")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not _unchanged(before, opened):
            raise EvidenceError("Original changed while being opened")
        yield stream
        check_path(path)
        if not _unchanged(opened, os.fstat(stream.fileno())) or not _unchanged(before, path.stat()):
            raise EvidenceError("Original changed during reading")


def sha256_stream(stream: BinaryIO, chunk_size: int = CHUNK_SIZE) -> tuple[str, int]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(chunk_size):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def sha256_file(path: Path) -> str:
    with original_reader(path) as stream:
        digest, _ = sha256_stream(stream)
    return digest
