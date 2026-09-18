"""SQLite schemas and explicit, additive v1 -> v2 -> v3 -> v4 -> v5 migrations."""

import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import URL, Engine, create_engine, event, inspect

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.paths import check_path
from evidence_engine.models.entities import (
    Base,
    CorrelationCandidate,
    CorrelationRun,
    CorrelationSupport,
    DeviceObservation,
    NetworkObservation,
    NormalizationRun,
    NormalizedEvent,
    ObservationRun,
    ParsedRecord,
    ParserRun,
)

SCHEMA_VERSION = 5
V5_ADDITIONS = {
    CorrelationRun.__tablename__,
    CorrelationCandidate.__tablename__,
    CorrelationSupport.__tablename__,
}
V4_TABLES = set(Base.metadata.tables) - V5_ADDITIONS
V4_ADDITIONS = {
    ObservationRun.__tablename__,
    DeviceObservation.__tablename__,
    NetworkObservation.__tablename__,
}
V3_TABLES = V4_TABLES - V4_ADDITIONS
V3_ADDITIONS = {NormalizationRun.__tablename__, NormalizedEvent.__tablename__}
V2_TABLES = V3_TABLES - V3_ADDITIONS
V1_TABLES = V2_TABLES - {ParserRun.__tablename__, ParsedRecord.__tablename__}


def open_database(
    path: Path, *, initialize: bool = False, read_only: bool = False, migrate: bool = False
) -> Engine:
    if (initialize or migrate) and read_only:
        raise ValueError("Cannot initialize a read-only catalog")
    check_path(path)
    if not initialize and not path.is_file():
        raise EvidenceError("Catalog does not exist; run evidence ingest first")
    if not read_only and not migrate and path.is_file() and path.stat().st_size:
        # Reject old/unsupported catalogs before a writable connection could
        # recover a hot journal. Only explicit migration may open v1 for writing.
        preflight = open_database(path, read_only=True)
        preflight.dispose()
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
            connection.exec_driver_sql("BEGIN IMMEDIATE" if initialize or migrate else "BEGIN")
            version = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
            tables = set(inspect(connection).get_table_names())
            if version == 0 and not tables and initialize:
                Base.metadata.create_all(connection)
                connection.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif migrate and (
                (version == 1 and tables == V1_TABLES)
                or (version == 2 and tables == V2_TABLES)
                or (version == 3 and tables == V3_TABLES)
                or (version == 4 and tables == V4_TABLES)
            ):
                # All steps share one transaction, including v1 -> v5.
                if version == 1:
                    Base.metadata.tables[ParserRun.__tablename__].create(connection)
                    Base.metadata.tables[ParsedRecord.__tablename__].create(connection)
                    connection.exec_driver_sql("PRAGMA user_version = 2")
                if version <= 2:
                    Base.metadata.tables[NormalizationRun.__tablename__].create(connection)
                    Base.metadata.tables[NormalizedEvent.__tablename__].create(connection)
                    connection.exec_driver_sql("PRAGMA user_version = 3")
                if version <= 3:
                    for model in (ObservationRun, DeviceObservation, NetworkObservation):
                        Base.metadata.tables[model.__tablename__].create(connection)
                    connection.exec_driver_sql("PRAGMA user_version = 4")
                for correlation_model in (CorrelationRun, CorrelationCandidate, CorrelationSupport):
                    Base.metadata.tables[correlation_model.__tablename__].create(connection)
                connection.exec_driver_sql("PRAGMA user_version = 5")
            elif read_only and (
                (version == 2 and tables == V2_TABLES)
                or (version == 3 and tables == V3_TABLES)
                or (version == 4 and tables == V4_TABLES)
            ):
                # Verify/manifest can inspect v2/v3/v4 before explicit migration.
                pass
            elif version == 1 and tables == V1_TABLES:
                raise EvidenceError(
                    "Catalog schema v1 requires explicit migration: run evidence migrate"
                )
            elif version != SCHEMA_VERSION or tables != set(Base.metadata.tables):
                raise EvidenceError("Unsupported catalog schema; explicit migration required")
            connection.commit()
    except Exception:
        engine.dispose()
        raise
    return engine
