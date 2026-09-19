"""Read-only byte inspection of Foundation inventory, with no persistent media entities."""

import json
from dataclasses import asdict

import typer
from sqlalchemy.exc import SQLAlchemyError

from evidence_engine.cli.evidence import CaseRoot, fail
from evidence_engine.errors import EvidenceError
from evidence_engine.media.inventory import inventory_media

app = typer.Typer(help="Read-only inventory of cataloged media bytes.", no_args_is_help=True)


@app.command("inventory")
def inventory(case_root: CaseRoot) -> None:
    """Verify cataloged size/SHA-256, recognize signatures and group exact duplicates."""
    try:
        result = inventory_media(case_root)
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(asdict(result), ensure_ascii=True, sort_keys=True, separators=(",", ":")))
