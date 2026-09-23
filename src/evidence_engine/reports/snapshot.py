"""Deterministic support data under ADR 0031; no narrative or persisted report state."""

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypedDict

from sqlalchemy import Connection, func, select, tuple_

from evidence_engine import __version__
from evidence_engine.correlation.exact import (
    CORRELATOR_ID,
    CORRELATOR_VERSION,
    DEVICE_RULE,
    NETWORK_RULE,
    RULE_VERSION,
)
from evidence_engine.correlation.overlap import TemporalExactOverlapPolicy, overlap_in_snapshot
from evidence_engine.correlation.temporal import (
    TemporalPolicy,
    temporal_bounds,
    temporal_candidates_in_snapshot,
)
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.paths import CasePaths
from evidence_engine.media.contents import project_contents
from evidence_engine.media.inventory import inventory_media
from evidence_engine.media.perceptual import perceptual_hashes
from evidence_engine.media.source_links import POLICY_ID as SOURCE_MEDIA_POLICY_ID
from evidence_engine.media.source_links import POLICY_VERSION as SOURCE_MEDIA_POLICY_VERSION
from evidence_engine.media.source_links import source_links_in_snapshot
from evidence_engine.models.entities import (
    Base,
    Case,
    CorrelationCandidate,
    CorrelationRun,
    CorrelationSupport,
    EvidenceFile,
    NormalizedEvent,
)
from evidence_engine.query.catalog import read_catalog
from evidence_engine.query.incident import incident_window_in_snapshot
from evidence_engine.query.incident_candidates import incident_candidates_in_snapshot
from evidence_engine.query.policy import (
    CURRENT_NORMALIZERS,
    POLICY_ID,
    POLICY_VERSION,
    current_event_predicate,
)
from evidence_engine.query.provenance import record_origin
from evidence_engine.query.search import Projection
from evidence_engine.storage.database import SCHEMA_VERSION

SNAPSHOT_ID = "report.data_snapshot"
SNAPSHOT_VERSION = "1.1.0"
INCIDENT_LIMIT = 500
MATRIX_LIMIT = 100
PAIR_LIMIT = 1000
SOURCE_MEDIA_LIMIT = 1000
LIMITATIONS = (
    "TECHNICAL_CANDIDATES_NOT_SELECTED_FINDINGS",
    "NO_IDENTITY_AUTHORSHIP_SESSION_OR_CAUSALITY",
    "COUNTS_ARE_NOT_EVIDENTIARY_STRENGTH",
    "ABSENCE_LIMITED_TO_QUERIED_CATALOG_POLICIES_AND_SCOPE",
    "COVERAGE_IS_NOT_REAL_WORLD_COMPLETENESS",
    "SOURCE_MEDIA_COVERAGE_LIMITED",
    "NO_MESSAGE_ATTACHMENT_INFERENCE",
    "NO_ATOMIC_DATABASE_FILESYSTEM_SNAPSHOT",
    "SAME_RECORD_CONTEXT_IS_NOT_INDEPENDENT_SUPPORT",
)


@dataclass(frozen=True)
class ReportSnapshot:
    snapshot: Projection
    consistency: Projection
    scope: Projection
    policies: Projection
    inventory: Projection
    coverage: Projection
    current_events: Projection
    exact_candidates: Projection
    media: Projection
    analysis_window: Projection | None
    finding_candidates: Projection
    gap_inputs: Projection
    provenance_index: Projection


class _WindowFilters(TypedDict):
    start_utc: str
    end_utc: str
    platform: str | None
    event_kind: str | None


def _coverage(connection: Connection) -> Projection:
    dimensions = {
        "parser_runs": ("parser_id", "parser_version", "status"),
        "normalization_runs": ("normalizer_id", "normalizer_version", "status"),
        "observation_runs": ("observer_id", "observer_version", "status"),
        "correlation_runs": ("correlator_id", "correlator_version", "status"),
        "correlation_candidates": (
            "correlator_id",
            "correlator_version",
            "rule_id",
            "rule_version",
            "candidate_kind",
        ),
        "normalized_events": ("normalizer_id", "normalizer_version", "platform", "event_kind"),
        "device_observations": ("observer_id", "observer_version", "platform"),
        "network_observations": ("observer_id", "observer_version", "platform"),
    }
    result = {}
    for name, names in dimensions.items():
        table = Base.metadata.tables[name]
        columns = [table.c[n] for n in names]
        rows = connection.execute(
            select(*columns, func.count().label("count")).group_by(*columns).order_by(*columns)
        ).mappings()
        result[name] = {"unit": "physical_rows", "items": [dict(row) for row in rows]}
    return result


