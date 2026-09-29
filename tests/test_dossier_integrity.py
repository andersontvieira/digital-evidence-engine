"""Synthetic controlled packages only; no case, original evidence or publication."""

import ast
import hashlib
import inspect
import json
import os
import socket
import sqlite3
import subprocess
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from evidence_engine.dossier import integrity as e
from evidence_engine.dossier import packaging as p
from evidence_engine.dossier import rendering as r
from evidence_engine.errors import EvidenceError
from tests.test_dossier_canonical import current_snapshots, validate
from tests.test_dossier_packaging import finish, full_document, setup_inputs
from tests.test_dossier_projection import project, selection_document


def prepare(tmp_path, *, full=False, reverse=False):
    document = full_document() if full else None
    config = setup_inputs(tmp_path, document=document)
    batch, entries, metadata = finish(config)
    if reverse:
        batch = replace(batch, inputs=tuple(reversed(batch.inputs)))
    contents = {
        "human/dossier.md": b"# Synthetic opaque claim\nNot interpreted as a fact.\n",
        "human/annex-index.md": r.render_annex_index(entries),
        "technical/selection-metadata.json": metadata,
    }
    write_generated(config[2], contents)
    return batch, contents, config


def write_generated(root, contents):
    for name, data in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def finalize(batch, contents):
    return e.finalize_integrity(
        work_root=batch.capture_root,
        captured=batch,
        dossier_content=contents["human/dossier.md"],
        annex_index_content=contents["human/annex-index.md"],
        selection_metadata_content=contents["technical/selection-metadata.json"],
    )


