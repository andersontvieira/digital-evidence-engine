import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.hashing import sha256_file
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.ingest.generic.verification import verify
from evidence_engine.models.entities import (
    ArchiveMember,
    Case,
    EvidenceFile,
    IngestionRun,
    SourceRecord,
)
from evidence_engine.reports.manifest import manifest_json, write_manifest
from evidence_engine.storage.database import open_database


def test_new_idempotent_and_additional_file(case_root: Path) -> None:
    originals = case_root / "originals"
    (originals / "synthetic-document.txt").write_bytes(b"synthetic-content")
    first = ingest(case_root)
    snapshot = manifest_json(case_root)
    second = ingest(case_root)
    assert first.files_added == 1
    assert second.files_added == 0
    assert first.run_id != second.run_id
    assert snapshot == manifest_json(case_root)
    (originals / "synthetic-additional.txt").write_bytes(b"same-content-other-occurrence")
    third = ingest(case_root)
    assert third.files_added == 1
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(EvidenceFile)) == 2
        assert session.scalar(select(func.count()).select_from(SourceRecord)) == 2
        assert session.scalar(select(func.count()).select_from(IngestionRun)) == 3
        assert session.scalar(select(Case.name)) == "synthetic-case"
    engine.dispose()


@pytest.mark.parametrize("change", ["modified", "removed"])
def test_baseline_is_never_replaced(case_root: Path, change: str) -> None:
    original = case_root / "originals/synthetic-original.txt"
    original.write_bytes(b"synthetic-original-content")
    ingest(case_root)
    before = manifest_json(case_root)
    if change == "modified":
        original.write_bytes(b"changed")
    else:
        original.unlink()
    (case_root / "originals/aaa-synthetic-new.txt").write_bytes(b"new")
    with pytest.raises(EvidenceError, match="MODIFIED|MISSING"):
        ingest(case_root)
    assert manifest_json(case_root) == before
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(EvidenceFile)) == 1
        run = session.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc())).first()
        assert run is not None and run.status == "FAILED" and run.files_added == 0
        assert json.loads(run.errors)
    engine.dispose()


def test_verify_all_states_and_does_not_change_catalog(case_root: Path) -> None:
    originals = case_root / "originals"
    for name in ("ok", "missing", "modified"):
        (originals / f"synthetic-{name}.txt").write_text(name)
    ingest(case_root)
    baseline = manifest_json(case_root)
    (originals / "synthetic-missing.txt").unlink()
    (originals / "synthetic-modified.txt").write_text("different")
    (originals / "synthetic-new.txt").write_text("new")
    states = {item.relative_path: item.status for item in verify(case_root)}
    assert states == {
        "synthetic-ok.txt": "OK",
        "synthetic-missing.txt": "MISSING",
        "synthetic-modified.txt": "MODIFIED",
        "synthetic-new.txt": "UNTRACKED",
    }
    assert manifest_json(case_root) == baseline


def test_manifest_sorted_deterministic_and_correct(case_root: Path) -> None:
    for name in ("z", "a"):
        (case_root / f"originals/synthetic-{name}.txt").write_bytes(name.encode())
    ingest(case_root)
    first = write_manifest(case_root)
    assert first == write_manifest(case_root)
    assert first == (case_root / "output/manifest.json").read_text()
    manifest = json.loads(first)
    assert manifest["schema_version"] == 1
    assert manifest["generated_at"].endswith("Z")
    assert [file["relative_path"] for file in manifest["files"]] == [
        "synthetic-a.txt",
        "synthetic-z.txt",
    ]
    assert manifest["files"][0]["sha256"] == hashlib.sha256(b"a").hexdigest()
    assert str(case_root) not in first
    assert "case_root" not in first


def test_zip_provenance_and_original_immutability(case_root: Path) -> None:
    archive_path = case_root / "originals/synthetic-export.zip"
    payload = b"synthetic member content"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("synthetic-directory/", b"")
        archive.writestr("synthetic-directory/synthetic-document.txt", payload)
    before = sha256_file(archive_path)
    before_stat = archive_path.stat()
    result = ingest(case_root)
    assert sha256_file(archive_path) == before
    assert archive_path.stat().st_mtime_ns == before_stat.st_mtime_ns
    assert archive_path.stat().st_mode == before_stat.st_mode
    assert [item.status for item in verify(case_root)] == ["OK"]
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        original = session.scalars(select(EvidenceFile)).one()
        member = session.scalars(select(ArchiveMember)).one()
        assert member.evidence_file_id == original.id
        assert original.sha256 == before and original.is_archive
        assert member.sha256 == hashlib.sha256(payload).hexdigest()
        assert (case_root / "working" / member.working_relative_path).read_bytes() == payload
        assert member.ingestion_run_id == original.ingestion_run_id == result.run_id
        sources = session.scalars(select(SourceRecord)).all()
        assert len(sources) == 2
        assert {source.evidence_file_id for source in sources} == {None, original.id}
        assert {source.archive_member_id for source in sources} == {None, member.id}
        assert all(source.location == "whole-file" for source in sources)
        assert all(source.parser_id == "evidence_engine.inventory" for source in sources)
    engine.dispose()
    extracted_paths = sorted((case_root / "working").rglob("*.bin"))
    ingest(case_root)
    assert sorted((case_root / "working").rglob("*.bin")) == extracted_paths
    member_json = json.loads(manifest_json(case_root))["files"][0]["members"][0]
    assert member_json["sha256"] == hashlib.sha256(payload).hexdigest()