def _current_events(connection: Connection) -> Projection:
    rows = (
        connection.execute(
            select(
                NormalizedEvent.platform,
                NormalizedEvent.event_kind,
                func.count().label("total"),
                func.count(NormalizedEvent.occurred_at_utc).label("dated"),
            )
            .where(current_event_predicate())
            .group_by(NormalizedEvent.platform, NormalizedEvent.event_kind)
            .order_by(NormalizedEvent.platform, NormalizedEvent.event_kind)
        )
        .mappings()
        .all()
    )
    groups = [dict(row) | {"undated": row["total"] - row["dated"]} for row in rows]
    total, dated = sum(r["total"] for r in rows), sum(r["dated"] for r in rows)
    return {
        "unit": "current_events",
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "total": total,
        "dated": dated,
        "undated": total - dated,
        "by_platform_event_kind": groups,
    }


def _exact_summary(connection: Connection) -> Projection:
    c, r = CorrelationCandidate, CorrelationRun
    eligible = (
        select(c.id)
        .join(r, c.correlation_run_id == r.id)
        .where(
            c.correlator_id == CORRELATOR_ID,
            c.correlator_version == CORRELATOR_VERSION,
            c.rule_version == RULE_VERSION,
            tuple_(c.candidate_kind, c.rule_id).in_(
                (("device", DEVICE_RULE), ("network", NETWORK_RULE))
            ),
            r.status == "COMPLETED",
            r.case_id == c.case_id,
            r.correlator_id == c.correlator_id,
            r.correlator_version == c.correlator_version,
        )
    )
    rows = connection.execute(
        select(c.candidate_kind, func.count(), func.sum(c.support_count))
        .where(c.id.in_(eligible))
        .group_by(c.candidate_kind)
    ).all()
    counts = {kind: count for kind, count, _ in rows}
    supports = connection.scalar(
        select(func.count())
        .select_from(CorrelationSupport)
        .where(CorrelationSupport.candidate_id.in_(eligible))
    )
    if supports != sum(total for _, _, total in rows):
        raise EvidenceError("REPORT_CANDIDATE_SUPPORT_COUNT_MISMATCH")
    return {
        "unit": "eligible_persisted_candidates",
        "total": sum(counts.values()),
        "device": counts.get("device", 0),
        "network": counts.get("network", 0),
        "supports": {"unit": "persisted_support_rows", "total": supports},
        "eligibility": "exact_policy_versions_with_matching_completed_run",
    }


def _media(case_root: Path) -> Projection:
    inventory = inventory_media(case_root)
    contents = project_contents(inventory.items)
    perceptual = perceptual_hashes(case_root)
    # Separate verified reads can observe change: fail on differing content/occurrence sets.
    expected = [(c.content_sha256, c.size_bytes, c.occurrences) for c in contents.contents]
    actual = [(c.content_sha256, c.size_bytes, c.occurrences) for c in perceptual.items]
    if expected != actual:
        raise EvidenceError("REPORT_MEDIA_COMPONENTS_CHANGED")
    duplicates = []
    for content in contents.contents:
        if content.occurrence_count < 2:
            continue
        duplicates.append(
            {
                "content_sha256": content.content_sha256,
                "media_kind": content.media_kind,
                "media_format": content.media_format,
                "size_bytes": content.size_bytes,
                "occurrence_count": content.occurrence_count,
                "occurrences": [
                    {
                        "source_kind": o.source_kind,
                        "evidence_file_id": o.evidence_file_id,
                        "archive_member_id": o.archive_member_id,
                    }
                    for o in content.occurrences
                ],
            }
        )
    statuses = Counter((i.status, i.media_format) for i in perceptual.items)
    return {
        "inventory": {
            "unit": "cataloged_occurrences",
            **{
                name: getattr(inventory, name)
                for name in (
                    "scanned_occurrences",
                    "recognized_media",
                    "verified_media",
                    "unrecognized_occurrences",
                    "format_counts",
                    "kind_counts",
                )
            },
        },
        "contents": {
            "unit": "exact_contents",
            **{
                name: getattr(contents, name)
                for name in (
                    "exact_content_count",
                    "singleton_content_count",
                    "duplicate_content_count",
                    "format_counts_by_content",
                    "kind_counts_by_content",
                )
            },
            "occurrences": {
                "unit": "verified_media_occurrences",
                "total": contents.verified_media_occurrences,
                "in_duplicate_contents": contents.occurrences_in_duplicate_contents,
            },
            "duplicates": {
                "unit": "exact_contents",
                "total": len(duplicates),
                "returned": len(duplicates),
                "truncated": False,
                "items": duplicates,
            },
        },
        "perceptual": {
            "unit": "exact_contents",
            "policy": asdict(perceptual.policy),
            **{
                name: getattr(perceptual, name)
                for name in (
                    "exact_content_count",
                    "success_count",
                    "failed_count",
                    "unsupported_count",
                )
            },
            "by_status_format": [
                {"status": status, "media_format": fmt, "count": count}
                for (status, fmt), count in sorted(statuses.items())
            ],
        },
    }


