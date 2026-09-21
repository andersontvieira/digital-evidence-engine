"""Read-only structured report support; no automatic file creation."""

import json
from dataclasses import asdict
from typing import Annotated

import typer
from sqlalchemy.exc import SQLAlchemyError

from evidence_engine.cli.evidence import CaseRoot, fail
from evidence_engine.errors import EvidenceError
from evidence_engine.reports.snapshot import report_snapshot

app = typer.Typer(help="Read-only technical report support data.", no_args_is_help=True)


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
