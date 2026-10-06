"""Linux PDF operation supervision; publication belongs only to this process."""

import ctypes
import hashlib
import os
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from evidence_engine.dossier import integrity, packaging
from evidence_engine.dossier.pdf_worker import (
    CHANNEL_BYTES,
    MESSAGE_BYTES,
    OUTPUT_PATHS,
    History,
    OutputRecord,
    decode,
    encode,
    fail,
    safe_error_code,
)
from evidence_engine.errors import EvidenceError

GLOBAL_SECONDS = 900
PHASE_SECONDS = 180
SCRATCH_BYTES = 256 * 1024**2
_OPERATION_LOCK = threading.Lock()


class _ExecutionStillActive(EvidenceError):
    """Never permit filesystem cleanup when termination could not be established."""


@dataclass(frozen=True, slots=True)
class PdfExportResult:
    output_dir: Path
    file_count: int
    total_byte_size: int
    files: tuple[OutputRecord, ...]


@contextmanager
def _staging_errors() -> Iterator[None]:
    try:
        yield
    except (MemoryError, RecursionError):
        fail("RESOURCE_LIMIT")
    except EvidenceError as error:
        if str(error).startswith("DOSSIER_PDF_"):
            raise
        fail("STAGING_FAILURE")
    except OSError:
        fail("STAGING_FAILURE")


def write_staged(root: packaging._Baseline, files: tuple[tuple[str, bytes], ...]) -> None:
    """Narrow allowlist adapter over the approved exclusive/fsynced writer."""
    with _staging_errors():
        if tuple(path for path, _ in files) != OUTPUT_PATHS:
            fail("INTERNAL_ERROR")
        for path, content in files:
            limit = 64 * 1024**2 if path.endswith(".pdf") else 1024**2
            if type(content) is not bytes or len(content) > limit:
                fail("RESOURCE_LIMIT")
            with packaging._writer(root, path) as stream:
                for offset in range(0, len(content), packaging.CHUNK_SIZE):
                    stream.write(content[offset : offset + packaging.CHUNK_SIZE])


def read_staged(root: packaging._Baseline) -> dict[str, bytes]:
    """Worker-only bounded stable bytes for D; no independent interpretation."""
    with _staging_errors():
        files, directories = integrity._tree(root, set(OUTPUT_PATHS))
        result = {}
        for path, baseline in sorted(files.items()):
            limit = 64 * 1024**2 if path.endswith(".pdf") else 1024**2
            with packaging._reader(baseline) as stream:
                result[path] = b"".join(packaging._chunks(stream, limit))
        after, after_dirs = integrity._tree(root, set(OUTPUT_PATHS))
        integrity._check_baselines(files, after)
        integrity._check_baselines(directories, after_dirs, directories=True)
        return result


def _operational_records(root: packaging._Baseline) -> tuple[OutputRecord, ...]:
    with _staging_errors():
        files, directories = integrity._tree(root, set(OUTPUT_PATHS))
        records = []
        for path, baseline in sorted(files.items()):
            digest = hashlib.sha256()
            size = 0
            limit = 64 * 1024**2 if path.endswith(".pdf") else 1024**2
            with packaging._reader(baseline) as stream:
                for chunk in packaging._chunks(stream, limit):
                    digest.update(chunk)
                    size += len(chunk)
            records.append(OutputRecord(path, size, digest.hexdigest()))
        after, after_dirs = integrity._tree(root, set(OUTPUT_PATHS))
        integrity._check_baselines(files, after)
        integrity._check_baselines(directories, after_dirs, directories=True)
        return tuple(records)


def _prepare_paths(
    input_package: Path, output_dir: Path
) -> tuple[packaging._Baseline, packaging.OutputDestination]:
    try:
        if str(input_package) in ("", ".", "..") or str(output_dir) in ("", ".", ".."):
            fail("INVALID_PACKAGE")
        source = packaging._inspect(input_package, directory=True)
        output = packaging._lexical(output_dir)
        parent = packaging._inspect(output.parent, directory=True)
        if output.is_relative_to(source.path) or source.path.is_relative_to(output):
            fail("INVALID_PACKAGE")
        source_id = packaging.file_identity(source.info)
        parent_ids = {identity for _, identity, _ in parent.parents}
        parent_ids.add(packaging.file_identity(parent.info))
        if source_id in parent_ids:
            fail("INVALID_PACKAGE")
        try:
            existing = output.lstat()
        except FileNotFoundError:
            pass
        else:
            # Observable filesystem aliases are checked before ordinary existence.
            if packaging.file_identity(existing) in {
                source_id,
                *(identity for _, identity, _ in source.parents),
            }:
                fail("INVALID_PACKAGE")
            fail("OUTPUT_EXISTS")
        return source, packaging.OutputDestination(output, parent)
    except EvidenceError as error:
        if str(error).startswith("DOSSIER_PDF_"):
            raise
        fail("INVALID_PACKAGE")
    except (OSError, ValueError):
        fail("INVALID_PACKAGE")


