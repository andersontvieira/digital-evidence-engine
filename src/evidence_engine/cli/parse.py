"""Small parser CLI; only counts and fixed technical messages reach the console."""

import json
from dataclasses import asdict

import typer

from evidence_engine.cli.evidence import CaseRoot, fail
from evidence_engine.errors import EvidenceError

app = typer.Typer(help="Extract observations from cataloged sources.", no_args_is_help=True)


@app.command("apple")
def apple(case_root: CaseRoot) -> None:
    """Parse only Apple device inventory, sign-on and media device CSV records."""
    from sqlalchemy.exc import SQLAlchemyError

    from evidence_engine.ingest.parsing.service import parse_apple

    try:
        summary = parse_apple(case_root)
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(asdict(summary), sort_keys=True))
    if summary.errors:
        raise typer.Exit(1)


@app.command("instagram")
def instagram(case_root: CaseRoot) -> None:
    """Parse the three supported Meta artifacts; preserve values and provenance."""
    from sqlalchemy.exc import SQLAlchemyError

    from evidence_engine.ingest.parsing.service import parse_instagram

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
    from sqlalchemy.exc import SQLAlchemyError

    from evidence_engine.ingest.parsing.service import parse_google

    try:
        summary = parse_google(case_root)
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(asdict(summary), sort_keys=True))
    if summary.errors:
        raise typer.Exit(1)
