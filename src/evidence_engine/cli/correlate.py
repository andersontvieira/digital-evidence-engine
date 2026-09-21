"""Persisted exact groups and separate read-only temporal pair candidates."""

import json
from dataclasses import asdict
from typing import Annotated

import typer
from sqlalchemy.exc import SQLAlchemyError

from evidence_engine.cli.evidence import CaseRoot, fail
from evidence_engine.correlation.overlap import temporal_exact_overlap
from evidence_engine.correlation.service import correlate_exact
from evidence_engine.correlation.temporal import temporal_candidates
from evidence_engine.errors import EvidenceError

app = typer.Typer(
    help="Exact groups and read-only temporal candidates, without resolving identity.",
    no_args_is_help=True,
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


@app.command("temporal-candidates")
def temporal(
    case_root: CaseRoot,
    start: Annotated[str, typer.Option(help="Required inclusive UTC bound ending in Z.")],
    end: Annotated[str, typer.Option(help="Required exclusive UTC bound ending in Z.")],
    max_delta_seconds: Annotated[
        int,
        typer.Option(
            min=1, max=86400, help="Required retrieval bound, not an evidentiary threshold."
        ),
    ],
    platform: Annotated[str | None, typer.Option(help="Exact event platform filter.")] = None,
    event_kind: Annotated[str | None, typer.Option(help="Exact event kind filter.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=10000)] = 1000,
) -> None:
    """Return DERIVED current-event time proximity pairs; no conclusive correlation."""
    try:
        result = temporal_candidates(
            case_root,
            start=start,
            end=end,
            max_delta_seconds=max_delta_seconds,
            platform=platform,
            event_kind=event_kind,
            limit=limit,
        )
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    _emit_json(asdict(result))


def _emit_json(value: object) -> None:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    typer.echo((payload + "\n").encode("ascii"), nl=False)


@app.command("temporal-exact-overlap")
def overlap(
    case_root: CaseRoot,
    start: Annotated[str, typer.Option(help="Required inclusive UTC bound ending in Z.")],
    end: Annotated[str, typer.Option(help="Required exclusive UTC bound ending in Z.")],
    max_delta_seconds: Annotated[
        int,
        typer.Option(
            min=1, max=86400, help="Required retrieval bound, not an evidentiary threshold."
        ),
    ],
    platform: Annotated[str | None, typer.Option(help="Exact event platform filter.")] = None,
    event_kind: Annotated[str | None, typer.Option(help="Exact event kind filter.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=10000)] = 1000,
) -> None:
    """Enrich the temporal prefix with shared persisted exact candidate IDs."""
    try:
        result = temporal_exact_overlap(
            case_root,
            start=start,
            end=end,
            max_delta_seconds=max_delta_seconds,
            platform=platform,
            event_kind=event_kind,
            limit=limit,
        )
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    _emit_json(asdict(result))
