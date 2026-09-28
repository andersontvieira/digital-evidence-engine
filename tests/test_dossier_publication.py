"""Real Linux no-replace and synthetic failure/ownership races; no real evidence."""

import errno
import os
import stat
from pathlib import Path

import pytest

from evidence_engine.dossier import packaging as p
from evidence_engine.dossier import selection as a
from evidence_engine.errors import EvidenceError
from tests.test_dossier_service import assert_no_staging, inputs, run


def stage_for(config):
    prepared = p.prepare_capture(
        selection_path=config[0], selection=a.parse_selection_bytes(config[0].read_bytes())
    )
    return p.create_staging(p.prepare_output(prepared, config[1]))


@pytest.mark.skipif(p._PLATFORM != "linux", reason="Real Linux renameat2 gate")
def test_real_linux_noreplace_preserves_existing_and_publishes_new(tmp_path):
    config = inputs(tmp_path)
    stage = stage_for(config)
    (stage.path / "owned").write_bytes(b"synthetic staged bytes")
    config[1].mkdir()
    (config[1] / "sentinel").write_bytes(b"existing")
    with pytest.raises(EvidenceError) as error:
        p.publish_staging(stage)
    if str(error.value) == "DOSSIER_PUBLICATION_FAILURE":
        # Explicit unsupported primitive outcome, never a success claim/fallback.
        assert stage.path.exists() and (config[1] / "sentinel").read_bytes() == b"existing"
        return
    assert str(error.value) == "DOSSIER_OUTPUT_EXISTS"
    assert (config[1] / "sentinel").read_bytes() == b"existing"
    (config[1] / "sentinel").unlink()
    config[1].rmdir()
    p.publish_staging(stage)
    assert not stage.path.exists()
    assert (config[1] / "owned").read_bytes() == b"synthetic staged bytes"


@pytest.mark.parametrize(
    "code,expected",
    [
        (errno.EEXIST, "OUTPUT_EXISTS"),
        (errno.ENOSYS, "PUBLICATION_FAILURE"),
        (errno.EOPNOTSUPP, "PUBLICATION_FAILURE"),
        (errno.EINVAL, "PUBLICATION_FAILURE"),
        (errno.EXDEV, "PUBLICATION_FAILURE"),
        (errno.EIO, "PUBLICATION_FAILURE"),
    ],
)
def test_linux_errno_no_fallback(tmp_path, monkeypatch, code, expected):
    stage = stage_for(inputs(tmp_path))
    calls = []

    class Rename:
        def __call__(self, *args):
            calls.append(args)
            return -1

    class Library:
        renameat2 = Rename()

    def forbidden(*args):
        raise AssertionError("Plain rename fallback")

    monkeypatch.setattr(p, "_PLATFORM", "linux")
    monkeypatch.setattr(p.ctypes, "CDLL", lambda *args, **kwargs: Library())
    monkeypatch.setattr(p.ctypes, "get_errno", lambda: code)
    monkeypatch.setattr(p.os, "rename", forbidden)
    with pytest.raises(EvidenceError, match="^DOSSIER_" + expected + "$"):
        p.publish_staging(stage)
    assert len(calls) == 1 and calls[0][-1] == 1


def test_linux_missing_symbol_is_unsupported(tmp_path, monkeypatch):
    stage = stage_for(inputs(tmp_path))
    monkeypatch.setattr(p, "_PLATFORM", "linux")
    monkeypatch.setattr(p.ctypes, "CDLL", lambda *args, **kwargs: object())
    with pytest.raises(EvidenceError, match="^DOSSIER_PUBLICATION_FAILURE$"):
        p.publish_staging(stage)


