"""Selected-artifact capture plus explicit owned staging and safe publication.

Visuals initially occupy a reserved .jpg work slot (no format assertion). Both
possible destinations are checked before copying. The caller validates captured
bytes, then resolves the slot; a PNG is copied exclusively from the verified
capture, never from the source. Only that owned provisional file is removed.
The D capture API retains caller-owned root semantics. F lifecycle helpers are
explicit and separate. No discovery or package manifest algorithm here.
"""

import ctypes
import errno
import hashlib
import os
import stat
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import BinaryIO

from evidence_engine.dossier.projection import ROLE_CLASSES, AnnexIndexEntry, package_paths, require
from evidence_engine.dossier.selection import (
    DossierSelection,
    SelectedInput,
    VisualExhibitInput,
    _input_reference,
    _selection,
)
from evidence_engine.dossier.selection import (
    _label as _label,
)
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.hashing import file_identity as file_identity
from evidence_engine.ingest.generic.hashing import original_reader, read_stability
from evidence_engine.ingest.generic.paths import check_path

CHUNK_SIZE = 1024 * 1024
MAX_SELECTION_BYTES = 1024 * 1024
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
MAX_TOTAL_SNAPSHOT_BYTES = 128 * 1024 * 1024
MAX_REPORT_BYTES = 64 * 1024 * 1024
MAX_SUPPLEMENTAL_BYTES = 16 * 1024 * 1024
MAX_VISUAL_BYTES = 32 * 1024 * 1024
MAX_TOTAL_INPUT_BYTES = 512 * 1024 * 1024
GENERATED_PATHS = (
    "human/dossier.md",
    "human/annex-index.md",
    "technical/selection-metadata.json",
    "integrity/manifest.json",
    "integrity/SHA256SUMS.txt",
)


@dataclass(frozen=True, slots=True)
class _Baseline:
    path: Path
    info: os.stat_result
    parents: tuple[tuple[Path, tuple[int, int, int], int], ...]


@dataclass(frozen=True, slots=True)
class _PlannedInput:
    item: SelectedInput
    baseline: _Baseline
    destinations: tuple[str, ...]
    limit: int


@dataclass(frozen=True, slots=True)
class CapturedInput:
    """Operational DTO, never supplied to a human/metadata renderer."""

    local_label: str
    source_class: str
    role: str
    captured_path: Path
    byte_size: int
    sha256: str
    package_path: str | None
    validated_format: str | None = None


@dataclass(frozen=True, slots=True)
class CaptureBatch:
    capture_root: Path
    inputs: tuple[CapturedInput, ...]


@dataclass(frozen=True, slots=True)
class PreparedCapture:
    """Operational source baselines only; never serialized or rendered."""

    selection: DossierSelection
    selection_file: _Baseline
    base: _Baseline
    plans: tuple[_PlannedInput, ...]


@dataclass(frozen=True, slots=True)
class OutputDestination:
    path: Path
    parent: _Baseline


@dataclass(frozen=True, slots=True)
class OwnedStaging:
    root: _Baseline
    destination: OutputDestination

    @property
    def path(self) -> Path:
        return self.root.path


def _limit(role: str) -> int:
    return {
        "report_snapshot": MAX_SNAPSHOT_BYTES,
        "consolidated_report": MAX_REPORT_BYTES,
        "technical_review": MAX_SUPPLEMENTAL_BYTES,
        "structured_support": MAX_SUPPLEMENTAL_BYTES,
        "validation_report": MAX_SUPPLEMENTAL_BYTES,
        "contextual_visual": MAX_VISUAL_BYTES,
    }[role]


def _validated_selection(selection: DossierSelection) -> DossierSelection:
    """Reuse accepted shape/role/path/count/approval rules even for manual DTOs."""
    try:
        return _selection_document(selection)
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None
    except (KeyError, TypeError, ValueError):
        raise EvidenceError("DOSSIER_INVALID_SELECTION") from None


def _selection_document(selection: DossierSelection) -> DossierSelection:
    value = asdict(selection)
    for key in ("issued_date", "case_reference"):
        if value[key] is None:
            del value[key]
    for group in (
        "canonical_inputs",
        "supplemental_inputs",
        "validation_artifacts",
        "visual_exhibits",
    ):
        value[group] = list(value[group])
        for item in value[group]:
            if item.get("expected_sha256") is None:
                item.pop("expected_sha256", None)
    return _selection(value)


