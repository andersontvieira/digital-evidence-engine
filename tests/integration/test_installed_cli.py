"""Run installed entry points from an empty directory, without source-path tricks."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from evidence_engine import __version__


@pytest.mark.parametrize("args", [["--help"], ["version"]])
@pytest.mark.parametrize("launcher", [["dee"], [sys.executable, "-m", "evidence_engine"]])
def test_installed_cli_has_no_case_side_effects(
    tmp_path: Path, launcher: list[str], args: list[str]
) -> None:
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run(
        [*launcher, *args],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    if args == ["version"]:
        assert result.stdout.strip() == __version__
    else:
        assert "version" in result.stdout
    assert list(tmp_path.iterdir()) == []