def _window(
    connection: Connection,
    *,
    paths: CasePaths,
    start_utc: str,
    end_utc: str,
    max_delta_seconds: int,
    platform: str | None,
    event_kind: str | None,
) -> Projection:
    scope = _WindowFilters(
        start_utc=start_utc, end_utc=end_utc, platform=platform, event_kind=event_kind
    )
    incident = incident_window_in_snapshot(connection, **scope, limit=INCIDENT_LIMIT)
    # record origins are emitted once in the typed provenance index.
    for item in incident["items"]:
        item.pop("provenance")
    matrix = incident_candidates_in_snapshot(
        connection, **scope, candidate_kind=None, limit=MATRIX_LIMIT
    )
    temporal = temporal_candidates_in_snapshot(
        connection, **scope, max_delta_seconds=max_delta_seconds, limit=PAIR_LIMIT
    )
    overlap = overlap_in_snapshot(connection, temporal)
    return {
        "window": asdict(temporal.window),
        "max_delta_seconds": max_delta_seconds,
        "incident_window": incident,
        "incident_candidates": matrix,
        "temporal_proximity": asdict(temporal),
        "temporal_exact_overlap": asdict(overlap),
        "source_media_links": _source_media_projection(
            source_links_in_snapshot(paths, connection, **scope, limit=SOURCE_MEDIA_LIMIT)
        ),
    }


def _source_media_projection(result: Projection) -> Projection:
    """Explicit report allowlist; source URI/path/payload never enters the snapshot."""
    items = []
    for item in result["items"]:
        reference = item["source_reference"]
        resolution = item["resolution"]
        projected = {
            key: resolution[key]
            for key in (
                "classification",
                "status",
                "archive_member_id",
                "evidence_file_id",
                "size_bytes",
                "archive_member_sha256",
                "bytes_verified",
            )
            if key in resolution
        }
        if "exact_media_content" in resolution:
            content = resolution["exact_media_content"]
            projected["exact_media_content"] = (
                {
                    key: content[key]
                    for key in (
                        "content_sha256",
                        "size_bytes",
                        "media_kind",
                        "media_format",
                        "occurrence_count",
                    )
                }
                if content is not None
                else None
            )
        items.append(
            {
                "event": item["event"],
                "source_reference": {
                    key: reference[key]
                    for key in (
                        "parsed_record_id",
                        "platform",
                        "parser_id",
                        "parser_version",
                        "source_field_locator",
                        "classification",
                    )
                }
                if reference is not None
                else None,
                "resolution": projected,
                "limitations": item["limitations"],
            }
        )
    return {key: result[key] for key in ("policy", "scope", "consistency", "summary")} | {
        "items": items
    }


def _source_media_index(window: Projection | None) -> list[Projection]:
    if window is None:
        return []
    return [
        {
            "pointer": f"analysis_window.source_media_links.items[{i}]",
            "parsed_record_id": item["event"]["parsed_record_id"],
            "archive_member_id": item["resolution"].get("archive_member_id"),
            "evidence_file_id": item["resolution"].get("evidence_file_id"),
        }
        for i, item in enumerate(window["source_media_links"]["items"])
    ]


def _record_references(window: Projection | None) -> set[str]:
    if window is None:
        return set()
    records = {e["parsed_record_id"] for e in window["incident_window"]["items"]}
    records.update(
        e["parsed_record_id"] for c in window["incident_candidates"]["items"] for e in c["events"]
    )
    records.update(
        e["parsed_record_id"]
        for p in window["temporal_proximity"]["items"]
        for e in (p["event_a"], p["event_b"])
    )
    records.update(i["event"]["parsed_record_id"] for i in window["source_media_links"]["items"])
    return records