@pytest.mark.parametrize("full", [False, True])
def test_exact_manifest_sums_schema_order_and_acyclic_completeness(tmp_path, full):
    batch, contents, _ = prepare(tmp_path, full=full)
    result = finalize(batch, contents)
    root = batch.capture_root
    payloads = {i.package_path for i in batch.inputs} | set(contents)
    expected = payloads | {e.MANIFEST_PATH, e.SUMS_PATH}
    actual = {f.relative_to(root).as_posix() for f in root.rglob("*") if f.is_file()}
    assert actual == expected
    assert (root / e.MANIFEST_PATH).read_bytes() == result.manifest_content
    assert (root / e.SUMS_PATH).read_bytes() == result.sums_content
    value = json.loads(result.manifest_content)
    assert set(value) == {"policy_id", "policy_version", "entries"}
    assert value["policy_id"] == "dossier.package_manifest" and value["policy_version"] == "1.0.0"
    assert [i["package_path"] for i in value["entries"]] == sorted(payloads)
    selected = {i.package_path: i for i in batch.inputs}
    for row in value["entries"]:
        path = row["package_path"]
        keys = {"package_path", "role", "source_class", "byte_size", "sha256"}
        if path in selected:
            keys.add("local_label")
            source = selected[path]
            assert (row["role"], row["source_class"], row["local_label"]) == (
                source.role,
                source.source_class,
                source.local_label,
            )
        else:
            assert (row["role"], row["source_class"]) == e.GENERATED_PAYLOADS[path]
        assert set(row) == keys
        content = (root / path).read_bytes()
        assert type(row["byte_size"]) is int and row["byte_size"] == len(content)
        assert row["sha256"] == hashlib.sha256(content).hexdigest()
    assert result.manifest_content == (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    covered = sorted(payloads | {e.MANIFEST_PATH})
    assert (
        result.sums_content
        == "".join(
            hashlib.sha256((root / path).read_bytes()).hexdigest() + "  " + path + "\n"
            for path in covered
        ).encode()
    )
    assert [f.package_path for f in result.files] == sorted(expected)
    assert result.total_byte_size == sum((root / name).stat().st_size for name in expected)
    for f in result.files:
        assert f.sha256 == hashlib.sha256((root / f.package_path).read_bytes()).hexdigest()
    with pytest.raises(FrozenInstanceError):
        result.total_byte_size = 0


def test_real_c_renderer_output_is_inherited_by_byte_equality(tmp_path):
    canonical = validate(current_snapshots())
    document = selection_document(canonical)
    payloads = {s.local_label: json.dumps(s.snapshot).encode() for s in canonical.snapshots}
    payloads["report"] = canonical.report_content
    config = setup_inputs(tmp_path, document=document, payloads=payloads)
    batch, entries, metadata = finish(config)
    dossier = r.render_dossier_markdown(project(canonical, document))
    assert dossier.count(b"\n## ") == 14
    contents = dict(
        zip(e.GENERATED_PAYLOADS, (dossier, r.render_annex_index(entries), metadata), strict=True)
    )
    write_generated(batch.capture_root, contents)
    assert finalize(batch, contents)
    assert (batch.capture_root / "human/dossier.md").read_bytes() == dossier


def test_determinism_roots_order_and_privacy(tmp_path):
    a, contents, config = prepare(tmp_path / "private-host-a", full=True)
    b, other, _ = prepare(tmp_path / "private-host-b", full=True, reverse=True)
    first, second = finalize(a, contents), finalize(b, other)
    assert first == second
    output = first.manifest_content + first.sums_content
    for forbidden in (
        str(tmp_path),
        str(config[0].parent),
        str(a.capture_root),
        "input_reference",
        "expected_sha256",
        "generated_at",
        "st_mtime",
        "st_ino",
        "source-secret",
        *(i.input_reference for i in config[1].canonical_inputs),
    ):
        assert forbidden.encode() not in output
    assert b"sha256" in first.manifest_content  # Contracted technical integrity, not narrative.


@pytest.mark.parametrize("size_change", [False, True])
def test_selected_tampering_rejected_before_manifest(tmp_path, size_change):
    batch, contents, _ = prepare(tmp_path)
    path = batch.inputs[0].captured_path
    original = path.read_bytes()
    path.write_bytes(original + b"!" if size_change else b"!" + original[1:])
    with pytest.raises(EvidenceError, match="^DOSSIER_HASH_MISMATCH$"):
        finalize(batch, contents)
    assert not (batch.capture_root / e.MANIFEST_PATH).exists()


@pytest.mark.parametrize("name", list(e.GENERATED_PAYLOADS))
@pytest.mark.parametrize("change", ["byte", "crlf", "bom", "space", "final_lf"])
def test_generated_byte_tampering_is_not_normalized(tmp_path, name, change):
    batch, contents, _ = prepare(tmp_path)
    old = contents[name]
    changed = {
        "byte": b"!" + old[1:],
        "crlf": old.replace(b"\n", b"\r\n"),
        "bom": b"\xef\xbb\xbf" + old,
        "space": b" " + old,
        "final_lf": old.rstrip(b"\n"),
    }[change]
    (batch.capture_root / name).write_bytes(changed)
    with pytest.raises(EvidenceError, match="^DOSSIER_INTERNAL_ERROR$"):
        finalize(batch, contents)


@pytest.mark.parametrize("name", ["selected", *e.GENERATED_PAYLOADS])
def test_missing_file(tmp_path, name):
    batch, contents, _ = prepare(tmp_path)
    path = batch.inputs[0].captured_path if name == "selected" else batch.capture_root / name
    path.unlink()
    with pytest.raises(EvidenceError, match="^DOSSIER_INTERNAL_ERROR$"):
        finalize(batch, contents)


@pytest.mark.parametrize(
    "name",
    [
        "scratch.tmp",
        "debug.log",
        "unknown.json",
        ".git/anything",
        "__pycache__/x",
        "selection.json",
    ],
)
def test_extra_payload_never_opened(tmp_path, monkeypatch, name):
    batch, contents, _ = prepare(tmp_path)
    path = batch.capture_root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic private scratch")
    actual = p.original_reader

    def guarded(path):
        assert path.name not in {
            "scratch.tmp",
            "debug.log",
            "unknown.json",
            "anything",
            "x",
            "selection.json",
        }
        return actual(path)

    monkeypatch.setattr(p, "original_reader", guarded)
    with pytest.raises(EvidenceError, match="^DOSSIER_INTERNAL_ERROR$"):
        finalize(batch, contents)


@pytest.mark.parametrize("name", ["scratch", ".git", "technical/unused", "integrity"])
def test_extra_empty_directory(tmp_path, name):
    batch, contents, _ = prepare(tmp_path)
    (batch.capture_root / name).mkdir()
    with pytest.raises(EvidenceError, match="^DOSSIER_INTERNAL_ERROR$"):
        finalize(batch, contents)


@pytest.mark.parametrize("name", [e.MANIFEST_PATH, e.SUMS_PATH])
def test_preexisting_integrity_not_overwritten(tmp_path, name):
    batch, contents, _ = prepare(tmp_path)
    path = batch.capture_root / name
    path.parent.mkdir()
    path.write_bytes(b"preexisting")
    with pytest.raises(EvidenceError, match="^DOSSIER_STAGING_FAILURE$"):
        finalize(batch, contents)
    assert path.read_bytes() == b"preexisting"


@pytest.mark.parametrize("kind", ["symlink", "directory_link", "hardlink", "fifo", "socket"])
def test_unsafe_nodes_rejected_before_hashing(tmp_path, monkeypatch, kind):
    batch, contents, _ = prepare(tmp_path)
    target = batch.inputs[0].captured_path
    external = tmp_path / "external"
    external.write_bytes(b"outside untouched")
    listener = None
    if kind == "directory_link":
        directory = target.parent
        directory.rename(tmp_path / "displaced")
        try:
            directory.symlink_to(tmp_path, target_is_directory=True)
        except OSError:
            pytest.skip("Host cannot create directory symlink")
    else:
        target.unlink()
        if kind == "symlink":
            try:
                target.symlink_to(external)
            except OSError:
                pytest.skip("Host cannot create symlink")
        elif kind == "hardlink":
            os.link(external, target)
        elif kind == "fifo":
            if not hasattr(os, "mkfifo"):
                pytest.skip("FIFO requires POSIX")
            os.mkfifo(target)
        else:
            if os.name != "posix":
                pytest.skip("Synthetic UNIX socket requires POSIX")
            listener = socket.socket(socket.AF_UNIX)
            # Short path avoids host-dependent AF_UNIX pathname length limits.
            target = batch.capture_root / "socket"
            listener.bind(str(target))

    def forbidden(*args):
        raise AssertionError("Unsafe tree must fail before any content read")

    monkeypatch.setattr(p, "original_reader", forbidden)
    try:
        with pytest.raises(EvidenceError, match="^DOSSIER_UNSAFE_FILE_TYPE$"):
            finalize(batch, contents)
    finally:
        if listener is not None:
            listener.close()
    assert external.read_bytes() == b"outside untouched"


@pytest.mark.skipif(os.name != "nt", reason="Real Windows junction requires native Windows")
def test_real_windows_junction(tmp_path):
    batch, contents, _ = prepare(tmp_path)
    parent = batch.capture_root / "human"
    target = tmp_path / "junction-target"
    parent.rename(target)
    sentinel = target / "external-sentinel"
    sentinel.write_bytes(b"synthetic external target untouched")
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(parent), str(target)], capture_output=True
    )
    if result.returncode:
        pytest.skip("Host cannot create junction")
    assert parent.is_junction()
    with pytest.raises(EvidenceError, match="^DOSSIER_UNSAFE_FILE_TYPE$"):
        finalize(batch, contents)

    assert sentinel.read_bytes() == b"synthetic external target untouched"


