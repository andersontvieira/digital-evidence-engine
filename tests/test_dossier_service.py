"""Synthetic A→E service assembly, phase ordering and failure isolation."""

import ast
import hashlib
import inspect
import json
import os
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from evidence_engine.dossier import integrity as e
from evidence_engine.dossier import packaging as p
from evidence_engine.dossier import rendering as r
from evidence_engine.dossier import service as s
from evidence_engine.errors import EvidenceError
from evidence_engine.reports import consolidated as report
from tests.test_dossier_canonical import current_snapshots, many_windows
from tests.test_dossier_packaging import image_bytes
from tests.test_dossier_selection import item, minimal


def inputs(tmp_path, *, full=False, windows=False, reverse=False):
    values = many_windows() if windows else current_snapshots()[:1]
    document = minimal()
    payloads = {"report": report.render_markdown(report.build_consolidated_model(values)).encode()}
    document["canonical_inputs"] = [item("consolidated_report", "report")]
    for i, value in enumerate(values):
        label = "anchor" if i == 0 else f"window-{i}"
        document["canonical_inputs"].append(item(label=label))
        payloads[label] = json.dumps(value).encode()
    if full:
        document.update(
            case_reference="synthetic-token",
            issued_date="2026-01-02",
            supplemental_inputs=[
                item("technical_review", "review"),
                item("structured_support", "support"),
            ],
            validation_artifacts=[item("validation_report", "validation")],
            visual_exhibits=[item("contextual_visual", "visual", "inputs/source-image.jpg")],
        )
        payloads.update(
            review=b"# Synthetic claim: opaque\r\n",
            support=b"null",
            validation=b"synthetic\n",
            visual=image_bytes("PNG"),
        )
    base = tmp_path / "synthetic-private-input"
    base.mkdir(parents=True)
    for key in (
        "canonical_inputs",
        "supplemental_inputs",
        "validation_artifacts",
        "visual_exhibits",
    ):
        group = document.get(key, [])
        if reverse:
            group.reverse()
        for entry in group:
            path = base / entry["input_reference"]
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(payloads[entry["local_label"]])
    selection = base / "selection-private.json"
    selection.write_bytes(json.dumps(document).encode())
    parent = tmp_path / "deliveries"
    parent.mkdir()
    return selection, parent / "package", document, payloads


def run(config):
    return s.assemble_dossier(selection_path=config[0], output_dir=config[1])


def package_bytes(root):
    return {f.relative_to(root).as_posix(): f.read_bytes() for f in root.rglob("*") if f.is_file()}


def assert_no_staging(output):
    assert not list(output.parent.glob(p.STAGING_PREFIX + "*"))


@pytest.mark.parametrize("full", [False, True])
def test_happy_path_exact_package_and_renderer_structure(tmp_path, full):
    config = inputs(tmp_path, full=full)
    result = run(config)
    actual = package_bytes(config[1])
    paths = set(p.GENERATED_PATHS) | {
        "technical/canonical/consolidated-report.md",
        "technical/canonical/snapshots/anchor.json",
    }
    if full:
        paths |= {
            "technical/supplemental/review.md",
            "technical/structured/support.json",
            "technical/validation/validation.md",
            "exhibits/visual/visual.png",
        }
    assert set(actual) == paths
    assert result.output_dir == config[1] and result.file_count == len(paths)
    assert result.total_byte_size == sum(map(len, actual.values()))
    assert {f.name for f in fields(result)} == {"output_dir", "file_count", "total_byte_size"}
    with pytest.raises(FrozenInstanceError):
        result.file_count = 0
    dossier = actual["human/dossier.md"].decode()
    assert dossier.splitlines()[0] == "# " + r.TITLE
    assert [line for line in dossier.splitlines() if line.startswith("## ")] == [
        f"## {i}. {title}" for i, title in enumerate(r.SECTIONS, 1)
    ]
    manifest = json.loads(actual[e.MANIFEST_PATH])
    for entry in manifest["entries"]:
        content = actual[entry["package_path"]]
        assert entry["sha256"] == hashlib.sha256(content).hexdigest()
        assert entry["byte_size"] == len(content)
        if "local_label" in entry:
            assert content == config[3][entry["local_label"]]
    assert (
        actual[e.SUMS_PATH]
        == "".join(
            hashlib.sha256(content).hexdigest() + "  " + path + "\n"
            for path, content in sorted(actual.items())
            if path != e.SUMS_PATH
        ).encode()
    )
    if full:
        assert b"exhibits/visual/visual.png" in actual["human/annex-index.md"]
        assert b"source-image.jpg" not in actual["technical/selection-metadata.json"]
    assert_no_staging(config[1])