def _findings(media: Projection, window: Projection | None) -> Projection:
    def section(items: list[Projection], total: int) -> Projection:
        return {
            "unit": "candidate_projections",
            "total": total,
            "returned": len(items),
            "truncated": total > len(items),
            "items": items,
        }

    def finding(kind: str, basis: Projection, references: Projection) -> Projection:
        return {
            "candidate_type": kind,
            "classification": "DERIVED",
            "technical_basis": basis,
            "references": references,
            "limitations_ref": "global_limitations",
        }

    duplicates = media["contents"]["duplicates"]
    result = {
        "global_limitations": list(LIMITATIONS),
        "exact_media_duplicate": section(
            [
                finding(
                    "exact_media_duplicate",
                    {
                        "relation": "verified_size_sha256_equality",
                        "projection_policy_id": SNAPSHOT_ID,
                        "projection_policy_version": SNAPSHOT_VERSION,
                    },
                    {"content_sha256": c["content_sha256"], "occurrences": c["occurrences"]},
                )
                for c in duplicates["items"]
            ],
            duplicates["total"],
        ),
    }
    if window is None:
        return result
    matrix = window["incident_candidates"]
    result["window_exact_candidate"] = section(
        [
            finding(
                "window_exact_candidate",
                {
                    k: c[k]
                    for k in ("correlator_id", "correlator_version", "rule_id", "rule_version")
                },
                {
                    "candidate_kind": c["candidate_kind"],
                    "candidate_id": c["candidate_id"],
                    "event_ids": [e["event_id"] for e in c["events"]],
                },
            )
            for c in matrix["items"]
        ],
        matrix["matched_candidates"],
    )
    for component, kind in (
        ("temporal_proximity", "temporal_pair_candidate"),
        ("temporal_exact_overlap", "temporal_exact_overlap_candidate"),
    ):
        source = window[component]
        items = []
        for pair in source["items"]:
            references = {
                "event_a_id": pair["event_a"]["event_id"],
                "event_b_id": pair["event_b"]["event_id"],
                "delta_microseconds": pair["delta_microseconds"],
            }
            if component == "temporal_exact_overlap":
                references.update(
                    same_parsed_record=pair["same_parsed_record"],
                    shared_exact_candidates=pair["shared_exact_candidates"],
                )
            items.append(finding(kind, source["policy"], references))
        result[kind] = section(items, source["matched_pairs"])
    source = window["source_media_links"]
    positive = {"LINK_EXACT_MEDIA_CONTENT", "LINK_ARCHIVE_MEMBER_ONLY"}
    result["source_media_provenance_link"] = section(
        [
            finding(
                "source_media_provenance_link",
                source["policy"],
                {"source_media_item_index": i, "event_id": item["event"]["event_id"]},
            )
            for i, item in enumerate(source["items"])
            if item["resolution"]["status"] in positive
        ],
        sum(source["summary"]["status_counts"].get(status, 0) for status in positive),
    )
    return result


