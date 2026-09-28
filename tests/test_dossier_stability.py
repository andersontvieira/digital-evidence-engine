"""Synthetic mutations and budget boundaries; no restoration of source metadata."""

import os
from contextlib import contextmanager

import pytest

from evidence_engine.dossier import packaging as p
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic import hashing
from tests.test_dossier_packaging import capture, setup_inputs
from tests.test_dossier_selection import item, minimal
from tests.test_file_stability import info


def test_all_baselines_precede_first_copy(tmp_path, monkeypatch):
    config = setup_inputs(tmp_path)
    source_paths = {config[0].parent / i.input_reference for i in config[1].canonical_inputs}
    baselined = set()
    actual_inspect, actual_copy = p._inspect, p._copy

    def inspect(path, **kwargs):
        result = actual_inspect(path, **kwargs)
        if path in source_paths:
            baselined.add(path)
        return result

    def copy(*args):
        assert baselined == source_paths
        return actual_copy(*args)

    monkeypatch.setattr(p, "_inspect", inspect)
    monkeypatch.setattr(p, "_copy", copy)
    capture(config)


@pytest.mark.parametrize("phase", ["before_open", "after_copy", "final"])
def test_source_replacement_invalidates_set(tmp_path, monkeypatch, phase):
    config = setup_inputs(tmp_path)
    source = config[0].parent / config[1].canonical_inputs[0].input_reference
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"synthetic changed")
    actual_copy = p._copy
    calls = 0

    def copy(*args):
        nonlocal calls
        calls += 1
        if phase == "before_open" and calls == 1:
            replacement.replace(source)
        result = actual_copy(*args)
        if (phase == "after_copy" and calls == 1) or (phase == "final" and calls == 2):
            replacement.replace(source)
        return result

    monkeypatch.setattr(p, "_copy", copy)
    with pytest.raises(EvidenceError, match="^DOSSIER_INPUT_CHANGED$"):
        capture(config)


@pytest.mark.parametrize("mutation", ["truncate", "grow", "same_size", "mode"])
def test_mutation_during_read(tmp_path, monkeypatch, mutation):
    config = setup_inputs(tmp_path)
    original = p._chunks
    source = config[0].parent / config[1].canonical_inputs[0].input_reference
    done = False

    def chunks(stream, limit):
        nonlocal done
        for chunk in original(stream, limit):
            if not done:
                done = True
                if mutation == "mode":
                    source.chmod(0o400)
                else:
                    data = source.read_bytes()
                    source.write_bytes(
                        b""
                        if mutation == "truncate"
                        else data + b"extra"
                        if mutation == "grow"
                        else b"x" * len(data)
                    )
            yield chunk

    monkeypatch.setattr(p, "_chunks", chunks)
    with pytest.raises(EvidenceError, match="^DOSSIER_INPUT_CHANGED$"):
        capture(config)


def test_handle_identity_swap(tmp_path, monkeypatch):
    config = setup_inputs(tmp_path)
    actual = os.fstat

    def swapped(fd):
        result = actual(fd)
        return info(
            st_dev=result.st_dev,
            st_ino=result.st_ino + 1,
            st_mode=result.st_mode,
            st_size=result.st_size,
            st_mtime_ns=result.st_mtime_ns,
            st_ctime_ns=result.st_ctime_ns,
            st_nlink=result.st_nlink,
        )

    monkeypatch.setattr(hashing.os, "fstat", swapped)
    with pytest.raises(EvidenceError, match="^DOSSIER_INPUT_CHANGED$"):
        capture(config)


@pytest.mark.parametrize("windows", [False, True])
def test_platform_stability_policy_not_native_parity(monkeypatch, windows):
    monkeypatch.setattr(hashing, "_WINDOWS", windows)
    before = info(st_nlink=1)
    assert p._same(before, info(st_nlink=1, st_ctime_ns=999)) is windows
    assert p._same(before, info(st_nlink=1, st_atime_ns=999, st_birthtime_ns=999))
    assert not p._same(before, info(st_nlink=1, st_mode=before.st_mode ^ 0o200))


