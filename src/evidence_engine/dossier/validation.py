"""Canonical compatibility over captured bytes only (8B1-B, ADR 0037).

Completeness concerns only the supplied support set, never the real-world case.
The captured-format boundary also enforces selected JSON depth/node aggregation;
canonical semantics keep their shared historical decoder and report behavior.
"""

import json
import math
import warnings
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageFile

from evidence_engine.dossier import selection as selection_contract
from evidence_engine.errors import EvidenceError
from evidence_engine.media.signatures import PREFIX_LIMIT, identify
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
MAX_SUPPLEMENTAL_BYTES = 16 * 1024 * 1024
MAX_VISUAL_BYTES = 32 * 1024 * 1024
MAX_TOTAL_JSON_NODES = 2_000_000
MAX_IMAGE_DIMENSION = 16384
MAX_IMAGE_PIXELS = 16_000_000


@dataclass(frozen=True, slots=True)
class CapturedFormatInput:
    """Caller supplies verified captured bytes, never reopens an input source."""

    local_label: str
    role: str
    content: bytes


@dataclass(frozen=True, slots=True)
class ValidatedFormat:
    local_label: str
    role: str
    image_format: str | None


def _json_nodes(content: bytes, role: str) -> int:
    invalid = "CANONICAL_SET_INVALID" if role == "report_snapshot" else "UNSUPPORTED_FORMAT"

    def integer(text: str) -> int:
        _require(len(text) <= selection_contract.MAX_NUMBER_CHARS, "RESOURCE_LIMIT")
        return int(text)

    def floating(text: str) -> float:
        _require(len(text) <= selection_contract.MAX_NUMBER_CHARS, "RESOURCE_LIMIT")
        value = float(text)
        _require(math.isfinite(value), "RESOURCE_LIMIT")
        return value

    try:
        _require(not content.startswith(b"\xef\xbb\xbf"), invalid)
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=selection_contract._unique_object,
            parse_constant=selection_contract._constant,
            parse_int=integer,
            parse_float=floating,
        )
        return selection_contract._check_structure(value, allow_null=True)
    except EvidenceError as error:
        if str(error) == "DOSSIER_RESOURCE_LIMIT":
            raise
        raise EvidenceError(f"DOSSIER_{invalid}") from None
    except (UnicodeError, ValueError):
        raise EvidenceError(f"DOSSIER_{invalid}") from None


def _visual(content: bytes) -> str:
    hint = identify(content[:PREFIX_LIMIT]).media_format
    _require(hint in ("jpeg", "png"), "UNSUPPORTED_FORMAT")
    expected = {"jpeg": "JPEG", "png": "PNG"}[hint]
    # Do not silently honor a process-wide relaxation set by another caller.
    _require(not ImageFile.LOAD_TRUNCATED_IMAGES, "UNSUPPORTED_FORMAT")
    try:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            for verify in (True, False):
                with Image.open(BytesIO(content), formats=[expected]) as image:
                    _require(image.format == expected, "UNSUPPORTED_FORMAT")
                    width, height = image.size
                    _require(width > 0 and height > 0, "UNSUPPORTED_FORMAT")
                    _require(
                        width <= MAX_IMAGE_DIMENSION
                        and height <= MAX_IMAGE_DIMENSION
                        and width * height <= MAX_IMAGE_PIXELS,
                        "RESOURCE_LIMIT",
                    )
                    _require(
                        getattr(image, "n_frames", 1) == 1
                        and not getattr(image, "is_animated", False)
                        and image.get_format_mimetype() != "image/apng",
                        "UNSUPPORTED_FORMAT",
                    )
                    if verify:
                        image.verify()
                    else:
                        image.load()
        return hint
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None
    except (OSError, ValueError, SyntaxError, TypeError, KeyError, OverflowError):
        raise EvidenceError("DOSSIER_UNSUPPORTED_FORMAT") from None


def validate_captured_formats(inputs: Iterable[CapturedFormatInput]) -> tuple[ValidatedFormat, ...]:
    """Sequential format-only validation, including aggregate snapshot/support JSON nodes.

    No canonical semantics, Markdown interpretation or image transformation.
    A generator lets the caller release one captured payload before reading another.
    """
    result = []
    labels: set[str] = set()
    nodes = 0
    try:
        for item in inputs:
            _require(item.local_label not in labels, "INVALID_SELECTION")
            labels.add(item.local_label)
            limits = {
                "report_snapshot": MAX_SNAPSHOT_BYTES,
                "consolidated_report": MAX_CONSOLIDATED_REPORT_BYTES,
                "technical_review": MAX_SUPPLEMENTAL_BYTES,
                "validation_report": MAX_SUPPLEMENTAL_BYTES,
                "structured_support": MAX_SUPPLEMENTAL_BYTES,
                "contextual_visual": MAX_VISUAL_BYTES,
            }
            _require(item.role in limits, "INVALID_ROLE_CLASS")
            _require(type(item.content) is bytes, "UNSUPPORTED_FORMAT")
            _require(len(item.content) <= limits[item.role], "RESOURCE_LIMIT")
            image_format = None
            if item.role in ("report_snapshot", "structured_support"):
                nodes += _json_nodes(item.content, item.role)
                _require(nodes <= MAX_TOTAL_JSON_NODES, "RESOURCE_LIMIT")
            elif item.role in ("technical_review", "validation_report"):
                _require(
                    not item.content.startswith(b"\xef\xbb\xbf") and b"\0" not in item.content,
                    "UNSUPPORTED_FORMAT",
                )
                item.content.decode("utf-8")
            elif item.role == "contextual_visual":
                image_format = _visual(item.content)
            result.append(ValidatedFormat(item.local_label, item.role, image_format))
        return tuple(result)
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None
    except UnicodeError:
        raise EvidenceError("DOSSIER_UNSUPPORTED_FORMAT") from None


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
