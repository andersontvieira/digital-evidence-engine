"""Synthetic published-package capture, source binding and acyclic PDF integrity."""

import ast
import hashlib
import inspect
import json
import os
import shutil
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from evidence_engine.dossier import pdf_package as p
from evidence_engine.dossier import pdf_renderer as renderer
from evidence_engine.errors import EvidenceError
from tests.test_dossier_service import inputs, package_bytes, run
from tests.test_pdf_renderer import pytestmark as pytestmark


def sha(content):
    return hashlib.sha256(content).hexdigest()


def encode(value):
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode()


def reseal(root, *, refresh=False):
    """Only trusted synthetic paths; refresh is never used after hostile path edits."""
    path = root / p.SOURCE_MANIFEST
    value = json.loads(path.read_bytes())
    if refresh:
        for entry in value["entries"]:
            content = (root / entry["package_path"]).read_bytes()
            entry.update(byte_size=len(content), sha256=sha(content))
    content = encode(value)
    path.write_bytes(content)
    rows = [(e["package_path"], e["sha256"]) for e in value["entries"]]
    rows.append((p.SOURCE_MANIFEST, sha(content)))
    (root / p.SUMS_PATH).write_bytes("".join(f"{h}  {path}\n" for path, h in sorted(rows)).encode())


@pytest.fixture(scope="module")
def valid(tmp_path_factory):
    config = inputs(tmp_path_factory.mktemp("pdf-source"))
    run(config)
    source = p.capture_source_package(config[1])
    dossier = renderer.render_dossier_pdf(source.source_bytes("human/dossier.md"))
    report = renderer.render_consolidated_report_pdf(
        source.source_bytes("technical/canonical/consolidated-report.md")
    )
    result = p.bind_pdf_export(source, dossier_pdf=dossier, consolidated_report_pdf=report)
    return config[1], source, result


@pytest.fixture
def root(valid, tmp_path):
    return Path(shutil.copytree(valid[0], tmp_path / "published"))


def failure(code=None):
    return pytest.raises(EvidenceError, match="^DOSSIER_PDF_" + (code or "[A-Z_]+") + "$")


def bind(source, result):
    files = dict(result.files)
    return p.bind_pdf_export(
        source,
        dossier_pdf=files["human/dossier.pdf"],
        consolidated_report_pdf=files["human/consolidated-report.pdf"],
    )


def test_complete_binding_and_exact_bytes(valid):
    root, source, result = valid
    before = package_bytes(root)
    assert set(dict(source.retained)) == p._RETAIN
    assert all(source.source_bytes(path) == before[path] for path in p._RETAIN)
    assert p.verify_pdf_export(source, dict(result.files)) == result
    value = json.loads(result.manifest_content)
    assert result.manifest_content == encode(value)
    assert set(value) == {
        "policy_id",
        "policy_version",
        "export_policy_id",
        "export_policy_version",
        "delivery_profile",
        "render_environment_id",
        "source_package",
        "entries",
    }
    assert value["source_package"] == {
        "manifest_sha256": sha(before[p.SOURCE_MANIFEST]),
        "sha256sums_sha256": sha(before[p.SUMS_PATH]),
    }
    assert [e["package_path"] for e in value["entries"]] == [
        "human/consolidated-report.pdf",
        "human/dossier.pdf",
    ]
    files = dict(result.files)
    assert set(files) == p._OUTPUT_PATHS
    assert (
        result.sums_content
        == "".join(
            f"{sha(data)}  {path}\n" for path, data in sorted(files.items()) if path != p.SUMS_PATH
        ).encode()
    )
    for entry in value["entries"]:
        assert entry["source_sha256"] == sha(before[entry["source_package_path"]])
        assert entry["source_byte_size"] == len(before[entry["source_package_path"]])
        assert entry["sha256"] == sha(files[entry["package_path"]])
        assert entry["byte_size"] == len(files[entry["package_path"]])
        assert entry["page_count"] > 0
    assert package_bytes(root) == before
    with pytest.raises(FrozenInstanceError):
        result.manifest_content = b""


