"""Concrete regressions and failure injection for the Evidence Foundation audit."""

import errno
import hashlib
import io
import json
import random
import sqlite3
import stat
import struct
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.cli.evidence import manifest as manifest_command
from evidence_engine.config import ZipLimits
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic import service
from evidence_engine.ingest.generic.archives import MetadataReader, validate_name
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.ingest.generic.verification import verify
from evidence_engine.models.entities import ArchiveMember, EvidenceFile, IngestionRun, SourceRecord
from evidence_engine.reports.manifest import manifest_json, write_manifest
from evidence_engine.storage.database import open_database


def synthetic_zip(
    root: Path,
    names: tuple[str, ...] = ("synthetic.txt",),
    payload: bytes = b"synthetic-hidden-payload",
    method: int = zipfile.ZIP_DEFLATED,
) -> Path:
    path = root / "originals/synthetic-export.zip"
    with zipfile.ZipFile(path, "w", compression=method) as archive:
        for name in names:
            archive.writestr(name, payload)
    return path


def snapshot(directory: Path) -> dict[str, tuple[bytes, int, int, int]]:
    # atime is controlled by the host mount, not by SQLite's read-only mode.
    return {
        path.relative_to(directory).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            path.stat().st_ctime_ns,
            path.stat().st_mode,
        )
        for path in directory.rglob("*")
        if path.is_file()
    }


def assert_failed_without_cataloged_files(root: Path) -> None:
    engine = open_database(root / "database/evidence.db")
    with Session(engine) as session:
        run = session.scalars(select(IngestionRun)).one()
        assert run.status == "FAILED" and run.files_added == 0
        for model in (EvidenceFile, ArchiveMember, SourceRecord):
            assert session.scalar(select(func.count()).select_from(model)) == 0
    engine.dispose()
    assert list((root / "working").iterdir()) == []