def test_reparse_flag_precedes_resolve_and_open(tmp_path, monkeypatch):
    batch, contents, _ = prepare(tmp_path)
    target = batch.inputs[0].captured_path
    actual = Path.lstat

    def reparse(self, *args, **kwargs):
        info = actual(self, *args, **kwargs)
        return (
            SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            if self == target
            else info
        )

    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(EvidenceError, match="^DOSSIER_UNSAFE_FILE_TYPE$"):
        finalize(batch, contents)


def test_independent_stream_rehash_and_no_source_reopen(tmp_path, monkeypatch):
    batch, contents, config = prepare(tmp_path, full=True)
    for i in config[1].canonical_inputs:
        (config[0].parent / i.input_reference).unlink()
    actual = p.original_reader
    reads = []

    @contextmanager
    def guarded(path):
        assert path.is_relative_to(batch.capture_root)
        reads.append(path.relative_to(batch.capture_root).as_posix())
        with actual(path) as stream:

            class Bounded:
                def fileno(self):
                    return stream.fileno()

                def read(self, size):
                    assert 0 < size <= p.CHUNK_SIZE
                    return stream.read(size)

            yield Bounded()

    def forbidden(*args, **kwargs):
        raise AssertionError("No database, network, rendering or recapture in E")

    monkeypatch.setattr(p, "original_reader", guarded)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(p, "capture_selected_inputs", forbidden)
    monkeypatch.setattr(r, "render_dossier_markdown", forbidden)
    monkeypatch.setattr(r, "render_annex_index", forbidden)
    monkeypatch.setattr(r, "render_selection_metadata", forbidden)
    result = finalize(batch, contents)
    assert {f.package_path for f in result.files} == set(reads)
    assert all(reads.count(i.package_path) >= 2 for i in batch.inputs)


