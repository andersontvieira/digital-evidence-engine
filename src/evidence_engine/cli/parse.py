"""Small parser CLI; only counts and fixed technical messages reach the console."""

import json
from dataclasses import asdict

import typer
from sqlalchemy.exc import SQLAlchemyError

from evidence_engine.cli.evidence import CaseRoot, fail
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.parsing.service import parse_google, parse_instagram

app = typer.Typer(help="Extract observations from cataloged sources.", no_args_is_help=True)


@app.command("instagram")
def instagram(case_root: CaseRoot) -> None:
    """Parse the three supported Meta artifacts; preserve values and provenance."""
    try:
        summary = parse_instagram(case_root)
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(asdict(summary), sort_keys=True))
    if summary.errors:
        raise typer.Exit(1)


@app.command("google")
def google(case_root: CaseRoot) -> None:
    """Parse only SubscriberInfo and ChangeHistory Takeout tables."""
    try:
        summary = parse_google(case_root)
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(asdict(summary), sort_keys=True))
    if summary.errors:
        raise typer.Exit(1)
