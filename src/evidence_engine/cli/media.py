"""Read-only byte inspection of Foundation inventory, with no persistent media entities."""

import json
from dataclasses import asdict
from typing import Annotated

import typer
from sqlalchemy.exc import SQLAlchemyError

from evidence_engine.cli.evidence import CaseRoot, fail
from evidence_engine.errors import EvidenceError
from evidence_engine.media.contents import media_contents
from evidence_engine.media.inventory import inventory_media
from evidence_engine.media.perceptual import perceptual_hashes
from evidence_engine.media.source_links import query_source_links

app = typer.Typer(help="Read-only inventory of cataloged media bytes.", no_args_is_help=True)


@app.command("source-links")
def source_links(
    case_root: CaseRoot,
    start: Annotated[str, typer.Option(help="Inclusive UTC bound ending in Z.")],
    end: Annotated[str, typer.Option(help="Exclusive UTC bound ending in Z.")],
    platform: Annotated[str | None, typer.Option(help="Exact platform filter.")] = None,
    event_kind: Annotated[str | None, typer.Option(help="Exact event kind filter.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=5000)] = 500,
) -> None:
    """Resolve approved persisted source references to verified exact archive members."""
    try:
        result = query_source_links(
            case_root, start=start, end=end, platform=platform, event_kind=event_kind, limit=limit
        )
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    payload = json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    typer.echo((payload + "\n").encode("ascii"), nl=False)


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
