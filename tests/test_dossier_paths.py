"""Portable path policy and synthetic filesystem alias rejection."""

import os
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from evidence_engine.dossier import packaging as p
from evidence_engine.errors import EvidenceError
from tests.test_dossier_packaging import capture, setup_inputs


@pytest.mark.parametrize(
    "reference",
    [
        "/absolute",
        "C:/drive",
        "//server/share",
        "a\\b",
        "../escape",
        "a/../b",
        "./a",
        "a//b",
        "a/",
        "a\0b",
        "a\nb",
        "file:ads",
        "bad<",
        "bad>",
        'bad"',
        "bad|",
        "bad?",
        "bad*",
        "end.",
        "end ",
        "CON",
        "lpt1.txt",
        "COM¹",
        "e\u0301",
        "https://example.invalid/a",
        "originals/a",
        "ORIGINALS/a",
        "working/a",
        "Working/a",
        "evidence.db",
        "EVIDENCE.DB",
    ],
)
def test_manual_reference_revalidated_before_open(tmp_path, monkeypatch, reference):
    path, selected, root = setup_inputs(tmp_path)
    inputs = (
        replace(selected.canonical_inputs[0], input_reference=reference),
        *selected.canonical_inputs[1:],
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("payload opened")

    monkeypatch.setattr(p, "original_reader", forbidden)
    with pytest.raises(EvidenceError, match="^DOSSIER_(INVALID_PATH|RESOURCE_LIMIT)$"):
        capture((path, replace(selected, canonical_inputs=inputs), root))


@pytest.mark.parametrize("area", ["originals", "Working", "evidence.db"])
def test_selection_path_prohibited_before_open(tmp_path, monkeypatch, area):
    def forbidden(*args, **kwargs):
        raise AssertionError("opened prohibited path")

    monkeypatch.setattr(p, "original_reader", forbidden)
    with pytest.raises(EvidenceError, match="^DOSSIER_INVALID_PATH$"):
        p.read_selection_bytes_stable(tmp_path / area / "selection.json")


@pytest.mark.parametrize("kind", ["symlink", "parent_link", "hardlink", "directory", "fifo"])
def test_unsafe_file_types(tmp_path, kind):
    path, selected, root = setup_inputs(tmp_path)
    target = path.parent / selected.canonical_inputs[0].input_reference
    other = tmp_path / "other"
    other.write_bytes(b"synthetic")
    target.unlink()
    if kind == "symlink":
        try:
            target.symlink_to(other)
        except OSError:
            pytest.skip("Host cannot create symlinks")
    elif kind == "hardlink":
        os.link(other, target)
    elif kind == "directory":
        target.mkdir()
    elif kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("FIFO requires POSIX")
        os.mkfifo(target)
    else:
        replacement = tmp_path / "linked-directory"
        target.parent.rename(replacement)
        try:
            target.parent.symlink_to(replacement, target_is_directory=True)
        except OSError:
            pytest.skip("Host cannot create directory symlinks")
    with pytest.raises(EvidenceError, match="^DOSSIER_UNSAFE_FILE_TYPE$"):
        capture((path, selected, root))
    assert list(root.iterdir()) == []
    assert other.read_bytes() == b"synthetic"


@pytest.mark.skipif(os.name != "nt", reason="Real Windows junction requires Windows")
def test_real_windows_junction(tmp_path):
    path, selected, root = setup_inputs(tmp_path)
    parent = path.parent / "inputs"
    moved = tmp_path / "junction-target"
    parent.rename(moved)
    sentinel = moved / "external-sentinel"
    sentinel.write_bytes(b"synthetic external target untouched")
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(parent), str(moved)], capture_output=True
    )
    if result.returncode:
        pytest.skip("Host cannot create junctions")
    assert parent.is_junction()
    with pytest.raises(EvidenceError, match="^DOSSIER_UNSAFE_FILE_TYPE$"):
        capture((path, selected, root))

    assert sentinel.read_bytes() == b"synthetic external target untouched"


@pytest.mark.parametrize("mode", ["same", "inside", "outside"])
def test_root_overlap(tmp_path, mode):
    path, selected, root = setup_inputs(tmp_path)
    if mode == "same":
        root = path.parent
    elif mode == "inside":
        root = path.parent / "capture"
        root.mkdir()
    else:
        root = tmp_path
    with pytest.raises(EvidenceError, match="^DOSSIER_INVALID_PATH$"):
        capture((path, selected, root))


def test_self_selection(tmp_path):
    path, selected, root = setup_inputs(tmp_path)
    inputs = (
        replace(selected.canonical_inputs[0], input_reference=path.name),
        *selected.canonical_inputs[1:],
    )
    with pytest.raises(EvidenceError, match="^DOSSIER_INVALID_PATH$"):
        capture((path, replace(selected, canonical_inputs=inputs), root))


