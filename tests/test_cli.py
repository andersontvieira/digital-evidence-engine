"""Exercise delivered command discovery and keep future commands unavailable."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from evidence_engine import __version__
from evidence_engine.cli import app

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"], color=False)
    assert result.exit_code == 0
    assert "version" in result.output
    assert "Local, reproducible Python data-processing engine" in result.output


def test_root_cli_does_not_eagerly_import_sqlalchemy(tmp_path: Path) -> None:
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import evidence_engine.cli; print(int('sqlalchemy' in sys.modules))",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0"


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


@pytest.mark.parametrize("command", ["ingest", "search", "timeline"])
def test_future_commands_are_not_exposed(command: str) -> None:
    result = runner.invoke(app, [command])
    assert result.exit_code == 2
    assert "No such command" in result.output


@pytest.mark.parametrize("arguments", [["media", "--help"], ["media", "inventory", "--help"]])
def test_media_help(arguments: list[str]) -> None:
    result = runner.invoke(app, arguments, color=False)
    assert result.exit_code == 0
    assert "inventory" in result.output