def test_optional_items_opaque_and_read_only(tmp_path, monkeypatch):
    config = inputs(tmp_path, full=True)
    run(config)
    root = config[1]
    # Capture verifies bytes, never interprets snapshot/structured/media semantics.
    for path in (
        "technical/canonical/snapshots/anchor.json",
        "technical/structured/support.json",
        "exhibits/visual/visual.png",
    ):
        (root / path).write_bytes(b"synthetic opaque, deliberately not decodable")
    reseal(root, refresh=True)
    before = package_bytes(root)

    def forbidden(*args, **kwargs):
        raise AssertionError("producer/write reached")

    from evidence_engine.dossier import service
    from evidence_engine.reports import consolidated

    monkeypatch.setattr(service, "assemble_dossier", forbidden)
    monkeypatch.setattr(consolidated, "build_consolidated_model", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    source = p.capture_source_package(root)
    p.recheck_source_package(source)
    assert len(source.files) == 11 and len(source.retained) == 5
    assert package_bytes(root) == before


@pytest.mark.parametrize(
    "path",
    [
        p.SOURCE_MANIFEST,
        p.SUMS_PATH,
        p.METADATA_PATH,
        "human/dossier.md",
        "technical/canonical/consolidated-report.md",
    ],
)
def test_missing_source_file(root, path):
    (root / path).unlink()
    with failure():
        p.capture_source_package(root)


@pytest.mark.parametrize(
    "content",
    [
        b"{",
        b"{}\n",
        b'{"policy_id":1,"policy_id":2}\n',
        b'{"x":NaN}\n',
        b"\xef\xbb\xbf{}\n",
        b'{"x":1e999}\n',
        b'{"x":null}\n',
    ],
)
@pytest.mark.parametrize("path", [p.SOURCE_MANIFEST, p.METADATA_PATH])
def test_administrative_json_failure(root, content, path):
    (root / path).write_bytes(content)
    if path == p.METADATA_PATH:
        reseal(root, refresh=True)
    with failure():
        p.capture_source_package(root)


@pytest.mark.parametrize(
    "mutation",
    [
        "policy",
        "version",
        "duplicate",
        "order",
        "coverage",
        "role",
        "class",
        "path",
        "label",
        "size",
        "hash",
        "bool",
        "unknown",
    ],
)
def test_source_manifest_failures(root, mutation):
    path = root / p.SOURCE_MANIFEST
    value = json.loads(path.read_bytes())
    row = value["entries"][0]
    if mutation == "policy":
        value["policy_id"] = "unknown"
    elif mutation == "version":
        value["policy_version"] = "2.0.0"
    elif mutation == "duplicate":
        value["entries"].append(row.copy())
    elif mutation == "order":
        value["entries"].reverse()
    elif mutation == "coverage":
        value["entries"].pop()
    elif mutation == "role":
        row["role"] = "report_snapshot"
    elif mutation == "class":
        row["source_class"] = "CANONICAL_TECHNICAL"
    elif mutation == "path":
        row["package_path"] = "../escape"
    elif mutation == "label":
        row["local_label"] = "unexpected"
    elif mutation == "size":
        row["byte_size"] += 1
    elif mutation == "hash":
        row["sha256"] = "0" * 64
    elif mutation == "bool":
        row["byte_size"] = True
    else:
        row["extra"] = "synthetic"
    path.write_bytes(encode(value))
    reseal(root)
    with failure():
        p.capture_source_package(root)


@pytest.mark.parametrize(
    "field,value",
    [
        ("policy_id", "other"),
        ("policy_version", "2.0.0"),
        ("delivery_profile", "pdf-presentation-v1"),
        ("issued_date", "yesterday"),
        ("case_reference", "../bad"),
        ("unknown", "synthetic"),
    ],
)
def test_metadata_contract(root, field, value):
    path = root / p.METADATA_PATH
    document = json.loads(path.read_bytes())
    document[field] = value
    path.write_bytes(encode(document))
    reseal(root, refresh=True)
    with failure():
        p.capture_source_package(root)


@pytest.mark.parametrize("mutation", ["order", "missing", "class", "path", "extra"])
def test_metadata_items(root, mutation):
    path = root / p.METADATA_PATH
    value = json.loads(path.read_bytes())
    if mutation == "order":
        value["items"].reverse()
    elif mutation == "missing":
        value["items"].pop()
    elif mutation == "class":
        value["items"][0]["source_class"] = "VISUAL_EXHIBIT"
    elif mutation == "path":
        value["items"][0]["package_path"] = "human/dossier.md"
    else:
        value["items"][0]["input_reference"] = "private"
    path.write_bytes(encode(value))
    reseal(root, refresh=True)
    with failure():
        p.capture_source_package(root)


@pytest.mark.parametrize("kind", ["extra-file", "extra-directory", "hash", "sums"])
def test_source_tree_integrity(root, kind):
    if kind == "extra-file":
        (root / "extra").write_bytes(b"synthetic")
    elif kind == "extra-directory":
        (root / "extra").mkdir()
    elif kind == "hash":
        path = root / "human/annex-index.md"
        content = path.read_bytes()
        path.write_bytes(b"!" + content[1:])
    else:
        (root / p.SUMS_PATH).write_bytes(b"")
    with failure():
        p.capture_source_package(root)


@pytest.mark.parametrize(
    "path",
    [
        "human/dossier.md",
        "technical/canonical/consolidated-report.md",
        p.SOURCE_MANIFEST,
        p.SUMS_PATH,
        "technical/canonical/snapshots/anchor.json",
    ],
)
@pytest.mark.parametrize("mutation", ["edit", "replace", "delete"])
def test_source_recheck_change(root, path, mutation):
    source = p.capture_source_package(root)
    target = root / path
    content = target.read_bytes()
    if mutation in ("replace", "delete"):
        target.unlink()
    if mutation != "delete":
        target.write_bytes(content if mutation == "replace" else b"!" + content[1:])
    with failure("INPUT_CHANGED"):
        p.recheck_source_package(source)


def test_change_during_recheck(root, monkeypatch):
    source = p.capture_source_package(root)
    read = p.source_integrity._read_payload

    def replaced(*args, **kwargs):
        result = read(*args, **kwargs)
        path = root / "human/dossier.md"
        content = path.read_bytes()
        path.unlink()
        path.write_bytes(content)
        return result

    monkeypatch.setattr(p.source_integrity, "_read_payload", replaced)
    with failure("INPUT_CHANGED"):
        p.recheck_source_package(source)


def test_change_during_capture(root, monkeypatch):
    read = p._read

    def replaced(*args, **kwargs):
        result = read(*args, **kwargs)
        if args[1] == "human/dossier.md":
            path = root / "human/dossier.md"
            content = path.read_bytes()
            path.unlink()
            path.write_bytes(content)
        return result

    monkeypatch.setattr(p, "_read", replaced)
    with failure("INPUT_CHANGED"):
        p.capture_source_package(root)


def test_change_during_pdf_validation(root, valid, monkeypatch):
    source = p.capture_source_package(root)
    validate = p.validate_pdf_bytes

    def modified(*args, **kwargs):
        result = validate(*args, **kwargs)
        (root / "human/annex-index.md").write_bytes(b"synthetic changed")
        return result

    monkeypatch.setattr(p, "validate_pdf_bytes", modified)
    with failure("INPUT_CHANGED"):
        bind(source, valid[2])


@pytest.mark.parametrize("kind", ["extra-file", "extra-directory", "directory-replaced"])
def test_changed_tree_at_recheck(root, kind):
    source = p.capture_source_package(root)
    if kind == "extra-file":
        (root / "extra").write_bytes(b"synthetic")
    elif kind == "extra-directory":
        (root / "extra").mkdir()
    else:
        (root / "human").rename(root.parent / "old-human")
        shutil.copytree(root.parent / "old-human", root / "human")
    with failure("INPUT_CHANGED"):
        p.recheck_source_package(source)


def test_twenty_one_snapshots_no_semantic_cap(tmp_path):
    config = inputs(tmp_path, windows=True)
    run(config)
    source = p.capture_source_package(config[1])
    assert (
        sum(f.package_path.startswith("technical/canonical/snapshots/") for f in source.files) == 21
    )


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo"])
def test_unsafe_nodes(root, kind):
    path = root / "human/dossier.md"
    if kind == "hardlink":
        os.link(path, root.parent / "linked")
    else:
        path.unlink()
        if kind == "symlink":
            try:
                path.symlink_to(root / "human/annex-index.md")
            except OSError:
                pytest.skip("symlink creation unavailable")
        else:
            if not hasattr(os, "mkfifo"):
                pytest.skip("FIFO unavailable")
            os.mkfifo(path)
    with failure():
        p.capture_source_package(root)


@pytest.mark.parametrize("kind", ["swapped", "dossier", "report", "byte"])
def test_wrong_pdf(valid, kind):
    _, source, result = valid
    files = dict(result.files)
    dossier, report = files["human/dossier.pdf"], files["human/consolidated-report.pdf"]
    if kind == "swapped":
        dossier, report = report, dossier
    elif kind == "dossier":
        dossier = report
    elif kind == "report":
        report = dossier
    else:
        dossier = b"!" + dossier[1:]
    with failure("PDF_VALIDATION_FAILURE"):
        p.bind_pdf_export(source, dossier_pdf=dossier, consolidated_report_pdf=report)


def test_different_source_expectation(root, valid):
    path = root / "human/dossier.md"
    path.write_bytes(path.read_bytes().replace(b"## 1.", b"Texto sintetico diferente.\n\n## 1.", 1))
    reseal(root, refresh=True)
    with failure():
        bind(p.capture_source_package(root), valid[2])


def test_closed_binding_api(valid):
    assert set(inspect.signature(p.bind_pdf_export).parameters) == {
        "source",
        "dossier_pdf",
        "consolidated_report_pdf",
    }
    with pytest.raises(TypeError):
        p.bind_pdf_export(valid[1], mapping={})


@pytest.mark.parametrize("field", ["retained", "files", "directories"])
def test_forged_capture(valid, field):
    source = replace(valid[1], **{field: ()})
    with failure("INPUT_CHANGED"):
        p.recheck_source_package(source)


def test_determinism_and_no_renderer(root, valid, monkeypatch):
    source = p.capture_source_package(root)

    def forbidden(*args, **kwargs):
        raise AssertionError("rendering forbidden during binding")

    monkeypatch.setattr(renderer, "render_dossier_pdf", forbidden)
    monkeypatch.setattr(renderer, "render_consolidated_report_pdf", forbidden)
    actual = bind(source, valid[2])
    assert actual == valid[2]
    entries = [pdf.entry for pdf in actual.pdfs]
    kwargs = dict(
        manifest_sha256=sha(source.source_bytes(p.SOURCE_MANIFEST)),
        sha256sums_sha256=sha(source.source_bytes(p.SUMS_PATH)),
        render_environment_id=actual.render_environment_id,
    )
    assert p.serialize_pdf_manifest(entries[::-1], **kwargs) == actual.manifest_content


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "missing",
        "policy",
        "version",
        "profile",
        "source-hash",
        "source-extra",
        "missing-entry",
        "extra-entry",
        "duplicate",
        "order",
        "bool",
        "negative",
        "zero-page",
        "negative-page",
        "uppercase",
        "bad-hash",
        "path",
        "source-path",
    ],
)
def test_output_manifest_failures(valid, mutation):
    files = dict(valid[2].files)
    value = json.loads(files[p.MANIFEST_PATH])
    row = value["entries"][0]
    if mutation == "unknown":
        value["extra"] = "x"
    elif mutation == "missing":
        del value["policy_id"]
    elif mutation == "policy":
        value["policy_id"] = "other"
    elif mutation == "version":
        value["export_policy_version"] = "2.0.0"
    elif mutation == "profile":
        value["delivery_profile"] = "directory-v1"
    elif mutation == "source-hash":
        value["source_package"]["manifest_sha256"] = "0" * 64
    elif mutation == "source-extra":
        value["source_package"]["extra"] = "x"
    elif mutation == "missing-entry":
        value["entries"].pop()
    elif mutation == "extra-entry":
        value["entries"].append(row.copy())
    elif mutation == "duplicate":
        value["entries"][1] = row.copy()
    elif mutation == "order":
        value["entries"].reverse()
    elif mutation == "bool":
        row["byte_size"] = True
    elif mutation == "negative":
        row["source_byte_size"] = -1
    elif mutation == "zero-page":
        row["page_count"] = 0
    elif mutation == "negative-page":
        row["page_count"] = -1
    elif mutation == "uppercase":
        row["sha256"] = "A" * 64
    elif mutation == "bad-hash":
        row["sha256"] = "x"
    elif mutation == "path":
        row["package_path"] = "human/other.pdf"
    else:
        row["source_package_path"] = "human/dossier.md"
    files[p.MANIFEST_PATH] = encode(value)
    # Recompute sums so manifest failures cannot be masked by checksum rejection.
    files[p.SUMS_PATH] = p.serialize_pdf_sha256sums(
        dossier_pdf=files["human/dossier.pdf"],
        consolidated_report_pdf=files["human/consolidated-report.pdf"],
        manifest=files[p.MANIFEST_PATH],
    )
    with failure():
        p.verify_pdf_export(valid[1], files)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "duplicate",
        "order",
        "uppercase",
        "malformed",
        "one-space",
        "three-space",
        "crlf",
        "absolute",
        "traversal",
        "backslash",
        "self",
    ],
)
@pytest.mark.parametrize("output", [False, True])
def test_sums_failures(root, valid, mutation, output):
    files = dict(valid[2].files) if output else package_bytes(root)
    lines = files[p.SUMS_PATH].decode().splitlines(keepends=True)
    if mutation == "missing":
        lines.pop()
    elif mutation == "extra":
        lines.append("0" * 64 + "  extra\n")
    elif mutation == "duplicate":
        lines.append(lines[0])
    elif mutation == "order":
        lines.reverse()
    elif mutation == "uppercase":
        lines[0] = lines[0][:64].upper() + lines[0][64:]
    elif mutation == "malformed":
        lines[0] = "x" + lines[0][1:]
    elif mutation == "one-space":
        lines[0] = lines[0].replace("  ", " ", 1)
    elif mutation == "three-space":
        lines[0] = lines[0].replace("  ", "   ", 1)
    elif mutation == "crlf":
        lines = [line.replace("\n", "\r\n") for line in lines]
    elif mutation == "absolute":
        lines[0] = lines[0][:66] + "/" + lines[0][66:]
    elif mutation == "traversal":
        lines[0] = lines[0][:66] + "../" + lines[0][66:]
    elif mutation == "backslash":
        lines[0] = lines[0].replace("/", "\\")
    else:
        lines.append("0" * 64 + "  " + p.SUMS_PATH + "\n")
    files[p.SUMS_PATH] = "".join(lines).encode()
    with failure():
        if output:
            p.verify_pdf_export(valid[1], files)
        else:
            (root / p.SUMS_PATH).write_bytes(files[p.SUMS_PATH])
            p.capture_source_package(root)


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_output_coverage(valid, mutation):
    files = dict(valid[2].files)
    if mutation == "missing":
        files.pop("human/dossier.pdf")
    else:
        files["extra"] = b""
    with failure("INTEGRITY_MISMATCH"):
        p.verify_pdf_export(valid[1], files)