@pytest.mark.parametrize(
    "paths",
    [
        ["a/file", "a/file"],
        ["a/File", "a/file"],
        ["A/a", "a/b"],
        ["a", "a/b"],
        ["human/dossier.md"],
        ["integrity/manifest.json"],
        ["../outside"],
    ],
)
def test_destination_collisions(paths):
    with pytest.raises(EvidenceError, match="^DOSSIER_INVALID_PATH$"):
        p.validate_destination_set(paths)


def test_existing_destination_is_not_overwritten(tmp_path):
    config = setup_inputs(tmp_path)
    target = config[2] / "technical/canonical/consolidated-report.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"existing")
    with pytest.raises(EvidenceError, match="^DOSSIER_STAGING_FAILURE$"):
        capture(config)
    assert target.read_bytes() == b"existing"


def test_containment_resolution_disagreement(tmp_path, monkeypatch):
    config = setup_inputs(tmp_path)
    actual = Path.resolve
    source = config[0].parent / config[1].canonical_inputs[0].input_reference

    def changed(self, **kwargs):
        return tmp_path / "escaped" if self == source else actual(self, **kwargs)

    monkeypatch.setattr(Path, "resolve", changed)
    with pytest.raises(EvidenceError, match="^DOSSIER_PATH_ESCAPE$"):
        capture(config)


def test_generic_reparse_attribute_guard_before_resolve(tmp_path, monkeypatch):
    config = setup_inputs(tmp_path)
    source = config[0].parent / config[1].canonical_inputs[0].input_reference
    actual_lstat, actual_resolve = Path.lstat, Path.resolve

    def reparse(self, *args, **kwargs):
        info = actual_lstat(self, *args, **kwargs)
        if self == source:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    def resolve(self, *args, **kwargs):
        assert self != source
        return actual_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", reparse)
    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(EvidenceError, match="^DOSSIER_UNSAFE_FILE_TYPE$"):
        capture(config)


@pytest.mark.skipif(os.name != "posix", reason="Descriptor-relative writer test requires POSIX")
def test_parent_swap_cannot_redirect_payload_write(tmp_path, monkeypatch):
    config = setup_inputs(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    parent = config[2] / "technical/canonical"
    actual = os.open
    swapped = False

    def race(path, flags, *args, **kwargs):
        nonlocal swapped
        if flags & os.O_CREAT and not swapped:
            swapped = True
            parent.rename(parent.with_name("displaced"))
            parent.symlink_to(external, target_is_directory=True)
        return actual(path, flags, *args, **kwargs)

    monkeypatch.setattr(p.os, "open", race)
    with pytest.raises(EvidenceError, match="^DOSSIER_INPUT_CHANGED$"):
        capture(config)
    assert swapped and list(external.iterdir()) == []


@pytest.mark.parametrize(
    "stage,code", [("foundation", "UNSAFE_FILE_TYPE"), ("resolve", "PATH_ESCAPE")]
)
def test_preflight_errors_are_sanitized(tmp_path, monkeypatch, stage, code):
    config = setup_inputs(tmp_path)

    def fail(*args, **kwargs):
        if stage == "foundation":
            raise EvidenceError("private source path")
        raise RuntimeError("private symlink path")

    if stage == "foundation":
        monkeypatch.setattr(p, "check_path", fail)
    else:
        monkeypatch.setattr(Path, "resolve", fail)
    with pytest.raises(EvidenceError, match=f"^DOSSIER_{code}$"):
        capture(config)


@pytest.mark.skipif(os.name != "posix", reason="Descriptor-relative unlink requires POSIX")
def test_provisional_unlink_cannot_follow_swapped_parent(tmp_path, monkeypatch):
    from tests.test_dossier_packaging import full_document

    config = setup_inputs(tmp_path, document=full_document())
    batch = capture(config)
    external = tmp_path / "external"
    external.mkdir()
    unrelated = external / "visual.jpg"
    unrelated.write_bytes(b"must remain")
    parent = config[2] / "exhibits/visual"
    actual = os.unlink
    swapped = False

    def race(path, *args, **kwargs):
        nonlocal swapped
        if path == "visual.jpg" and kwargs.get("dir_fd") is not None:
            swapped = True
            parent.rename(parent.with_name("displaced"))
            parent.symlink_to(external, target_is_directory=True)
        return actual(path, *args, **kwargs)

    monkeypatch.setattr(p.os, "unlink", race)
    # After the parent is swapped, subsequent rechecks must reject the set.
    with pytest.raises(EvidenceError, match="^DOSSIER_(UNSAFE_FILE_TYPE|INPUT_CHANGED)$"):
        p.resolve_captured_inputs(batch, image_formats={"visual": "png"})
    assert swapped and unrelated.read_bytes() == b"must remain"
