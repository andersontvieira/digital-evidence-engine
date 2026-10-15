"""Evidence commands: explicit configuration, technical errors, JSON outputs."""

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from evidence_engine.errors import EvidenceError

app = typer.Typer(help="Catalog and verify local originals.", no_args_is_help=True)
CaseRoot = Annotated[
    Path, typer.Option("--case-root", envvar="CASE_ROOT", help="Existing external case root.")
]


def fail(error: Exception) -> None:
    message = (
        str(error)
        if isinstance(error, EvidenceError)
        else f"Technical failure: {type(error).__name__}"
    )
    typer.echo(f"ERROR: {message}", err=True)
    raise typer.Exit(2)


@app.command("ingest")
def ingest(
    case_root: CaseRoot,
    max_file_bytes: Annotated[int, typer.Option(min=1)] = 512 * 1024 * 1024,
    max_total_bytes: Annotated[int, typer.Option(min=1)] = 2 * 1024 * 1024 * 1024,
    max_members: Annotated[int, typer.Option(min=1)] = 10_000,
    max_ratio: Annotated[float, typer.Option(min=1)] = 200.0,
) -> None:
    """Hash originals and safely extract first-level ZIP members."""
    from pydantic import ValidationError
    from sqlalchemy.exc import SQLAlchemyError

    from evidence_engine.config import ZipLimits
    from evidence_engine.ingest.generic.service import ingest as ingest_case

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        limits = ZipLimits(
            max_file_bytes=max_file_bytes,
            max_total_bytes=max_total_bytes,
            max_members=max_members,
            max_ratio=max_ratio,
        )
        result = ingest_case(case_root, limits)
        typer.echo(json.dumps(asdict(result), sort_keys=True))
    except (EvidenceError, OSError, SQLAlchemyError, ValidationError) as error:
        fail(error)


@app.command("manifest")
def manifest(case_root: CaseRoot) -> None:
    """Write output/manifest.json and emit the same deterministic JSON."""
    from sqlalchemy.exc import SQLAlchemyError

    from evidence_engine.reports.manifest import write_manifest

    try:
        # Binary output preserves UTF-8 and LF on Windows and redirected stdout.
        typer.echo(write_manifest(case_root).encode("utf-8"), nl=False)
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)


@app.command("migrate")
def migrate(case_root: CaseRoot) -> None:
    """Explicitly advance v1/v2/v3/v4 catalogs to v5 without changing evidence."""
    from sqlalchemy.exc import SQLAlchemyError

    from evidence_engine.ingest.generic.paths import CasePaths
    from evidence_engine.storage.database import SCHEMA_VERSION, open_database

    try:
        paths = CasePaths.load(case_root)
        engine = open_database(paths.db_file, migrate=True)
        engine.dispose()
        typer.echo(json.dumps({"schema_version": SCHEMA_VERSION}))
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)


@app.command("verify")
def verify(case_root: CaseRoot) -> None:
    """Report OK, MISSING, MODIFIED or UNTRACKED; never repair originals."""
    from sqlalchemy.exc import SQLAlchemyError

    from evidence_engine.ingest.generic.verification import verify as verify_case

    try:
        results = verify_case(case_root)
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps([asdict(item) for item in results], indent=2))
    if any(item.status in ("MISSING", "MODIFIED") for item in results):
        raise typer.Exit(1)
