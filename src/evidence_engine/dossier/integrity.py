"""Acyclic integrity over actual controlled-work-root bytes (ADR 0037).

Only the two integrity files are written. The caller owns the root, generated
presentation bytes, cleanup and eventual publication. No source is reopened.
"""

import hashlib
import json
import os
import re
import stat
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from evidence_engine.dossier import packaging as capture
from evidence_engine.dossier.projection import ROLE_CLASSES, package_paths, require
from evidence_engine.errors import EvidenceError

MAX_GENERATED_FILE_BYTES = 64 * 1024 * 1024
MAX_PACKAGE_BYTES = 1024 * 1024 * 1024
MANIFEST_PATH = "integrity/manifest.json"
SUMS_PATH = "integrity/SHA256SUMS.txt"
GENERATED_PAYLOADS = {
    "human/dossier.md": ("human_dossier", "GENERATED_PRESENTATION"),
    "human/annex-index.md": ("annex_index", "GENERATED_PRESENTATION"),
    "technical/selection-metadata.json": ("selection_metadata", "GENERATED_METADATA"),
}
_FIXED_PATHS = {*GENERATED_PAYLOADS, MANIFEST_PATH, SUMS_PATH}


@dataclass(frozen=True, slots=True)
class IntegrityPayload:
    package_path: str
    byte_size: int
    sha256: str

    def __post_init__(self) -> None:
        require(type(self.package_path) is str, "INVALID_PATH")
        if self.package_path not in _FIXED_PATHS:
            capture.validate_destination_set((self.package_path,))
        require(type(self.byte_size) is int and self.byte_size >= 0, "INTERNAL_ERROR")
        require(
            type(self.sha256) is str and re.fullmatch(r"[0-9a-f]{64}", self.sha256) is not None,
            "INTERNAL_ERROR",
        )


@dataclass(frozen=True, slots=True)
class ManifestEntry(IntegrityPayload):
    role: str
    source_class: str
    local_label: str | None = None

    def __post_init__(self) -> None:
        IntegrityPayload.__post_init__(self)
        require(type(self.role) is str and type(self.source_class) is str, "INTERNAL_ERROR")
        if self.package_path in GENERATED_PAYLOADS:
            require(
                (self.role, self.source_class) == GENERATED_PAYLOADS[self.package_path]
                and self.local_label is None,
                "INTERNAL_ERROR",
            )
        else:
            require(self.package_path not in (MANIFEST_PATH, SUMS_PATH), "INTERNAL_ERROR")
            capture._label(self.local_label)
            require(ROLE_CLASSES.get(self.role) == self.source_class, "INTERNAL_ERROR")
            require(
                self.package_path in package_paths(self.role, self.local_label or ""),
                "INVALID_PATH",
            )


@dataclass(frozen=True, slots=True)
class PackageIntegrityResult:
    manifest_content: bytes
    sums_content: bytes
    entries: tuple[ManifestEntry, ...]
    files: tuple[IntegrityPayload, ...]
    total_byte_size: int


def _bounded_bytes(chunks: Iterable[str]) -> bytes:
    output = bytearray()
    for chunk in chunks:
        encoded = chunk.encode("utf-8")
        require(len(output) + len(encoded) <= MAX_GENERATED_FILE_BYTES, "RESOURCE_LIMIT")
        output.extend(encoded)
    return bytes(output)


