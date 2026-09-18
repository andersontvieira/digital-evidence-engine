"""Exact candidate groups; only aggregate counts reach stdout."""

import json
from dataclasses import asdict

import typer
from sqlalchemy.exc import SQLAlchemyError

from evidence_engine.cli.evidence import CaseRoot, fail
from evidence_engine.correlation.service import correlate_exact
from evidence_engine.errors import EvidenceError

app = typer.Typer(
    help="Group exact technical matches without resolving identity.", no_args_is_help=True
)


@app.command("exact")
def exact(case_root: CaseRoot) -> None:
    """Create candidate groups supported by existing device/network observations."""
    try:
        summary = correlate_exact(case_root)
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(asdict(summary), sort_keys=True))
    if summary.errors:
        raise typer.Exit(1)
