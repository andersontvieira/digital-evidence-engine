"""Read-only byte inspection of Foundation inventory, with no persistent media entities."""

import json
from dataclasses import asdict

import typer
from sqlalchemy.exc import SQLAlchemyError

from evidence_engine.cli.evidence import CaseRoot, fail
from evidence_engine.errors import EvidenceError
from evidence_engine.media.contents import media_contents
from evidence_engine.media.inventory import inventory_media
from evidence_engine.media.perceptual import perceptual_hashes

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


@app.command("perceptual-hash")
def perceptual_hash(case_root: CaseRoot) -> None:
    """Compute DERIVED pHash once per JPEG/PNG content; no similarity interpretation."""
    try:
        result = perceptual_hashes(case_root)
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    payload = json.dumps(asdict(result), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    typer.echo((payload + "\n").encode("ascii"), nl=False)
    if result.failed_count or result.unsupported_count:
        raise typer.Exit(1)


@app.command("contents")
def contents(case_root: CaseRoot) -> None:
    """Project verified media into exact SHA-256 contents, preserving every occurrence."""
    try:
        result = media_contents(case_root)
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(asdict(result), ensure_ascii=True, sort_keys=True, separators=(",", ":")))
