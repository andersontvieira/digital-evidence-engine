"""Synthetic staging/no-replace probes, independent of PDF semantic validation."""

import errno
import hashlib
import os
from dataclasses import FrozenInstanceError

import pytest

from evidence_engine.dossier import packaging
from evidence_engine.dossier import pdf_service as service
from evidence_engine.dossier import pdf_worker as worker
from evidence_engine.errors import EvidenceError
from tests.test_pdf_renderer import pytestmark as pytestmark


@pytest.fixture
def operation(tmp_path, monkeypatch):
    source = tmp_path / "input"
    source.mkdir()
    output = tmp_path / "output"
    observed = []
    monkeypatch.setattr(service, "_runtime_preflight", lambda *args: None)

    def synthetic_worker(command, *, scratch, deadline, on_drop, monitor_scratch):
        root = packaging._inspect(scratch.parent, directory=True)
        observed.append(root.path)
        assert root.path.parent == output.parent and root.path != output
        assert root.info.st_mode & 0o077 == 0
        assert not output.exists()
        data = tuple((path, (path + " synthetic\n").encode()) for path in worker.OUTPUT_PATHS)
        service.write_staged(root, data)
        monitor_scratch()
        on_drop()
        assert not scratch.exists()
        return tuple(
            worker.OutputRecord(path, len(content), hashlib.sha256(content).hexdigest())
            for path, content in data
        )

    monkeypatch.setattr(service, "_supervise", synthetic_worker)
    return source, output, observed


def test_exact_four_files_exclusive_private_staging(operation):
    source, output, observed = operation
    result = service.export_dossier_pdf(source, output)
    assert result.file_count == 4 and result.output_dir == output
    assert {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()} == set(
        worker.OUTPUT_PATHS
    )
    assert result.total_byte_size == sum(p.stat().st_size for p in output.rglob("*") if p.is_file())
    assert not observed[0].exists() and not list(source.iterdir())
    with pytest.raises(FrozenInstanceError):
        result.file_count = 0


@pytest.mark.parametrize("kind", ["file", "directory", "link"])
def test_preexisting_destination_preserved(operation, kind):
    source, output, observed = operation
    if kind == "file":
        output.write_bytes(b"winner")
    elif kind == "directory":
        output.mkdir()
    else:
        output.symlink_to(source, target_is_directory=True)
    with pytest.raises(EvidenceError, match="OUTPUT_EXISTS"):
        service.export_dossier_pdf(source, output)
    assert output.is_symlink() if kind == "link" else output.exists()
    assert not observed


@pytest.mark.parametrize(
    "kind", ["equal", "output-nested", "source-nested", "unsafe-parent", "ads"]
)
def test_unsafe_paths_fail_before_staging(operation, kind):
    source, output, observed = operation
    if kind == "equal":
        output = source
    elif kind == "output-nested":
        output = source / "output"
    elif kind == "source-nested":
        output = source.parent
    elif kind == "unsafe-parent":
        link = source.parent / "alias"
        link.symlink_to(source, target_is_directory=True)
        output = link / "output"
    else:
        output = output.parent / "output:stream"
    with pytest.raises(EvidenceError, match="INVALID_PACKAGE"):
        service.export_dossier_pdf(source, output)
    assert not observed


def test_racing_destination_preserves_winner(operation, monkeypatch):
    source, output, _ = operation
    publish = packaging.publish_staging

    def racing(staging):
        output.mkdir()
        (output / "winner").write_bytes(b"unchanged")
        publish(staging)

    monkeypatch.setattr(packaging, "publish_staging", racing)
    with pytest.raises(EvidenceError, match="OUTPUT_EXISTS"):
        service.export_dossier_pdf(source, output)
    assert (output / "winner").read_bytes() == b"unchanged"
    assert not list(output.parent.glob(packaging.STAGING_PREFIX + "*"))


