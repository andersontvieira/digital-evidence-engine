"""Validate packaging and the project's essential documented boundaries."""

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_python_and_src_layout() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
        config = tomllib.load(stream)
    assert config["project"]["requires-python"] == ">=3.12"
    assert config["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    assert config["project"]["scripts"]["dee"] == "evidence_engine.cli:app"
    assert config["tool"]["mypy"]["strict"] is True
    assert config["tool"]["ruff"]["target-version"] == "py312"


def test_preservation_decisions_exist() -> None:
    for name in (
        "0001-sqlite-local-storage",
        "0002-original-evidence-read-only",
        "0003-sha256-primary-content-hash",
        "0004-utc-canonical-time",
        "0005-observation-vs-interpretation",
        "0006-provenance-preserving-deduplication",
    ):
        content = (PROJECT_ROOT / "docs" / "adr" / f"{name}.md").read_text(encoding="utf-8")
        for section in ("Status", "Context", "Decision", "Consequences"):
            assert f"## {section}" in content
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Real case evidence must never be committed to this repository." in readme
