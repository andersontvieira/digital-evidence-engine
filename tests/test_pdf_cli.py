"""Closed PDF command syntax and exact channels; no caller paths in errors."""

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.dossier import pdf_service as service
from evidence_engine.dossier import pdf_worker as worker
from evidence_engine.errors import EvidenceError

runner = CliRunner()
VALID = ["--input-package", "/synthetic-input", "--output-dir", "/synthetic-output"]


def invoke(args):
    return runner.invoke(app, ["dossier", "pdf", *args], color=False)


def assert_failure(result, code="INVALID_PACKAGE"):
    assert result.exit_code == 2
    assert result.stdout_bytes == b""
    assert result.stderr_bytes == ("ERROR: DOSSIER_PDF_" + code + "\n").encode()


@pytest.mark.parametrize(
    "args",
    [
        [],
        VALID[:2],
        VALID[2:],
        [*VALID, "--input-package", "/duplicate"],
        [*VALID, "--output-dir=/duplicate"],
        [*VALID, "--unknown"],
        [*VALID, "position"],
        ["/synthetic-input", "/synthetic-output"],
        ["--input-package=", *VALID[2:]],
        ["--input-package", "", *VALID[2:]],
        [*VALID[:2], "--output-dir"],
        [*VALID[:2], "--output-dir="],
        ["-i", "/synthetic-input", *VALID[2:]],
        ["--input-package", "-", *VALID[2:]],
        ["--input-package", "--output-dir", "/synthetic-output"],
        ["--input-package", "/private/../source", *VALID[2:]],
        ["--input-package", "/private//source", *VALID[2:]],
        ["--help", "--unknown"],
    ],
)
def test_invalid_syntax_never_calls_service(args, monkeypatch):
    monkeypatch.setattr(
        service, "export_dossier_pdf", lambda **kwargs: pytest.fail("service reached")
    )
    assert_failure(invoke(args))


@pytest.mark.parametrize(
    "args", [VALID, ["--output-dir=/synthetic-output", "--input-package=/synthetic-input"]]
)
def test_exact_success_and_path_delivery(args, monkeypatch):
    calls = []
    monkeypatch.setattr(service, "export_dossier_pdf", lambda **kwargs: calls.append(kwargs))
    result = invoke(args)
    assert result.exit_code == 0 and result.stdout_bytes == b"DOSSIER_PDF_OK\n"
    assert result.stderr_bytes == b"" and len(calls) == 1
    assert set(calls[0]) == {"input_package", "output_dir"}


@pytest.mark.parametrize("code", sorted(worker.SAFE_CODES))
def test_public_error_allowlist_exact_channels(code, monkeypatch):
    def failure(**kwargs):
        raise EvidenceError(code)

    monkeypatch.setattr(service, "export_dossier_pdf", failure)
    assert_failure(invoke(VALID), code.removeprefix("DOSSIER_PDF_"))


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("private path/hash/payload"),
        EvidenceError("DOSSIER_PDF_INPUT_CHANGED private"),
        MemoryError(),
    ],
)
def test_unexpected_callback_is_sanitized(error, monkeypatch):
    def failure(**kwargs):
        raise error

    monkeypatch.setattr(service, "export_dossier_pdf", failure)
    assert_failure(
        invoke(VALID), "RESOURCE_LIMIT" if isinstance(error, MemoryError) else "INTERNAL_ERROR"
    )


def test_help_and_exact_command_options(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("help accessed data/runtime")

    monkeypatch.setattr(service, "export_dossier_pdf", forbidden)
    monkeypatch.setattr(service, "_runtime_preflight", forbidden)
    monkeypatch.setattr(service, "_prepare_paths", forbidden)
    result = invoke(["--help"])
    assert result.exit_code == 0 and result.stderr_bytes == b""
    command = get_command(app).commands["dossier"].commands["pdf"]
    assert {option for param in command.params for option in param.opts} == {
        "--input-package",
        "--output-dir",
    }
    assert all(param.required for param in command.params)