@pytest.mark.parametrize(
    "failure",
    ["write", "fsync", "scratch", "scratch-overflow", "extra", "missing", "mutated", "link"],
)
def test_staging_failures_never_publish(operation, monkeypatch, failure):
    source, output, _ = operation
    if failure == "write":
        monkeypatch.setattr(
            packaging,
            "_writer",
            lambda *args: (_ for _ in ()).throw(OSError(errno.EIO, "synthetic")),
        )
    elif failure == "fsync":
        monkeypatch.setattr(
            os, "fsync", lambda fd: (_ for _ in ()).throw(OSError(errno.EIO, "synthetic"))
        )
    elif failure == "scratch":
        monkeypatch.setattr(service, "_drop_scratch", lambda *args: service.fail("STAGING_FAILURE"))
    elif failure == "scratch-overflow":
        create = service._create_scratch

        def oversized(staging):
            scratch = create(staging)
            with (scratch.path / "synthetic").open("wb") as stream:
                stream.truncate(service.SCRATCH_BYTES + 1)
            return scratch

        monkeypatch.setattr(service, "_create_scratch", oversized)
    else:
        supervise = service._supervise

        def tamper(*args, **kwargs):
            result = supervise(*args, **kwargs)
            root = kwargs["scratch"].parent
            target = root / worker.OUTPUT_PATHS[0]
            if failure == "extra":
                (root / "extra").write_bytes(b"x")
            elif failure == "missing":
                target.unlink()
            elif failure == "link":
                target.unlink()
                target.symlink_to(source)
            else:
                target.write_bytes(b"mutated")
            return result

        monkeypatch.setattr(service, "_supervise", tamper)
    expected = "RESOURCE_LIMIT" if failure == "scratch-overflow" else "STAGING_FAILURE"
    with pytest.raises(EvidenceError, match=expected):
        service.export_dossier_pdf(source, output)
    assert not output.exists()


def test_changed_ownership_never_deletes_replacement(operation, monkeypatch):
    source, output, observed = operation
    supervise = service._supervise

    def replaced(*args, **kwargs):
        result = supervise(*args, **kwargs)
        root = kwargs["scratch"].parent
        root.rename(root.parent / "displaced-synthetic")
        root.mkdir()
        (root / "foreign").write_bytes(b"preserve")
        return result

    monkeypatch.setattr(service, "_supervise", replaced)
    with pytest.raises(EvidenceError, match="STAGING_FAILURE"):
        service.export_dossier_pdf(source, output)
    assert (observed[0] / "foreign").read_bytes() == b"preserve"
    assert not output.exists()


@pytest.mark.parametrize("ambiguous", [False, True])
def test_publication_failure_no_fallback_or_rollback(operation, monkeypatch, ambiguous):
    source, output, observed = operation
    publish = packaging.publish_staging
    calls = []

    def failed(staging):
        calls.append(1)
        if ambiguous:
            publish(staging)
        raise EvidenceError("DOSSIER_PUBLICATION_FAILURE")

    monkeypatch.setattr(packaging, "publish_staging", failed)
    with pytest.raises(EvidenceError, match="PUBLICATION_FAILURE"):
        service.export_dossier_pdf(source, output)
    assert calls == [1] and output.exists() == ambiguous
    assert not observed[0].exists()


def test_cleanup_error_takes_precedence(operation, monkeypatch):
    source, output, _ = operation
    monkeypatch.setattr(
        service, "_supervise", lambda *args, **kwargs: service.fail("RESOURCE_LIMIT")
    )
    monkeypatch.setattr(packaging, "cleanup_staging", lambda *args: service.fail("STAGING_FAILURE"))
    with pytest.raises(EvidenceError, match="STAGING_FAILURE"):
        service.export_dossier_pdf(source, output)


def test_no_filesystem_io_after_confirmed_publish(operation, monkeypatch):
    source, output, _ = operation
    publish = packaging.publish_staging
    confirmed = False

    def once(staging):
        nonlocal confirmed
        publish(staging)
        confirmed = True

    for name in ("stat", "lstat", "open", "scandir", "fsync", "unlink", "rmdir", "readlink"):
        original = getattr(os, name)

        def guarded(*args, _original=original, **kwargs):
            assert not confirmed, "filesystem access after publication"
            return _original(*args, **kwargs)

        monkeypatch.setattr(os, name, guarded)
    monkeypatch.setattr(packaging, "publish_staging", once)
    result = service.export_dossier_pdf(source, output)
    assert confirmed and result.file_count == 4
    confirmed = False  # pytest may now inspect/remove its own temporary files.


def test_writer_is_exclusive_and_closed(tmp_path):
    root = packaging._inspect(tmp_path, directory=True)
    files = tuple((path, b"x") for path in worker.OUTPUT_PATHS)
    service.write_staged(root, files)
    with pytest.raises(EvidenceError, match="STAGING_FAILURE"):
        service.write_staged(root, files)
    with pytest.raises(EvidenceError, match="INTERNAL_ERROR"):
        service.write_staged(root, (("other", b"x"),))
