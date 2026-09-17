import hashlib
import stat
import struct
import warnings
import zipfile
import zlib
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from evidence_engine.config import ZipLimits
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.archives import validate_name
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.models.entities import ArchiveMember, EvidenceFile, IngestionRun, SourceRecord
from evidence_engine.reports.manifest import manifest_json
from evidence_engine.storage.database import open_database


def make_zip(
    case_root: Path,
    names: list[str],
    payload: bytes = b"synthetic",
    *,
    compression: int = zipfile.ZIP_STORED,
) -> Path:
    path = case_root / "originals/synthetic-export.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w", compression=compression) as archive:
            for name in names:
                archive.writestr(name, payload)
    return path


def assert_rejected(case_root: Path, limits: ZipLimits | None = None) -> None:
    original = case_root / "originals/synthetic-export.zip"
    before = original.read_bytes()
    with pytest.raises(EvidenceError):
        ingest(case_root, limits)
    assert original.read_bytes() == before
    assert list((case_root / "working").iterdir()) == []
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        for model in (EvidenceFile, ArchiveMember, SourceRecord):
            assert session.scalar(select(func.count()).select_from(model)) == 0
        run = session.scalars(select(IngestionRun)).one()
        assert run.status == "FAILED" and run.errors != "[]"
    engine.dispose()


@pytest.mark.parametrize(
    "name",
    [
        "../../synthetic-escape",
        "/synthetic-absolute",
        "C:\\synthetic-windows",
        "C:synthetic-relative",
        "..\\..\\synthetic-escape",
        "//synthetic/share",
        "synthetic/../escape",
        "synthetic//empty",
        "./synthetic",
        "synthetic/CON.txt",
        "synthetic/trailing.",
        "synthetic/trailing ",
        "synthetic/invalid?.txt",
        "synthetic/line\nfeed",
        "synthetic/e\u0301.txt",
    ],
)
def test_unsafe_paths_rejected(case_root: Path, name: str) -> None:
    make_zip(case_root, [name])
    assert_rejected(case_root)
    assert not (case_root.parent / "synthetic-escape").exists()


@pytest.mark.parametrize(
    "name",
    [
        "folder/Apple Media Services: Account Change History.csv",
        "outro/nome:legitimo.csv",
        "synthetic/filename:stream",
    ],
)
def test_logical_colon_never_becomes_materialized_path(case_root: Path, name: str) -> None:
    payload = b"synthetic colon member"
    original = make_zip(case_root, [name], payload)
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    assert ingest(case_root).files_added == 1
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        member = session.scalars(select(ArchiveMember)).one()
        member_id = member.id
        assert member.member_path == name
        assert ":" not in member.working_relative_path
        target = case_root / "working" / member.working_relative_path
        assert target.resolve().is_relative_to((case_root / "working").resolve())
        assert target.name == "00000000.bin"
        assert target.read_bytes() == payload
        assert member.sha256 == hashlib.sha256(payload).hexdigest()
        assert member.size_bytes == len(payload)
        assert member.crc32 == zlib.crc32(payload)
    assert ingest(case_root).files_added == 0
    with Session(engine) as session:
        assert session.scalars(select(ArchiveMember.id)).one() == member_id
    engine.dispose()
    assert hashlib.sha256(original.read_bytes()).hexdigest() == original_hash


@pytest.mark.parametrize(
    "name",
    [
        "C:/evil.txt",
        "C:evil.txt",
        "C:\\evil.txt",
        "../evil.txt",
        "/evil.txt",
        "\\\\server\\share\\evil.txt",
        "folder:logical/../evil.txt",
        "folder:logical/..\\evil.txt",
    ],
)
def test_colon_exception_does_not_allow_unsafe_paths(case_root: Path, name: str) -> None:
    make_zip(case_root, [name])
    assert_rejected(case_root)


@pytest.mark.parametrize(
    "names",
    [
        ["synthetic.txt", "synthetic.txt"],
        ["synthetic.txt", "SYNTHETIC.TXT"],
        ["synthetic", "synthetic/child.txt"],
    ],
)
def test_duplicates_and_file_directory_conflicts(case_root: Path, names: list[str]) -> None:
    make_zip(case_root, names)
    assert_rejected(case_root)