def _lexical(path: Path) -> Path:
    # Path is a local API, not a URL parser. Do not follow anything to validate it.
    require(not str(path).startswith(("//", "\\\\")), "INVALID_PATH")
    absolute = path.absolute()
    for part in absolute.parts[1:]:
        _input_reference(part)
    return absolute


def _safe_info(path: Path, *, directory: bool) -> os.stat_result:
    info = path.lstat()
    require(
        not stat.S_ISLNK(info.st_mode)
        and not (
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
        and not path.is_junction(),
        "UNSAFE_FILE_TYPE",
    )
    require(
        stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode), "UNSAFE_FILE_TYPE"
    )
    if not directory:
        require(info.st_nlink == 1, "UNSAFE_FILE_TYPE")
    return info


def _inspect(path: Path, *, directory: bool = False) -> _Baseline:
    path = _lexical(path)
    parents = []
    for parent in reversed(path.parents):
        info = _safe_info(parent, directory=True)
        parents.append((parent, file_identity(info), info.st_mode))
    info = _safe_info(path, directory=directory)
    # Foundation's broader checks follow our root-to-leaf no-reparse prechecks.
    try:
        check_path(path)
    except EvidenceError:
        raise EvidenceError("DOSSIER_UNSAFE_FILE_TYPE") from None
    try:
        resolved = path.resolve(strict=True)
    except RuntimeError:
        raise EvidenceError("DOSSIER_PATH_ESCAPE") from None
    require(resolved == path, "PATH_ESCAPE")
    return _Baseline(path, info, tuple(parents))


def _same(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        file_identity(before) == file_identity(after)
        and read_stability(before) == read_stability(after)
        and before.st_mode == after.st_mode
        and before.st_nlink == after.st_nlink
        and getattr(before, "st_file_attributes", 0) == getattr(after, "st_file_attributes", 0)
    )


def _parents(baseline: _Baseline, *, include_self: bool = False) -> None:
    expected = baseline.parents
    if include_self:
        expected += ((baseline.path, file_identity(baseline.info), baseline.info.st_mode),)
    for path, identity, mode in expected:
        info = _safe_info(path, directory=True)
        require(file_identity(info) == identity and info.st_mode == mode, "INPUT_CHANGED")


@contextmanager
def _reader(baseline: _Baseline) -> Iterator[BinaryIO]:
    try:
        _parents(baseline)
        require(_same(baseline.info, _safe_info(baseline.path, directory=False)), "INPUT_CHANGED")
        with original_reader(baseline.path) as stream:
            require(_same(baseline.info, os.fstat(stream.fileno())), "INPUT_CHANGED")
            _parents(baseline)
            yield stream
            require(_same(baseline.info, os.fstat(stream.fileno())), "INPUT_CHANGED")
            _parents(baseline)
        require(_same(baseline.info, _safe_info(baseline.path, directory=False)), "INPUT_CHANGED")
    except EvidenceError as error:
        if str(error).startswith("DOSSIER_") and str(error) not in (
            "DOSSIER_UNSAFE_FILE_TYPE",
            "DOSSIER_PATH_ESCAPE",
        ):
            raise
        raise EvidenceError("DOSSIER_INPUT_CHANGED") from None
    except FileNotFoundError:
        raise EvidenceError("DOSSIER_INPUT_CHANGED") from None
    except OSError:
        raise EvidenceError("DOSSIER_INPUT_READ_ERROR") from None


def _chunks(stream: BinaryIO, limit: int) -> Iterator[bytes]:
    count = 0
    while chunk := stream.read(CHUNK_SIZE):
        count += len(chunk)
        require(count <= limit, "RESOURCE_LIMIT")
        yield chunk


def read_selection_bytes_stable(selection_path: Path) -> bytes:
    """No JSON parsing; bounded read of the explicit selection file only."""
    try:
        baseline = _inspect(selection_path)
        require(baseline.info.st_size <= MAX_SELECTION_BYTES, "RESOURCE_LIMIT")
        with _reader(baseline) as stream:
            content = b"".join(_chunks(stream, MAX_SELECTION_BYTES))
            require(len(content) == baseline.info.st_size, "INPUT_CHANGED")
        return content
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None
    except OSError:
        raise EvidenceError("DOSSIER_INPUT_READ_ERROR") from None