@pytest.mark.parametrize(
    "limit", ["MAX_SOURCE_FILES", "MAX_SOURCE_BYTES", "MAX_MARKDOWN_TOTAL", "MAX_ADMIN_BYTES"]
)
def test_capture_boundaries(root, monkeypatch, limit):
    files = package_bytes(root)
    threshold = {
        "MAX_SOURCE_FILES": len(files),
        "MAX_SOURCE_BYTES": sum(map(len, files.values())),
        "MAX_MARKDOWN_TOTAL": sum(len(files[s]) for _, s, _ in p._BINDINGS),
        "MAX_ADMIN_BYTES": max(map(len, files.values())),
    }[limit]
    monkeypatch.setattr(p, limit, threshold)
    p.capture_source_package(root)
    monkeypatch.setattr(p, limit, threshold - 1)
    with failure("RESOURCE_LIMIT"):
        p.capture_source_package(root)


@pytest.mark.parametrize("limit", ["MAX_PDF_TOTAL", "MAX_OUTPUT_BYTES", "MAX_INTEGRITY_BYTES"])
def test_output_boundaries(valid, monkeypatch, limit):
    result = valid[2]
    files = dict(result.files)
    threshold = {
        "MAX_PDF_TOTAL": sum(len(pdf.content) for pdf in result.pdfs),
        "MAX_OUTPUT_BYTES": sum(map(len, files.values())),
        "MAX_INTEGRITY_BYTES": len(result.manifest_content),
    }[limit]
    monkeypatch.setattr(p, limit, threshold)
    assert bind(valid[1], result) == result
    monkeypatch.setattr(p, limit, threshold - 1)
    with failure("RESOURCE_LIMIT"):
        bind(valid[1], result)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("source_byte_size", True),
        ("byte_size", -1),
        ("page_count", False),
        ("page_count", 0),
        ("page_count", 1001),
        ("sha256", "A" * 64),
        ("source_sha256", "bad"),
    ],
)
def test_pure_manifest_types(valid, field, bad):
    entries = [pdf.entry for pdf in valid[2].pdfs]
    entries[0] = replace(entries[0], **{field: bad})
    with failure():
        p.serialize_pdf_manifest(
            entries,
            manifest_sha256="0" * 64,
            sha256sums_sha256="1" * 64,
            render_environment_id="2" * 64,
        )


