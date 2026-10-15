"""Public demo tests use only generated synthetic inputs and temporary state."""

import hashlib
import json
import re
import socket
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

import evidence_engine.demo as demo_module
from evidence_engine.cli import app
from evidence_engine.demo import OUTPUT_FILES, _synthetic_sources, run_demo

runner = CliRunner()


@pytest.fixture
def completed_demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("demo must not use the network")

    monkeypatch.setattr(socket, "create_connection", no_network)
    output = tmp_path / "portfolio-demo"
    result = runner.invoke(app, ["demo", "--output-dir", str(output)])
    assert result.exit_code == 0, result.output
    return output, result


def test_sources_are_generated_and_conspicuously_synthetic() -> None:
    sources = _synthetic_sources()
    assert set(sources) == {
        "profile_activity.json",
        "ChangeHistory.html",
        "Informações da Conta Apple e do dispositivo/Apple ID SignOn Information.csv",
    }
    assert all(b"SYNTHETIC" in content for content in sources.values())
    combined = b"\n".join(sources.values())
    assert b"example.invalid" in combined
    assert b"192.0.2.10" in combined and b"203.0.113.77" in combined


def test_cli_output_allowlist_checksums_privacy_and_counts(
    completed_demo: tuple[Path, object], tmp_path: Path
) -> None:
    output, invocation = completed_demo
    assert {path.name for path in output.iterdir()} == set(OUTPUT_FILES)
    assert not any(path.name in {"database", "working", "originals"} for path in output.iterdir())

    combined = b"".join((output / name).read_bytes() for name in OUTPUT_FILES)
    for forbidden in (str(tmp_path).encode(), str(Path.cwd()).encode(), b"evidence.db"):
        assert forbidden not in combined
    assert re.search(rb"\b[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-", combined) is None

    sums = {}
    for line in (output / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    assert set(sums) == set(OUTPUT_FILES) - {"SHA256SUMS.txt"}
    assert all(
        hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
        for name, digest in sums.items()
    )

    summary = json.loads((output / "pipeline-summary.json").read_text(encoding="ascii"))
    counts = summary["stages"]
    expected_lines = (
        f"INGESTION: {counts['ingestion']['cataloged_originals']} originals; "
        f"{counts['ingestion']['cataloged_archive_members']} archive members",
        f"TRANSFORMATION: {counts['transformation']['parsed_records']} parsed records; "
        f"{counts['transformation']['normalized_events']} normalized events",
        f"OBSERVATION: {counts['observation']['device_observations']} device; "
        f"{counts['observation']['network_observations']} network",
        f"CORRELATION: {counts['correlation']['exact_candidates']} exact groups; "
        f"{counts['correlation']['temporal_pairs']} temporal pairs "
        f"({counts['correlation']['temporal_pairs_with_exact_signal']} with exact signal, "
        f"{counts['correlation']['temporal_pairs_without_exact_signal']} temporal-only)",
        f"OUTPUT: {len(OUTPUT_FILES)} deterministic files",
    )
    assert invocation.output.splitlines() == list(expected_lines)


def test_independent_runs_have_identical_public_outputs(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    run_demo(first)
    run_demo(second)
    assert {name: (first / name).read_bytes() for name in OUTPUT_FILES} == {
        name: (second / name).read_bytes() for name in OUTPUT_FILES
    }


def test_existing_output_is_not_touched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("caller-owned", encoding="utf-8")

    def forbidden_pipeline(case_root: Path):
        raise AssertionError(f"pipeline unexpectedly started: {case_root.name}")

    monkeypatch.setattr(demo_module, "_pipeline", forbidden_pipeline)
    result = runner.invoke(app, ["demo", "--output-dir", str(output)])
    assert result.exit_code == 2
    assert result.output == "ERROR: Demo output directory already exists\n"
    assert sentinel.read_text(encoding="utf-8") == "caller-owned"
    assert list(output.iterdir()) == [sentinel]


def test_temporary_case_is_external_and_cleaned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actual = tempfile.TemporaryDirectory
    roots: list[Path] = []

    def tracked(*args: object, **kwargs: object):
        temporary = actual(*args, **kwargs)
        roots.append(Path(temporary.name).resolve())
        return temporary

    monkeypatch.setattr(demo_module.tempfile, "TemporaryDirectory", tracked)
    run_demo(tmp_path / "output")
    project = Path(__file__).resolve().parents[1]
    assert roots and all(not root.is_relative_to(project) for root in roots)
    assert all(not root.exists() for root in roots)
    assert not (project / "database").exists()
    assert not (project / "working").exists()
