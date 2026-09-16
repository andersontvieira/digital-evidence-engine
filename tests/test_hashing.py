import hashlib
from io import BytesIO
from pathlib import Path

import pytest

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.hashing import original_reader, sha256_file, sha256_stream


def test_known_hash(tmp_path: Path) -> None:
    path = tmp_path / "synthetic-document.txt"
    path.write_bytes(b"abc")
    assert sha256_file(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_streaming_reads_are_bounded() -> None:
    class BoundedStream(BytesIO):
        calls = 0

        def read(self, size: int = -1) -> bytes:
            assert 0 < size <= 4096
            self.calls += 1
            return super().read(size)

    content = b"synthetic" * 100_000
    stream = BoundedStream(content)
    assert sha256_stream(stream, 4096) == (hashlib.sha256(content).hexdigest(), len(content))
    assert stream.calls > 200


def test_empty_file_and_invalid_chunk_size(tmp_path: Path) -> None:
    path = tmp_path / "synthetic-empty"
    path.touch()
    assert sha256_file(path) == hashlib.sha256(b"").hexdigest()
    with pytest.raises(ValueError):
        sha256_stream(BytesIO(), 0)


def test_mutation_during_read_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "synthetic-changing"
    path.write_bytes(b"before")
    with pytest.raises(EvidenceError, match="changed during reading"):
        with original_reader(path) as stream:
            stream.read(1)
            path.write_bytes(b"after-changing-size")
