"""Atomic device/network observations; stdout contains aggregate counts only."""

import json
from dataclasses import asdict

import typer

from evidence_engine.cli.evidence import CaseRoot, fail
from evidence_engine.errors import EvidenceError

app = typer.Typer(
    help="Derive atomic device/network facts from ParsedRecords.", no_args_is_help=True
)


@app.command("device-network")
def device_network(case_root: CaseRoot) -> None:
    """Observe explicit technical fields without correlating identities."""
    from sqlalchemy.exc import SQLAlchemyError

    from evidence_engine.observations.service import observe_device_network

    try:
        summary = observe_device_network(case_root)
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(asdict(summary), sort_keys=True))
    if summary.errors:
        raise typer.Exit(1)
