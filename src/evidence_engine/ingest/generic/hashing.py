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


def fingerprint(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


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
        if fingerprint(before) != fingerprint(os.fstat(stream.fileno())):
            raise EvidenceError("Original changed while being opened")
        yield stream
        check_path(path)
        if fingerprint(before) != fingerprint(os.fstat(stream.fileno())) or fingerprint(
            before
        ) != fingerprint(path.stat()):
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