@pytest.mark.parametrize(
    "failure,expected",
    [(None, None), (errno.EEXIST, "OUTPUT_EXISTS"), (errno.EIO, "PUBLICATION_FAILURE")],
)
def test_windows_dispatch_simulation_not_native_gate(tmp_path, monkeypatch, failure, expected):
    stage = stage_for(inputs(tmp_path))
    calls = []

    def rename(source, destination):
        calls.append((source, destination))
        if failure is not None:
            raise OSError(failure, "private host/path")

    monkeypatch.setattr(p, "_PLATFORM", "win32")
    monkeypatch.setattr(p.os, "rename", rename)
    if expected:
        with pytest.raises(EvidenceError, match="^DOSSIER_" + expected + "$"):
            p.publish_staging(stage)
    else:
        p.publish_staging(stage)
    assert calls == [(stage.path, stage.destination.path)]


def test_unsupported_platform_cleans_owned_work(tmp_path, monkeypatch):
    config = inputs(tmp_path)
    monkeypatch.setattr(p, "_PLATFORM", "unsupported")
    with pytest.raises(EvidenceError, match="^DOSSIER_PUBLICATION_FAILURE$"):
        run(config)
    assert not config[1].exists()
    assert_no_staging(config[1])


@pytest.mark.parametrize("empty", [False, True])
def test_destination_race_no_replace_or_merge(tmp_path, monkeypatch, empty):
    config = inputs(tmp_path)
    publish = p.publish_staging

    def race(stage):
        config[1].mkdir()
        if not empty:
            (config[1] / "sentinel").write_bytes(b"third party")
        publish(stage)

    monkeypatch.setattr(p, "publish_staging", race)
    with pytest.raises(EvidenceError, match="^DOSSIER_OUTPUT_EXISTS$"):
        run(config)
    assert config[1].is_dir()
    if not empty:
        assert (config[1] / "sentinel").read_bytes() == b"third party"
    assert_no_staging(config[1])


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_replaced_staging_not_cleaned(tmp_path, monkeypatch, kind):
    config = inputs(tmp_path)
    captured = []

    def swap(prepared, *, capture_root):
        capture_root.rename(tmp_path / "displaced-owned")
        if kind == "directory":
            capture_root.mkdir()
            (capture_root / "sentinel").write_bytes(b"replacement")
        else:
            external = tmp_path / "external"
            external.mkdir()
            (external / "sentinel").write_bytes(b"replacement")
            try:
                capture_root.symlink_to(external, target_is_directory=True)
            except OSError:
                pytest.skip("Host cannot create symlink")
        captured.append(capture_root)
        raise EvidenceError("DOSSIER_HASH_MISMATCH")

    monkeypatch.setattr(p, "capture_prepared_inputs", swap)
    with pytest.raises(EvidenceError, match="^DOSSIER_STAGING_FAILURE$"):
        run(config)
    assert (captured[0] / "sentinel").read_bytes() == b"replacement"
    assert (tmp_path / "displaced-owned").exists()


def test_cleanup_does_not_follow_inserted_link(tmp_path):
    stage = stage_for(inputs(tmp_path))
    external = tmp_path / "external"
    external.mkdir()
    (external / "keep").write_bytes(b"untouched")
    try:
        (stage.path / "link").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Host cannot create symlink")
    with pytest.raises(EvidenceError, match="^DOSSIER_STAGING_FAILURE$"):
        p.cleanup_staging(stage)
    assert (external / "keep").read_bytes() == b"untouched"


def test_publication_confirmation_loss_never_deletes_final(tmp_path, monkeypatch):
    config = inputs(tmp_path)
    publish = p.publish_staging
    calls = []

    def lost(stage):
        calls.append("publish")
        publish(stage)
        raise EvidenceError("DOSSIER_PUBLICATION_FAILURE")

    def forbidden(*args):
        raise AssertionError("Cleanup/retry after ambiguous successful move")

    monkeypatch.setattr(p, "publish_staging", lost)
    monkeypatch.setattr(p, "cleanup_staging", forbidden)
    with pytest.raises(EvidenceError, match="^DOSSIER_PUBLICATION_FAILURE$"):
        run(config)
    assert config[1].is_dir() and (config[1] / "integrity/manifest.json").is_file()
    assert calls == ["publish"]