def _mounts() -> list[tuple[Path, frozenset[str], str]]:
    result = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ", 1)
        parts = left.split()
        # Decode only the kernel's mountinfo path escaping, never shell escapes.
        name = parts[4]
        for encoded, decoded in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
            name = name.replace(encoded, decoded)
        result.append((Path(name), frozenset(parts[5].split(",")), right.split()[0]))
    return result


def _runtime_preflight(source: Path, output_parent: Path) -> None:
    from evidence_engine.dossier.pdf_environment import verify_environment

    try:
        verify_environment()
        status = dict(
            line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines()
        )
        if any(int(status[name].strip(), 16) for name in ("CapPrm", "CapInh", "CapBnd", "CapAmb")):
            fail("ENVIRONMENT_UNSUPPORTED")
        if Path("/proc/self/cgroup").read_text() != "0::/\n":
            fail("ENVIRONMENT_UNSUPPORTED")
        for name, expected in (
            ("memory.max", "2147483648"),
            ("memory.swap.max", "0"),
            ("pids.max", "64"),
            ("cpu.max", "200000 100000"),
        ):
            if (Path("/sys/fs/cgroup") / name).read_text().strip() != expected:
                fail("ENVIRONMENT_UNSUPPORTED")
        mounts = _mounts()
        for target, readonly in ((source, True), (output_parent, False)):
            applicable = [row for row in mounts if target.is_relative_to(row[0])]
            if not applicable:
                fail("ENVIRONMENT_UNSUPPORTED")
            mount, options, filesystem = max(applicable, key=lambda row: len(row[0].parts))
            if mount == Path("/") or ("ro" in options) != readonly:
                fail("ENVIRONMENT_UNSUPPORTED")
            if filesystem not in {"ext4", "xfs", "btrfs", "tmpfs", "virtiofs", "9p"}:
                fail("ENVIRONMENT_UNSUPPORTED")
            if bool(os.statvfs(target).f_flag & os.ST_RDONLY) != readonly:
                fail("ENVIRONMENT_UNSUPPORTED")
            # A writable submount must not bypass the read-only package mount.
            if readonly and any(
                p.is_relative_to(target) and "ro" not in flags for p, flags, _ in mounts
            ):
                fail("ENVIRONMENT_UNSUPPORTED")
    except (OSError, ValueError, IndexError, KeyError):
        fail("ENVIRONMENT_UNSUPPORTED")


def _create_scratch(staging: packaging.OwnedStaging) -> packaging._Baseline:
    with _staging_errors():
        packaging.revalidate_staging(staging)
        path = Path(tempfile.mkdtemp(prefix="scratch-", dir=staging.path))
        root = packaging._inspect(path, directory=True)
        if root.path.parent != staging.path or root.info.st_mode & 0o077:
            fail("STAGING_FAILURE")
        return root


def _scratch_size(root: packaging._Baseline) -> int:
    with _staging_errors():
        total = 0
        nodes = 0
        pending = [root]
        while pending:
            directory = pending.pop()
            with integrity._directory_entries(directory) as entries:
                for entry in entries:
                    nodes += 1
                    if nodes > 200_000:
                        fail("RESOURCE_LIMIT")
                    path = directory.path / entry.name
                    info = path.lstat()
                    is_directory = stat.S_ISDIR(info.st_mode)
                    checked = packaging._inspect(path, directory=is_directory)
                    if is_directory:
                        pending.append(checked)
                    else:
                        total += info.st_size
                        if total > SCRATCH_BYTES:
                            fail("RESOURCE_LIMIT")
        return total


def _drop_scratch(staging: packaging.OwnedStaging, scratch: packaging._Baseline) -> None:
    with _staging_errors():
        packaging._remove_owned_contents(staging, scratch)
        with packaging._directory_handle(staging.root) as fd:
            packaging._parents(scratch, include_self=True)
            if packaging.file_identity(
                os.stat(scratch.path.name, dir_fd=fd, follow_symlinks=False)
            ) != packaging.file_identity(scratch.info):
                fail("STAGING_FAILURE")
            os.rmdir(scratch.path.name, dir_fd=fd)


