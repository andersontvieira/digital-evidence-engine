"""Read-only directory-v1 capture and PDF binding; no rendering or publication."""

import hashlib
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, NoReturn, cast

from evidence_engine.dossier import integrity as source_integrity
from evidence_engine.dossier import packaging as capture
from evidence_engine.dossier import pdf_limits, selection
from evidence_engine.dossier.pdf_environment import register_fonts, verify_environment
from evidence_engine.dossier.pdf_model import DocumentKind, parse_presentation_bytes
from evidence_engine.dossier.pdf_renderer import _Layout
from evidence_engine.dossier.pdf_validation import validate_pdf_bytes
from evidence_engine.errors import EvidenceError

MAX_SOURCE_BYTES = 1024**3
MAX_SOURCE_FILES = 261
MAX_ADMIN_BYTES = 64 * 1024**2
MAX_MARKDOWN_TOTAL = 128 * 1024**2
MAX_PDF_TOTAL = 128 * 1024**2
MAX_INTEGRITY_BYTES = 1024**2
MAX_OUTPUT_BYTES = 130 * 1024**2
MANIFEST_PATH = "integrity/pdf-export-manifest.json"
SUMS_PATH = "integrity/SHA256SUMS.txt"
SOURCE_MANIFEST = "integrity/manifest.json"
METADATA_PATH = "technical/selection-metadata.json"
# ASCII output order also fixes validation order; callers cannot define a mapping.
_BINDINGS: tuple[tuple[str, str, DocumentKind], ...] = (
    (
        "human/consolidated-report.pdf",
        "technical/canonical/consolidated-report.md",
        "consolidated-report",
    ),
    ("human/dossier.pdf", "human/dossier.md", "dossier"),
)
_OUTPUT_PATHS = frozenset({MANIFEST_PATH, SUMS_PATH, *(p for p, _, _ in _BINDINGS)})
_RETAIN = frozenset({SOURCE_MANIFEST, SUMS_PATH, METADATA_PATH, *(s for _, s, _ in _BINDINGS)})
_SHA = re.compile(r"[0-9a-f]{64}")
type PackageError = Literal[
    "INVALID_PACKAGE", "INTEGRITY_MISMATCH", "INPUT_CHANGED", "RESOURCE_LIMIT", "INTERNAL_ERROR"
]
_PDF_ERRORS = frozenset(
    "DOSSIER_PDF_" + code
    for code in (
        "INVALID_PACKAGE",
        "INTEGRITY_MISMATCH",
        "INPUT_CHANGED",
        "RESOURCE_LIMIT",
        "INTERNAL_ERROR",
        "ENVIRONMENT_UNSUPPORTED",
        "FONT_UNSUPPORTED",
        "UNSUPPORTED_MARKDOWN",
        "UNSUPPORTED_LAYOUT",
        "RENDER_FAILURE",
        "PDF_VALIDATION_FAILURE",
    )
)


def _fail(code: PackageError) -> NoReturn:
    raise EvidenceError("DOSSIER_PDF_" + code)


def _require(condition: bool, code: PackageError = "INVALID_PACKAGE") -> None:
    if not condition:
        _fail(code)


@contextmanager
def _errors(*, recheck: bool = False) -> Iterator[None]:
    try:
        yield
    except (MemoryError, RecursionError):
        _fail("RESOURCE_LIMIT")
    except EvidenceError as error:
        code = str(error)
        if code in ("DOSSIER_RESOURCE_LIMIT", "DOSSIER_PDF_RESOURCE_LIMIT"):
            raise EvidenceError("DOSSIER_PDF_RESOURCE_LIMIT") from None
        if recheck:
            raise EvidenceError("DOSSIER_PDF_INPUT_CHANGED") from None
        if code in _PDF_ERRORS:
            raise EvidenceError(code) from None
        mapped: PackageError = (
            "INPUT_CHANGED"
            if code == "DOSSIER_INPUT_CHANGED"
            else "INTEGRITY_MISMATCH"
            if code == "DOSSIER_HASH_MISMATCH"
            else "INVALID_PACKAGE"
        )
        raise EvidenceError("DOSSIER_PDF_" + mapped) from None
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError):
        raise EvidenceError(
            "DOSSIER_PDF_INPUT_CHANGED" if recheck else "DOSSIER_PDF_INVALID_PACKAGE"
        ) from None
    except Exception:
        raise EvidenceError("DOSSIER_PDF_INTERNAL_ERROR") from None


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _bytes(content: bytes, limit: int) -> None:
    _require(type(content) is bytes)
    _require(len(content) <= limit, "RESOURCE_LIMIT")


