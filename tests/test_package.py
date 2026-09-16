"""The installed package is the distribution users invoke."""

import importlib.metadata

import evidence_engine


def test_package_and_distribution_share_version() -> None:
    assert evidence_engine.__version__ == "0.1.0"
    assert importlib.metadata.version("digital-evidence-engine") == evidence_engine.__version__


def test_console_entry_point() -> None:
    distribution = importlib.metadata.distribution("digital-evidence-engine")
    entry = next(item for item in distribution.entry_points if item.name == "dee")
    assert entry.group == "console_scripts"
    assert entry.value == "evidence_engine.cli:app"