@pytest.mark.parametrize(
    "limit_name,role",
    [
        ("MAX_REPORT_BYTES", "consolidated_report"),
        ("MAX_SNAPSHOT_BYTES", "report_snapshot"),
        ("MAX_SUPPLEMENTAL_BYTES", "technical_review"),
        ("MAX_SUPPLEMENTAL_BYTES", "structured_support"),
        ("MAX_SUPPLEMENTAL_BYTES", "validation_report"),
        ("MAX_VISUAL_BYTES", "contextual_visual"),
    ],
)
@pytest.mark.parametrize("over", [False, True])
def test_role_budget_before_open(tmp_path, monkeypatch, limit_name, role, over):
    document = minimal()
    label = "report" if role == "consolidated_report" else "anchor"
    if role not in ("consolidated_report", "report_snapshot"):
        label = "extra"
        group = (
            "visual_exhibits"
            if role == "contextual_visual"
            else ("validation_artifacts" if role == "validation_report" else "supplemental_inputs")
        )
        document[group] = [item(role, label)]
    config = setup_inputs(tmp_path, document=document, payloads={label: b"x" * (32 + over)})
    monkeypatch.setattr(p, limit_name, 32)
    if over:

        def forbidden(*args):
            raise AssertionError("over-budget file opened")

        monkeypatch.setattr(p, "original_reader", forbidden)
        with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
            capture(config)
    else:
        assert capture(config)


@pytest.mark.parametrize("budget", ["MAX_TOTAL_INPUT_BYTES", "MAX_TOTAL_SNAPSHOT_BYTES"])
@pytest.mark.parametrize("over", [False, True])
def test_aggregate_bytes(tmp_path, monkeypatch, budget, over):
    document = minimal()
    document["canonical_inputs"].append(item(label="second"))
    config = setup_inputs(
        tmp_path, document=document, payloads={"report": b"x", "anchor": b"12", "second": b"34"}
    )
    size = 5 if budget == "MAX_TOTAL_INPUT_BYTES" else 4
    monkeypatch.setattr(p, budget, size - int(over))
    if over:
        with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
            capture(config)
    else:
        assert len(capture(config).inputs) == 3


def test_selection_stable_byte_budget(tmp_path, monkeypatch):
    path = tmp_path / "selection.json"
    path.write_bytes(b"{}")
    monkeypatch.setattr(p, "MAX_SELECTION_BYTES", 2)
    assert p.read_selection_bytes_stable(path) == b"{}"
    path.write_bytes(b"{} ")
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        p.read_selection_bytes_stable(path)


def test_stream_growth_budget_precedes_stability(tmp_path, monkeypatch):
    config = setup_inputs(tmp_path, payloads={"report": b"1234"})
    monkeypatch.setattr(p, "MAX_REPORT_BYTES", 4)
    monkeypatch.setattr(p, "CHUNK_SIZE", 2)
    original = p.original_reader

    @contextmanager
    def reader(path):
        with original(path) as stream:
            if path.name == "report.synthetic":

                class Growing:
                    def fileno(self):
                        return stream.fileno()

                    def read(self, size):
                        assert size == 2
                        return b"xx"

                yield Growing()
            else:
                yield stream

    monkeypatch.setattr(p, "original_reader", reader)
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        capture(config)


def test_captured_copy_tampering_and_failure_not_success(tmp_path, monkeypatch):
    config = setup_inputs(tmp_path)
    actual = p.read_captured_bytes

    def tamper(item):
        item.captured_path.write_bytes(b"z" * item.byte_size)
        return actual(item)

    monkeypatch.setattr(p, "read_captured_bytes", tamper)
    with pytest.raises(EvidenceError, match="^DOSSIER_HASH_MISMATCH$"):
        capture(config)
    assert config[2].is_dir()


def test_distinct_physical_files_same_bytes_are_kept(tmp_path):
    config = setup_inputs(tmp_path, payloads={"report": b"{}", "anchor": b"{}"})
    batch = capture(config)
    assert len(batch.inputs) == 2 and batch.inputs[0].sha256 == batch.inputs[1].sha256


def test_physical_alias_identity_even_when_names_differ(tmp_path, monkeypatch):
    original = p.file_identity

    def identity(info):
        result = original(info)
        return (1, 1, result[2]) if info.st_size == 2 else result

    document = minimal()
    document["canonical_inputs"].append(item(label="second"))
    other = setup_inputs(tmp_path / "aliases", document=document)
    monkeypatch.setattr(p, "file_identity", identity)
    with pytest.raises(EvidenceError, match="^DOSSIER_INVALID_PATH$"):
        capture(other)


def test_failed_write_has_sanitized_error_and_keeps_caller_root(tmp_path, monkeypatch):
    config = setup_inputs(tmp_path)
    actual = p.os.fsync

    def fail(fd):
        actual(fd)
        raise OSError("private synthetic host/path/hash")

    monkeypatch.setattr(p.os, "fsync", fail)
    with pytest.raises(EvidenceError, match="^DOSSIER_STAGING_FAILURE$"):
        capture(config)
    assert config[2].is_dir()
