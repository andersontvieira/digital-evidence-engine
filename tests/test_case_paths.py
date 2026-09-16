import os
from pathlib import Path

import pytest

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.paths import CasePaths
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.reports.manifest import write_manifest


def symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError:
        pytest.skip("Host does not permit creating test symlinks")


def test_missing_originals_never_created(tmp_path: Path) -> None:
    with pytest.raises(EvidenceError, match="originals"):
        ingest(tmp_path)
    assert not (tmp_path / "originals").exists()
    assert not (tmp_path / "database").exists()


def test_case_inside_git_rejected(case_root: Path) -> None:
    (case_root.parent / ".git").mkdir()
    with pytest.raises(EvidenceError, match="Git"):
        ingest(case_root)


def test_original_symlink_rejected(case_root: Path) -> None:
    target = case_root.parent / "synthetic-external.txt"
    target.write_bytes(b"synthetic")
    symlink_or_skip(case_root / "originals/synthetic-link", target)
    with pytest.raises(EvidenceError, match="Links"):
        ingest(case_root)
    assert target.read_bytes() == b"synthetic"


def test_working_alias_to_originals_rejected_before_write(case_root: Path) -> None:
    symlink_or_skip(case_root / "working", case_root / "originals", directory=True)
    with pytest.raises(EvidenceError, match="Links"):
        ingest(case_root)
    assert list((case_root / "originals").iterdir()) == []


def test_hardlink_original_rejected(case_root: Path) -> None:
    path = case_root / "originals/synthetic-document"
    path.write_bytes(b"synthetic")
    os.link(path, case_root / "synthetic-hardlink")
    with pytest.raises(EvidenceError, match="Hard-linked"):
        ingest(case_root)


def test_database_symlink_to_original_rejected(case_root: Path) -> None:
    path = case_root / "originals/synthetic-document"
    path.write_bytes(b"synthetic")
    (case_root / "database").mkdir()
    symlink_or_skip(case_root / "database/evidence.db", path)
    with pytest.raises(EvidenceError, match="Links"):
        ingest(case_root)
    assert path.read_bytes() == b"synthetic"


def test_manifest_symlink_to_original_rejected(case_root: Path) -> None:
    path = case_root / "originals/synthetic-document"
    path.write_bytes(b"synthetic")
    ingest(case_root)
    symlink_or_skip(case_root / "output/manifest.json", path)
    with pytest.raises(EvidenceError, match="Links"):
        write_manifest(case_root)
    assert path.read_bytes() == b"synthetic"


def test_case_paths_are_configurable(case_root: Path) -> None:
    paths = CasePaths.load(case_root, create=True)
    assert paths.db_file == case_root / "database/evidence.db"
    assert paths.originals == case_root / "originals"


def test_special_file_rejected_without_blocking(case_root: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO test requires POSIX")
    os.mkfifo(case_root / "originals/synthetic-fifo")
    with pytest.raises(EvidenceError, match="Special files"):
        ingest(case_root)


def test_special_database_file_rejected_before_sqlite_open(case_root: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO test requires POSIX")
    (case_root / "database").mkdir()
    os.mkfifo(case_root / "database/evidence.db")
    with pytest.raises(EvidenceError, match="Special files"):
        ingest(case_root)
