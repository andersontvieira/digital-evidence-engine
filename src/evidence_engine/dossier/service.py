"""Explicit local selection to a new directory; compose A–E, never investigate."""

from dataclasses import dataclass
from pathlib import Path

from evidence_engine.dossier import (
    integrity,
    packaging,
    projection,
    rendering,
    selection,
    validation,
)
from evidence_engine.errors import EvidenceError

_SAFE_CODES = frozenset(
    "DOSSIER_" + code
    for code in (
        "INVALID_SELECTION",
        "UNSUPPORTED_POLICY_VERSION",
        "INVALID_ROLE_CLASS",
        "INVALID_PATH",
        "PATH_ESCAPE",
        "UNSAFE_FILE_TYPE",
        "UNSUPPORTED_FORMAT",
        "RESOURCE_LIMIT",
        "INPUT_CHANGED",
        "INPUT_READ_ERROR",
        "HASH_MISMATCH",
        "CANONICAL_SET_INVALID",
        "CANONICAL_REPORT_MISMATCH",
        "PRIVACY_CONTRACT_VIOLATION",
        "OUTPUT_EXISTS",
        "STAGING_FAILURE",
        "PUBLICATION_FAILURE",
        "INTERNAL_ERROR",
    )
)


def safe_error_code(error: BaseException) -> str:
    if isinstance(error, (MemoryError, RecursionError)):
        return "DOSSIER_RESOURCE_LIMIT"
    if isinstance(error, EvidenceError) and str(error) in _SAFE_CODES:
        return str(error)
    return "DOSSIER_INTERNAL_ERROR"


@dataclass(frozen=True, slots=True)
class DossierAssemblyResult:
    output_dir: Path
    file_count: int
    total_byte_size: int


def assemble_dossier(*, selection_path: Path, output_dir: Path) -> DossierAssemblyResult:
    staging = None
    publishing = False
    try:
        content = packaging.read_selection_bytes_stable(selection_path)
        selected = selection.parse_selection_bytes(content)
        prepared = packaging.prepare_capture(
            selection_path=selection_path, selection=selected, selection_content=content
        )
        destination = packaging.prepare_output(prepared, output_dir)
        staging = packaging.create_staging(destination)
        captured = packaging.capture_prepared_inputs(prepared, capture_root=staging.path)
        formats = validation.validate_captured_formats(
            validation.CapturedFormatInput(i.local_label, i.role, packaging.read_captured_bytes(i))
            for i in captured.inputs
        )
        report = next(i for i in captured.inputs if i.role == "consolidated_report")
        canonical = validation.validate_canonical_set(
            report_content=packaging.read_captured_bytes(report),
            snapshots=tuple(
                validation.CapturedSnapshot(i.local_label, packaging.read_captured_bytes(i))
                for i in captured.inputs
                if i.role == "report_snapshot"
            ),
        )
        resolved = packaging.resolve_captured_inputs(
            captured,
            image_formats={
                i.local_label: i.image_format for i in formats if i.image_format is not None
            },
        )
        model = projection.project_dossier(selection=selected, canonical=canonical)
        # The accepted renderer is authoritative for H1/14 H2 sections; integration
        # tests assert its structure. No second Markdown/facts parser here.
        dossier = rendering.render_dossier_markdown(model)
        entries = packaging.resolved_annex_entries(selected, resolved)
        annex = rendering.render_annex_index(entries)
        metadata = rendering.render_selection_metadata(
            projection.SelectionMetadata(entries, selected.issued_date, selected.case_reference)
        )
        for path, data in (
            ("human/dossier.md", dossier),
            ("human/annex-index.md", annex),
            ("technical/selection-metadata.json", metadata),
        ):
            packaging.write_generated_file(staging, path, data)
        checked = integrity.finalize_integrity(
            work_root=staging.path,
            captured=resolved,
            dossier_content=dossier,
            annex_index_content=annex,
            selection_metadata_content=metadata,
        )
        packaging.revalidate_staging(staging)
        integrity.verify_integrity_result(staging.path, checked)
        packaging.sync_staging_directories(staging, tuple(i.package_path for i in checked.files))
        result = DossierAssemblyResult(
            destination.path, len(checked.files), checked.total_byte_size
        )
        publishing = True
        packaging.publish_staging(staging)
        return result  # Deliberately no filesystem action after confirmed publication.
    except Exception as error:
        code = safe_error_code(error)
        if staging is not None:
            if publishing and not packaging.staging_is_owned(staging):
                raise EvidenceError("DOSSIER_PUBLICATION_FAILURE") from None
            try:
                packaging.cleanup_staging(staging)
            except Exception:
                raise EvidenceError("DOSSIER_STAGING_FAILURE") from None
        raise EvidenceError(code) from None