def report_snapshot(
    case_root: Path,
    *,
    start: str | None = None,
    end: str | None = None,
    max_delta_seconds: int | None = None,
    platform: str | None = None,
    event_kind: str | None = None,
) -> ReportSnapshot:
    """Read support data, with zero or one validated analytical window, without writes."""
    supplied = (start is not None, end is not None, max_delta_seconds is not None)
    if any(supplied) and not all(supplied):
        raise EvidenceError("Report window requires start, end and max_delta_seconds together")
    if not all(supplied) and (platform is not None or event_kind is not None):
        raise EvidenceError("Report platform/event_kind filters require a complete window")
    bounds = None
    if start is not None and end is not None and max_delta_seconds is not None:
        bounds = temporal_bounds(start, end, max_delta_seconds, PAIR_LIMIT)
    with read_catalog(case_root) as connection:
        case_id = connection.execute(select(Case.id)).scalar_one()
        inventory = {
            "unit": "physical_rows",
            "tables": {
                name: connection.execute(select(func.count()).select_from(table)).scalar_one()
                for name, table in sorted(Base.metadata.tables.items())
            },
        }
        coverage = _coverage(connection)
        current = _current_events(connection)
        exact = _exact_summary(connection)
        window = None
        if bounds is not None:
            assert max_delta_seconds is not None
            window = _window(
                connection,
                paths=CasePaths.load(case_root),
                start_utc=bounds[0],
                end_utc=bounds[1],
                max_delta_seconds=max_delta_seconds,
                platform=platform,
                event_kind=event_kind,
            )
        origins = {}
        for record_id in sorted(_record_references(window)):
            origin = record_origin(connection, record_id)
            origins[record_id] = {
                k: v
                for k, v in origin.items()
                if k not in {"evidence_relative_path", "member_path"}
            }
            origins[record_id]["classification"] = "OBSERVED"
        evidence = {
            row.id: {"cataloged_sha256": row.sha256}
            for row in connection.execute(
                select(EvidenceFile.id, EvidenceFile.sha256).order_by(EvidenceFile.id)
            )
        }
    media = _media(case_root)
    temporal_policy = asdict(TemporalPolicy(max_delta_seconds or 1))
    overlap_policy = asdict(TemporalExactOverlapPolicy(max_delta_seconds or 1))
    # A retrieval radius is an execution input, not a default implied for a missing window.
    temporal_policy.pop("max_delta_seconds")
    overlap_policy.pop("max_delta_seconds")
    executed = [
        "inventory",
        "coverage",
        "current_events",
        "exact_candidates",
        "media_inventory",
        "media_contents",
        "perceptual_hash",
    ]
    if window is not None:
        executed.extend(
            (
                "incident_window",
                "incident_candidates",
                "temporal_proximity",
                "temporal_exact_overlap",
                "source_media_links",
            )
        )
    truncated = (
        []
        if window is None
        else sorted(
            name
            for name in (
                "incident_window",
                "incident_candidates",
                "temporal_proximity",
                "temporal_exact_overlap",
            )
            if window[name]["truncated"]
        )
    )
    parser_gaps = {
        status: sum(
            row["count"] for row in coverage["parser_runs"]["items"] if row["status"] == status
        )
        for status in ("UNSUPPORTED", "FAILED")
    }
    if window is not None and window["source_media_links"]["summary"]["truncated"]:
        truncated = sorted([*truncated, "source_media_links"])
    return ReportSnapshot(
        snapshot={
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_version": SNAPSHOT_VERSION,
            "feature_class": "DERIVED",
            "evidence_schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "engine_version": __version__,
        },
        consistency={
            "database_consistency": "single_read_snapshot",
            "database_scope": "direct_db_components_and_provenance_index",
            "media_consistency": "verified_read_only_components",
            "media_catalogs": "separate_read_snapshots",
            "atomic_database_filesystem": False,
        },
        scope={
            "case_wide_summaries": True,
            "executed_components": executed,
            "limits": {
                "incident_events": INCIDENT_LIMIT,
                "matrix_candidates": MATRIX_LIMIT,
                "temporal_pairs": PAIR_LIMIT,
                "overlap_pairs": PAIR_LIMIT,
                "source_media_items": SOURCE_MEDIA_LIMIT,
            },
            "underlying_classifications": {
                "parsed_records": "OBSERVED",
                "normalized_events": "DERIVED",
            },
        },
        policies={
            "availability": "known_policies_not_execution_claims",
            "current_event_policy": {"policy_id": POLICY_ID, "policy_version": POLICY_VERSION},
            "eligible_normalizers": [
                {"normalizer_id": n, "normalizer_version": v} for n, v in CURRENT_NORMALIZERS
            ],
            "observers": [
                {"observer_id": f"{k}.observer", "observer_version": "1.0.0"}
                for k in ("device", "network")
            ],
            "exact_correlator": {
                "correlator_id": CORRELATOR_ID,
                "correlator_version": CORRELATOR_VERSION,
            },
            "exact_rules": [
                {"rule_id": r, "rule_version": RULE_VERSION} for r in (DEVICE_RULE, NETWORK_RULE)
            ],
            "perceptual_hash": media["perceptual"]["policy"],
            "temporal_proximity": temporal_policy,
            "temporal_exact_overlap": overlap_policy,
            "source_media_links": {
                "policy_id": SOURCE_MEDIA_POLICY_ID,
                "policy_version": SOURCE_MEDIA_POLICY_VERSION,
            },
        },
        inventory=inventory,
        coverage=coverage,
        current_events=current,
        exact_candidates=exact,
        media=media,
        analysis_window=window,
        finding_candidates=_findings(media, window),
        gap_inputs={
            "parser_runs": {"unit": "physical_rows", **parser_gaps},
            "undated_current_events": {"unit": "current_events", "count": current["undated"]},
            "unrecognized_media": {
                "unit": "cataloged_occurrences",
                "count": media["inventory"]["unrecognized_occurrences"],
            },
            "perceptual_status_counts": {
                "unit": "exact_contents",
                "failed": media["perceptual"]["failed_count"],
                "unsupported": media["perceptual"]["unsupported_count"],
            },
            "truncated_components": truncated,
            "whatsapp_parser_available": False,
            "known_capability_limits": list(LIMITATIONS),
        },
        provenance_index={
            "parsed_records": origins,
            "evidence_files": evidence,
            "source_media_links": _source_media_index(window),
        },
    )
