"""Pure, allowlisted human presentation; no source dictionaries cross this boundary."""

import re
from dataclasses import dataclass

from evidence_engine.dossier.selection import (
    DossierSelection,
    _caption,
    _issued_date,
    _label,
)
from evidence_engine.dossier.validation import ValidatedCanonicalSet
from evidence_engine.errors import EvidenceError
from evidence_engine.reports.consolidated import (
    COMPONENTS,
    SOURCE_MEDIA_STATUSES,
    TABLES,
    Object,
    TechnicalReference,
    _count,
    _technical,
    _utc,
    _version,
)

ACCOUNT_KINDS = frozenset(
    {"account.profile_activity", "account.security_activity", "account.change", "account.sign_on"}
)
CLASS_ORDER = (
    "CANONICAL_TECHNICAL",
    "SUPPLEMENTAL_TECHNICAL",
    "VALIDATION_ARTIFACT",
    "VISUAL_EXHIBIT",
)
ROLE_CLASSES = {
    "consolidated_report": "CANONICAL_TECHNICAL",
    "report_snapshot": "CANONICAL_TECHNICAL",
    "technical_review": "SUPPLEMENTAL_TECHNICAL",
    "structured_support": "SUPPLEMENTAL_TECHNICAL",
    "validation_report": "VALIDATION_ARTIFACT",
    "contextual_visual": "VISUAL_EXHIBIT",
}
_BIDI = frozenset("\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def require(condition: bool, code: str = "CANONICAL_SET_INVALID") -> None:
    if not condition:
        raise EvidenceError(f"DOSSIER_{code}")


def single_line(value: str) -> str:
    """Reject structural controls, without interpreting the meaning of prose."""
    require(
        type(value) is str
        and not any(
            ord(c) < 32
            or 127 <= ord(c) <= 159
            or 0xD800 <= ord(c) <= 0xDFFF
            or c in _BIDI
            or c in "\u2028\u2029"
            for c in value
        ),
        "PRIVACY_CONTRACT_VIOLATION",
    )
    return value


@dataclass(frozen=True, slots=True)
class DocumentIdentity:
    report_policy_id: str
    report_policy_version: str
    snapshot_policy_id: str
    snapshot_policy_version: str
    evidence_schema_version: int
    engine_version: str
    delivery_profile: str
    issued_date: str | None
    case_reference: str | None


@dataclass(frozen=True, slots=True)
class SelectedMaterial:
    local_label: str
    source_class: str
    role: str


@dataclass(frozen=True, slots=True)
class PolicyDisplay:
    component: str
    policy_id: str
    version: str


@dataclass(frozen=True, slots=True)
class Measure:
    name: str
    count: int
    unit: str


@dataclass(frozen=True, slots=True)
class CoverageRow:
    component_id: str
    version: str
    status_or_platform: str
    count: int
    unit: str


@dataclass(frozen=True, slots=True)
class EventCount:
    platform: str
    event_kind: str
    total: int
    dated: int
    undated: int


@dataclass(frozen=True, slots=True)
class CurrentEvents:
    policy_id: str
    policy_version: str
    unit: str
    total: int
    dated: int
    undated: int
    rows: tuple[EventCount, ...]


@dataclass(frozen=True, slots=True)
class IncidentRow:
    occurred_at_utc: str
    platform: str
    event_kind: str
    pointer: str


@dataclass(frozen=True, slots=True)
class ComponentCount:
    component: str
    unit: str
    total: int
    returned: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class WindowDisplay:
    window_id: str
    start: str
    end: str
    platform: str | None
    event_kind: str | None
    max_delta_seconds: int
    undated_current_events: int
    eligible_events: int
    counts: tuple[ComponentCount, ...]
    truncated_components: tuple[str, ...]
    source_media_statuses: tuple[Measure, ...]
    incidents: tuple[IncidentRow, ...]


@dataclass(frozen=True, slots=True)
class ReferenceDisplay:
    local_id: str
    snapshot: str
    pointer: str


@dataclass(frozen=True, slots=True)
class FindingDisplay:
    finding_id: str
    candidate_type: str
    classification: str
    statement: str
    technical_basis: str
    reference: ReferenceDisplay
    limitations: str


@dataclass(frozen=True, slots=True)
class GapDisplay:
    gap_id: str
    category: str
    statement: str
    technical_basis: str
    scope: str
    limitation: str


@dataclass(frozen=True, slots=True)
class ObservationContext:
    rows: tuple[CoverageRow, ...]
    exact_candidates: int
    candidate_unit: str


@dataclass(frozen=True, slots=True)
class SnapshotDestination:
    reference: str
    local_label: str
    package_path: str


@dataclass(frozen=True, slots=True)
class HumanDossierProjection:
    identity: DocumentIdentity
    materials: tuple[SelectedMaterial, ...]
    inventory: tuple[Measure, ...]
    parser_runs: tuple[CoverageRow, ...]
    policies: tuple[PolicyDisplay, ...]
    windows: tuple[WindowDisplay, ...]
    current_events: CurrentEvents
    findings: tuple[FindingDisplay, ...]
    media: tuple[Measure, ...]
    device: ObservationContext
    network: ObservationContext
    limitations: tuple[str, ...]
    gaps: tuple[GapDisplay, ...]
    references: tuple[ReferenceDisplay, ...]
    snapshots: tuple[SnapshotDestination, ...]


def package_paths(role: str, label: str) -> tuple[str, ...]:
    """Logical allowlist only. Visual alternatives are not format detection."""
    return {
        "consolidated_report": ("technical/canonical/consolidated-report.md",),
        "report_snapshot": (f"technical/canonical/snapshots/{label}.json",),
        "technical_review": (f"technical/supplemental/{label}.md",),
        "structured_support": (f"technical/structured/{label}.json",),
        "validation_report": (f"technical/validation/{label}.md",),
        "contextual_visual": (f"exhibits/visual/{label}.jpg", f"exhibits/visual/{label}.png"),
    }.get(role, ())


@dataclass(frozen=True, slots=True)
class AnnexIndexEntry:
    """Already resolved destination; visual selection/approval precedes this DTO.

    This validates display/path syntax only, never the format or contents of a file.
    """

    local_label: str
    role: str
    source_class: str
    package_path: str
    display_caption: str | None = None

    def __post_init__(self) -> None:
        _label(self.local_label)
        require(ROLE_CLASSES.get(self.role) == self.source_class, "INVALID_ROLE_CLASS")
        require(self.package_path in package_paths(self.role, self.local_label), "INVALID_PATH")
        if self.role == "contextual_visual":
            _caption(self.display_caption)
        else:
            require(self.display_caption is None, "PRIVACY_CONTRACT_VIOLATION")


@dataclass(frozen=True, slots=True)
class SelectionMetadata:
    """Resolved administrative fields only; selection/capture paths never enter."""

    items: tuple[AnnexIndexEntry, ...]
    issued_date: str | None = None
    case_reference: str | None = None

    def __post_init__(self) -> None:
        require(type(self.items) is tuple, "INVALID_SELECTION")
        if self.issued_date is not None:
            _issued_date(self.issued_date)
        if self.case_reference is not None:
            _label(self.case_reference)


def _reference(value: TechnicalReference) -> ReferenceDisplay:
    require(re.fullmatch(r"F-[0-9]{3,}", value.local_id) is not None)
    require(re.fullmatch(r"Anchor|W-[0-9]{3,}", value.snapshot) is not None)
    require(
        re.fullmatch(
            r"(?:finding_candidates\.(?:exact_media_duplicate|window_exact_candidate|"
            r"temporal_pair_candidate|temporal_exact_overlap_candidate)|"
            r"analysis_window\.source_media_links)\.items\[[0-9]+\]",
            value.pointer,
        )
        is not None
    )
    return ReferenceDisplay(value.local_id, value.snapshot, value.pointer)


def _basis(kind: str, value: Object) -> str:
    if kind == "exact_media_duplicate":
        return (
            "Igualdade SHA-256/tamanho verificada na 8A1; report.data_snapshot / "
            f"{_version(value['projection_policy_version'])}."
        )
    if kind == "window_exact_candidate":
        return (
            f"{_technical(value['correlator_id'])} / {_version(value['correlator_version'])}; "
            f"{_technical(value['rule_id'])} / {_version(value['rule_version'])}."
        )
    require(
        kind
        in {
            "temporal_pair_candidate",
            "temporal_exact_overlap_candidate",
            "source_media_provenance_link",
        }
    )
    return f"{_technical(value['policy_id'])} / {_version(value['policy_version'])}."


def _coverage(value: Object, prefix: str, dimension: str) -> tuple[CoverageRow, ...]:
    return tuple(
        CoverageRow(
            _technical(row[prefix + "_id"]),
            _version(row[prefix + "_version"]),
            _technical(row[dimension]),
            _count(row["count"]),
            _technical(value["unit"]),
        )
        for row in value["items"]
    )


def _policies(value: Object) -> tuple[PolicyDisplay, ...]:
    result = []
    for name, prefix, multiple in (
        ("current_event_policy", "policy", False),
        ("eligible_normalizers", "normalizer", True),
        ("observers", "observer", True),
        ("exact_rules", "rule", True),
        ("exact_correlator", "correlator", False),
        ("temporal_proximity", "policy", False),
        ("temporal_exact_overlap", "policy", False),
        ("perceptual_hash", "algorithm", False),
        ("source_media_links", "policy", False),
    ):
        rows = value[name] if multiple else (value[name],)
        for row in sorted(rows, key=lambda r: (r[prefix + "_id"], r[prefix + "_version"])):
            result.append(
                PolicyDisplay(
                    name, _technical(row[prefix + "_id"]), _version(row[prefix + "_version"])
                )
            )
    return tuple(result)


def _project(
    selection: DossierSelection, canonical: ValidatedCanonicalSet
) -> HumanDossierProjection:
    selected = selection.canonical_inputs
    require(sum(i.role == "consolidated_report" for i in selected) == 1)
    require(
        all(
            i.source_class == "CANONICAL_TECHNICAL"
            and i.role in ("consolidated_report", "report_snapshot")
            for i in selected
        )
    )
    labels = [i.local_label for i in selected if i.role == "report_snapshot"]
    supplied = [s.local_label for s in canonical.snapshots]
    require(len(labels) == len(set(labels)) and len(supplied) == len(set(supplied)))
    require(set(labels) == set(supplied))
    model = canonical.model
    by_reference = {s.reference: s for s in canonical.snapshots}
    refs = ("Anchor", *(w.window_id for w in model.windows))
    require(len(refs) == len(set(refs)) == len(by_reference) == len(canonical.snapshots))
    require(set(refs) == set(by_reference))
    require(by_reference["Anchor"].snapshot["analysis_window"] is None)
    meta = model.metadata
    identity = DocumentIdentity(
        _technical(meta["report_policy_id"]),
        _version(meta["report_policy_version"]),
        _technical(meta["snapshot_policy_id"]),
        _version(meta["snapshot_policy_version"]),
        _count(meta["evidence_schema_version"]),
        _version(meta["engine_version"]),
        _technical(selection.delivery_profile),
        _issued_date(selection.issued_date) if selection.issued_date is not None else None,
        _label(selection.case_reference) if selection.case_reference is not None else None,
    )
    all_items = (
        *selected,
        *selection.supplemental_inputs,
        *selection.validation_artifacts,
        *selection.visual_exhibits,
    )
    materials = []
    for item in all_items:
        require(ROLE_CLASSES.get(item.role) == item.source_class, "INVALID_ROLE_CLASS")
        materials.append(SelectedMaterial(_label(item.local_label), item.source_class, item.role))
    require(len({m.local_label for m in materials}) == len(materials))
    windows = []
    for window in model.windows:
        scope = window.scope
        counts = []
        for name in (*COMPONENTS, "source_media_links"):
            row = window.component_counts[name]
            require(type(row["truncated"]) is bool)
            counts.append(
                ComponentCount(
                    name,
                    _technical(row["unit"]),
                    _count(row["total"]),
                    _count(row["returned"]),
                    row["truncated"],
                )
            )
        statuses = window.component_counts["source_media_links"]["status_counts"]
        require(set(statuses) <= SOURCE_MEDIA_STATUSES)
        incidents = []
        for index, event in enumerate(
            by_reference[window.window_id].snapshot["analysis_window"]["incident_window"]["items"]
        ):
            # Map every invalid event display field to the privacy contract code.
            try:
                incident = IncidentRow(
                    _utc(event["occurred_at_utc"]),
                    _technical(event["platform"]),
                    _technical(event["event_kind"]),
                    f"analysis_window.incident_window.items[{index}]",
                )
            except (EvidenceError, KeyError, TypeError, ValueError):
                raise EvidenceError("DOSSIER_PRIVACY_CONTRACT_VIOLATION") from None
            incidents.append(incident)
        windows.append(
            WindowDisplay(
                _technical(window.window_id),
                _utc(scope["start"]),
                _utc(scope["end"]),
                _technical(scope["platform"]) if scope["platform"] is not None else None,
                _technical(scope["event_kind"]) if scope["event_kind"] is not None else None,
                _count(scope["max_delta_seconds"]),
                _count(scope["undated_current_events"]),
                _count(scope["eligible_events"]),
                tuple(counts),
                tuple(_technical(c) for c in window.truncated_components),
                tuple(
                    Measure(k, _count(statuses[k]), "event_source_reference_items")
                    for k in sorted(statuses)
                ),
                tuple(incidents),
            )
        )
    current = model.technical_counts["current_events"]
    events = CurrentEvents(
        _technical(current["policy_id"]),
        _version(current["policy_version"]),
        _technical(current["unit"]),
        _count(current["total"]),
        _count(current["dated"]),
        _count(current["undated"]),
        tuple(
            EventCount(
                _technical(r["platform"]),
                _technical(r["event_kind"]),
                _count(r["total"]),
                _count(r["dated"]),
                _count(r["undated"]),
            )
            for r in current["by_platform_event_kind"]
        ),
    )
    findings = tuple(
        FindingDisplay(
            _technical(f.finding_id),
            _technical(f.candidate_type),
            _technical(f.classification),
            single_line(f.statement),
            _basis(f.candidate_type, f.technical_basis),
            _reference(f.provenance_basis),
            single_line(f.limitations),
        )
        for f in model.findings
    )
    media: list[Measure] = []
    for section, names in (
        (
            "inventory",
            (
                "scanned_occurrences",
                "recognized_media",
                "verified_media",
                "unrecognized_occurrences",
            ),
        ),
        ("contents", ("exact_content_count", "singleton_content_count", "duplicate_content_count")),
        (
            "perceptual",
            ("exact_content_count", "success_count", "failed_count", "unsupported_count"),
        ),
    ):
        row = model.media_summary[section]
        media.extend(
            Measure(f"{section}.{name}", _count(row[name]), _technical(row["unit"]))
            for name in names
        )
    occurrences = model.media_summary["contents"]["occurrences"]
    media.extend(
        Measure(f"occurrences.{name}", _count(occurrences[name]), _technical(occurrences["unit"]))
        for name in ("total", "in_duplicate_contents")
    )
    exact = model.technical_counts["exact_candidates"]
    return HumanDossierProjection(
        identity,
        tuple(
            sorted(
                materials, key=lambda m: (CLASS_ORDER.index(m.source_class), m.role, m.local_label)
            )
        ),
        tuple(
            Measure(
                k,
                _count(model.evidence_scope["tables"][k]),
                _technical(model.evidence_scope["unit"]),
            )
            for k in TABLES
        ),
        _coverage(model.coverage["parser_runs"], "parser", "status"),
        _policies(model.methodology),
        tuple(windows),
        events,
        findings,
        tuple(media),
        ObservationContext(
            _coverage(model.coverage["device_observations"], "observer", "platform"),
            _count(exact["device"]),
            _technical(exact["unit"]),
        ),
        ObservationContext(
            _coverage(model.coverage["network_observations"], "observer", "platform"),
            _count(exact["network"]),
            _technical(exact["unit"]),
        ),
        tuple(single_line(v) for v in model.limitations),
        tuple(
            GapDisplay(
                _technical(g.gap_id),
                _technical(g.category),
                single_line(g.statement),
                single_line(g.technical_basis),
                single_line(g.scope),
                single_line(g.limitation),
            )
            for g in model.gaps
        ),
        tuple(_reference(r) for r in model.technical_reference_map),
        tuple(
            SnapshotDestination(
                ref,
                _label(by_reference[ref].local_label),
                package_paths("report_snapshot", _label(by_reference[ref].local_label))[0],
            )
            for ref in refs
        ),
    )


def project_dossier(
    *, selection: DossierSelection, canonical: ValidatedCanonicalSet
) -> HumanDossierProjection:
    """Copy approved primitives only; preserve canonical F/W/G and row order."""
    try:
        return _project(selection, canonical)
    except (MemoryError, RecursionError):
        raise EvidenceError("DOSSIER_RESOURCE_LIMIT") from None
    except EvidenceError as error:
        if str(error).startswith("DOSSIER_"):
            raise
        code = (
            "PRIVACY_CONTRACT_VIOLATION"
            if str(error) == "REPORT_UNSAFE_DISPLAY_VALUE"
            else "CANONICAL_SET_INVALID"
        )
        raise EvidenceError(f"DOSSIER_{code}") from None
    except (KeyError, TypeError, ValueError, OverflowError):
        raise EvidenceError("DOSSIER_CANONICAL_SET_INVALID") from None