@pytest.mark.parametrize("name", [e.MANIFEST_PATH, e.SUMS_PATH])
def test_integrity_tampering_after_write(tmp_path, monkeypatch, name):
    batch, contents, _ = prepare(tmp_path)
    actual = e._write_integrity

    def tamper(root, path, content):
        actual(root, path, content)
        if path == name:
            (root.path / path).write_bytes(b"!" + content[1:])

    monkeypatch.setattr(e, "_write_integrity", tamper)
    with pytest.raises(EvidenceError, match="^DOSSIER_INTERNAL_ERROR$"):
        finalize(batch, contents)
    assert batch.capture_root.exists()
    if name == e.MANIFEST_PATH:
        assert not (batch.capture_root / e.SUMS_PATH).exists()


@pytest.mark.parametrize("target", ["selected", "generated", "extra", "missing"])
def test_mutation_while_integrity_is_generated(tmp_path, monkeypatch, target):
    batch, contents, _ = prepare(tmp_path)
    actual = e._write_integrity

    def change(root, path, content):
        actual(root, path, content)
        if path == e.SUMS_PATH:
            changed = batch.inputs[0].captured_path
            if target == "generated":
                changed = root.path / "human/dossier.md"
            if target == "missing":
                changed.unlink()
            elif target == "extra":
                (root.path / "scratch.tmp").write_bytes(b"extra")
            else:
                changed.write_bytes(b"!" + changed.read_bytes()[1:])

    monkeypatch.setattr(e, "_write_integrity", change)
    with pytest.raises(
        EvidenceError, match="^DOSSIER_(INPUT_CHANGED|INTERNAL_ERROR|HASH_MISMATCH)$"
    ):
        finalize(batch, contents)


def test_mutation_after_earlier_final_rehash_is_detected(tmp_path, monkeypatch):
    batch, contents, _ = prepare(tmp_path)
    actual = e._read_payload
    calls = 0

    def change(*args, **kwargs):
        nonlocal calls
        result = actual(*args, **kwargs)
        if result.package_path == batch.inputs[-1].package_path:
            calls += 1
            if calls == 2:
                (batch.capture_root / "human/dossier.md").write_bytes(b"changed late")
        return result

    monkeypatch.setattr(e, "_read_payload", change)
    with pytest.raises(EvidenceError, match="^DOSSIER_INPUT_CHANGED$"):
        finalize(batch, contents)


