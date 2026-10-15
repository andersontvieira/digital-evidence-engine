"""Public synthetic portfolio demonstration command."""

from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy.exc import SQLAlchemyError

from evidence_engine.cli.evidence import fail
from evidence_engine.errors import EvidenceError


def demo(
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            help="New caller-owned directory for deterministic synthetic demo outputs.",
        ),
    ],
) -> None:
    """Run an offline synthetic pipeline without CASE_ROOT or external data."""
    from evidence_engine.demo import run_demo

    try:
        result = run_demo(output_dir)
    except (EvidenceError, OSError, SQLAlchemyError) as error:
        fail(error)
        return
    typer.echo(
        f"INGESTION: {result.sources_cataloged} originals; "
        f"{result.archive_members_cataloged} archive members"
    )
    typer.echo(
        f"TRANSFORMATION: {result.parsed_records} parsed records; "
        f"{result.normalized_events} normalized events"
    )
    typer.echo(
        f"OBSERVATION: {result.device_observations} device; {result.network_observations} network"
    )
    typer.echo(
        f"CORRELATION: {result.exact_candidates} exact groups; "
        f"{result.temporal_pairs} temporal pairs "
        f"({result.exact_signal_pairs} with exact signal, "
        f"{result.temporal_only_pairs} temporal-only)"
    )
    typer.echo(f"OUTPUT: {result.files_written} deterministic files")
