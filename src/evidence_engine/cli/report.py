"""Read-only structured report support; no automatic file creation."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

import typer

from evidence_engine.cli.evidence import CaseRoot, fail
from evidence_engine.errors import EvidenceError

app = typer.Typer(help="Read-only technical report support data.", no_args_is_help=True)


def report_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Load the database-backed report implementation only when invoked."""
    from evidence_engine.reports.snapshot import report_snapshot as implementation

    return implementation(*args, **kwargs)


@app.command("snapshot")
def snapshot(
    case_root: CaseRoot,
    start: Annotated[
        str | None, typer.Option(help="Inclusive UTC Z bound; requires end/radius.")
    ] = None,
    end: Annotated[
        str | None, typer.Option(help="Exclusive UTC Z bound; requires start/radius.")
    ] = None,
    max_delta_seconds: Annotated[int | None, typer.Option(min=1, max=86400)] = None,
    platform: Annotated[str | None, typer.Option(help="Window event platform filter.")] = None,
    event_kind: Annotated[str | None, typer.Option(help="Window event kind filter.")] = None,
) -> None:
    """Emit deterministic JSON to stdout, with zero or one analysis window."""
    from sqlalchemy.exc import SQLAlchemyError

    try:
        result = report_snapshot(
            case_root,
            start=start,
            end=end,
            max_delta_seconds=max_delta_seconds,
            platform=platform,
            event_kind=event_kind,
        )
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    payload = json.dumps(asdict(result), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    typer.echo((payload + "\n").encode("ascii"), nl=False)


@app.command("consolidated")
def consolidated(
    snapshots: Annotated[
        list[Path],
        typer.Option(
            "--snapshot", help="External 8A1 JSON; repeat up to 20 times, with exactly one anchor."
        ),
    ],
) -> None:
    """Render deterministic pt-BR Markdown from snapshots only, without CASE_ROOT."""
    from evidence_engine.reports.consolidated import consolidated_report

    try:
        content = consolidated_report(snapshots)
    except EvidenceError as error:
        fail(error)
        return
    typer.echo(content.encode("utf-8"), nl=False)