@pytest.mark.parametrize("kind", ["manifest", "sums"])
def test_incremental_integrity_output_budget(tmp_path, monkeypatch, kind):
    batch, contents, _ = prepare(tmp_path)
    result = finalize(batch, contents)
    fn, values, output = (
        (e.serialize_manifest, result.entries, result.manifest_content)
        if kind == "manifest"
        else (
            e.serialize_sha256sums,
            tuple(f for f in result.files if f.package_path != e.SUMS_PATH),
            result.sums_content,
        )
    )
    monkeypatch.setattr(e, "MAX_GENERATED_FILE_BYTES", len(output))
    assert fn(values) == output
    monkeypatch.setattr(e, "MAX_GENERATED_FILE_BYTES", len(output) - 1)
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        fn(values)


@pytest.mark.parametrize("name", list(e.GENERATED_PAYLOADS))
@pytest.mark.parametrize("over", [False, True])
def test_actual_generated_byte_limit(tmp_path, monkeypatch, name, over):
    batch, contents, _ = prepare(tmp_path)
    contents[name] = b"x" * 8192
    write_generated(batch.capture_root, contents)
    if over:
        (batch.capture_root / name).write_bytes(contents[name] + b"!")
    monkeypatch.setattr(e, "MAX_GENERATED_FILE_BYTES", 8192)
    if over:
        with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
            finalize(batch, contents)
    else:
        assert finalize(batch, contents)


@pytest.mark.parametrize("over", [False, True])
def test_total_actual_bytes_includes_both_integrity_files(tmp_path, monkeypatch, over):
    batch, contents, _ = prepare(tmp_path / "measure")
    result = finalize(batch, contents)
    total = sum(f.byte_size for f in result.files)
    assert total == sum(i.byte_size for i in batch.inputs) + sum(map(len, contents.values())) + len(
        result.manifest_content
    ) + len(result.sums_content)
    batch, contents, _ = prepare(tmp_path / "limit")
    monkeypatch.setattr(e, "MAX_PACKAGE_BYTES", total - int(over))
    if over:
        with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
            finalize(batch, contents)
    else:
        assert finalize(batch, contents).total_byte_size == total


@pytest.mark.parametrize("size", [True, False, -1, 1.0])
def test_manifest_size_type(size):
    with pytest.raises(EvidenceError, match="^DOSSIER_INTERNAL_ERROR$"):
        e.ManifestEntry(
            "human/dossier.md", size, "a" * 64, "human_dossier", "GENERATED_PRESENTATION"
        )


@pytest.mark.parametrize("sha", ["A" * 64, "a" * 63, "a" * 65, "z" * 64])
def test_manifest_hash_type(sha):
    with pytest.raises(EvidenceError, match="^DOSSIER_INTERNAL_ERROR$"):
        e.IntegrityPayload("human/dossier.md", 1, sha)


@pytest.mark.parametrize("mutation", ["role", "class", "label", "duplicate", "self", "path"])
def test_manifest_entry_invariants(tmp_path, mutation):
    batch, contents, _ = prepare(tmp_path)
    result = finalize(batch, contents)
    generated = next(i for i in result.entries if i.package_path == "human/dossier.md")
    with pytest.raises(EvidenceError):
        if mutation == "duplicate":
            e.serialize_manifest((*result.entries, result.entries[0]))
        else:
            changes = {
                "role": {"role": "annex_index"},
                "class": {"source_class": "CANONICAL_TECHNICAL"},
                "label": {"local_label": "unexpected"},
                "self": {"package_path": e.MANIFEST_PATH},
                "path": {"package_path": "../outside"},
            }[mutation]
            replace(generated, **changes)


