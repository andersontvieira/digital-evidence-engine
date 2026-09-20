"""Synthetic identity/stability policy and filesystem regressions for both platforms."""

import os
import stat
from types import SimpleNamespace

import pytest

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic import hashing
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.media.inventory import inventory_media


def info(**changes):
    fields = dict(
        st_dev=7,
        st_ino=11,
        st_mode=stat.S_IFREG | 0o600,
        st_size=8,
        st_mtime_ns=100,
        st_ctime_ns=200,
    )
    fields.update(changes)
    return SimpleNamespace(**fields)


@pytest.mark.parametrize("windows", [False, True])
def test_unchanged_identity_and_stability(monkeypatch, windows):
    monkeypatch.setattr(hashing, "_WINDOWS", windows)
    assert hashing.file_identity(info()) == (7, 11, stat.S_IFREG)
    assert hashing._unchanged(info(), info())
    assert hashing.read_stability(info()) == ((8, 100) if windows else (8, 100, 200))


@pytest.mark.parametrize("windows", [False, True])
def test_ctime_policy_explicit(monkeypatch, windows):
    monkeypatch.setattr(hashing, "_WINDOWS", windows)
    assert hashing._unchanged(info(), info(st_ctime_ns=999)) is windows


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize(
    "changes",
    [
        {"st_dev": 8},
        {"st_ino": 12},
        {"st_mode": stat.S_IFDIR | 0o600},
        {"st_size": 9},
        {"st_mtime_ns": 101},
    ],
)
def test_identity_and_content_changes_rejected(monkeypatch, windows, changes):
    monkeypatch.setattr(hashing, "_WINDOWS", windows)
    assert not hashing._unchanged(info(), info(**changes))


def test_birthtime_not_required_or_used(monkeypatch):
    monkeypatch.setattr(hashing, "_WINDOWS", True)
    assert hashing._unchanged(info(), info(st_birthtime_ns=900, st_birthtime=0.0000009))


@pytest.mark.parametrize("windows", [False, True])
def test_reader_ctime_change_after_read(monkeypatch, tmp_path, windows):
    monkeypatch.setattr(hashing, "_WINDOWS", windows)
    path = tmp_path / "synthetic-read.bin"
    path.write_bytes(b"synthetic")
    actual = os.fstat
    calls = 0

    def changed(fd):
        nonlocal calls
        calls += 1
        result = actual(fd)
        return info(
            st_dev=result.st_dev,
            st_ino=result.st_ino,
            st_mode=result.st_mode,
            st_size=result.st_size,
            st_mtime_ns=result.st_mtime_ns,
            st_ctime_ns=path.stat().st_ctime_ns + (1 if calls > 1 else 0),
        )

    monkeypatch.setattr(hashing.os, "fstat", changed)
    if windows:
        with hashing.original_reader(path) as stream:
            assert stream.read() == b"synthetic"
    else:
        with pytest.raises(EvidenceError, match="changed during reading"):
            with hashing.original_reader(path) as stream:
                stream.read()


def test_windows_path_handle_ctime_difference_allowed(monkeypatch, tmp_path):
    monkeypatch.setattr(hashing, "_WINDOWS", True)
    path = tmp_path / "synthetic-open.bin"
    path.write_bytes(b"synthetic")
    actual = os.fstat

    def changed(fd):
        result = actual(fd)
        return info(
            st_dev=result.st_dev,
            st_ino=result.st_ino,
            st_mode=result.st_mode,
            st_size=result.st_size,
            st_mtime_ns=result.st_mtime_ns,
            st_ctime_ns=1,
        )

    monkeypatch.setattr(hashing.os, "fstat", changed)
    assert hashing.sha256_file(path)


@pytest.mark.parametrize("stage", ["open", "final"])
def test_path_handle_replacement_detected(monkeypatch, tmp_path, stage):
    path = tmp_path / "synthetic-original.bin"
    path.write_bytes(b"synthetic")
    actual = os.fstat
    calls = 0

    def changed(fd):
        nonlocal calls
        calls += 1
        result = actual(fd)
        replace_now = stage == "open" or calls > 1
        return info(
            st_dev=result.st_dev,
            st_ino=result.st_ino + int(replace_now),
            st_mode=result.st_mode,
            st_size=result.st_size,
            st_mtime_ns=result.st_mtime_ns,
            st_ctime_ns=result.st_ctime_ns,
        )

    monkeypatch.setattr(hashing.os, "fstat", changed)
    with pytest.raises(EvidenceError, match="changed"):
        hashing.sha256_file(path)


def test_actual_replacement_between_validation_and_open(monkeypatch, tmp_path):
    path = tmp_path / "synthetic-original.bin"
    replacement = tmp_path / "synthetic-replacement.bin"
    path.write_bytes(b"same size")
    replacement.write_bytes(b"different")
    actual_open = os.open

    def replace_then_open(name, flags, *args, **kwargs):
        replacement.replace(path)
        return actual_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(hashing.os, "open", replace_then_open)
    with pytest.raises(EvidenceError, match="changed while being opened"):
        hashing.sha256_file(path)


def test_final_path_substitution_detected(monkeypatch, tmp_path):
    from pathlib import Path

    path = tmp_path / "synthetic-original.bin"
    replacement = tmp_path / "synthetic-replacement.bin"
    path.write_bytes(b"synthetic")
    replacement.write_bytes(b"synthetic")
    actual_stat = Path.stat
    with pytest.raises(EvidenceError, match="changed during reading"):
        with hashing.original_reader(path) as stream:
            stream.read()
            # Model path replacement when Windows sharing modes prohibit unlinking an open file.
            monkeypatch.setattr(
                Path,
                "stat",
                lambda self, *a, **kw: actual_stat(replacement if self == path else self, *a, **kw),
            )


@pytest.mark.parametrize("mutation", ["same_size", "size", "missing", "replacement"])
def test_cataloged_integrity_still_fails(case_root, mutation):
    path = case_root / "originals/synthetic-image.jpg"
    original = b"\xff\xd8\xffsynthetic"
    path.write_bytes(original)
    ingest(case_root)
    before = (case_root / "database/evidence.db").read_bytes()
    if mutation == "missing":
        path.unlink()
    elif mutation == "replacement":
        replacement = case_root / "originals/synthetic-new.bin"
        replacement.write_bytes(original[:-1] + b"!")
        replacement.replace(path)
    else:
        path.write_bytes(original[:-1] + b"!" if mutation == "same_size" else original + b"!")
    with pytest.raises(EvidenceError, match="MISMATCH|MISSING"):
        inventory_media(case_root)
    assert (case_root / "database/evidence.db").read_bytes() == before


def test_removed_after_open_detected(monkeypatch, tmp_path):
    from pathlib import Path

    path = tmp_path / "synthetic-removed.bin"
    path.write_bytes(b"synthetic")
    actual_stat = Path.stat

    def missing(self, *args, **kwargs):
        if self == path:
            raise FileNotFoundError("synthetic removal")
        return actual_stat(self, *args, **kwargs)

    with pytest.raises(FileNotFoundError):
        with hashing.original_reader(path) as stream:
            stream.read()
            monkeypatch.setattr(Path, "stat", missing)
