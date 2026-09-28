"""Canonical compatibility over captured bytes only (8B1-B, ADR 0037).

Completeness concerns only the supplied support set, never the real-world case.
JSON depth/node aggregation belongs to future captured-input orchestration;
this module shares the strict historical snapshot decoder, not selection's parser.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from evidence_engine.errors import EvidenceError
from evidence_engine.reports.consolidated import (
    ConsolidatedReportModel,
    Object,
    _decode_snapshot_json,
    _window,
    build_consolidated_model,
    render_markdown,
)

MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
MAX_TOTAL_SNAPSHOT_BYTES = 128 * 1024 * 1024
MAX_CONSOLIDATED_REPORT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class CapturedSnapshot:
    """Bytes plus an explicit local label already validated by 8B1-A."""

    local_label: str
    content: bytes


@dataclass(frozen=True, slots=True)
class ValidatedSnapshot:
    local_label: str
    reference: str  # Existing model's Anchor/W-ID, not a new finding identifier.
    snapshot: Object


@dataclass(frozen=True, slots=True)
class ValidatedCanonicalSet:
    """Frozen envelope using the existing report model/dictionary representation.

    Nested report dictionaries remain caller-owned in-memory data; this DTO is
    not a tamper-proof certification object. No input dictionary is shared.
    """

    model: ConsolidatedReportModel
    snapshots: tuple[ValidatedSnapshot, ...]
    report_content: bytes


def _require(condition: bool, code: str = "CANONICAL_SET_INVALID") -> None:
    if not condition:
        raise EvidenceError(f"DOSSIER_{code}")


def validate_canonical_set(
    *, report_content: bytes, snapshots: Sequence[CapturedSnapshot]
) -> ValidatedCanonicalSet:
    """Compare opaque report bytes to the pure renderer of all supplied snapshots.

    Local labels come from selection validation; only their uniqueness is checked
    here. No labels are derived, no Markdown facts parsed and no inputs discovered.
    """
    try:
        _require(type(report_content) is bytes)
        _require(len(report_content) <= MAX_CONSOLIDATED_REPORT_BYTES, "RESOURCE_LIMIT")
        captured = tuple(snapshots)
        _require(bool(captured))
        total = 0
        labels: set[str] = set()
        for item in captured:
            _require(isinstance(item, CapturedSnapshot))
            _require(type(item.local_label) is str and bool(item.local_label))
            _require(item.local_label not in labels)
            labels.add(item.local_label)
            _require(type(item.content) is bytes)
            _require(len(item.content) <= MAX_SNAPSHOT_BYTES, "RESOURCE_LIMIT")
            total += len(item.content)
            _require(total <= MAX_TOTAL_SNAPSHOT_BYTES, "RESOURCE_LIMIT")

        # Shared JSON decoding, then version dispatch across the entire set. This
        # distinguishes mixed future/current versions without relaxing the legacy
        # validate_snapshot contract or decoding every document twice.
        decoded = [_decode_snapshot_json(item.content) for item in captured]
        versions: set[str] = set()
        for snapshot in decoded:
            meta = snapshot.get("snapshot")
            if type(meta) is not dict:
                raise EvidenceError("DOSSIER_CANONICAL_SET_INVALID")
            _require(meta.get("snapshot_id") == "report.data_snapshot")
            version = meta.get("snapshot_version")
            if type(version) is not str:
                raise EvidenceError("DOSSIER_CANONICAL_SET_INVALID")
            versions.add(version)
        _require(len(versions) == 1)
        _require(versions == {"1.1.0"}, "UNSUPPORTED_POLICY_VERSION")
        # The builder includes validate_snapshot for every document and preserves
        # all report semantic checks, sorting and F/W/G construction.
        model = build_consolidated_model(decoded)
        expected = render_markdown(model).encode("utf-8")
        _require(len(expected) <= MAX_CONSOLIDATED_REPORT_BYTES, "RESOURCE_LIMIT")
        _require(expected == report_content, "CANONICAL_REPORT_MISMATCH")

        paired = list(zip(captured, decoded, strict=True))
        anchor = next(pair for pair in paired if pair[1]["analysis_window"] is None)
        # Reuse the exact report key (including normalized UTC/filter presence),
        # rather than reproducing sorting semantics in the dossier layer.
        windows = sorted(
            (pair for pair in paired if pair[1]["analysis_window"] is not None),
            key=lambda pair: _window(
                pair[1]["analysis_window"], pair[1]["provenance_index"]["parsed_records"]
            ),
        )
        ordered = (ValidatedSnapshot(anchor[0].local_label, "Anchor", anchor[1]),) + tuple(
            ValidatedSnapshot(item.local_label, window.window_id, snapshot)
            for window, (item, snapshot) in zip(model.windows, windows, strict=True)
        )
        return ValidatedCanonicalSet(model, ordered, report_content)
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None
    except EvidenceError as error:
        code = str(error)
        if code.startswith("DOSSIER_"):
            raise
        mapped = (
            "PRIVACY_CONTRACT_VIOLATION"
            if code == "REPORT_UNSAFE_DISPLAY_VALUE"
            else "CANONICAL_SET_INVALID"
        )
        raise EvidenceError(f"DOSSIER_{mapped}") from None
    except (KeyError, TypeError, ValueError, OverflowError):
        # Malformed snapshot structures may fail inside historical report helpers.
        raise EvidenceError("DOSSIER_CANONICAL_SET_INVALID") from None