@pytest.mark.parametrize(
    "mutation", ["unresolved", "root", "outside", "duplicate", "visual_format"]
)
def test_manual_capture_batch_rejected(tmp_path, mutation):
    batch, contents, _ = prepare(tmp_path, full=True)
    first = batch.inputs[0]
    if mutation == "root":
        batch = replace(batch, capture_root=tmp_path / "outside")
        contents_root = tmp_path / "synthetic-capture-private"
        with pytest.raises(EvidenceError):
            e.finalize_integrity(
                work_root=contents_root,
                captured=batch,
                dossier_content=contents["human/dossier.md"],
                annex_index_content=contents["human/annex-index.md"],
                selection_metadata_content=contents["technical/selection-metadata.json"],
            )
        assert contents_root.is_dir()
        return
    if mutation == "duplicate":
        batch = replace(batch, inputs=(*batch.inputs, first))
    elif mutation == "visual_format":
        batch = replace(
            batch,
            inputs=tuple(
                replace(i, validated_format=None) if i.role == "contextual_visual" else i
                for i in batch.inputs
            ),
        )
    else:
        changed = replace(
            first,
            **(
                {"package_path": None}
                if mutation == "unresolved"
                else {"captured_path": tmp_path / "outside"}
            ),
        )
        batch = replace(batch, inputs=(changed, *batch.inputs[1:]))
    with pytest.raises(EvidenceError):
        finalize(batch, contents)


@pytest.mark.parametrize(
    "error,code",
    [
        (OSError, "STAGING_FAILURE"),
        (MemoryError, "RESOURCE_LIMIT"),
        (RecursionError, "RESOURCE_LIMIT"),
    ],
)
def test_safe_errors_and_no_cleanup(tmp_path, monkeypatch, error, code):
    batch, contents, _ = prepare(tmp_path)

    def fail(*args, **kwargs):
        raise error("private host/path/hash/label/payload")

    monkeypatch.setattr(e, "_write_integrity", fail)
    with pytest.raises(EvidenceError, match=f"^DOSSIER_{code}$"):
        finalize(batch, contents)
    assert batch.capture_root.is_dir()
    assert all(i.captured_path.is_file() for i in batch.inputs)


def test_import_boundary():
    allowed = {
        "hashlib",
        "json",
        "os",
        "re",
        "stat",
        "collections.abc",
        "contextlib",
        "dataclasses",
        "pathlib",
        "evidence_engine.dossier",
        "evidence_engine.dossier.projection",
        "evidence_engine.errors",
    }
    for node in ast.walk(ast.parse(inspect.getsource(e))):
        if isinstance(node, ast.ImportFrom):
            assert node.module in allowed
            if node.module == "evidence_engine.dossier":
                assert {a.name for a in node.names} == {"packaging"}
        elif isinstance(node, ast.Import):
            assert {a.name for a in node.names} <= allowed


@pytest.mark.parametrize("mutation", ["duplicate", "self", "missing_manifest"])
def test_sums_rejects_invalid_coverage(tmp_path, mutation):
    batch, contents, _ = prepare(tmp_path)
    result = finalize(batch, contents)
    covered = tuple(i for i in result.files if i.package_path != e.SUMS_PATH)
    if mutation == "duplicate":
        covered += (covered[0],)
    elif mutation == "self":
        covered = result.files
    else:
        covered = tuple(i for i in covered if i.package_path != e.MANIFEST_PATH)
    with pytest.raises(EvidenceError, match="^DOSSIER_INTERNAL_ERROR$"):
        e.serialize_sha256sums(covered)


def test_selected_entry_requires_label(tmp_path):
    batch, contents, _ = prepare(tmp_path)
    entry = next(i for i in finalize(batch, contents).entries if i.local_label is not None)
    with pytest.raises(EvidenceError):
        replace(entry, local_label=None)


