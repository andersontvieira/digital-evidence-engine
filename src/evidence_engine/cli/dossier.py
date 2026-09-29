"""Explicit dossier assembly CLI; no case option, discovery or diagnostic payload."""

from pathlib import Path
from typing import Annotated

import typer

from evidence_engine.dossier.service import assemble_dossier, safe_error_code
from evidence_engine.errors import EvidenceError

app = typer.Typer(
    help="Assemble an explicitly selected dossier into a new directory.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


def _explicit_path(value: str) -> Path:
    # Check the spelling before Path discards dot/empty components. Native
    # Windows separators are permitted for CLI host paths, never input_reference.
    text = value.replace("\\", "/")
    parts = text.split("/")
    if text.startswith("/"):
        parts = parts[1:]
    if not value or any(part in ("", ".", "..") for part in parts):
        raise EvidenceError("DOSSIER_INVALID_PATH")
    return Path(value)


@app.command("assemble")
def assemble(
    selection: Annotated[str, typer.Option("--selection", help="Explicit local selection JSON.")],
    output_dir: Annotated[
        str, typer.Option("--output-dir", help="New directory under an existing parent.")
    ],
) -> None:
    try:
        assemble_dossier(
            selection_path=_explicit_path(selection), output_dir=_explicit_path(output_dir)
        )
    except Exception as error:
        # Bytes preserve the contracted LF even on native Windows text streams.
        typer.echo(("ERROR: " + safe_error_code(error) + "\n").encode("ascii"), err=True, nl=False)
        raise typer.Exit(2) from None
    typer.echo(b"DOSSIER_ASSEMBLY_OK\n", nl=False)
