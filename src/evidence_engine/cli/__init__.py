"""Public command-line interface for the local evidence foundation."""

import typer

from evidence_engine import __version__
from evidence_engine.cli.correlate import app as correlate_app
from evidence_engine.cli.evidence import app as evidence_app
from evidence_engine.cli.media import app as media_app
from evidence_engine.cli.normalize import app as normalize_app
from evidence_engine.cli.observe import app as observe_app
from evidence_engine.cli.parse import app as parse_app
from evidence_engine.cli.query import app as query_app

app = typer.Typer(
    help="Local engine for organizing and tracing digital evidence.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)
app.add_typer(evidence_app, name="evidence")
app.add_typer(parse_app, name="parse")
app.add_typer(normalize_app, name="normalize")
app.add_typer(observe_app, name="observe")
app.add_typer(correlate_app, name="correlate")
app.add_typer(query_app, name="query")
app.add_typer(media_app, name="media")


@app.callback()
def main() -> None:
    """Digital Evidence Engine — evidence foundation."""


@app.command()
def version() -> None:
    """Show the installed engine version."""
    typer.echo(__version__)