@pytest.mark.parametrize("path", [e.MANIFEST_PATH, e.SUMS_PATH])
def test_exclusive_integrity_write_race_preserves_existing_bytes(tmp_path, monkeypatch, path):
    batch, contents, _ = prepare(tmp_path)
    actual = e._write_integrity

    def race(root, relative, content):
        if relative == path:
            destination = root.path / relative
            destination.parent.mkdir(exist_ok=True)
            destination.write_bytes(b"concurrent existing")
        actual(root, relative, content)

    monkeypatch.setattr(e, "_write_integrity", race)
    with pytest.raises(EvidenceError, match="^DOSSIER_STAGING_FAILURE$"):
        finalize(batch, contents)
    assert (batch.capture_root / path).read_bytes() == b"concurrent existing"


def test_partial_failure_keeps_owned_work_and_retry_fails_closed(tmp_path, monkeypatch):
    batch, contents, _ = prepare(tmp_path)
    actual = e._write_integrity

    def fail(root, path, content):
        actual(root, path, content)
        if path == e.MANIFEST_PATH:
            raise OSError("synthetic failure after file creation")

    with monkeypatch.context() as patch:
        patch.setattr(e, "_write_integrity", fail)
        with pytest.raises(EvidenceError, match="^DOSSIER_STAGING_FAILURE$"):
            finalize(batch, contents)
    saved = (batch.capture_root / e.MANIFEST_PATH).read_bytes()
    with pytest.raises(EvidenceError, match="^DOSSIER_STAGING_FAILURE$"):
        finalize(batch, contents)
    assert (batch.capture_root / e.MANIFEST_PATH).read_bytes() == saved
    assert all(i.captured_path.is_file() for i in batch.inputs)


@pytest.mark.skipif(os.name != "posix", reason="Descriptor-relative traversal requires POSIX")
def test_directory_swap_before_scan_never_enumerates_external(tmp_path, monkeypatch):
    batch, contents, _ = prepare(tmp_path)
    parent = batch.capture_root / "human"
    external = tmp_path / "external-dir"
    external.mkdir()
    (external / "private-sentinel").write_bytes(b"must not be opened")
    inode = parent.stat().st_ino
    actual = os.scandir
    swapped = False

    def race(target):
        nonlocal swapped
        if isinstance(target, int) and os.fstat(target).st_ino == inode and not swapped:
            swapped = True
            parent.rename(tmp_path / "displaced-human")
            parent.symlink_to(external, target_is_directory=True)
        if isinstance(target, int):
            assert os.fstat(target).st_ino != external.stat().st_ino
        return actual(target)

    monkeypatch.setattr(e.os, "scandir", race)
    with pytest.raises(EvidenceError, match="^DOSSIER_(INPUT_CHANGED|UNSAFE_FILE_TYPE)$"):
        finalize(batch, contents)
    assert swapped and (external / "private-sentinel").read_bytes() == b"must not be opened"


def test_root_identity_change_during_integrity_is_rejected(tmp_path, monkeypatch):
    batch, contents, _ = prepare(tmp_path)
    actual = e._write_integrity

    def swap(root, path, content):
        actual(root, path, content)
        if path == e.MANIFEST_PATH:
            root.path.rename(tmp_path / "displaced-root")
            root.path.mkdir()

    monkeypatch.setattr(e, "_write_integrity", swap)
    with pytest.raises(EvidenceError, match="^DOSSIER_(INTERNAL_ERROR|INPUT_CHANGED)$"):
        finalize(batch, contents)


def test_stream_growth_resource_limit(tmp_path, monkeypatch):
    batch, contents, _ = prepare(tmp_path)
    actual = p.original_reader
    target = batch.inputs[0].captured_path
    monkeypatch.setattr(p, "MAX_REPORT_BYTES", target.stat().st_size)

    @contextmanager
    def growing(path):
        with actual(path) as stream:
            if path != target:
                yield stream
                return

            class Growing:
                def fileno(self):
                    return stream.fileno()

                def read(self, size):
                    return b"x" * size

            yield Growing()

    monkeypatch.setattr(p, "original_reader", growing)
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        finalize(batch, contents)
