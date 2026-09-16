"""Minimal public command-line interface."""

import typer

from evidence_engine import __version__

app = typer.Typer(
    help="Local engine for organizing and tracing digital evidence.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)


@app.callback()
def main() -> None:
    """Digital Evidence Engine — architecture foundation."""


@app.command()
def version() -> None:
    """Show the installed engine version."""
    typer.echo(__version__)