def test_twenty_one_snapshots_uses_pure_unbounded_core(tmp_path, monkeypatch):
    config = inputs(tmp_path, windows=True)

    def forbidden(*args, **kwargs):
        raise AssertionError("Legacy snapshot-count API reached")

    monkeypatch.setattr(report, "consolidate_snapshots", forbidden)
    monkeypatch.setattr(report, "load_snapshots", forbidden)
    run(config)
    assert len(list((config[1] / "technical/canonical/snapshots").iterdir())) == 21


def test_determinism_different_roots_and_random_names(tmp_path, monkeypatch):
    names = []
    create = p.create_staging

    def record(destination):
        stage = create(destination)
        names.append(stage.path.name)
        assert stage.path.parent == destination.path.parent
        assert stage.path.name.startswith(p.STAGING_PREFIX)
        for forbidden in ("synthetic-token", "anchor", "selection-private", "package"):
            assert forbidden not in stage.path.name
        if os.name == "posix":
            assert stage.path.stat().st_mode & 0o777 == 0o700
        return stage

    monkeypatch.setattr(p, "create_staging", record)
    first, second = (
        inputs(tmp_path / "first", full=True),
        inputs(tmp_path / "other", full=True, reverse=True),
    )
    run(first)
    run(second)
    a, b = package_bytes(first[1]), package_bytes(second[1])
    assert a == b and names[0] != names[1]
    for path in p.GENERATED_PATHS:
        for forbidden in (*names, str(tmp_path), "selection-private.json", "source-image.jpg"):
            assert forbidden.encode() not in a[path]


@pytest.mark.parametrize(
    "failure", ["selection", "reference", "budget", "hardlink", "parent", "overlap", "output"]
)
def test_preflight_failures_never_create_staging(tmp_path, monkeypatch, failure):
    config = list(inputs(tmp_path))
    selected = config[0].parent / config[2]["canonical_inputs"][0]["input_reference"]
    if failure == "selection":
        config[0].write_bytes(b"invalid")
    elif failure == "reference":
        config[2]["canonical_inputs"][0]["input_reference"] = "../outside"
        config[0].write_bytes(json.dumps(config[2]).encode())
    elif failure == "budget":
        monkeypatch.setattr(p, "MAX_REPORT_BYTES", 1)
    elif failure == "hardlink":
        os.link(selected, tmp_path / "alias")
    elif failure == "parent":
        config[1] = tmp_path / "absent" / "package"
    elif failure == "overlap":
        config[1] = config[0].parent / "package"
    else:
        config[1].mkdir()
        (config[1] / "sentinel").write_bytes(b"untouched")

    def forbidden(*args):
        raise AssertionError("Staging created before failed preflight")

    monkeypatch.setattr(p, "create_staging", forbidden)
    with pytest.raises(EvidenceError) as error:
        run(config)
    assert str(error.value) != "DOSSIER_INTERNAL_ERROR"
    if failure == "output":
        assert str(error.value) == "DOSSIER_OUTPUT_EXISTS"
        assert (config[1] / "sentinel").read_bytes() == b"untouched"


def test_prepared_baselines_survive_until_capture(tmp_path, monkeypatch):
    config = inputs(tmp_path)
    create = p.create_staging

    def mutate(destination):
        stage = create(destination)
        target = config[0].parent / config[2]["canonical_inputs"][0]["input_reference"]
        target.write_bytes(b"changed between preflight and capture")
        return stage

    monkeypatch.setattr(p, "create_staging", mutate)
    with pytest.raises(EvidenceError, match="^DOSSIER_INPUT_CHANGED$"):
        run(config)
    assert_no_staging(config[1])


def test_selection_read_is_bound_to_prepared_baseline(tmp_path, monkeypatch):
    config = inputs(tmp_path)
    actual = p.prepare_capture

    def changed(**kwargs):
        config[0].write_bytes(config[0].read_bytes() + b" ")
        return actual(**kwargs)

    monkeypatch.setattr(p, "prepare_capture", changed)
    with pytest.raises(EvidenceError, match="^DOSSIER_INPUT_CHANGED$"):
        run(config)
    assert_no_staging(config[1])


