"""SQLite baseline migration v1; unknown/unversioned schemas fail closed."""

import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import URL, Engine, create_engine, event, inspect

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.paths import check_path
from evidence_engine.models.entities import Base

SCHEMA_VERSION = 1


def open_database(path: Path, *, initialize: bool = False, read_only: bool = False) -> Engine:
    if initialize and read_only:
        raise ValueError("Cannot initialize a read-only catalog")
    check_path(path)
    if not initialize and not path.is_file():
        raise EvidenceError("Catalog does not exist; run evidence ingest first")
    if read_only:
        # WAL readers may create/write shared-memory files even in mode=ro.
        # M1 uses DELETE journaling; refuse external WAL configuration unchanged.
        with path.open("rb") as stream:
            header = stream.read(20)
        if header[18:20] == b"\x02\x02":
            raise EvidenceError("Read-only catalog access requires DELETE journal mode")
        url = URL.create(
            "sqlite", database=path.absolute().as_uri(), query={"mode": "ro", "uri": "true"}
        )
    else:
        url = URL.create("sqlite", database=str(path))
    engine = create_engine(url, connect_args={"timeout": 30})

    @event.listens_for(engine, "connect")
    def configure(connection: sqlite3.Connection, record: Any) -> None:
        connection.execute("PRAGMA foreign_keys = ON")
        if read_only:
            connection.execute("PRAGMA query_only = ON")

    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE" if initialize else "BEGIN")
            version = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
            tables = set(inspect(connection).get_table_names())
            if version == 0 and not tables and initialize:
                Base.metadata.create_all(connection)
                connection.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version != SCHEMA_VERSION or tables != set(Base.metadata.tables):
                raise EvidenceError("Unsupported catalog schema; explicit migration required")
            connection.commit()
    except Exception:
        engine.dispose()
        raise
    return engine