def serialize_manifest(entries: Sequence[ManifestEntry]) -> bytes:
    """Closed manifest schema, no host metadata, bounded incremental encoding."""
    try:
        rows: list[dict[str, str | int]] = []
        paths: set[str] = set()
        labels: set[str] = set()
        for entry in sorted(entries, key=lambda e: e.package_path):
            entry.__post_init__()
            require(entry.package_path not in paths, "INTERNAL_ERROR")
            paths.add(entry.package_path)
            row: dict[str, str | int] = {
                "package_path": entry.package_path,
                "role": entry.role,
                "source_class": entry.source_class,
                "byte_size": entry.byte_size,
                "sha256": entry.sha256,
            }
            if entry.local_label is not None:
                require(entry.local_label not in labels, "INTERNAL_ERROR")
                labels.add(entry.local_label)
                row["local_label"] = entry.local_label
            rows.append(row)
        value = {
            "policy_id": "dossier.package_manifest",
            "policy_version": "1.0.0",
            "entries": rows,
        }
        encoder = json.JSONEncoder(
            ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        return _bounded_bytes(_with_final_lf(encoder.iterencode(value)))
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None


def _with_final_lf(chunks: Iterable[str]) -> Iterator[str]:
    yield from chunks
    yield "\n"


def serialize_sha256sums(files: Sequence[IntegrityPayload]) -> bytes:
    """P plus the actual written manifest; never a checksum of this output itself."""
    try:
        ordered = sorted(files, key=lambda f: f.package_path)
        paths: set[str] = set()
        for item in ordered:
            IntegrityPayload.__post_init__(item)
            require(
                item.package_path not in paths and item.package_path != SUMS_PATH, "INTERNAL_ERROR"
            )
            paths.add(item.package_path)
        require(MANIFEST_PATH in paths, "INTERNAL_ERROR")
        return _bounded_bytes(f"{f.sha256}  {f.package_path}\n" for f in ordered)
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None


@contextmanager
def _directory_entries(baseline: capture._Baseline) -> Iterator[Iterator[os.DirEntry[str]]]:
    """Use a verified directory descriptor on POSIX; pre/post checks on all hosts."""
    capture._parents(baseline, include_self=True)
    descriptor = None
    try:
        target: int | Path = baseline.path
        if os.name == "posix":
            descriptor = os.open(baseline.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            require(
                capture.file_identity(os.fstat(descriptor)) == capture.file_identity(baseline.info),
                "INPUT_CHANGED",
            )
            target = descriptor
        capture._parents(baseline, include_self=True)
        with os.scandir(target) as entries:
            yield entries
        capture._parents(baseline, include_self=True)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _tree(
    root: capture._Baseline, expected: set[str]
) -> tuple[dict[str, capture._Baseline], dict[str, capture._Baseline]]:
    """Exact directory closure and file set; unknown nodes are never opened."""
    allowed_dirs = {p[:index] for p in expected for index, c in enumerate(p) if c == "/"}
    files: dict[str, capture._Baseline] = {}
    directories = {"": root}
    pending = [("", root)]
    while pending:
        relative, directory = pending.pop()
        with _directory_entries(directory) as children:
            names = []
            for child in children:
                capture._parents(directory, include_self=True)
                path = directory.path / child.name
                name = f"{relative}/{child.name}" if relative else child.name
                info = path.lstat()
                is_dir = stat.S_ISDIR(info.st_mode)
                capture._safe_info(path, directory=is_dir)
                require(name in (allowed_dirs if is_dir else expected), "INTERNAL_ERROR")
                names.append((name, path, is_dir))
            for name, path, is_dir in sorted(names):
                checked = capture._inspect(path, directory=is_dir)
                require(checked.path.is_relative_to(root.path), "PATH_ESCAPE")
                if is_dir:
                    directories[name] = checked
                    pending.append((name, checked))
                else:
                    files[name] = checked
    require(set(files) == expected and set(directories) == allowed_dirs | {""}, "INTERNAL_ERROR")
    capture._parents(root, include_self=True)
    return files, directories


def _read_payload(
    baseline: capture._Baseline,
    path: str,
    limit: int,
    expected: ManifestEntry | None = None,
    content: bytes | None = None,
) -> IntegrityPayload:
    require(baseline.info.st_size <= limit, "RESOURCE_LIMIT")
    if content is not None:
        require(baseline.info.st_size == len(content), "INTERNAL_ERROR")
    if expected is not None:
        require(baseline.info.st_size == expected.byte_size, "HASH_MISMATCH")
    digest = hashlib.sha256()
    size = 0
    with capture._reader(baseline) as stream:
        for chunk in capture._chunks(stream, limit):
            if content is not None:
                require(content[size : size + len(chunk)] == chunk, "INTERNAL_ERROR")
            digest.update(chunk)
            size += len(chunk)
        require(size == baseline.info.st_size, "INPUT_CHANGED")
    sha = digest.hexdigest()
    if expected is not None:
        require(sha == expected.sha256, "HASH_MISMATCH")
    return IntegrityPayload(path, size, sha)


def _write_integrity(root: capture._Baseline, path: str, content: bytes) -> None:
    require(path in (MANIFEST_PATH, SUMS_PATH), "INTERNAL_ERROR")
    require(len(content) <= MAX_GENERATED_FILE_BYTES, "RESOURCE_LIMIT")
    with capture._writer(root, path) as output:
        for offset in range(0, len(content), capture.CHUNK_SIZE):
            output.write(content[offset : offset + capture.CHUNK_SIZE])


def _selected_expectations(
    root: capture._Baseline, captured: capture.CaptureBatch
) -> dict[str, ManifestEntry]:
    require(capture._lexical(captured.capture_root) == root.path, "INVALID_PATH")
    paths = []
    selected = {}
    labels: set[str] = set()
    for item in captured.inputs:
        if item.package_path is None:
            raise EvidenceError("DOSSIER_INTERNAL_ERROR")
        entry = ManifestEntry(
            item.package_path,
            item.byte_size,
            item.sha256,
            item.role,
            item.source_class,
            item.local_label,
        )
        require(item.captured_path == root.path / entry.package_path, "INVALID_PATH")
        require(
            entry.package_path not in selected and item.local_label not in labels, "INTERNAL_ERROR"
        )
        if item.role == "contextual_visual":
            extension = {"jpeg": ".jpg", "png": ".png"}.get(item.validated_format or "")
            require(
                extension is not None and entry.package_path.endswith(extension), "INTERNAL_ERROR"
            )
        paths.append(entry.package_path)
        labels.add(item.local_label)
        selected[entry.package_path] = entry
    capture.validate_destination_set(paths)
    require(sum(e.role == "consolidated_report" for e in selected.values()) == 1, "INTERNAL_ERROR")
    require(any(e.role == "report_snapshot" for e in selected.values()), "INTERNAL_ERROR")
    return selected


def _no_existing_integrity(root: capture._Baseline) -> None:
    directory = root.path / "integrity"
    try:
        directory.lstat()
    except FileNotFoundError:
        return
    checked = capture._inspect(directory, directory=True)
    for path in (MANIFEST_PATH, SUMS_PATH):
        capture._parents(checked, include_self=True)
        try:
            (root.path / path).lstat()
        except FileNotFoundError:
            continue
        raise EvidenceError("DOSSIER_STAGING_FAILURE")


def _check_baselines(
    before: Mapping[str, capture._Baseline],
    after: Mapping[str, capture._Baseline],
    *,
    directories: bool = False,
) -> None:
    for path, baseline in before.items():
        require(path in after, "INTERNAL_ERROR")
        if directories:
            capture._parents(baseline, include_self=True)
        else:
            require(capture._same(baseline.info, after[path].info), "INPUT_CHANGED")


def finalize_integrity(
    *,
    work_root: Path,
    captured: capture.CaptureBatch,
    dossier_content: bytes,
    annex_index_content: bytes,
    selection_metadata_content: bytes,
) -> PackageIntegrityResult:
    """Verify P, write manifest then sums, and recheck the complete actual package.

    Expected human bytes come from C/D; equality inherits their contracts without
    a second semantic parser. Success is internal consistency, not publication,
    an atomic filesystem snapshot or a guarantee against later mutation.
    """
    try:
        root = capture._inspect(work_root, directory=True)
        selected = _selected_expectations(root, captured)
        generated = dict(
            zip(
                GENERATED_PAYLOADS,
                (dossier_content, annex_index_content, selection_metadata_content),
                strict=True,
            )
        )
        for content in generated.values():
            require(type(content) is bytes, "INTERNAL_ERROR")
            require(len(content) <= MAX_GENERATED_FILE_BYTES, "RESOURCE_LIMIT")
        _no_existing_integrity(root)
        payload_paths = set(selected) | set(generated)
        baselines, directories = _tree(root, payload_paths)
        require(
            sum(b.info.st_size for b in baselines.values()) <= MAX_PACKAGE_BYTES, "RESOURCE_LIMIT"
        )
        entries = []
        total = 0
        for path in sorted(payload_paths):
            expected = selected.get(path)
            limit = (
                capture._limit(expected.role) if expected is not None else MAX_GENERATED_FILE_BYTES
            )
            actual = _read_payload(
                baselines[path],
                path,
                min(limit, MAX_PACKAGE_BYTES - total),
                expected,
                generated.get(path),
            )
            total += actual.byte_size
            role, source_class = (
                (expected.role, expected.source_class)
                if expected is not None
                else GENERATED_PAYLOADS[path]
            )
            entries.append(
                ManifestEntry(
                    path,
                    actual.byte_size,
                    actual.sha256,
                    role,
                    source_class,
                    expected.local_label if expected else None,
                )
            )
        manifest = serialize_manifest(entries)
        require(total + len(manifest) <= MAX_PACKAGE_BYTES, "RESOURCE_LIMIT")
        _write_integrity(root, MANIFEST_PATH, manifest)
        baselines[MANIFEST_PATH] = capture._inspect(root.path / MANIFEST_PATH)
        manifest_file = _read_payload(
            baselines[MANIFEST_PATH], MANIFEST_PATH, MAX_GENERATED_FILE_BYTES, content=manifest
        )
        sums = serialize_sha256sums((*entries, manifest_file))
        require(total + manifest_file.byte_size + len(sums) <= MAX_PACKAGE_BYTES, "RESOURCE_LIMIT")
        _write_integrity(root, SUMS_PATH, sums)
        baselines[SUMS_PATH] = capture._inspect(root.path / SUMS_PATH)
        _read_payload(baselines[SUMS_PATH], SUMS_PATH, MAX_GENERATED_FILE_BYTES, content=sums)
        generated.update({MANIFEST_PATH: manifest, SUMS_PATH: sums})
        final_paths = payload_paths | {MANIFEST_PATH, SUMS_PATH}
        final_tree, final_dirs = _tree(root, final_paths)
        _check_baselines(directories, final_dirs, directories=True)
        _check_baselines(baselines, final_tree)
        # Freshly hash every final file; actual written manifest/sums must equal
        # the authoritative serialized bytes, never a parsed replacement.
        files = []
        total = 0
        for path in sorted(final_paths):
            expected = selected.get(path)
            limit = (
                capture._limit(expected.role) if expected is not None else MAX_GENERATED_FILE_BYTES
            )
            actual = _read_payload(
                final_tree[path],
                path,
                min(limit, MAX_PACKAGE_BYTES - total),
                expected,
                generated.get(path),
            )
            files.append(actual)
            total += actual.byte_size
        # Catch changes to an earlier file while a later file was verified.
        checked_files, checked_dirs = _tree(root, final_paths)
        _check_baselines(final_tree, checked_files)
        _check_baselines(final_dirs, checked_dirs, directories=True)
        return PackageIntegrityResult(manifest, sums, tuple(entries), tuple(files), total)
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None
    except FileNotFoundError:
        raise EvidenceError("DOSSIER_INTERNAL_ERROR") from None
    except OSError:
        raise EvidenceError("DOSSIER_STAGING_FAILURE") from None
    except (TypeError, ValueError, KeyError, AttributeError):
        raise EvidenceError("DOSSIER_INTERNAL_ERROR") from None