def validate_destination_set(paths: Sequence[str]) -> None:
    """Includes generated reservations; syntax/casefold/prefix collisions fail closed."""
    files: set[tuple[str, ...]] = set()
    prefixes: dict[tuple[str, ...], tuple[str, ...]] = {}
    for path in (*paths, *GENERATED_PATHS):
        _input_reference(path)
        parts = tuple(path.split("/"))
        folded = tuple(p.casefold() for p in parts)
        require(folded not in files, "INVALID_PATH")
        files.add(folded)
        for i in range(1, len(parts) + 1):
            require(folded[:i] not in prefixes or prefixes[folded[:i]] == parts[:i], "INVALID_PATH")
            prefixes[folded[:i]] = parts[:i]
    require(
        not any(parts[:i] in files for parts in files for i in range(1, len(parts))), "INVALID_PATH"
    )
    for path in paths:
        label = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        try:
            _label(label)
        except EvidenceError:
            raise EvidenceError("DOSSIER_INVALID_PATH") from None
        require(any(path in package_paths(role, label) for role in ROLE_CLASSES), "INVALID_PATH")


def _destination(root: _Baseline, relative: str) -> Path:
    """Check/create only contracted parents; never enumerate or merge payload files."""
    _parents(root, include_self=True)
    destination = root.path.joinpath(*relative.split("/"))
    current = root.path
    for part in relative.split("/")[:-1]:
        current /= part
        try:
            current.mkdir()
        except FileExistsError:
            pass
        _safe_info(current, directory=True)
    checked = _inspect(destination.parent, directory=True)
    require(checked.path.is_relative_to(root.path), "PATH_ESCAPE")
    _parents(root, include_self=True)
    return destination


