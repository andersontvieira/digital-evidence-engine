"""Compare originals against the stored baseline, without repairing either."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from evidence_engine.ingest.generic.hashing import sha256_file
from evidence_engine.ingest.generic.paths import CasePaths, discover
from evidence_engine.models.entities import EvidenceFile
from evidence_engine.storage.database import open_database


@dataclass(frozen=True)
class Verification:
    relative_path: str
    status: Literal["OK", "MISSING", "MODIFIED", "UNTRACKED"]


def verify(case_root: Path) -> list[Verification]:
    paths = CasePaths.load(case_root)
    engine = open_database(paths.db_file, read_only=True)
    try:
        with Session(engine) as session:
            session.connection().exec_driver_sql("BEGIN")
            known = {
                item.relative_path: item.sha256 for item in session.scalars(select(EvidenceFile))
            }
        present = {
            path.relative_to(paths.originals).as_posix(): path for path in discover(paths.originals)
        }
        results = []
        for relative in sorted(known.keys() | present.keys()):
            # Read only paths obtained from safe discovery, never constructed from the DB.
            if relative not in known:
                results.append(Verification(relative, "UNTRACKED"))
            elif relative not in present:
                results.append(Verification(relative, "MISSING"))
            else:
                try:
                    digest = sha256_file(present[relative])
                except FileNotFoundError:
                    results.append(Verification(relative, "MISSING"))
                    continue
                results.append(
                    Verification(relative, "OK" if digest == known[relative] else "MODIFIED")
                )
        return results
    finally:
        engine.dispose()
