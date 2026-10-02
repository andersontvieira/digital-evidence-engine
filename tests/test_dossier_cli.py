"""CLI contract, synthetic publication and runtime case/network sentinels."""

import ast
import inspect
import socket
import sqlite3

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.cli import dossier as cli
from evidence_engine.dossier import packaging as p
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic import paths
from tests.test_dossier_service import assert_no_staging, inputs

runner = CliRunner()


@pytest.mark.parametrize("args", [["dossier", "--help"], ["dossier", "assemble", "--help"]])
def test_cli_help(args):
    result = runner.invoke(app, args, color=False)
    assert result.exit_code == 0
    for forbidden in (
        "--case-root",
        "--force",
        "--overwrite",
        "--format",
        "--pdf",
        "--zip",
        "--budget",
        "--cleanup",
        "--retry",
        "--recursive",
        "--discover",
    ):
        assert forbidden not in result.output
    command = get_command(app).commands["dossier"].commands["assemble"]
    assert {option for param in command.params for option in param.opts} == {
        "--selection",
        "--output-dir",
    }
    assert all(param.required for param in command.params)


def test_cli_happy_path_no_case_db_network_or_path_leak(tmp_path, monkeypatch):
    config = inputs(tmp_path, full=True)
    names = []
    create = p.create_staging

    def record(destination):
        result = create(destination)
        names.append(result.path.name)
        return result

    def forbidden(*args, **kwargs):
        raise AssertionError("Forbidden case/database/network action")

    monkeypatch.setattr(p, "create_staging", record)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(paths.CasePaths, "load", forbidden)
    monkeypatch.setattr(paths, "discover", forbidden)
    monkeypatch.setenv("CASE_ROOT", str(tmp_path / "must-not-open"))
    result = runner.invoke(
        app, ["dossier", "assemble", "--selection", str(config[0]), "--output-dir", str(config[1])]
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == "DOSSIER_ASSEMBLY_OK\n" and result.stderr == ""
    assert config[1].is_dir()
    assert_no_staging(config[1])
    assert all(name not in result.output for name in names)


@pytest.mark.parametrize(
    "failure,code",
    [
        ("selection", "INVALID_SELECTION"),
        ("output", "OUTPUT_EXISTS"),
        ("publication", "PUBLICATION_FAILURE"),
        ("unexpected", "INTERNAL_ERROR"),
        ("unsafe_error", "INTERNAL_ERROR"),
    ],
)
def test_cli_errors_sanitized(tmp_path, monkeypatch, failure, code):
    config = inputs(tmp_path)
    if failure == "selection":
        config[0].write_bytes(b"invalid")
    elif failure == "output":
        config[1].mkdir()
    elif failure == "publication":
        monkeypatch.setattr(p, "_PLATFORM", "unsupported")
    else:

        def fail(**kwargs):
            if failure == "unsafe_error":
                raise EvidenceError("DOSSIER_INTERNAL_ERROR private path/hash/label")
            raise RuntimeError("private path/hash/label")

        monkeypatch.setattr(cli, "assemble_dossier", fail)
    result = runner.invoke(
        app, ["dossier", "assemble", "--selection", str(config[0]), "--output-dir", str(config[1])]
    )
    assert result.exit_code == 2
    assert result.stdout == "" and result.stderr == "ERROR: DOSSIER_" + code + "\n"


@pytest.mark.parametrize(
    "path", ["", ".", "..", "some/./path", "some//path", "some/path/", "//server/share"]
)
def test_cli_rejects_spelling_before_path_normalization(path):
    result = runner.invoke(
        app, ["dossier", "assemble", "--selection", path, "--output-dir", "target"]
    )
    assert result.exit_code == 2
    assert result.stderr == "ERROR: DOSSIER_INVALID_PATH\n"


@pytest.mark.parametrize(
    "args",
    [[], ["--selection", "synthetic.json"], ["--output-dir", "new"], ["--case-root", "synthetic"]],
)
def test_required_and_only_explicit_options(args):
    result = runner.invoke(app, ["dossier", "assemble", *args])
    assert result.exit_code == 2


def test_cli_import_boundary():
    allowed = {
        "pathlib",
        "typing",
        "typer",
        "typer.core",
        "evidence_engine.dossier.pdf_worker",
        "evidence_engine.dossier.pdf_service",
        "evidence_engine.dossier.service",
        "evidence_engine.errors",
    }
    for node in ast.walk(ast.parse(inspect.getsource(cli))):
        if isinstance(node, ast.ImportFrom):
            assert node.module in allowed
        elif isinstance(node, ast.Import):
            assert {a.name for a in node.names} <= allowed
