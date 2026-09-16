"""Stable JSON catalog snapshots, with no original content or absolute paths."""

import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from evidence_engine import __version__
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.paths import CasePaths, check_path
from evidence_engine.models.entities import ArchiveMember, Case, EvidenceFile
from evidence_engine.storage.database import open_database


class ManifestMember(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_path: str
    size_bytes: int
    compressed_size: int
    crc32: int
    sha256: str


class ManifestFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relative_path: str
    size_bytes: int
    sha256: str
    members: list[ManifestMember]


class ManifestCase(BaseModel):
    id: str
    name: str


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    engine_version: str
    generated_at: str
    case: ManifestCase
    files: list[ManifestFile]


def manifest_json(case_root: Path) -> str:
    paths = CasePaths.load(case_root)
    engine = open_database(paths.db_file, read_only=True)
    try:
        with Session(engine) as session:
            session.connection().exec_driver_sql("BEGIN")
            case = session.scalars(select(Case)).one_or_none()
            if case is None:
                raise EvidenceError("Catalog has no case")
            files = []
            for item in session.scalars(select(EvidenceFile).order_by(EvidenceFile.relative_path)):
                members = session.scalars(
                    select(ArchiveMember)
                    .where(ArchiveMember.evidence_file_id == item.id)
                    .order_by(ArchiveMember.member_path)
                )
                files.append(
                    ManifestFile(
                        relative_path=item.relative_path,
                        size_bytes=item.size_bytes,
                        sha256=item.sha256,
                        members=[
                            ManifestMember(
                                member_path=member.member_path,
                                size_bytes=member.size_bytes,
                                compressed_size=member.compressed_size,
                                crc32=member.crc32,
                                sha256=member.sha256,
                            )
                            for member in members
                        ],
                    )
                )
            manifest = Manifest(
                engine_version=__version__,
                generated_at=case.inventory_updated_at,
                case=ManifestCase(id=case.id, name=case.name),
                files=files,
            )
            return manifest.model_dump_json(indent=2) + "\n"
    finally:
        engine.dispose()


def write_manifest(case_root: Path) -> str:
    paths = CasePaths.load(case_root)
    content = manifest_json(case_root)
    destination = paths.output / "manifest.json"
    check_path(destination)
    descriptor, temporary = tempfile.mkstemp(prefix="manifest-", suffix=".tmp", dir=paths.output)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        check_path(destination)
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return content