def _processes() -> dict[int, tuple[int, int]]:
    """PID -> (parent, start ticks); identity protects against PID reuse."""
    result = {}
    for path in Path("/proc").iterdir():
        if path.name.isdecimal():
            try:
                fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
                result[int(path.name)] = (int(fields[1]), int(fields[19]))
            except (FileNotFoundError, ProcessLookupError):
                continue
    return result


@contextmanager
def _subreaper() -> Iterator[None]:
    library = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    if library.prctl(37, ctypes.byref(previous), 0, 0, 0) or library.prctl(36, 1, 0, 0, 0):
        fail("ENVIRONMENT_UNSUPPORTED")
    try:
        yield
    finally:
        if library.prctl(36, previous.value, 0, 0, 0):
            fail("ENVIRONMENT_UNSUPPORTED")


def _descendants(worker: int, existing: set[int]) -> dict[int, int]:
    processes = _processes()
    selected = {worker}
    changed = True
    while changed:
        before = len(selected)
        for pid, (parent, _) in processes.items():
            if parent in selected or (parent == os.getpid() and pid not in existing):
                selected.add(pid)
        changed = len(selected) != before
    return {pid: processes[pid][1] for pid in selected if pid != worker and pid in processes}


def _kill_reap(process: subprocess.Popen[bytes], existing: set[int]) -> None:
    known = _descendants(process.pid, existing)
    if process.poll() is None or known:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for pid, started in known.items():
        current = _processes().get(pid)
        if current is not None and current[1] == started:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    process.wait()
    # Reparented grandchildren now belong to this temporary subreaper.
    known.update(_descendants(process.pid, existing))
    for pid, started in known.items():
        current = _processes().get(pid)
        if current is not None and current[1] == started:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                if pid in _processes():
                    fail("INTERNAL_ERROR")
    if _descendants(process.pid, existing):
        fail("INTERNAL_ERROR")


def _worker_environment(scratch: Path) -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "PATH": "/opt/venv/bin:/usr/local/bin:/usr/bin:/bin",
        "PYTHONPATH": "/app/src",
        "TMPDIR": str(scratch),
        "TMP": str(scratch),
        "TEMP": str(scratch),
    }


def _supervise(
    command: Callable[[int, int], list[str]],
    *,
    scratch: Path,
    deadline: float,
    on_drop: Callable[[], None],
    monitor_scratch: Callable[[], None],
) -> tuple[OutputRecord, ...]:
    """No semantic inputs here; externally enforce even a blocked library call."""
    history = History(deadline, PHASE_SECONDS)
    events_read, events_write = os.pipe()
    ack_read, ack_write = os.pipe()
    process = None
    inherited_closed = False
    try:
        with _subreaper():
            existing = {pid for pid, (parent, _) in _processes().items() if parent == os.getpid()}
            try:
                process = subprocess.Popen(
                    command(events_write, ack_read),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    start_new_session=True,
                    pass_fds=(events_write, ack_read),
                    close_fds=True,
                    cwd=scratch,
                    env=_worker_environment(scratch),
                )
                os.close(events_write)
                os.close(ack_read)
                inherited_closed = True
                assert process.stdout is not None and process.stderr is not None
                counts = {"events": 0, "stdout": 0, "stderr": 0, "ack": 0}
                buffer = bytearray()
                dropped = False
                with selectors.DefaultSelector() as selector:
                    for fd, name in (
                        (events_read, "events"),
                        (process.stdout.fileno(), "stdout"),
                        (process.stderr.fileno(), "stderr"),
                    ):
                        os.set_blocking(fd, False)
                        selector.register(fd, selectors.EVENT_READ, name)
                    while selector.get_map() or process.poll() is None:
                        history.check_time(time.monotonic())
                        if _descendants(process.pid, existing):
                            fail("INTERNAL_ERROR")
                        if not dropped:
                            monitor_scratch()
                        for key, _ in selector.select(
                            min(
                                0.025,
                                max(0, min(deadline, history.phase_deadline) - time.monotonic()),
                            )
                        ):
                            chunk = os.read(key.fd, MESSAGE_BYTES + 1)
                            if not chunk:
                                selector.unregister(key.fd)
                                if key.data == "events" and buffer:
                                    fail("INTERNAL_ERROR")
                                continue
                            counts[key.data] += len(chunk)
                            if counts[key.data] > CHANNEL_BYTES:
                                fail("RESOURCE_LIMIT")
                            if key.data != "events":
                                continue
                            buffer.extend(chunk)
                            while b"\n" in buffer:
                                line, _, remainder = buffer.partition(b"\n")
                                buffer = bytearray(remainder)
                                message = decode(bytes(line) + b"\n")
                                history.accept(message, time.monotonic())
                                if (
                                    message.get("event") == "ENTER"
                                    and message.get("phase") == "DROP_SCRATCH"
                                ):
                                    on_drop()
                                    dropped = True
                                history.check_time(time.monotonic())
                                ack = encode({"v": 1, "seq": message["seq"], "event": "ACK"})
                                counts["ack"] += len(ack)
                                if counts["ack"] > CHANNEL_BYTES:
                                    fail("RESOURCE_LIMIT")
                                if os.write(ack_write, ack) != len(ack):
                                    fail("INTERNAL_ERROR")
                            if len(buffer) >= MESSAGE_BYTES:
                                fail("RESOURCE_LIMIT")
                    history.check_time(time.monotonic())
                    if process.wait() != 0 or history.records is None or not dropped:
                        fail("INTERNAL_ERROR")
                    if _descendants(process.pid, existing):
                        fail("INTERNAL_ERROR")
                return history.records
            finally:
                if process is not None:
                    try:
                        _kill_reap(process, existing)
                    except BaseException:
                        raise _ExecutionStillActive("DOSSIER_PDF_INTERNAL_ERROR") from None
    finally:
        for fd in (events_read, ack_write):
            os.close(fd)
        if not inherited_closed:
            os.close(events_write)
            os.close(ack_read)
        if process is not None:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()