@pytest.mark.parametrize("method", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
@pytest.mark.parametrize("declared", [0, 1])
def test_forged_size_and_prefix_crc_cannot_truncate_member(
    case_root: Path, method: int, declared: int
) -> None:
    payload = b"synthetic-hidden-payload"
    path = synthetic_zip(case_root, payload=payload, method=method)
    data = bytearray(path.read_bytes())
    central = data.index(b"PK\x01\x02")
    crc = zlib.crc32(payload[:declared])
    struct.pack_into("<I", data, central + 24, declared)
    struct.pack_into("<I", data, central + 16, crc)
    struct.pack_into("<I", data, 22, declared)
    struct.pack_into("<I", data, 14, crc)
    path.write_bytes(data)
    with pytest.raises(EvidenceError, match="size"):
        ingest(case_root)
    assert path.read_bytes() == data
    assert_failed_without_cataloged_files(case_root)


@pytest.mark.parametrize(
    "names",
    [
        ("Synthetic/first.txt", "synthetic/second.txt"),
        ("Synthetic/", "synthetic/second.txt"),
        ("synthetic", "SYNTHETIC/child.txt"),
        ("foo/", "FOO/"),
    ],
)
def test_implicit_directory_case_collisions_rejected(
    case_root: Path, names: tuple[str, ...]
) -> None:
    path = case_root / "originals/synthetic-export.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, b"" if name.endswith("/") else b"synthetic")
    with pytest.raises(EvidenceError, match="colli"):
        ingest(case_root)
    assert_failed_without_cataloged_files(case_root)


@pytest.mark.parametrize("method", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
@pytest.mark.parametrize("variant", ["classic", "zip64", "descriptor"])
def test_valid_multiblock_zip_variants(case_root: Path, method: int, variant: str) -> None:
    class UnseekableOutput(io.BytesIO):
        def seek(self, *args):
            raise io.UnsupportedOperation("synthetic nonseekable output")

    # More than two compressed/input chunks, followed by highly compressible output
    # to exercise both input boundaries and bounded DEFLATE output draining.
    payload = random.Random(0).randbytes(2 * 1024 * 1024 + 17) + b"synthetic" * 400000
    stream = UnseekableOutput() if variant == "descriptor" else io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=method) as archive:
        with archive.open("synthetic-member", "w", force_zip64=variant == "zip64") as member:
            member.write(payload)
    original = case_root / "originals/synthetic-export.zip"
    original.write_bytes(stream.getvalue())
    before = snapshot(case_root / "originals")
    assert ingest(case_root).files_added == 1
    assert next((case_root / "working").rglob("*.bin")).read_bytes() == payload
    member_json = json.loads(manifest_json(case_root))["files"][0]["members"][0]
    assert member_json["sha256"] == hashlib.sha256(payload).hexdigest()
    assert member_json["size_bytes"] == len(payload)
    assert snapshot(case_root / "originals") == before


@pytest.mark.parametrize("name", [r"\\synthetic\share\file", r"synthetic/..\escape", ""])
def test_unc_mixed_and_empty_names(name: str) -> None:
    with pytest.raises(EvidenceError):
        validate_name(zipfile.ZipInfo(name))


@pytest.mark.parametrize("kind", [stat.S_IFIFO, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFSOCK])
def test_zip_special_files_are_rejected(case_root: Path, kind: int) -> None:
    path = case_root / "originals/synthetic-export.zip"
    entry = zipfile.ZipInfo("synthetic-special")
    entry.create_system = 3
    entry.external_attr = (kind | 0o600) << 16
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(entry, b"")
    with pytest.raises(EvidenceError, match="special"):
        ingest(case_root)


def test_metadata_read_limit_precedes_allocation(monkeypatch) -> None:
    class BoundedInput(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            assert 0 <= size <= 80, "Underlying oversized read attempted"
            return super().read(size)

    monkeypatch.setattr("evidence_engine.ingest.generic.archives.MAX_METADATA_BYTES", 80)
    reader = MetadataReader(BoundedInput(b"x" * 81), 10)
    reader.seek(0)
    with pytest.raises(EvidenceError, match="metadata"):
        reader.read(81)


def test_actual_member_count_checked_before_zipinfo_objects(case_root: Path, monkeypatch) -> None:
    path = synthetic_zip(case_root, ("synthetic-a", "synthetic-b"))
    data = bytearray(path.read_bytes())
    end = data.rindex(b"PK\x05\x06")
    struct.pack_into("<HH", data, end + 8, 1, 1)  # False counts in end record.
    path.write_bytes(data)

    def reject_allocation(*args, **kwargs):
        raise AssertionError("ZipInfo allocation before member limit check")

    monkeypatch.setattr(zipfile, "ZipInfo", reject_allocation)
    with pytest.raises(EvidenceError, match="member count"):
        ingest(case_root, ZipLimits(max_members=1))


@pytest.mark.parametrize("change", ["missing", "modified"])
def test_reingestion_cannot_succeed_with_damaged_extractions(case_root: Path, change: str) -> None:
    synthetic_zip(case_root)
    ingest(case_root)
    baseline = manifest_json(case_root)
    extracted = next((case_root / "working").rglob("*.bin"))
    if change == "missing":
        extracted.unlink()
    else:
        extracted.write_bytes(b"synthetic alteration")
    with pytest.raises(EvidenceError, match="cataloged extraction"):
        ingest(case_root)
    assert manifest_json(case_root) == baseline


def test_disk_sync_failure_rolls_back(case_root: Path, monkeypatch) -> None:
    original = synthetic_zip(case_root)
    before = original.read_bytes()

    def disk_full(descriptor: int) -> None:
        raise OSError(errno.ENOSPC, "synthetic disk failure")

    monkeypatch.setattr("evidence_engine.ingest.generic.archives.os.fsync", disk_full)
    with pytest.raises(EvidenceError):
        ingest(case_root)
    assert original.read_bytes() == before
    assert_failed_without_cataloged_files(case_root)


def test_constraint_failure_after_extraction_rolls_back(case_root: Path, monkeypatch) -> None:
    synthetic_zip(case_root)
    validate = service.validate_materialized_members

    def inject_constraint(session: Session, paths, case_id: str) -> None:
        assert list(paths.working.rglob("*.bin")), "Failure must occur after extraction"
        run_id = session.scalar(select(IngestionRun.id))
        session.add(
            SourceRecord(
                ingestion_run_id=run_id,
                evidence_file_id="synthetic-missing-id",
                location="whole-file",
                parser_id="synthetic",
                parser_version="0",
            )
        )
        validate(session, paths, case_id)

    monkeypatch.setattr(service, "validate_materialized_members", inject_constraint)
    with pytest.raises(EvidenceError, match="IntegrityError"):
        ingest(case_root)
    assert_failed_without_cataloged_files(case_root)


def test_missing_new_extraction_detected_before_commit(case_root: Path, monkeypatch) -> None:
    synthetic_zip(case_root)
    validate = service.validate_materialized_members

    def remove_before_commit(session: Session, paths, case_id: str) -> None:
        next(paths.working.rglob("*.bin")).unlink()
        validate(session, paths, case_id)

    monkeypatch.setattr(service, "validate_materialized_members", remove_before_commit)
    with pytest.raises(EvidenceError, match="MISSING"):
        ingest(case_root)
    assert_failed_without_cataloged_files(case_root)


def test_failure_after_commit_never_deletes_committed_extractions(case_root: Path) -> None:
    synthetic_zip(case_root)

    def fail_acknowledgement(session: Session) -> None:
        if any(
            isinstance(item, IngestionRun) and item.status == "COMPLETED"
            for item in session.identity_map.values()
        ):
            raise RuntimeError("synthetic lost commit acknowledgement")

    event.listen(Session, "after_commit", fail_acknowledgement)
    try:
        with pytest.raises(EvidenceError, match="committed; staging preserved"):
            ingest(case_root)
    finally:
        event.remove(Session, "after_commit", fail_acknowledgement)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        assert session.scalars(select(IngestionRun.status)).one() == "COMPLETED"
        member = session.scalars(select(ArchiveMember)).one()
        content = (case_root / "working" / member.working_relative_path).read_bytes()
        assert hashlib.sha256(content).hexdigest() == member.sha256
    engine.dispose()


def test_process_interrupted_before_commit_is_not_success(case_root: Path) -> None:
    original = synthetic_zip(case_root)
    before = original.read_bytes()
    code = """
import os, sys
from pathlib import Path
from sqlalchemy import event
from sqlalchemy.orm import Session
from evidence_engine.models.entities import IngestionRun
from evidence_engine.ingest.generic.service import ingest
def stop(session):
    if any(isinstance(x, IngestionRun) and x.status == 'COMPLETED'
           for x in session.identity_map.values()):
        os._exit(23)
event.listen(Session, 'before_commit', stop)
ingest(Path(sys.argv[1]))
"""
    result = subprocess.run([sys.executable, "-c", code, str(case_root)], timeout=30, check=False)
    assert result.returncode == 23
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        run = session.scalars(select(IngestionRun)).one()
        assert run.status == "RUNNING" and run.finished_at is None
        assert session.scalar(select(func.count()).select_from(EvidenceFile)) == 0
    engine.dispose()
    assert original.read_bytes() == before
    assert list((case_root / "working").rglob("*.bin")), "Orphan staging remains for manual review"


def test_verify_does_not_recover_hot_journal(case_root: Path) -> None:
    ingest(case_root)
    database = case_root / "database/evidence.db"
    code = """
import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute('PRAGMA cache_size=1')
connection.execute('BEGIN IMMEDIATE')
connection.execute('UPDATE ingestion_runs SET errors=?', ('x' * 1000000,))
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", code, str(database)], check=True, timeout=30)
    assert database.with_name("evidence.db-journal").is_file()
    before = snapshot(case_root / "database")
    result = CliRunner().invoke(app, ["evidence", "verify", "--case-root", str(case_root)])
    assert result.exit_code == 2
    assert snapshot(case_root / "database") == before


def test_read_only_connections_enforce_policy_and_fk(case_root: Path) -> None:
    ingest(case_root)
    engine = open_database(case_root / "database/evidence.db", read_only=True)
    with engine.connect() as first, engine.connect() as second:
        for connection in (first, second):
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            with pytest.raises(OperationalError):
                connection.exec_driver_sql("UPDATE cases SET name='synthetic-change'")
    engine.dispose()


@pytest.mark.parametrize("command", ["verify", "manifest"])
def test_missing_catalog_is_not_created_by_read_commands(case_root: Path, command: str) -> None:
    for name in ("working", "database", "output"):
        (case_root / name).mkdir()
    before = snapshot(case_root)
    result = CliRunner().invoke(app, ["evidence", command, "--case-root", str(case_root)])
    assert result.exit_code == 2 and "Catalog does not exist" in result.output
    assert snapshot(case_root) == before


def test_source_record_cannot_reference_both_origins(case_root: Path) -> None:
    synthetic_zip(case_root)
    result = ingest(case_root)
    engine = open_database(case_root / "database/evidence.db")
    try:
        with Session(engine) as session:
            member = session.scalars(select(ArchiveMember)).one()
            session.add(
                SourceRecord(
                    ingestion_run_id=result.run_id,
                    evidence_file_id=member.evidence_file_id,
                    archive_member_id=member.id,
                    location="whole-file",
                    parser_id="synthetic",
                    parser_version="0",
                )
            )
            with pytest.raises(IntegrityError, match="exactly_one_source"):
                session.commit()
            session.rollback()
            assert session.scalar(select(func.count()).select_from(SourceRecord)) == 2
    finally:
        engine.dispose()


def test_wal_catalog_refused_without_side_effects(case_root: Path) -> None:
    ingest(case_root)
    with sqlite3.connect(case_root / "database/evidence.db") as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    before = snapshot(case_root / "database")
    with pytest.raises(EvidenceError, match="DELETE"):
        verify(case_root)
    assert snapshot(case_root / "database") == before


def test_removed_then_restored_and_same_filename_in_two_directories(case_root: Path) -> None:
    for directory in ("synthetic-a", "synthetic-b"):
        target = case_root / "originals" / directory / "synthetic-document.txt"
        target.parent.mkdir()
        target.write_bytes(b"identical synthetic content")
    ingest(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        ids = {item.relative_path: item.id for item in session.scalars(select(EvidenceFile))}
        assert len(set(ids.values())) == 2
        assert all(UUID(value).version == 4 for value in ids.values())
    restored = case_root / "originals/synthetic-a/synthetic-document.txt"
    restored.unlink()
    with pytest.raises(EvidenceError, match="MISSING"):
        ingest(case_root)
    restored.write_bytes(b"identical synthetic content")
    assert ingest(case_root).files_added == 0
    with Session(engine) as session:
        assert {
            item.relative_path: item.id for item in session.scalars(select(EvidenceFile))
        } == ids
    engine.dispose()


def test_verify_empty_large_renamed_and_extra_directory(case_root: Path) -> None:
    originals = case_root / "originals"
    (originals / "synthetic-empty").touch()
    (originals / "synthetic-large").write_bytes(b"synthetic" * 400000)
    ingest(case_root)
    assert {item.status for item in verify(case_root)} == {"OK"}
    (originals / "synthetic-large").rename(originals / "synthetic-renamed")
    (originals / "synthetic-extra-directory").mkdir()
    before = snapshot(case_root / "database")
    result = CliRunner().invoke(app, ["evidence", "verify", "--case-root", str(case_root)])
    assert result.exit_code == 1
    assert {item["status"] for item in json.loads(result.stdout)} == {"OK", "MISSING", "UNTRACKED"}
    assert snapshot(case_root / "database") == before


def test_manifest_bytes_and_effective_catalog_timestamp(case_root: Path, monkeypatch) -> None:
    first_time = "2000-01-01T00:00:00.000000Z"
    second_time = "2000-01-02T00:00:00.000000Z"
    monkeypatch.setattr(service, "utc_now", lambda: first_time)
    (case_root / "originals/synthetic-\u96ea.txt").write_bytes(b"synthetic")
    ingest(case_root)
    expected = write_manifest(case_root).encode("utf-8")
    monkeypatch.setattr(service, "utc_now", lambda: second_time)
    ingest(case_root)
    assert write_manifest(case_root).encode("utf-8") == expected
    assert json.loads(expected)["generated_at"] == first_time
    assert (case_root / "output/manifest.json").read_bytes() == expected
    assert b"\r\n" not in expected and expected.endswith(b"\n")
    buffer = io.BytesIO()
    simulated_windows_stdout = io.TextIOWrapper(buffer, encoding="cp1252", newline="\r\n")
    with monkeypatch.context() as context:
        context.setattr(sys, "stdout", simulated_windows_stdout)
        manifest_command(case_root)
        simulated_windows_stdout.flush()
    assert buffer.getvalue() == expected
    (case_root / "originals/synthetic-additional").write_bytes(b"additional")
    ingest(case_root)
    assert json.loads(manifest_json(case_root))["generated_at"] == second_time