@pytest.mark.parametrize("relative", p.GENERATED_PATHS[:3])
def test_generated_writer_preserves_preexisting_bytes(tmp_path, relative):
    stage = stage_for(inputs(tmp_path))
    path = stage.path / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"preexisting")
    with pytest.raises(EvidenceError, match="^DOSSIER_STAGING_FAILURE$"):
        p.write_generated_file(stage, relative, b"new")
    assert path.read_bytes() == b"preexisting"
    p.cleanup_staging(stage)
    assert not stage.path.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory fsync")
@pytest.mark.parametrize("failure", [None, errno.EINVAL, errno.EIO])
def test_directory_sync_order_and_error_mapping(tmp_path, monkeypatch, failure):
    stage = stage_for(inputs(tmp_path))
    paths = ("human/dossier.md", "technical/selection-metadata.json")
    for path in paths:
        p.write_generated_file(stage, path, b"synthetic\n")
    wanted = [
        stage.path / "human",
        stage.path / "technical",
        stage.path,
        stage.destination.parent.path,
    ]
    identities = {path.stat().st_ino: path for path in wanted}
    actual, seen = os.fsync, []

    def sync(fd):
        info = os.fstat(fd)
        assert stat.S_ISDIR(info.st_mode)
        seen.append(identities[info.st_ino])
        if failure is not None:
            raise OSError(failure, "private directory")
        actual(fd)

    monkeypatch.setattr(p.os, "fsync", sync)
    if failure == errno.EIO:
        with pytest.raises(EvidenceError, match="^DOSSIER_STAGING_FAILURE$"):
            p.sync_staging_directories(stage, paths)
    else:
        p.sync_staging_directories(stage, paths)
        assert seen == wanted


def test_staging_creation_failure_preserves_parent(tmp_path, monkeypatch):
    config = inputs(tmp_path)
    sentinel = config[1].parent / "keep"
    sentinel.write_bytes(b"existing")

    def fail(**kwargs):
        raise OSError("private host/path")

    monkeypatch.setattr(p.tempfile, "mkdtemp", fail)
    with pytest.raises(EvidenceError, match="^DOSSIER_STAGING_FAILURE$"):
        run(config)
    assert sentinel.read_bytes() == b"existing"


@pytest.mark.parametrize("name", [".", "..", "bad.", "bad ", "CON", "bad:ads", "bad\x00name"])
def test_output_component_rejected_before_staging(tmp_path, name):
    config = inputs(tmp_path)
    prepared = p.prepare_capture(
        selection_path=config[0], selection=a.parse_selection_bytes(config[0].read_bytes())
    )
    output = Path(name) if name in (".", "..") else config[1].parent / name
    with pytest.raises(EvidenceError, match="^DOSSIER_INVALID_PATH$"):
        p.prepare_output(prepared, output)
    assert_no_staging(config[1])


@pytest.mark.skipif(os.name != "posix", reason="Descriptor-relative cleanup race requires POSIX")
def test_cleanup_parent_swap_cannot_delete_external_payload(tmp_path, monkeypatch):
    stage = stage_for(inputs(tmp_path))
    directory = stage.path / "partial"
    directory.mkdir()
    (directory / "payload").write_bytes(b"owned")
    external = tmp_path / "external"
    external.mkdir()
    (external / "payload").write_bytes(b"external must remain")
    original = os.unlink
    swapped = False

    def race(name, *args, **kwargs):
        nonlocal swapped
        if name == "payload" and kwargs.get("dir_fd") is not None:
            swapped = True
            directory.rename(stage.path / "displaced")
            directory.symlink_to(external, target_is_directory=True)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(p.os, "unlink", race)
    with pytest.raises(EvidenceError, match="^DOSSIER_STAGING_FAILURE$"):
        p.cleanup_staging(stage)
    assert swapped and (external / "payload").read_bytes() == b"external must remain"