@pytest.mark.parametrize(
    "module,name",
    [
        (p, "capture_prepared_inputs"),
        (s.validation, "validate_captured_formats"),
        (s.validation, "validate_canonical_set"),
        (s.projection, "project_dossier"),
        (r, "render_dossier_markdown"),
        (p, "write_generated_file"),
        (e, "finalize_integrity"),
        (p, "sync_staging_directories"),
        (p, "publish_staging"),
    ],
)
def test_phase_failures_cleanup_owned_partial_work(tmp_path, monkeypatch, module, name):
    config = inputs(tmp_path)
    code = "PUBLICATION_FAILURE" if name == "publish_staging" else "HASH_MISMATCH"

    def fail(*args, **kwargs):
        raise EvidenceError("DOSSIER_" + code)

    monkeypatch.setattr(module, name, fail)
    with pytest.raises(EvidenceError, match="^DOSSIER_" + code + "$"):
        run(config)
    assert not config[1].exists()
    assert_no_staging(config[1])


def test_capture_hash_mismatch_cleanup(tmp_path):
    config = inputs(tmp_path)
    config[2]["canonical_inputs"][0]["expected_sha256"] = "0" * 64
    config[0].write_bytes(json.dumps(config[2]).encode())
    with pytest.raises(EvidenceError, match="^DOSSIER_HASH_MISMATCH$"):
        run(config)
    assert_no_staging(config[1])


def test_cleanup_error_precedence(tmp_path, monkeypatch):
    config = inputs(tmp_path)

    def original(*args, **kwargs):
        raise EvidenceError("DOSSIER_HASH_MISMATCH")

    def cleanup(*args):
        raise OSError("private host/staging/hash")

    monkeypatch.setattr(p, "capture_prepared_inputs", original)
    monkeypatch.setattr(p, "cleanup_staging", cleanup)
    with pytest.raises(EvidenceError, match="^DOSSIER_STAGING_FAILURE$"):
        run(config)
    assert not config[1].exists()


def test_e_recheck_catches_tampering_after_finalization(tmp_path, monkeypatch):
    config = inputs(tmp_path)
    original = e.finalize_integrity

    def tamper(**kwargs):
        result = original(**kwargs)
        (kwargs["work_root"] / "human/dossier.md").write_bytes(b"tampered")
        return result

    monkeypatch.setattr(e, "finalize_integrity", tamper)
    with pytest.raises(EvidenceError, match="^DOSSIER_HASH_MISMATCH$"):
        run(config)
    assert_no_staging(config[1])


def test_no_post_publication_io_and_no_open_handles(tmp_path, monkeypatch):
    config = inputs(tmp_path)
    opened = set()
    open_fd, close_fd, fdopen = os.open, os.close, os.fdopen
    publish = p.publish_staging

    def opening(*args, **kwargs):
        fd = open_fd(*args, **kwargs)
        opened.add(fd)
        return fd

    def closing(fd):
        opened.discard(fd)
        return close_fd(fd)

    def wrapping(fd, *args, **kwargs):
        # File objects own and close their fds; check actual liveness at publication.
        return fdopen(fd, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("Filesystem access after confirmed publication")

    def final(stage):
        for fd in opened:
            with pytest.raises(OSError):
                os.fstat(fd)
        publish(stage)
        for name in (
            "read_selection_bytes_stable",
            "revalidate_staging",
            "cleanup_staging",
            "staging_is_owned",
            "sync_staging_directories",
        ):
            patch.setattr(p, name, forbidden)
        patch.setattr(e, "verify_integrity_result", forbidden)
        patch.setattr(Path, "stat", forbidden)
        patch.setattr(Path, "lstat", forbidden)
        patch.setattr(Path, "open", forbidden)

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", opening)
        patch.setattr(os, "close", closing)
        patch.setattr(os, "fdopen", wrapping)
        patch.setattr(p, "publish_staging", final)
        result = run(config)
        assert result.file_count == 7


def test_service_import_boundary():
    tree = ast.parse(inspect.getsource(s))
    allowed = {"dataclasses", "pathlib", "evidence_engine.dossier", "evidence_engine.errors"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module in allowed
        elif isinstance(node, ast.Import):
            assert {a.name for a in node.names} <= allowed