def _digest(value: object) -> None:
    _require(type(value) is str and _SHA.fullmatch(value) is not None)


def _integer(value: object, *, positive: bool = False) -> None:
    _require(type(value) is int and value >= (1 if positive else 0))


def _json_bytes(value: object, limit: int) -> bytes:
    encoder = json.JSONEncoder(
        ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    output = bytearray()
    for chunk in encoder.iterencode(value):
        encoded = chunk.encode("utf-8")
        _require(len(output) + len(encoded) + 1 <= limit, "RESOURCE_LIMIT")
        output.extend(encoded)
    output.extend(b"\n")
    return bytes(output)


def _json(content: bytes, limit: int) -> dict[str, object]:
    _bytes(content, limit)
    _require(not content.startswith(b"\xef\xbb\xbf"))
    value: object = json.loads(
        content.decode("utf-8"),
        object_pairs_hook=selection._unique_object,
        parse_constant=selection._constant,
        parse_int=selection._integer,
        parse_float=selection._float,
    )
    selection._check_structure(value)
    _require(type(value) is dict)
    _require(_json_bytes(value, limit) == content)
    return cast(dict[str, object], value)


@dataclass(frozen=True, slots=True)
class SourceFile:
    package_path: str
    byte_size: int
    sha256: str
    baseline: capture._Baseline


@dataclass(frozen=True, slots=True)
class CapturedSourcePackage:
    """Operational baselines never enter output metadata; retained bytes are immutable."""

    root: capture._Baseline
    files: tuple[SourceFile, ...]
    directories: tuple[tuple[str, capture._Baseline], ...]
    retained: tuple[tuple[str, bytes], ...]

    def source_bytes(self, package_path: str) -> bytes:
        for path, content in self.retained:
            if path == package_path:
                return content
        _fail("INVALID_PACKAGE")


@dataclass(frozen=True, slots=True)
class PdfManifestEntry:
    package_path: str
    source_package_path: str
    source_byte_size: int
    source_sha256: str
    byte_size: int
    sha256: str
    page_count: int


@dataclass(frozen=True, slots=True)
class BoundPdf:
    entry: PdfManifestEntry
    content: bytes


@dataclass(frozen=True, slots=True)
class PdfExportIntegrity:
    pdfs: tuple[BoundPdf, ...]
    manifest_content: bytes
    sums_content: bytes
    render_environment_id: str

    @property
    def files(self) -> tuple[tuple[str, bytes], ...]:
        return tuple(
            sorted(
                (
                    *((pdf.entry.package_path, pdf.content) for pdf in self.pdfs),
                    (MANIFEST_PATH, self.manifest_content),
                    (SUMS_PATH, self.sums_content),
                )
            )
        )


def _source_manifest(content: bytes) -> tuple[source_integrity.ManifestEntry, ...]:
    value = _json(content, MAX_ADMIN_BYTES)
    _require(set(value) == {"policy_id", "policy_version", "entries"})
    _require(
        value["policy_id"] == "dossier.package_manifest" and value["policy_version"] == "1.0.0"
    )
    rows = value["entries"]
    _require(type(rows) is list)
    rows = cast(list[object], rows)
    _require(len(rows) + 2 <= MAX_SOURCE_FILES, "RESOURCE_LIMIT")
    entries = []
    for raw in rows:
        _require(type(raw) is dict)
        row = cast(dict[str, object], raw)
        path = row.get("package_path")
        _require(type(path) is str)
        generated = path in source_integrity.GENERATED_PAYLOADS
        _require(
            set(row)
            == {"package_path", "role", "source_class", "byte_size", "sha256"}
            | (set() if generated else {"local_label"})
        )
        for name in ("package_path", "role", "source_class"):
            _require(type(row[name]) is str)
        _integer(row["byte_size"])
        _digest(row["sha256"])
        if not generated:
            selection._label(row["local_label"])
        entry = source_integrity.ManifestEntry(
            cast(str, path),
            cast(int, row["byte_size"]),
            cast(str, row["sha256"]),
            cast(str, row["role"]),
            cast(str, row["source_class"]),
            None if generated else cast(str, row["local_label"]),
        )
        entries.append(entry)
    paths = [entry.package_path for entry in entries]
    _require(paths == sorted(set(paths)))
    _require(set(source_integrity.GENERATED_PAYLOADS) <= set(paths))
    selected = [entry for entry in entries if entry.local_label is not None]
    capture.validate_destination_set([entry.package_path for entry in selected])
    _require(len({entry.local_label for entry in selected}) == len(selected))
    _require(sum(entry.role == "consolidated_report" for entry in selected) == 1)
    _require(any(entry.role == "report_snapshot" for entry in selected))
    _require(len(selected) <= selection.MAX_SELECTED_ITEMS, "RESOURCE_LIMIT")
    _require(
        sum(entry.byte_size for entry in selected) <= capture.MAX_TOTAL_INPUT_BYTES,
        "RESOURCE_LIMIT",
    )
    _require(
        sum(entry.byte_size for entry in selected if entry.role == "report_snapshot")
        <= capture.MAX_TOTAL_SNAPSHOT_BYTES,
        "RESOURCE_LIMIT",
    )
    for entry in entries:
        limit = MAX_ADMIN_BYTES if entry.local_label is None else capture._limit(entry.role)
        _require(entry.byte_size <= limit, "RESOURCE_LIMIT")
    return tuple(entries)


def _metadata(content: bytes, entries: Sequence[source_integrity.ManifestEntry]) -> None:
    value = _json(content, MAX_ADMIN_BYTES)
    required = {"policy_id", "policy_version", "delivery_profile", "items"}
    _require(required <= value.keys() <= required | {"issued_date", "case_reference"})
    _require(
        value["policy_id"] == "dossier.selection"
        and value["policy_version"] == "1.0.0"
        and value["delivery_profile"] == "directory-v1"
    )
    if "issued_date" in value:
        selection._issued_date(value["issued_date"])
    if "case_reference" in value:
        selection._label(value["case_reference"])
    selected = sorted(
        (entry for entry in entries if entry.local_label is not None),
        key=lambda entry: (entry.role, entry.local_label or ""),
    )
    items = value["items"]
    _require(type(items) is list)
    items = cast(list[object], items)
    _require(len(items) == len(selected))
    for raw, entry in zip(items, selected, strict=True):
        _require(type(raw) is dict)
        item = cast(dict[str, object], raw)
        fields = {"local_label", "role", "source_class", "package_path"}
        visual = entry.role == "contextual_visual"
        _require(
            set(item)
            == fields
            | ({"display_caption", "operator_selected", "display_approved"} if visual else set())
        )
        _require(all(item[key] == getattr(entry, key) and type(item[key]) is str for key in fields))
        if visual:
            selection._caption(item["display_caption"])
            _require(item["operator_selected"] is True and item["display_approved"] is True)
    for roles, limit in (
        (("technical_review", "structured_support"), selection.MAX_SUPPLEMENTAL_ITEMS),
        (("validation_report",), selection.MAX_VALIDATION_ARTIFACTS),
        (("contextual_visual",), selection.MAX_VISUAL_EXHIBITS),
    ):
        _require(sum(entry.role in roles for entry in selected) <= limit, "RESOURCE_LIMIT")


def _sums(rows: Sequence[tuple[str, str]], limit: int) -> bytes:
    output = bytearray()
    _require(len({path for path, _ in rows}) == len(rows))
    for path, digest in sorted(rows):
        selection._input_reference(path)
        _digest(digest)
        line = f"{digest}  {path}\n".encode("ascii")
        _require(len(output) + len(line) <= limit, "RESOURCE_LIMIT")
        output.extend(line)
    return bytes(output)


def _read(baseline: capture._Baseline, path: str, limit: int) -> tuple[SourceFile, bytes | None]:
    _require(baseline.info.st_size <= limit, "RESOURCE_LIMIT")
    retained = bytearray() if path in _RETAIN else None
    digest = hashlib.sha256()
    size = 0
    with capture._reader(baseline) as stream:
        for chunk in capture._chunks(stream, limit):
            digest.update(chunk)
            size += len(chunk)
            if retained is not None:
                retained.extend(chunk)
        _require(size == baseline.info.st_size, "INPUT_CHANGED")
    return SourceFile(
        path, size, digest.hexdigest(), baseline
    ), None if retained is None else bytes(retained)


def _capture_contents(source: CapturedSourcePackage) -> tuple[source_integrity.ManifestEntry, ...]:
    """Defend public DTO boundaries against substituted bytes/records before binding."""
    _require(type(source) is CapturedSourcePackage)
    _require(
        all(type(value) is tuple for value in (source.files, source.directories, source.retained))
    )
    retained = dict(source.retained)
    _require(len(retained) == len(source.retained) and set(retained) == _RETAIN)
    entries = _source_manifest(retained[SOURCE_MANIFEST])
    _metadata(retained[METADATA_PATH], entries)
    expected = {entry.package_path: (entry.byte_size, entry.sha256) for entry in entries}
    for path in (SOURCE_MANIFEST, SUMS_PATH):
        _bytes(retained[path], MAX_ADMIN_BYTES)
        expected[path] = (len(retained[path]), _sha(retained[path]))
    _require(len(source.files) == len(expected))
    _require([f.package_path for f in source.files] == sorted(expected))
    ancestor_paths = {p[:i] for p in expected for i, char in enumerate(p) if char == "/"} | {""}
    _require([p for p, _ in source.directories] == sorted(ancestor_paths))
    for path, baseline in source.directories:
        _require(baseline.path == source.root.path / path)
    _require(len(source.files) <= MAX_SOURCE_FILES, "RESOURCE_LIMIT")
    total = 0
    for item in source.files:
        _require(type(item) is SourceFile)
        _integer(item.byte_size)
        _digest(item.sha256)
        _require(item.baseline.path == source.root.path / item.package_path)
        _require((item.byte_size, item.sha256) == expected[item.package_path], "INTEGRITY_MISMATCH")
        total += item.byte_size
        if item.package_path in retained:
            content = retained[item.package_path]
            _bytes(content, MAX_ADMIN_BYTES)
            _require(
                (len(content), _sha(content)) == expected[item.package_path], "INTEGRITY_MISMATCH"
            )
    _require(total <= MAX_SOURCE_BYTES, "RESOURCE_LIMIT")
    _require(sum(len(retained[s]) for _, s, _ in _BINDINGS) <= MAX_MARKDOWN_TOTAL, "RESOURCE_LIMIT")
    for _, path, _ in _BINDINGS:
        _bytes(retained[path], pdf_limits.MAX_MARKDOWN_BYTES)
    _require(
        retained[SUMS_PATH]
        == _sums(
            [(p, digest) for p, (_, digest) in expected.items() if p != SUMS_PATH], MAX_ADMIN_BYTES
        ),
        "INTEGRITY_MISMATCH",
    )
    return entries


def capture_source_package(root: Path) -> CapturedSourcePackage:
    """Capture only an explicitly supplied published package; never write to it."""
    with _errors():
        base = capture._inspect(root, directory=True)
        bootstrap = capture._inspect(base.path / SOURCE_MANIFEST)
        manifest_file, manifest = _read(
            bootstrap, SOURCE_MANIFEST, min(MAX_ADMIN_BYTES, MAX_SOURCE_BYTES)
        )
        assert manifest is not None
        entries = _source_manifest(manifest)
        expected = {entry.package_path: entry for entry in entries}
        paths = set(expected) | {SOURCE_MANIFEST, SUMS_PATH}
        _require(len(paths) <= MAX_SOURCE_FILES, "RESOURCE_LIMIT")
        files, directories = source_integrity._tree(base, paths)
        _require(capture._same(bootstrap.info, files[SOURCE_MANIFEST].info), "INPUT_CHANGED")
        _require(
            sum(file.info.st_size for file in files.values()) <= MAX_SOURCE_BYTES, "RESOURCE_LIMIT"
        )
        _require(
            sum(files[path].info.st_size for _, path, _ in _BINDINGS) <= MAX_MARKDOWN_TOTAL,
            "RESOURCE_LIMIT",
        )
        records = []
        retained = []
        total = 0
        for path in sorted(files):
            entry = expected.get(path)
            limit = (
                MAX_ADMIN_BYTES
                if entry is None or entry.local_label is None
                else capture._limit(entry.role)
            )
            if path in {s for _, s, _ in _BINDINGS}:
                limit = min(limit, pdf_limits.MAX_MARKDOWN_BYTES)
            record, content = _read(files[path], path, min(limit, MAX_SOURCE_BYTES - total))
            if entry is not None:
                _require(
                    (record.byte_size, record.sha256) == (entry.byte_size, entry.sha256),
                    "INTEGRITY_MISMATCH",
                )
            if path == SOURCE_MANIFEST:
                _require(
                    content == manifest and record.sha256 == manifest_file.sha256, "INPUT_CHANGED"
                )
            records.append(record)
            total += record.byte_size
            if content is not None:
                retained.append((path, content))
        result = CapturedSourcePackage(
            base, tuple(records), tuple(sorted(directories.items())), tuple(retained)
        )
        _capture_contents(result)
        recheck_source_package(result)
        return result


def recheck_source_package(source: CapturedSourcePackage) -> None:
    """Rehash the entire captured tree; observable change fails, no atomic snapshot claim."""
    with _errors(recheck=True):
        entries = _capture_contents(source)
        expected = {item.package_path: item for item in source.files}
        files, directories = source_integrity._tree(source.root, set(expected))
        source_integrity._check_baselines(dict(source.directories), directories, directories=True)
        before = {path: item.baseline for path, item in expected.items()}
        source_integrity._check_baselines(before, files)
        limits_by_path = {
            entry.package_path: MAX_ADMIN_BYTES
            if entry.local_label is None
            else capture._limit(entry.role)
            for entry in entries
        }
        total = 0
        for path in sorted(files):
            item = expected[path]
            # No retained copy is needed here; approved streaming primitive hashes only.
            checked = source_integrity._read_payload(
                files[path],
                path,
                min(limits_by_path.get(path, MAX_ADMIN_BYTES), MAX_SOURCE_BYTES - total),
            )
            _require(
                (checked.byte_size, checked.sha256) == (item.byte_size, item.sha256),
                "INPUT_CHANGED",
            )
            total += checked.byte_size
        final_files, final_dirs = source_integrity._tree(source.root, set(expected))
        source_integrity._check_baselines(files, final_files)
        source_integrity._check_baselines(directories, final_dirs, directories=True)


def serialize_pdf_manifest(
    entries: Sequence[PdfManifestEntry],
    *,
    manifest_sha256: str,
    sha256sums_sha256: str,
    render_environment_id: str,
) -> bytes:
    """Pure closed-schema serialization; binding callers compute all fingerprints."""
    with _errors():
        _digest(manifest_sha256)
        _digest(sha256sums_sha256)
        _digest(render_environment_id)
        _require(len(entries) == 2)
        ordered = sorted(entries, key=lambda entry: entry.package_path)
        for entry, (pdf_path, source_path, _) in zip(ordered, _BINDINGS, strict=True):
            _require(type(entry) is PdfManifestEntry)
            _require(entry.package_path == pdf_path and entry.source_package_path == source_path)
            _integer(entry.source_byte_size)
            _integer(entry.byte_size)
            _integer(entry.page_count, positive=True)
            _digest(entry.source_sha256)
            _digest(entry.sha256)
            _require(
                entry.source_byte_size <= pdf_limits.MAX_MARKDOWN_BYTES
                and entry.byte_size <= pdf_limits.MAX_PDF_BYTES
                and entry.page_count <= pdf_limits.MAX_PAGES,
                "RESOURCE_LIMIT",
            )
        _require(
            sum(e.byte_size for e in ordered) <= MAX_PDF_TOTAL
            and sum(e.source_byte_size for e in ordered) <= MAX_MARKDOWN_TOTAL,
            "RESOURCE_LIMIT",
        )
        return _json_bytes(
            {
                "policy_id": "dossier.pdf_export_manifest",
                "policy_version": "1.0.0",
                "export_policy_id": "dossier.pdf_export",
                "export_policy_version": "1.0.0",
                "delivery_profile": "pdf-presentation-v1",
                "render_environment_id": render_environment_id,
                "source_package": {
                    "manifest_sha256": manifest_sha256,
                    "sha256sums_sha256": sha256sums_sha256,
                },
                "entries": [asdict(entry) for entry in ordered],
            },
            MAX_INTEGRITY_BYTES,
        )


def serialize_pdf_sha256sums(
    *, dossier_pdf: bytes, consolidated_report_pdf: bytes, manifest: bytes
) -> bytes:
    """Exactly three lines, computed from bytes, with no self-reference."""
    with _errors():
        for content in (dossier_pdf, consolidated_report_pdf):
            _bytes(content, pdf_limits.MAX_PDF_BYTES)
        _bytes(manifest, MAX_INTEGRITY_BYTES)
        _require(len(dossier_pdf) + len(consolidated_report_pdf) <= MAX_PDF_TOTAL, "RESOURCE_LIMIT")
        result = _sums(
            [
                ("human/dossier.pdf", _sha(dossier_pdf)),
                ("human/consolidated-report.pdf", _sha(consolidated_report_pdf)),
                (MANIFEST_PATH, _sha(manifest)),
            ],
            MAX_INTEGRITY_BYTES,
        )
        _require(
            len(dossier_pdf) + len(consolidated_report_pdf) + len(manifest) + len(result)
            <= MAX_OUTPUT_BYTES,
            "RESOURCE_LIMIT",
        )
        return result


def bind_pdf_export(
    source: CapturedSourcePackage,
    *,
    dossier_pdf: bytes,
    consolidated_report_pdf: bytes,
) -> PdfExportIntegrity:
    """Validate supplied PDF bytes against captured source; never invoke a PDF renderer."""
    with _errors():
        for content in (dossier_pdf, consolidated_report_pdf):
            _bytes(content, pdf_limits.MAX_PDF_BYTES)
        _require(len(dossier_pdf) + len(consolidated_report_pdf) <= MAX_PDF_TOTAL, "RESOURCE_LIMIT")
        recheck_source_package(source)
        environment_id = verify_environment()
        register_fonts()
        pdfs = []
        for (pdf_path, source_path, kind), pdf in zip(
            _BINDINGS, (consolidated_report_pdf, dossier_pdf), strict=True
        ):
            content = source.source_bytes(source_path)
            document = parse_presentation_bytes(content, kind)
            expected = _Layout(document).build().expected
            validation = validate_pdf_bytes(pdf, expected)
            entry = PdfManifestEntry(
                pdf_path,
                source_path,
                len(content),
                _sha(content),
                len(pdf),
                _sha(pdf),
                validation.page_count,
            )
            pdfs.append(BoundPdf(entry, pdf))
        manifest = serialize_pdf_manifest(
            [pdf.entry for pdf in pdfs],
            manifest_sha256=_sha(source.source_bytes(SOURCE_MANIFEST)),
            sha256sums_sha256=_sha(source.source_bytes(SUMS_PATH)),
            render_environment_id=environment_id,
        )
        sums = serialize_pdf_sha256sums(
            dossier_pdf=dossier_pdf,
            consolidated_report_pdf=consolidated_report_pdf,
            manifest=manifest,
        )
        recheck_source_package(source)
        return PdfExportIntegrity(tuple(pdfs), manifest, sums, environment_id)


def verify_pdf_export(
    source: CapturedSourcePackage, files: Mapping[str, bytes]
) -> PdfExportIntegrity:
    """Independently rebind PDFs and compare exact logical output bytes and coverage."""
    with _errors():
        _require(set(files) == _OUTPUT_PATHS, "INTEGRITY_MISMATCH")
        for path, content in files.items():
            _bytes(
                content,
                MAX_INTEGRITY_BYTES
                if path in (MANIFEST_PATH, SUMS_PATH)
                else pdf_limits.MAX_PDF_BYTES,
            )
        _require(sum(map(len, files.values())) <= MAX_OUTPUT_BYTES, "RESOURCE_LIMIT")
        # Strict decode rejects duplicates, noncanonical bytes and JSON resource attacks;
        # equality below rejects every unknown/missing field, type, order and fingerprint.
        _json(files[MANIFEST_PATH], MAX_INTEGRITY_BYTES)
        _require(
            files[SUMS_PATH]
            == serialize_pdf_sha256sums(
                dossier_pdf=files["human/dossier.pdf"],
                consolidated_report_pdf=files["human/consolidated-report.pdf"],
                manifest=files[MANIFEST_PATH],
            ),
            "INTEGRITY_MISMATCH",
        )
        actual = bind_pdf_export(
            source,
            dossier_pdf=files["human/dossier.pdf"],
            consolidated_report_pdf=files["human/consolidated-report.pdf"],
        )
        _require(dict(actual.files) == dict(files), "INTEGRITY_MISMATCH")
        return actual
