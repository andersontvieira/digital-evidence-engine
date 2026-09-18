"""Canonical event normalization; only aggregate counts reach stdout."""

import json
from dataclasses import asdict

import typer
from sqlalchemy.exc import SQLAlchemyError

from evidence_engine.cli.evidence import CaseRoot, fail
from evidence_engine.errors import EvidenceError
from evidence_engine.normalization.service import normalize_events

app = typer.Typer(
    help="Derive canonical events from cataloged ParsedRecords.", no_args_is_help=True
)


@app.command("events")
def events(case_root: CaseRoot) -> None:
    """Normalize supported observations without correlating identities."""
    try:
        summary = normalize_events(case_root)
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(asdict(summary), sort_keys=True))
    if summary.errors:
        raise typer.Exit(1)