@contextmanager
def _writer(root: _Baseline, relative: str) -> Iterator[BinaryIO]:
    try:
        destination = _destination(root, relative)
        parents = _inspect(destination.parent, directory=True)
        # Exclusive creation never overwrites a preexisting file, including aliases.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        if os.name == "posix":
            parent_fd = os.open(parents.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                require(
                    file_identity(os.fstat(parent_fd)) == file_identity(parents.info),
                    "STAGING_FAILURE",
                )
                _parents(parents, include_self=True)
                fd = os.open(destination.name, flags, 0o600, dir_fd=parent_fd)
            finally:
                os.close(parent_fd)
        else:
            fd = os.open(destination, flags, 0o600)
        with os.fdopen(fd, "wb") as stream:
            _parents(parents, include_self=True)
            require(
                file_identity(os.fstat(stream.fileno()))
                == file_identity(_safe_info(destination, directory=False)),
                "STAGING_FAILURE",
            )
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
            _parents(parents, include_self=True)
            require(
                file_identity(os.fstat(stream.fileno()))
                == file_identity(_safe_info(destination, directory=False)),
                "STAGING_FAILURE",
            )
        _parents(root, include_self=True)
    except OSError:
        raise EvidenceError("DOSSIER_STAGING_FAILURE") from None


def _copy(plan: _PlannedInput, root: _Baseline, remaining: int) -> CapturedInput:
    destination = plan.destinations[0]
    digest = hashlib.sha256()
    count = 0
    with _reader(plan.baseline) as source:
        with _writer(root, destination) as output:
            for chunk in _chunks(source, min(plan.limit, remaining)):
                count += len(chunk)
                digest.update(chunk)
                output.write(chunk)
        require(count == plan.baseline.info.st_size, "INPUT_CHANGED")
    sha = digest.hexdigest()
    require(plan.item.expected_sha256 is None or sha == plan.item.expected_sha256, "HASH_MISMATCH")
    captured = CapturedInput(
        plan.item.local_label,
        plan.item.source_class,
        plan.item.role,
        root.path / destination,
        count,
        sha,
        None if plan.item.role == "contextual_visual" else destination,
    )
    read_captured_bytes(captured)
    return captured


def read_captured_bytes(item: CapturedInput) -> bytes:
    """Verify the controlled copy and return bounded bytes for downstream validation."""
    try:
        baseline = _inspect(item.captured_path)
        require(baseline.info.st_size <= _limit(item.role), "RESOURCE_LIMIT")
        require(baseline.info.st_size == item.byte_size, "HASH_MISMATCH")
        with _reader(baseline) as stream:
            data = b"".join(_chunks(stream, _limit(item.role)))
        require(
            len(data) == item.byte_size and hashlib.sha256(data).hexdigest() == item.sha256,
            "HASH_MISMATCH",
        )
        return data
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None
    except OSError:
        raise EvidenceError("DOSSIER_STAGING_FAILURE") from None


def prepare_capture(
    *, selection_path: Path, selection: DossierSelection, selection_content: bytes | None = None
) -> PreparedCapture:
    """Complete source/path/budget preflight without creating a work directory.

    The service supplies its stable-read selection bytes to bind parsing to this
    baseline. Existing D callers may continue supplying their accepted DTO only.
    """
    try:
        selection = _validated_selection(selection)
        selected = sorted(
            (
                *selection.canonical_inputs,
                *selection.supplemental_inputs,
                *selection.validation_artifacts,
                *selection.visual_exhibits,
            ),
            key=lambda i: (i.role, i.local_label),
        )
        selection_file = _inspect(selection_path)
        require(selection_file.info.st_size <= MAX_SELECTION_BYTES, "RESOURCE_LIMIT")
        if selection_content is not None:
            with _reader(selection_file) as stream:
                require(
                    b"".join(_chunks(stream, MAX_SELECTION_BYTES)) == selection_content,
                    "INPUT_CHANGED",
                )
        base = _inspect(selection_file.path.parent, directory=True)
        plans = []
        identities = {file_identity(selection_file.info)}
        for item in selected:
            reference = _input_reference(item.input_reference)
            baseline = _inspect(base.path.joinpath(*reference.split("/")))
            require(baseline.path.is_relative_to(base.path), "PATH_ESCAPE")
            identity = file_identity(baseline.info)
            require(
                identity not in identities and baseline.path != selection_file.path, "INVALID_PATH"
            )
            identities.add(identity)
            limit = _limit(item.role)
            require(baseline.info.st_size <= limit, "RESOURCE_LIMIT")
            plans.append(
                _PlannedInput(item, baseline, package_paths(item.role, item.local_label), limit)
            )
        validate_destination_set(tuple(d for plan in plans for d in plan.destinations))
        require(
            sum(p.baseline.info.st_size for p in plans) <= MAX_TOTAL_INPUT_BYTES, "RESOURCE_LIMIT"
        )
        require(
            sum(p.baseline.info.st_size for p in plans if p.item.role == "report_snapshot")
            <= MAX_TOTAL_SNAPSHOT_BYTES,
            "RESOURCE_LIMIT",
        )
        return PreparedCapture(selection, selection_file, base, tuple(plans))
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None
    except OSError:
        raise EvidenceError("DOSSIER_INPUT_READ_ERROR") from None


def capture_prepared_inputs(prepared: PreparedCapture, *, capture_root: Path) -> CaptureBatch:
    """Copy against all pre-staging baselines, preserving D's stable-read checks."""
    try:
        root = _inspect(capture_root, directory=True)
        base, plans = prepared.base, prepared.plans
        _parents(base, include_self=True)
        require(
            not root.path.is_relative_to(base.path)
            and not base.path.is_relative_to(root.path)
            and file_identity(root.info) != file_identity(base.info),
            "INVALID_PATH",
        )
        # Check all reserved destinations before the first write. Existing parents
        # are checked without creating or enumerating anything.
        for plan in plans:
            for relative in plan.destinations:
                path = root.path
                for component in relative.split("/"):
                    path /= component
                    try:
                        path.lstat()
                    except FileNotFoundError:
                        break
                    require(path != root.path / relative, "STAGING_FAILURE")
                    _safe_info(path, directory=True)
        captured = []
        total = snapshots = 0
        for plan in plans:
            remaining = MAX_TOTAL_INPUT_BYTES - total
            if plan.item.role == "report_snapshot":
                remaining = min(remaining, MAX_TOTAL_SNAPSHOT_BYTES - snapshots)
            result = _copy(plan, root, remaining)
            captured.append(result)
            total += result.byte_size
            if result.role == "report_snapshot":
                snapshots += result.byte_size
        for baseline in (prepared.selection_file, *(p.baseline for p in plans)):
            with _reader(baseline):
                pass
        _parents(root, include_self=True)
        return CaptureBatch(root.path, tuple(captured))
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None
    except OSError:
        raise EvidenceError("DOSSIER_INPUT_READ_ERROR") from None


def capture_selected_inputs(
    *, selection_path: Path, selection: DossierSelection, capture_root: Path
) -> CaptureBatch:
    """Compatible D entry point. Sources are not an atomic multi-file snapshot."""
    prepared = prepare_capture(selection_path=selection_path, selection=selection)
    return capture_prepared_inputs(prepared, capture_root=capture_root)


def resolve_captured_inputs(
    batch: CaptureBatch, *, image_formats: Mapping[str, str]
) -> CaptureBatch:
    """Caller provides successful format results from validation, keyed by visual label.

    No format inference here. All captured formats must be validated before this
    phase; canonical semantic validation still belongs to 8B1-B/future service.
    """
    try:
        root = _inspect(batch.capture_root, directory=True)
        visuals = {i.local_label for i in batch.inputs if i.role == "contextual_visual"}
        require(set(image_formats) == visuals, "INVALID_SELECTION")
        paths = []
        for item in batch.inputs:
            if item.role == "contextual_visual":
                require(image_formats[item.local_label] in ("jpeg", "png"), "UNSUPPORTED_FORMAT")
                suffix = 0 if image_formats[item.local_label] == "jpeg" else 1
                paths.append(package_paths(item.role, item.local_label)[suffix])
            else:
                paths.append(package_paths(item.role, item.local_label)[0])
        validate_destination_set(paths)
        result = []
        for item, relative in zip(batch.inputs, paths, strict=True):
            allowed = tuple(root.path / p for p in package_paths(item.role, item.local_label))
            require(item.captured_path in allowed, "INVALID_PATH")
            content = read_captured_bytes(item)
            final = root.path / relative
            if final != item.captured_path:
                original = _inspect(item.captured_path)
                with _writer(root, relative) as output:
                    for offset in range(0, len(content), CHUNK_SIZE):
                        output.write(content[offset : offset + CHUNK_SIZE])
                resolved = replace(
                    item,
                    captured_path=final,
                    package_path=relative,
                    validated_format=image_formats[item.local_label],
                )
                read_captured_bytes(resolved)
                with _reader(original):
                    pass
                require(original.path.is_relative_to(root.path), "PATH_ESCAPE")
                _remove_provisional(root, original)
            else:
                resolved = replace(
                    item,
                    package_path=relative,
                    validated_format=image_formats.get(item.local_label),
                )
            result.append(resolved)
        return CaptureBatch(root.path, tuple(result))
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None
    except OSError:
        raise EvidenceError("DOSSIER_STAGING_FAILURE") from None


def _remove_provisional(root: _Baseline, original: _Baseline) -> None:
    """Only the owned visual slot; this is not whole-work-root cleanup."""
    _parents(root, include_self=True)
    _parents(original)
    require(_same(original.info, _safe_info(original.path, directory=False)), "INPUT_CHANGED")
    if os.name == "posix":
        fd = os.open(original.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            require(file_identity(os.fstat(fd)) == original.parents[-1][1], "STAGING_FAILURE")
            _parents(original)
            info = os.stat(original.path.name, dir_fd=fd, follow_symlinks=False)
            require(_same(original.info, info), "INPUT_CHANGED")
            os.unlink(original.path.name, dir_fd=fd)
        finally:
            os.close(fd)
    else:
        original.path.unlink()
    _parents(original)
    _parents(root, include_self=True)


def resolved_annex_entries(
    selection: DossierSelection, batch: CaptureBatch
) -> tuple[AnnexIndexEntry, ...]:
    """Safe administrative boundary: no paths, hashes or identities from capture."""
    selection = _validated_selection(selection)
    selected = {
        i.local_label: i
        for i in (
            *selection.canonical_inputs,
            *selection.supplemental_inputs,
            *selection.validation_artifacts,
            *selection.visual_exhibits,
        )
    }
    require(
        len(batch.inputs) == len(selected)
        and {i.local_label for i in batch.inputs} == set(selected),
        "INVALID_SELECTION",
    )
    result = []
    for item in batch.inputs:
        source = selected[item.local_label]
        require(
            item.role == source.role and item.source_class == source.source_class,
            "INVALID_ROLE_CLASS",
        )
        if item.package_path is None:
            raise EvidenceError("DOSSIER_UNSUPPORTED_FORMAT")
        caption = source.display_caption if isinstance(source, VisualExhibitInput) else None
        result.append(
            AnnexIndexEntry(
                item.local_label, item.role, item.source_class, item.package_path, caption
            )
        )
    return tuple(sorted(result, key=lambda i: (i.role, i.local_label)))


_PLATFORM = sys.platform
STAGING_PREFIX = ".dee-dossier-staging-"
MAX_GENERATED_FILE_BYTES = 64 * 1024 * 1024


def prepare_output(prepared: PreparedCapture, output_dir: Path) -> OutputDestination:
    """An existing safe parent and absent destination are required before staging."""
    try:
        require(str(output_dir) not in ("", ".", ".."), "INVALID_PATH")
        require(not output_dir.drive or output_dir.is_absolute(), "INVALID_PATH")
        _input_reference(output_dir.name)
        output = _lexical(output_dir)
        parent = _inspect(output.parent, directory=True)
        try:
            output.lstat()
        except FileNotFoundError:
            pass
        else:
            raise EvidenceError("DOSSIER_OUTPUT_EXISTS")
        base = prepared.base
        _parents(base, include_self=True)
        require(
            not output.is_relative_to(base.path)
            and not base.path.is_relative_to(output)
            and not parent.path.is_relative_to(base.path),
            "PATH_ESCAPE",
        )
        return OutputDestination(output, parent)
    except OSError:
        raise EvidenceError("DOSSIER_STAGING_FAILURE") from None


def create_staging(destination: OutputDestination) -> OwnedStaging:
    try:
        _parents(destination.parent, include_self=True)
        path = Path(tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=destination.parent.path))
        root = _inspect(path, directory=True)
        require(root.path.parent == destination.parent.path, "STAGING_FAILURE")
        require(root.info.st_dev == destination.parent.info.st_dev, "STAGING_FAILURE")
        require(os.name != "posix" or root.info.st_mode & 0o077 == 0, "STAGING_FAILURE")
        owned = OwnedStaging(root, destination)
        revalidate_staging(owned)
        return owned
    except (OSError, EvidenceError):
        # No pathname-only deletion if creation/ownership establishment failed.
        raise EvidenceError("DOSSIER_STAGING_FAILURE") from None


def revalidate_staging(staging: OwnedStaging) -> None:
    require(
        staging.path.parent == staging.destination.parent.path
        and staging.path != staging.destination.path,
        "STAGING_FAILURE",
    )
    _parents(staging.destination.parent, include_self=True)
    _parents(staging.root, include_self=True)


def staging_is_owned(staging: OwnedStaging) -> bool:
    """Used only after failed publication; never inspect the potential final path."""
    try:
        revalidate_staging(staging)
        return True
    except (OSError, EvidenceError):
        return False


def write_generated_file(staging: OwnedStaging, package_path: str, content: bytes) -> None:
    require(package_path in GENERATED_PATHS[:3], "INVALID_PATH")
    require(type(content) is bytes, "INTERNAL_ERROR")
    require(len(content) <= MAX_GENERATED_FILE_BYTES, "RESOURCE_LIMIT")
    revalidate_staging(staging)
    with _writer(staging.root, package_path) as output:
        for offset in range(0, len(content), CHUNK_SIZE):
            output.write(content[offset : offset + CHUNK_SIZE])


@contextmanager
def _directory_handle(baseline: _Baseline) -> Iterator[int]:
    _parents(baseline, include_self=True)
    fd = os.open(baseline.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        require(file_identity(os.fstat(fd)) == file_identity(baseline.info), "STAGING_FAILURE")
        _parents(baseline, include_self=True)
        yield fd
        _parents(baseline, include_self=True)
    finally:
        os.close(fd)


def sync_staging_directories(staging: OwnedStaging, package_paths: Sequence[str]) -> None:
    """Fixed bottom-up order, including root and output parent, before publication."""
    try:
        revalidate_staging(staging)
        if os.name != "posix":
            return
        directories = {""}
        for path in package_paths:
            _input_reference(path)
            directories.update(path[:i] for i, c in enumerate(path) if c == "/")
        ordered = sorted(directories, key=lambda p: (-len(Path(p).parts), p))
        baselines = [_inspect(staging.path / path, directory=True) for path in ordered]
        baselines.append(staging.destination.parent)
        for baseline in baselines:
            revalidate_staging(staging)
            with _directory_handle(baseline) as fd:
                try:
                    os.fsync(fd)
                except OSError as error:
                    if error.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP):
                        raise
        revalidate_staging(staging)
    except (OSError, EvidenceError):
        raise EvidenceError("DOSSIER_STAGING_FAILURE") from None


def _remove_owned_contents(staging: OwnedStaging, directory: _Baseline) -> None:
    """No following links; POSIX deletions are relative to verified descriptors."""
    revalidate_staging(staging)
    require(directory.path.is_relative_to(staging.path), "STAGING_FAILURE")
    _parents(directory, include_self=True)
    if os.name == "posix":
        with _directory_handle(directory) as fd:
            with os.scandir(fd) as entries:
                names = sorted(entry.name for entry in entries)
            for name in names:
                revalidate_staging(staging)
                _parents(directory, include_self=True)
                path = directory.path / name
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                is_dir = stat.S_ISDIR(info.st_mode)
                baseline = _inspect(path, directory=is_dir)
                require(file_identity(info) == file_identity(baseline.info), "STAGING_FAILURE")
                if is_dir:
                    _remove_owned_contents(staging, baseline)
                revalidate_staging(staging)
                _parents(directory, include_self=True)
                current = os.stat(name, dir_fd=fd, follow_symlinks=False)
                require(file_identity(current) == file_identity(info), "STAGING_FAILURE")
                _safe_info(path, directory=is_dir)
                if is_dir:
                    os.rmdir(name, dir_fd=fd)
                else:
                    os.unlink(name, dir_fd=fd)
    else:
        with os.scandir(directory.path) as entries:
            names = sorted(entry.name for entry in entries)
        for name in names:
            revalidate_staging(staging)
            _parents(directory, include_self=True)
            path = directory.path / name
            is_dir = stat.S_ISDIR(path.lstat().st_mode)
            baseline = _inspect(path, directory=is_dir)
            if is_dir:
                _remove_owned_contents(staging, baseline)
            revalidate_staging(staging)
            _parents(directory, include_self=True)
            require(
                file_identity(_safe_info(path, directory=is_dir)) == file_identity(baseline.info),
                "STAGING_FAILURE",
            )
            if is_dir:
                path.rmdir()
            else:
                path.unlink()


def cleanup_staging(staging: OwnedStaging) -> None:
    """Remove only the proven execution-owned root. No retry or final-output access."""
    try:
        revalidate_staging(staging)
        _remove_owned_contents(staging, staging.root)
        revalidate_staging(staging)
        if os.name == "posix":
            with _directory_handle(staging.destination.parent) as fd:
                revalidate_staging(staging)
                require(
                    file_identity(os.stat(staging.path.name, dir_fd=fd, follow_symlinks=False))
                    == file_identity(staging.root.info),
                    "STAGING_FAILURE",
                )
                os.rmdir(staging.path.name, dir_fd=fd)
        else:
            staging.path.rmdir()
    except (OSError, EvidenceError, MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_STAGING_FAILURE") from None


def _linux_rename_noreplace(source: Path, destination: Path) -> None:
    """One kernel no-replace move; no plain-rename or copy fallback."""
    try:
        library = ctypes.CDLL(None, use_errno=True)
        rename = library.renameat2
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
            error = ctypes.get_errno()
            code = (
                "OUTPUT_EXISTS"
                if error in (errno.EEXIST, errno.ENOTEMPTY)
                else "PUBLICATION_FAILURE"
            )
            raise EvidenceError(f"DOSSIER_{code}")
    except (AttributeError, OSError):
        raise EvidenceError("DOSSIER_PUBLICATION_FAILURE") from None


def publish_staging(staging: OwnedStaging) -> None:
    """Last filesystem operation on success: no checks, sync or cleanup after move."""
    try:
        revalidate_staging(staging)
    except (EvidenceError, OSError):
        raise EvidenceError("DOSSIER_PUBLICATION_FAILURE") from None
    if _PLATFORM == "linux":
        _linux_rename_noreplace(staging.path, staging.destination.path)
    elif _PLATFORM == "win32":
        try:
            os.rename(staging.path, staging.destination.path)
        except OSError as error:
            exists = error.errno in (errno.EEXIST, errno.ENOTEMPTY) or getattr(
                error, "winerror", None
            ) in (80, 183)
            raise EvidenceError(
                "DOSSIER_OUTPUT_EXISTS" if exists else "DOSSIER_PUBLICATION_FAILURE"
            ) from None
    else:
        raise EvidenceError("DOSSIER_PUBLICATION_FAILURE")