def export_dossier_pdf(input_package: Path, output_dir: Path) -> PdfExportResult:
    deadline = time.monotonic() + GLOBAL_SECONDS
    # Subreaper state is process-wide. Concurrent callers use separate processes;
    # a second call in this process cannot adopt or kill the first call's worker.
    if not _OPERATION_LOCK.acquire(blocking=False):
        fail("INTERNAL_ERROR")
    staging = None
    publishing = False
    try:
        source, destination = _prepare_paths(input_package, output_dir)
        _runtime_preflight(source.path, destination.parent.path)
        if time.monotonic() >= deadline:
            fail("RESOURCE_LIMIT")
        with _staging_errors():
            staging = packaging.create_staging(destination)
        scratch = _create_scratch(staging)
        owned = staging

        def monitor() -> None:
            _scratch_size(scratch)

        records = _supervise(
            lambda events, ack: [
                sys.executable,
                "-m",
                "evidence_engine.dossier.pdf_worker",
                str(source.path),
                str(owned.path),
                str(events),
                str(ack),
            ],
            scratch=scratch.path,
            deadline=deadline,
            on_drop=lambda: _drop_scratch(owned, scratch),
            monitor_scratch=monitor,
        )
        with _staging_errors():
            packaging.revalidate_staging(staging)
            if _operational_records(staging.root) != records:
                fail("STAGING_FAILURE")
            packaging._parents(source, include_self=True)
            checked_source, checked_destination = _prepare_paths(source.path, destination.path)
            if packaging.file_identity(checked_source.info) != packaging.file_identity(
                source.info
            ) or packaging.file_identity(
                checked_destination.parent.info
            ) != packaging.file_identity(destination.parent.info):
                fail("INVALID_PACKAGE")
            packaging.sync_staging_directories(staging, OUTPUT_PATHS)
            packaging.revalidate_staging(staging)
        result = PdfExportResult(
            destination.path, 4, sum(row.byte_size for row in records), records
        )
        if time.monotonic() >= deadline:
            fail("RESOURCE_LIMIT")
        publishing = True
        try:
            packaging.publish_staging(staging)
        except EvidenceError as error:
            fail(
                "OUTPUT_EXISTS" if str(error) == "DOSSIER_OUTPUT_EXISTS" else "PUBLICATION_FAILURE"
            )
        return result  # No filesystem action after confirmed publication.
    except Exception as error:
        if isinstance(error, _ExecutionStillActive):
            raise EvidenceError("DOSSIER_PDF_INTERNAL_ERROR") from None
        code = safe_error_code(error)
        if staging is not None:
            if publishing and not packaging.staging_is_owned(staging):
                fail("PUBLICATION_FAILURE")
            try:
                packaging.cleanup_staging(staging)
            except Exception:
                fail("STAGING_FAILURE")
        raise EvidenceError(code) from None
    finally:
        _OPERATION_LOCK.release()
