"""Read snapshots using the same defensive database opener as the current timeline."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Connection

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.paths import CasePaths
from evidence_engine.storage.database import open_database


@contextmanager
def read_catalog(case_root: Path) -> Iterator[Connection]:
    paths = CasePaths.load(case_root)
    engine = open_database(paths.db_file, read_only=True)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            if connection.exec_driver_sql("PRAGMA user_version").scalar_one() != 5:
                raise EvidenceError("Technical queries require catalog schema v5")
            yield connection
    finally:
        engine.dispose()


def validate_limit(limit: int, maximum: int) -> None:
    if type(limit) is not int or not 1 <= limit <= maximum:
        raise EvidenceError(f"Query limit must be between 1 and {maximum}")