def test_symlink_member(case_root: Path) -> None:
    path = case_root / "originals/synthetic-export.zip"
    info = zipfile.ZipInfo("synthetic-link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(info, "../../synthetic-escape")
    assert_rejected(case_root)


@pytest.mark.parametrize(
    "limits,names,payload,compression",
    [
        (ZipLimits(max_file_bytes=3), ["synthetic.txt"], b"1234", zipfile.ZIP_STORED),
        (ZipLimits(max_total_bytes=6), ["synthetic-a", "synthetic-b"], b"1234", zipfile.ZIP_STORED),
        (ZipLimits(max_members=1), ["synthetic-a", "synthetic-b"], b"a", zipfile.ZIP_STORED),
        (ZipLimits(max_ratio=2), ["synthetic.txt"], b"a" * 4096, zipfile.ZIP_DEFLATED),
    ],
)
def test_configurable_bomb_limits(
    case_root: Path, limits: ZipLimits, names: list[str], payload: bytes, compression: int
) -> None:
    make_zip(case_root, names, payload, compression=compression)
    assert_rejected(case_root, limits)


def test_large_claimed_size_rejected_without_large_allocation(case_root: Path) -> None:
    path = make_zip(case_root, ["synthetic.txt"])
    data = bytearray(path.read_bytes())
    central = data.index(b"PK\x01\x02")
    struct.pack_into("<I", data, central + 24, 2**30)
    path.write_bytes(data)
    assert_rejected(case_root)


def test_bad_crc_rolls_back_already_extracted_members(case_root: Path) -> None:
    path = make_zip(case_root, ["synthetic-first", "synthetic-second"])
    data = bytearray(path.read_bytes())
    central = data.index(b"PK\x01\x02", data.index(b"PK\x01\x02") + 1)
    struct.pack_into("<I", data, central + 16, 0)
    path.write_bytes(data)
    assert_rejected(case_root)


def test_invalid_unicode_and_nul_names() -> None:
    for name in ("synthetic\x00hidden.txt", "synthetic\ud800.txt"):
        with pytest.raises(EvidenceError):
            validate_name(zipfile.ZipInfo(name))


def test_malformed_utf8_metadata(case_root: Path) -> None:
    path = make_zip(case_root, ["synthetic.txt"])
    data = bytearray(path.read_bytes())
    central = data.index(b"PK\x01\x02")
    struct.pack_into("<H", data, central + 8, 0x800)
    data[central + 46] = 0xFF
    path.write_bytes(data)
    assert_rejected(case_root)


def test_nested_zip_is_cataloged_without_recursion(case_root: Path) -> None:
    inner = BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr("../../synthetic-would-escape", b"synthetic")
    outer = make_zip(case_root, ["synthetic-inner.zip"], inner.getvalue())
    before = hashlib.sha256(outer.read_bytes()).hexdigest()
    ingest(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        member = session.scalars(select(ArchiveMember)).one()
        assert member.member_path == "synthetic-inner.zip"
        assert member.sha256 == hashlib.sha256(inner.getvalue()).hexdigest()
    engine.dispose()
    assert hashlib.sha256(outer.read_bytes()).hexdigest() == before


def test_valid_zip_without_zip_extension(case_root: Path) -> None:
    path = make_zip(case_root, ["synthetic.txt"])
    path.rename(path.with_suffix(".bin"))
    assert ingest(case_root).files_added == 1
    assert '"member_path": "synthetic.txt"' in manifest_json(case_root)


def test_fake_zip_extension_fails_explicitly(case_root: Path) -> None:
    (case_root / "originals/synthetic-export.zip").write_bytes(b"not a zip")
    assert_rejected(case_root)


def test_failure_rolls_back_other_new_files(case_root: Path) -> None:
    (case_root / "originals/aaa-synthetic-document.txt").write_bytes(b"synthetic")
    make_zip(case_root, ["../synthetic-invalid"])
    assert_rejected(case_root)


def test_deflate_and_empty_members_are_supported(case_root: Path) -> None:
    make_zip(case_root, ["synthetic-empty.txt"], b"", compression=zipfile.ZIP_DEFLATED)
    assert ingest(case_root).files_added == 1
    assert hashlib.sha256(b"").hexdigest() in manifest_json(case_root)


def test_cleanup_failure_still_records_failed_run(case_root: Path, monkeypatch) -> None:
    make_zip(case_root, ["../synthetic-invalid"])

    def fail_cleanup(path: Path) -> None:
        raise PermissionError("synthetic cleanup failure")

    monkeypatch.setattr("evidence_engine.ingest.generic.service.shutil.rmtree", fail_cleanup)
    with pytest.raises(EvidenceError, match="cleanup failed"):
        ingest(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        run = session.scalars(select(IngestionRun)).one()
        assert run.status == "FAILED" and "cleanup failed" in run.errors
        assert session.scalar(select(func.count()).select_from(EvidenceFile)) == 0
    engine.dispose()
