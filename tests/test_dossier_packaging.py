"""Entirely synthetic selected files; no case roots or catalog access."""

import ast
import hashlib
import inspect
import json
import sqlite3
from dataclasses import fields
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from evidence_engine.dossier import packaging as p
from evidence_engine.dossier import validation as v
from evidence_engine.dossier.projection import SelectionMetadata
from evidence_engine.dossier.rendering import render_selection_metadata
from evidence_engine.errors import EvidenceError
from tests.test_dossier_selection import item, minimal, parse


def image_bytes(fmt="PNG", size=(3, 2), **kwargs):
    stream = BytesIO()
    Image.new("RGB", size, (12, 34, 56)).save(stream, format=fmt, **kwargs)
    return stream.getvalue()


def setup_inputs(tmp_path, *, document=None, payloads=None):
    document = minimal() if document is None else document
    selected = parse(document)
    base = tmp_path / "synthetic-input-private"
    base.mkdir(parents=True)
    root = tmp_path / "synthetic-capture-private"
    root.mkdir()
    path = base / "selection.json"
    path.write_bytes(json.dumps(document).encode())
    defaults = {
        "consolidated_report": b"opaque synthetic report\r\n",
        "report_snapshot": b"{}",
        "technical_review": b"opaque\r\n",
        "structured_support": b"null",
        "validation_report": b"opaque\n",
        "contextual_visual": image_bytes(),
    }
    for group in (
        selected.canonical_inputs,
        selected.supplemental_inputs,
        selected.validation_artifacts,
        selected.visual_exhibits,
    ):
        for entry in group:
            target = base / entry.input_reference
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((payloads or {}).get(entry.local_label, defaults[entry.role]))
    return path, selected, root


def capture(config):
    path, selection, root = config
    return p.capture_selected_inputs(selection_path=path, selection=selection, capture_root=root)


def finish(config):
    batch = capture(config)
    formats = v.validate_captured_formats(
        v.CapturedFormatInput(i.local_label, i.role, p.read_captured_bytes(i)) for i in batch.inputs
    )
    resolved = p.resolve_captured_inputs(
        batch,
        image_formats={
            f.local_label: f.image_format for f in formats if f.image_format is not None
        },
    )
    entries = p.resolved_annex_entries(config[1], resolved)
    return (
        resolved,
        entries,
        render_selection_metadata(
            SelectionMetadata(entries, config[1].issued_date, config[1].case_reference)
        ),
    )


def full_document():
    document = minimal()
    document["supplemental_inputs"] = [
        item("technical_review", "review"),
        item("structured_support", "support"),
    ]
    document["validation_artifacts"] = [item("validation_report", "validation")]
    document["visual_exhibits"] = [item("contextual_visual", "visual")]
    return document


