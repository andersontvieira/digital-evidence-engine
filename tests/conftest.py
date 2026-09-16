"""All evidence is generated synthetic content in temporary external cases."""

from pathlib import Path

import pytest


@pytest.fixture
def case_root(tmp_path: Path) -> Path:
    root = tmp_path / "synthetic-case"
    (root / "originals").mkdir(parents=True)
    return root