def test_equal_content_preserves_occurrences(case_root: Path) -> None:
    for name in ("a", "b"):
        (case_root / f"originals/synthetic-{name}.txt").write_bytes(b"identical")
    ingest(case_root)
    files = json.loads(manifest_json(case_root))["files"]
    assert len(files) == 2 and files[0]["sha256"] == files[1]["sha256"]


def test_foreign_keys_and_source_exclusivity(case_root: Path) -> None:
    (case_root / "originals/synthetic-document.txt").write_bytes(b"synthetic")
    run = ingest(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA user_version").scalar_one() == 1
    with Session(engine) as session:
        session.add(
            SourceRecord(
                ingestion_run_id=run.run_id,
                evidence_file_id="nonexistent",
                location="whole-file",
                parser_id="synthetic-parser",
                parser_version="0",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(
            SourceRecord(
                ingestion_run_id=run.run_id,
                location="whole-file",
                parser_id="synthetic-parser",
                parser_version="0",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.scalar(select(func.count()).select_from(SourceRecord)) == 1
    engine.dispose()


def test_unknown_schema_rejected(case_root: Path) -> None:
    ingest(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA user_version = 99")
    engine.dispose()
    with pytest.raises(EvidenceError, match="migration"):
        ingest(case_root)


def test_empty_case(case_root: Path) -> None:
    assert ingest(case_root).files_seen == 0
    assert verify(case_root) == []
    assert json.loads(manifest_json(case_root))["files"] == []


def test_unversioned_nonempty_database_is_not_adopted(case_root: Path) -> None:
    import sqlite3

    (case_root / "database").mkdir()
    with sqlite3.connect(case_root / "database/evidence.db") as connection:
        connection.execute("CREATE TABLE synthetic_unknown (value TEXT)")
    with pytest.raises(EvidenceError, match="migration"):
        ingest(case_root)
    with sqlite3.connect(case_root / "database/evidence.db") as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (0,)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall() == [("synthetic_unknown",)]


def test_failed_later_zip_keeps_previous_committed_extraction(case_root: Path) -> None:
    with zipfile.ZipFile(case_root / "originals/synthetic-good.zip", "w") as archive:
        archive.writestr("synthetic.txt", b"synthetic")
    ingest(case_root)
    baseline = manifest_json(case_root)
    extracted = list((case_root / "working").rglob("*.bin"))
    with zipfile.ZipFile(case_root / "originals/synthetic-bad.zip", "w") as archive:
        archive.writestr("../synthetic-escape", b"synthetic")
    with pytest.raises(EvidenceError):
        ingest(case_root)
    assert manifest_json(case_root) == baseline
    assert extracted == list((case_root / "working").rglob("*.bin"))
    assert extracted[0].read_bytes() == b"synthetic"


def test_native_original_name_is_not_reinterpreted_as_zip_path(case_root: Path) -> None:
    import os

    if os.name == "nt":
        pytest.skip("Backslash is a separator on Windows")
    (case_root / "originals/synthetic\\literal.txt").write_bytes(b"synthetic")
    ingest(case_root)
    assert [item.status for item in verify(case_root)] == ["OK"]


def test_database_paths_are_never_used_for_filesystem_reads(case_root: Path, monkeypatch) -> None:
    (case_root / "originals/synthetic-document").write_bytes(b"synthetic")
    ingest(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        item = session.scalars(select(EvidenceFile)).one()
        item.relative_path = "../../synthetic-outside"
        session.commit()
    engine.dispose()

    def reject_read(path: Path) -> str:
        raise AssertionError("Catalog paths must never become read targets")

    monkeypatch.setattr("evidence_engine.ingest.generic.verification.sha256_file", reject_read)
    assert {item.status for item in verify(case_root)} == {"MISSING", "UNTRACKED"}