def test_layout_exact_copies_metadata_shape_and_no_discovery(tmp_path, monkeypatch):
    config = setup_inputs(tmp_path, document=full_document())
    ignored = config[0].parent / "unselected.synthetic"
    ignored.write_bytes(b"must not be opened")
    actual = p.original_reader

    def reader(path):
        assert path != ignored
        return actual(path)

    monkeypatch.setattr(p, "original_reader", reader)

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden directory discovery or database")

    monkeypatch.setattr(Path, "iterdir", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    batch, entries, content = finish(config)
    expected = {
        "report": "technical/canonical/consolidated-report.md",
        "anchor": "technical/canonical/snapshots/anchor.json",
        "review": "technical/supplemental/review.md",
        "support": "technical/structured/support.json",
        "validation": "technical/validation/validation.md",
        "visual": "exhibits/visual/visual.png",
    }
    selection = config[1]
    sources = {
        i.local_label: config[0].parent / i.input_reference
        for group in (
            selection.canonical_inputs,
            selection.supplemental_inputs,
            selection.validation_artifacts,
            selection.visual_exhibits,
        )
        for i in group
    }
    assert {i.local_label: i.package_path for i in batch.inputs} == expected
    for captured in batch.inputs:
        original = sources[captured.local_label].read_bytes()
        assert captured.captured_path.read_bytes() == original
        assert captured.sha256 == hashlib.sha256(original).hexdigest()
        assert captured.byte_size == len(original)
    assert not (config[2] / "exhibits/visual/visual.jpg").exists()
    assert not (config[2] / "selection.json").exists()
    assert not (config[2] / "integrity").exists()
    value = json.loads(content)
    assert set(value) == {"policy_id", "policy_version", "delivery_profile", "items"}
    assert [(i["role"], i["local_label"]) for i in value["items"]] == sorted(
        (i.role, i.local_label) for i in entries
    )
    for row in value["items"]:
        keys = {"local_label", "source_class", "role", "package_path"}
        if row["role"] == "contextual_visual":
            keys |= {"display_caption", "operator_selected", "display_approved"}
            assert row["operator_selected"] is row["display_approved"] is True
        assert set(row) == keys
    assert (
        content
        == (
            json.dumps(
                value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            + "\n"
        ).encode()
    )
    assert "input_reference" not in {f.name for f in fields(entries[0])}


def test_metadata_determinism_roots_order_privacy_optionals(tmp_path):
    document = full_document()
    document.update(issued_date="2026-01-02", case_reference="synthetic-token")
    first = setup_inputs(tmp_path / "first", document=document)
    a, _, output = finish(first)
    for key in (
        "canonical_inputs",
        "supplemental_inputs",
        "validation_artifacts",
        "visual_exhibits",
    ):
        document[key].reverse()
        for entry in document[key]:
            original = first[0].parent / entry["input_reference"]
            entry["expected_sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
            entry["input_reference"] = "private-sentinel/" + entry["local_label"] + ".source-secret"
    second = setup_inputs(tmp_path / "other-host", document=document)
    _, _, other = finish(second)
    assert output == other
    value = json.loads(output)
    assert value["issued_date"] == "2026-01-02" and value["case_reference"] == "synthetic-token"
    for forbidden in (
        "private-sentinel",
        "source-secret",
        "synthetic-input-private",
        "synthetic-capture-private",
        "sha256",
        "byte_size",
        "generated_at",
        str(tmp_path),
        *(i.sha256 for i in a.inputs),
    ):
        assert forbidden not in output.decode()


@pytest.mark.parametrize(
    "content", [b"\x00\xff\x80binary", "sintético".encode(), b"LF\n", b"CRLF\r\n"]
)
def test_raw_capture_never_normalizes(tmp_path, content):
    batch = capture(setup_inputs(tmp_path, payloads={"report": content}))
    assert (
        next(i for i in batch.inputs if i.local_label == "report").captured_path.read_bytes()
        == content
    )


@pytest.mark.parametrize("correct", [True, False])
def test_expected_hash(tmp_path, correct):
    document = minimal()
    document["canonical_inputs"][0]["expected_sha256"] = (
        hashlib.sha256(b"synthetic").hexdigest() if correct else "0" * 64
    )
    config = setup_inputs(tmp_path, document=document, payloads={"report": b"synthetic"})
    if correct:
        capture(config)
    else:
        with pytest.raises(EvidenceError, match="^DOSSIER_HASH_MISMATCH$"):
            capture(config)
        assert config[2].is_dir()


def test_import_boundary():
    allowed = {
        "ctypes",  # F: Linux renameat2(RENAME_NOREPLACE), no shell/dependency.
        "errno",  # F: contracted fsync/publication error mapping.
        "sys",  # F: platform dispatch, not native-platform emulation.
        "tempfile",  # F: exclusive generic sibling staging.
        "hashlib",
        "os",
        "stat",
        "collections.abc",
        "contextlib",
        "dataclasses",
        "pathlib",
        "typing",
        "evidence_engine.dossier.projection",
        "evidence_engine.dossier.selection",
        "evidence_engine.errors",
        "evidence_engine.ingest.generic.hashing",
        "evidence_engine.ingest.generic.paths",
    }
    for node in ast.walk(ast.parse(inspect.getsource(p))):
        if isinstance(node, ast.ImportFrom):
            assert node.module in allowed
            assert not {a.name for a in node.names} & {"CasePaths", "discover"}
        elif isinstance(node, ast.Import):
            assert {a.name for a in node.names} <= allowed


def test_metadata_output_budget(tmp_path, monkeypatch):
    from evidence_engine.dossier import rendering

    _, entries, content = finish(setup_inputs(tmp_path))
    metadata = SelectionMetadata(entries)
    monkeypatch.setattr(rendering, "MAX_GENERATED_FILE_BYTES", len(content))
    assert render_selection_metadata(metadata) == content
    monkeypatch.setattr(rendering, "MAX_GENERATED_FILE_BYTES", len(content) - 1)
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        render_selection_metadata(metadata)


def test_after_capture_formats_and_resolution_never_reopen_sources(tmp_path, monkeypatch):
    config = setup_inputs(tmp_path, document=full_document())
    batch = capture(config)
    for entry in config[1].visual_exhibits:
        (config[0].parent / entry.input_reference).write_bytes(b"source changed after capture")
    actual = p.original_reader

    def captured_only(path):
        assert path.is_relative_to(config[2])
        return actual(path)

    monkeypatch.setattr(p, "original_reader", captured_only)
    formats = v.validate_captured_formats(
        v.CapturedFormatInput(i.local_label, i.role, p.read_captured_bytes(i)) for i in batch.inputs
    )
    resolved = p.resolve_captured_inputs(
        batch,
        image_formats={
            i.local_label: i.image_format for i in formats if i.image_format is not None
        },
    )
    assert p.resolved_annex_entries(config[1], resolved)