@pytest.mark.parametrize(
    "path", ["a" * 255, "/".join(["a"] * 32), "/".join(["a" * 255] * 3 + ["a" * 254, "a"])]
)
def test_path_boundaries(path):
    with p._errors():
        p.selection._input_reference(path)
    suffix = "/a" if path.count("/") == 31 else "a"
    with failure("RESOURCE_LIMIT"), p._errors():
        p.selection._input_reference(path + suffix)


@pytest.mark.parametrize(
    "limit,content,threshold",
    [
        ("MAX_NUMBER_CHARS", b'{"a":123}\n', 3),
        ("MAX_JSON_NODES_PER_FILE", b'{"a":1}\n', 3),
        ("MAX_JSON_DEPTH", b'{"a":{"b":1}}\n', 2),
    ],
)
def test_json_boundaries(monkeypatch, limit, content, threshold):
    monkeypatch.setattr(p.selection, limit, threshold)
    with p._errors():
        p._json(content, 1024)
    monkeypatch.setattr(p.selection, limit, threshold - 1)
    with failure("RESOURCE_LIMIT"), p._errors():
        p._json(content, 1024)


def test_source_import_and_side_effect_sentinel():
    source = inspect.getsource(p)
    tree = ast.parse(source)
    imports = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports |= {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(
        any(
            part in name
            for part in (
                "storage",
                "sqlite",
                "reports",
                "service",
                "socket",
                "requests",
                "subprocess",
                "PIL",
            )
        )
        for name in imports
    )
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not calls & {
        "write_bytes",
        "write_text",
        "mkdir",
        "unlink",
        "rename",
        "replace",
        "assemble_dossier",
        "render_dossier_pdf",
        "render_consolidated_report_pdf",
        "load_case",
        "connect",
        "create_staging",
        "publish_staging",
    }
    assert "CASE_ROOT" not in source and "originals/" not in source and "working/" not in source


@pytest.mark.parametrize(
    "exception,code",
    [
        (OSError("private synthetic path"), "INVALID_PACKAGE"),
        (MemoryError(), "RESOURCE_LIMIT"),
        (RuntimeError("private synthetic payload"), "INTERNAL_ERROR"),
        (EvidenceError("DOSSIER_HASH_MISMATCH"), "INTEGRITY_MISMATCH"),
    ],
)
def test_sanitized_errors(monkeypatch, exception, code):
    def broken(*args, **kwargs):
        raise exception

    monkeypatch.setattr(p.capture, "_inspect", broken)
    with failure(code):
        p.capture_source_package(Path("synthetic"))
