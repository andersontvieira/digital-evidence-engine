"""Public command-line interface for the local evidence foundation."""

import typer

from evidence_engine import __version__
from evidence_engine.cli.evidence import app as evidence_app
from evidence_engine.cli.normalize import app as normalize_app
from evidence_engine.cli.parse import app as parse_app

app = typer.Typer(
    help="Local engine for organizing and tracing digital evidence.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)
app.add_typer(evidence_app, name="evidence")
app.add_typer(parse_app, name="parse")
app.add_typer(normalize_app, name="normalize")


@app.callback()
def main() -> None:
    """Digital Evidence Engine — evidence foundation."""


@app.command()
def version() -> None:
    """Show the installed engine version."""
    typer.echo(__version__)
