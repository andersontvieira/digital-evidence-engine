"""Exercise only the commands delivered in Milestone 0."""

import pytest
from typer.testing import CliRunner

from evidence_engine import __version__
from evidence_engine.cli import app

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"], color=False)
    assert result.exit_code == 0
    assert "version" in result.output


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


@pytest.mark.parametrize("command", ["ingest", "search", "timeline", "media"])
def test_future_commands_are_not_exposed(command: str) -> None:
    result = runner.invoke(app, [command])
    assert result.exit_code == 2
    assert "No such command" in result.output
