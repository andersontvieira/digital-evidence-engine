"""Public command-line interface for the local data-processing engine."""

import typer

from evidence_engine import __version__
from evidence_engine.cli.correlate import app as correlate_app
from evidence_engine.cli.demo import demo
from evidence_engine.cli.dossier import app as dossier_app
from evidence_engine.cli.evidence import app as evidence_app
from evidence_engine.cli.media import app as media_app
from evidence_engine.cli.normalize import app as normalize_app
from evidence_engine.cli.observe import app as observe_app
from evidence_engine.cli.parse import app as parse_app
from evidence_engine.cli.query import app as query_app
from evidence_engine.cli.report import app as report_app

app = typer.Typer(
    help=(
        "Local, reproducible Python data-processing engine for provenance-preserving "
        "digital evidence."
    ),
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
app.add_typer(report_app, name="report")
app.add_typer(dossier_app, name="dossier")
app.command("demo")(demo)


@app.callback()
def main() -> None:
    """Process supported digital datasets locally with explicit provenance."""


@app.command()
def version() -> None:
    """Show the installed engine version."""
    typer.echo(__version__)
