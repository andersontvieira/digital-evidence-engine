import json
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from evidence_engine.cli import app

runner = CliRunner()


def command(name: str, root: Path):
    return runner.invoke(app, ["evidence", name, "--case-root", str(root)])


def test_full_synthetic_cli_flow(case_root: Path) -> None:
    original = case_root / "originals/synthetic-document.txt"
    original.write_bytes(b"synthetic document")
    with zipfile.ZipFile(case_root / "originals/synthetic-export.zip", "w") as archive:
        archive.writestr("synthetic-directory/synthetic-member.txt", b"synthetic member")
    result = command("ingest", case_root)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["files_added"] == 2
    result = command("manifest", case_root)
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.stdout)["files"]) == 2
    assert result.stdout == (case_root / "output/manifest.json").read_text()
    result = command("verify", case_root)
    assert result.exit_code == 0
    assert all(item["status"] == "OK" for item in json.loads(result.stdout))
    assert json.loads(command("ingest", case_root).stdout)["files_added"] == 0
    original.write_bytes(b"modified")
    result = command("verify", case_root)
    assert result.exit_code == 1 and "MODIFIED" in result.stdout
    original.unlink()
    result = command("verify", case_root)
    assert result.exit_code == 1 and "MISSING" in result.stdout


def test_untracked_alone_is_informational(case_root: Path) -> None:
    assert command("ingest", case_root).exit_code == 0
    (case_root / "originals/synthetic-new.txt").write_bytes(b"synthetic")
    result = command("verify", case_root)
    assert result.exit_code == 0 and "UNTRACKED" in result.stdout


def test_env_default_and_cli_override(case_root: Path) -> None:
    result = runner.invoke(app, ["evidence", "ingest"], env={"CASE_ROOT": str(case_root)})
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        app,
        ["evidence", "verify", "--case-root", str(case_root)],
        env={"CASE_ROOT": str(case_root / "nonexistent")},
    )
    assert result.exit_code == 0


def test_missing_config_and_technical_errors(case_root: Path) -> None:
    result = command("verify", case_root)
    assert result.exit_code == 2 and "ERROR" in result.output
    assert str(case_root) not in result.output
    assert runner.invoke(app, ["evidence", "--help"]).exit_code == 0


def test_limit_flags_produce_explicit_failure(case_root: Path) -> None:
    with zipfile.ZipFile(case_root / "originals/synthetic-export.zip", "w") as archive:
        archive.writestr("synthetic.txt", b"synthetic")
    result = runner.invoke(
        app, ["evidence", "ingest", "--case-root", str(case_root), "--max-file-bytes", "1"]
    )
    assert result.exit_code == 2 and "limit" in result.output
