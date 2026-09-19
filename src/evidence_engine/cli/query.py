"""Read-only current timeline with deterministic, restricted JSON output."""

import json
from dataclasses import asdict
from typing import Annotated

import typer
from sqlalchemy.exc import SQLAlchemyError

from evidence_engine.cli.evidence import CaseRoot, fail
from evidence_engine.errors import EvidenceError
from evidence_engine.query.timeline import query_timeline

app = typer.Typer(
    help="Read-only queries of explicitly selected current events.", no_args_is_help=True
)


@app.command("timeline")
def timeline(
    case_root: CaseRoot,
    start: Annotated[str | None, typer.Option(help="Inclusive UTC bound ending in Z.")] = None,
    end: Annotated[str | None, typer.Option(help="Exclusive UTC bound ending in Z.")] = None,
    platform: Annotated[str | None, typer.Option(help="Exact platform filter.")] = None,
    event_kind: Annotated[str | None, typer.Option(help="Exact event kind filter.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=10000)] = 1000,
) -> None:
    """Return dated current events; undated counts obey platform/kind, not time bounds."""
    try:
        result = query_timeline(
            case_root, start=start, end=end, platform=platform, event_kind=event_kind, limit=limit
        )
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(json.dumps(asdict(result), ensure_ascii=True, sort_keys=True, separators=(",", ":")))
