"""Snapshot-only validation, consolidation and deterministic pt-BR Markdown (ADR 0033)."""

import json
import re
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from evidence_engine.errors import EvidenceError

type Object = dict[str, Any]

REPORT_ID = "report.consolidated"
REPORT_VERSION = "1.1.0"
MAX_SNAPSHOTS = 20
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
TITLE = "Relatório Técnico Consolidado de Análise e Organização de Evidências Digitais"
SECTIONS = (
    "Identificação do documento",
    "Objetivo e escopo",
    "Natureza e limitações do trabalho",
    "Materiais/evidências analisados",
    "Metodologia técnica",
    "Preservação, integridade e provenance",
    "Fontes e cobertura de parsing",
    "Normalização temporal",
    "Observações técnicas de dispositivo",
    "Observações técnicas de rede",
    "Candidates por igualdade exata",
    "Timeline e janelas relevantes",
    "Temporal Proximity Candidates",
    "Temporal + Exact Signal Overlap",
    "Análise técnica de mídia",
    "Achados técnicos consolidados",
    "Limitações e afirmações não estabelecidas",
    "Lacunas de evidência",
    "Próximas análises/aquisições recomendadas",
    "Apêndice técnico / mapa de provenance",
)
CASE_WIDE = ("policies", "inventory", "coverage", "current_events", "exact_candidates", "media")
GAP_FIELDS = (
    "parser_runs",
    "undated_current_events",
    "unrecognized_media",
    "perceptual_status_counts",
    "whatsapp_parser_available",
    "known_capability_limits",
)
WINDOW_TYPES = (
    "window_exact_candidate",
    "temporal_pair_candidate",
    "temporal_exact_overlap_candidate",
)
COMPONENTS = (
    "incident_window",
    "incident_candidates",
    "temporal_proximity",
    "temporal_exact_overlap",
)
COVERAGE = {
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
TABLES = (
    "cases",
    "evidence_files",
    "archive_members",
    "source_records",
    "parsed_records",
    "ingestion_runs",
    "parser_runs",
    "normalization_runs",
    "normalized_events",
    "observation_runs",
    "device_observations",
    "network_observations",
    "correlation_runs",
    "correlation_candidates",
    "correlation_supports",
)
LIMITATION = (
    "A inclusão decorre dos snapshots escolhidos pelo operador e do prefixo técnico retornado. "
    "Não estabelece identidade, autoria humana, sessão, causalidade ou conclusão jurídica."
)
SOURCE_MEDIA_POSITIVE = {"LINK_EXACT_MEDIA_CONTENT", "LINK_ARCHIVE_MEMBER_ONLY"}
SOURCE_MEDIA_STATUSES = SOURCE_MEDIA_POSITIVE | {
    "NO_CATALOG_MEMBER_MATCH",
    "NO_SOURCE_MEDIA_REFERENCE",
    "UNSUPPORTED_SOURCE_REFERENCE_TYPE",
}
SOURCE_MEDIA_LIMITATION = (
    "Cobertura estreita do adapter/policy atual, sem generalização para todo evento/mídia. "
    "Source-media provenance link não resolve communication.message attachments: "
    "SOURCE_LIMITATION. "
    "Ausência fora da cobertura não prova inexistência de mídia. "
    "Occurrence count representa ocorrências catalogadas do mesmo conteúdo exato; "
    "não número de envios, publicações, destinatários ou ações humanas. "
    "Duplicatas entre exports não demonstram disseminação. "
    "O vínculo não estabelece publicação, upload, envio ou exclusão. "
    "O raio temporal não participa da consulta source-media. "
    "WhatsApp permanece condicional/não acionado."
)
SOURCE_MEDIA_PARTIAL = (
    "Há vínculo source-media aprovado nas referências cobertas pela policy dos snapshots "
    "fornecidos; a cobertura de source-media linkage permanece parcial."
)
SOURCE_MEDIA_ABSENT = (
    "Nenhum link source-media aplicável foi retornado no conjunto de snapshots fornecidos; "
    "isso não afirma ausência global da capacidade no motor."
)


def _require(condition: bool, code: str = "REPORT_INVALID_SNAPSHOT") -> None:
    if not condition:
        raise EvidenceError(code)


def _object(value: Any, fields: dict[str, type] | None = None) -> Object:
    _require(type(value) is dict)
    result: Object = value
    for name, kind in (fields or {}).items():
        _require(name in result and type(result[name]) is kind)
    return result


def _count(value: Any) -> int:
    _require(type(value) is int and value >= 0)
    return int(value)


def _counts(value: Any, unit: str, names: Sequence[str]) -> Object:
    result = _object(value, {"unit": str})
    _require(result["unit"] == unit)
    for name in names:
        _count(result.get(name))
    return result


def _strings(value: Any) -> list[str]:
    _require(type(value) is list and all(type(v) is str for v in value))
    return list(value)


def _technical(value: Any) -> str:
    # Display only bounded technical labels, never arbitrary strings, paths or markup.
    _require(
        type(value) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,95}", value) is not None,
        "REPORT_UNSAFE_DISPLAY_VALUE",
    )
    _require(
        re.search(r"[0-9a-fA-F]{16,}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-", value) is None,
        "REPORT_UNSAFE_DISPLAY_VALUE",
    )
    return str(value)


def _version(value: Any) -> str:
    _require(type(value) is str and re.fullmatch(r"\d{1,4}\.\d{1,4}\.\d{1,4}", value) is not None)
    return str(value)


def _utc(value: Any) -> str:
    _require(
        type(value) is str
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value) is not None
    )
    try:
        return (
            datetime.fromisoformat(value).isoformat(timespec="microseconds").replace("+00:00", "Z")
        )
    except ValueError:
        raise EvidenceError("REPORT_INVALID_SNAPSHOT") from None


def _prefix(value: Any, total: str = "total", returned: str = "returned") -> Object:
    result = _object(value, {"items": list, "truncated": bool})
    n, r = _count(result.get(total)), _count(result.get(returned))
    _require(n >= r == len(result["items"]) and result["truncated"] == (n > r))
    for item in result["items"]:
        _object(item)
    return result


def _distribution(value: Any) -> Object:
    result = _object(value)
    for key, count in result.items():
        _technical(key)
        _count(count)
    return result


def _policy(value: Any, id_field: str, version_field: str) -> Object:
    result = _object(value, {id_field: str, version_field: str})
    _technical(result[id_field])
    _version(result[version_field])
    return result


def _policies(value: Any) -> None:
    p = _object(
        value,
        {"availability": str, "eligible_normalizers": list, "observers": list, "exact_rules": list},
    )
    _require(p["availability"] == "known_policies_not_execution_claims")
    _policy(p.get("current_event_policy"), "policy_id", "policy_version")
    _policy(p.get("exact_correlator"), "correlator_id", "correlator_version")
    for key, prefix in (
        ("eligible_normalizers", "normalizer"),
        ("observers", "observer"),
        ("exact_rules", "rule"),
    ):
        for row in p[key]:
            _policy(row, prefix + "_id", prefix + "_version")
    for key in ("temporal_proximity", "temporal_exact_overlap"):
        _policy(p.get(key), "policy_id", "policy_version")
    _policy(p.get("perceptual_hash"), "algorithm_id", "algorithm_version")


def _media(value: Any) -> None:
    m = _object(value, {"inventory": dict, "contents": dict, "perceptual": dict})
    inv = _counts(
        m["inventory"],
        "cataloged_occurrences",
        ("scanned_occurrences", "recognized_media", "verified_media", "unrecognized_occurrences"),
    )
    for name in ("format_counts", "kind_counts"):
        _distribution(inv.get(name))
    _require(
        inv["scanned_occurrences"] == inv["recognized_media"] + inv["unrecognized_occurrences"]
    )
    _require(inv["recognized_media"] == inv["verified_media"])
    c = _counts(
        m["contents"],
        "exact_contents",
        ("exact_content_count", "singleton_content_count", "duplicate_content_count"),
    )
    _require(
        c["exact_content_count"] == c["singleton_content_count"] + c["duplicate_content_count"]
    )
    for name in ("format_counts_by_content", "kind_counts_by_content"):
        _require(sum(_distribution(c.get(name)).values()) == c["exact_content_count"])
    occurrences = _counts(
        c.get("occurrences"), "verified_media_occurrences", ("total", "in_duplicate_contents")
    )
    _require(occurrences["total"] == inv["verified_media"])
    duplicates = _prefix(c.get("duplicates"))
    _require(duplicates.get("unit") == "exact_contents" and not duplicates["truncated"])
    _require(duplicates["total"] == c["duplicate_content_count"])
    for item in duplicates["items"]:
        _object(
            item,
            {"content_sha256": str, "occurrences": list, "media_kind": str, "media_format": str},
        )
        _count(item.get("size_bytes"))
        _require(_count(item.get("occurrence_count")) == len(item["occurrences"]) >= 2)
        for occurrence in item["occurrences"]:
            _object(occurrence, {"source_kind": str, "evidence_file_id": str})
            _require(
                "archive_member_id" in occurrence
                and (
                    occurrence["archive_member_id"] is None
                    or type(occurrence["archive_member_id"]) is str
                )
            )
    p = _counts(
        m["perceptual"],
        "exact_contents",
        ("exact_content_count", "success_count", "failed_count", "unsupported_count"),
    )
    _require(
        p["exact_content_count"]
        == c["exact_content_count"]
        == p["success_count"] + p["failed_count"] + p["unsupported_count"]
    )
    _policy(p.get("policy"), "algorithm_id", "algorithm_version")
    _object(p, {"by_status_format": list})
    for row in p["by_status_format"]:
        _object(row, {"status": str, "media_format": str})
        _require(row["status"] in {"SUCCESS", "FAILED", "UNSUPPORTED"})
        _technical(row["media_format"])
        _count(row.get("count"))


def _event(value: Any, origins: Object) -> None:
    e = _object(
        value,
        {
            "event_id": str,
            "parsed_record_id": str,
            "occurred_at_utc": str,
            "platform": str,
            "event_kind": str,
        },
    )
    _utc(e["occurred_at_utc"])
    _require(e["parsed_record_id"] in origins)


def _window(value: Any, origins: Object) -> tuple[str, str, bool, str, bool, str, int]:
    w = _object(value, {name: dict for name in ("window", *COMPONENTS)})
    bounds = _object(w["window"], {"start": str, "end": str})
    start, end = _utc(bounds["start"]), _utc(bounds["end"])
    radius = _count(w.get("max_delta_seconds"))
    _require(start < end and 1 <= radius <= 86400)
    for field in ("platform", "event_kind"):
        _require(field in bounds)
        if bounds[field] is not None:
            _technical(bounds[field])
    incident = _prefix(w["incident_window"], "matched_total")
    _policy(incident, "policy_id", "policy_version")
    _count(incident.get("undated_current_events"))
    for item in incident["items"]:
        _event(item, origins)
        _object(item, {"device_context": list, "network_context": list})
    matrix = _prefix(w["incident_candidates"], "matched_candidates", "returned_candidates")
    _policy(matrix, "policy_id", "policy_version")
    for item in matrix["items"]:
        _object(item, {"candidate_id": str, "candidate_kind": str, "events": list})
        _require(item["candidate_kind"] in {"device", "network"})
        _policy(item, "correlator_id", "correlator_version")
        _policy(item, "rule_id", "rule_version")
        for name in ("candidate_support_count", "window_event_count", "window_support_occurrences"):
            _count(item.get(name))
        _require(item["window_event_count"] == len(item["events"]))
        for e in item["events"]:
            _event(e, origins)
            _object(e, {"observation_links": list})
    for name in ("temporal_proximity", "temporal_exact_overlap"):
        component = _prefix(w[name], "matched_pairs", "returned_pairs")
        _count(component.get("eligible_events"))
        policy = _policy(component.get("policy"), "policy_id", "policy_version")
        _require(
            policy.get("max_delta_seconds") == radius
            and type(policy.get("max_delta_seconds")) is int
        )
        _require(component.get("window") == bounds)
        for pair in component["items"]:
            _event(pair.get("event_a"), origins)
            _event(pair.get("event_b"), origins)
            _count(pair.get("delta_microseconds"))
            if name == "temporal_exact_overlap":
                _object(pair, {"same_parsed_record": bool, "shared_exact_candidates": dict})
                shared = pair["shared_exact_candidates"]
                for kind in ("device", "network"):
                    _strings(shared.get(kind + "_candidate_ids"))
    a, b = w["temporal_proximity"], w["temporal_exact_overlap"]
    for key in ("eligible_events", "matched_pairs", "returned_pairs", "truncated"):
        _require(a[key] == b[key])
    for pair, overlap in zip(a["items"], b["items"], strict=True):
        _require(all(pair[k] == overlap[k] for k in ("event_a", "event_b", "delta_microseconds")))
    return (
        start,
        end,
        bounds["platform"] is not None,
        bounds["platform"] or "",
        bounds["event_kind"] is not None,
        bounds["event_kind"] or "",
        radius,
    )


def _findings(s: Object) -> None:
    findings = _object(s["finding_candidates"], {"global_limitations": list})
    _strings(findings["global_limitations"])
    kinds = ("exact_media_duplicate",) + (WINDOW_TYPES if s["analysis_window"] is not None else ())
    extra = (
        {"source_media_provenance_link"}
        if s["snapshot"]["snapshot_version"] == "1.1.0" and s["analysis_window"] is not None
        else set()
    )
    _require(set(findings) == {"global_limitations", *kinds, *extra})
    for kind in kinds:
        section = _prefix(findings.get(kind))
        _require(section.get("unit") == "candidate_projections")
        if kind == "exact_media_duplicate":
            source = s["media"]["contents"]["duplicates"]
            total, returned = "total", "returned"
        elif kind == "window_exact_candidate":
            source = s["analysis_window"]["incident_candidates"]
            total, returned = "matched_candidates", "returned_candidates"
        else:
            name = (
                "temporal_proximity"
                if kind == "temporal_pair_candidate"
                else "temporal_exact_overlap"
            )
            source = s["analysis_window"][name]
            total, returned = "matched_pairs", "returned_pairs"
        _require(
            section["total"] == source[total]
            and section["returned"] == source[returned]
            and section["truncated"] == source["truncated"]
        )
        for finding, item in zip(section["items"], source["items"], strict=True):
            _object(finding, {"technical_basis": dict, "references": dict})
            _require(
                finding.get("candidate_type") == kind
                and finding.get("classification") == "DERIVED"
                and finding.get("limitations_ref") == "global_limitations"
            )
            if kind == "exact_media_duplicate":
                expected = {k: item[k] for k in ("content_sha256", "occurrences")}
                basis = {
                    "relation": "verified_size_sha256_equality",
                    "projection_policy_id": "report.data_snapshot",
                    "projection_policy_version": s["snapshot"]["snapshot_version"],
                }
            elif kind == "window_exact_candidate":
                expected = {
                    "candidate_kind": item["candidate_kind"],
                    "candidate_id": item["candidate_id"],
                    "event_ids": [e["event_id"] for e in item["events"]],
                }
                basis = {
                    k: item[k]
                    for k in ("correlator_id", "correlator_version", "rule_id", "rule_version")
                }
            else:
                expected = {
                    "event_a_id": item["event_a"]["event_id"],
                    "event_b_id": item["event_b"]["event_id"],
                    "delta_microseconds": item["delta_microseconds"],
                }
                if kind == "temporal_exact_overlap_candidate":
                    expected.update(
                        same_parsed_record=item["same_parsed_record"],
                        shared_exact_candidates=item["shared_exact_candidates"],
                    )
                basis = source["policy"]
            _require(finding["references"] == expected and finding["technical_basis"] == basis)


def _source_media(s: Object) -> None:
    """Validate the 1.1 report projection without importing evidence/query services."""
    policy = {"policy_id": "source_media.provenance_link", "policy_version": "1.0.0"}
    _require(s["policies"].get("source_media_links") == policy)
    limit = _count(s["scope"]["limits"].get("source_media_items"))
    _require(1 <= limit <= 5000)
    index = s["provenance_index"]
    _require(type(index.get("source_media_links")) is list)
    window = s["analysis_window"]
    executed = "source_media_links" in s["scope"]["executed_components"]
    if window is None:
        _require(not executed and index["source_media_links"] == [])
        return
    _require(executed)
    links = _object(
        window.get("source_media_links"),
        {
            "policy": dict,
            "scope": dict,
            "consistency": dict,
            "summary": dict,
            "items": list,
        },
    )
    _require(set(links) == {"policy", "scope", "consistency", "summary", "items"})
    _require(
        links["policy"]
        == policy
        | {
            "feature_class": "DERIVED",
            "relation_kind": "source_media.exact_provenance_link",
            "current_event_policy_id": s["policies"]["current_event_policy"]["policy_id"],
            "current_event_policy_version": s["policies"]["current_event_policy"]["policy_version"],
        }
    )
    _require(links["scope"] == window["window"] | {"limit": limit})
    consistency = _object(links["consistency"], {"exact_media_contents_consulted": bool})
    _require(
        consistency
        == {
            "database_consistency": "single_read_snapshot",
            "database_scope": "events_references_provenance_members_and_media_inventory",
            "filesystem_consistency": "verified_stable_reads",
            "atomic_database_filesystem": False,
            "exact_media_contents_consulted": consistency["exact_media_contents_consulted"],
        }
    )
    summary = _prefix(links["summary"] | {"items": links["items"]}, "matched_total")
    _require(summary.get("unit") == "event_source_reference_items")
    _require(summary.get("status_counts_scope") == "all_matched_items")
    counts = _distribution(summary.get("status_counts"))
    _require(
        set(counts) <= SOURCE_MEDIA_STATUSES and sum(counts.values()) == summary["matched_total"]
    )
    _require(summary["returned"] == min(limit, summary["matched_total"]))
    eligible = _count(summary.get("eligible_events"))
    references = _count(summary.get("source_references"))
    _require(eligible <= summary["matched_total"] and references <= summary["matched_total"])
    _require(
        references
        == sum(
            n
            for k, n in counts.items()
            if k not in {"NO_SOURCE_MEDIA_REFERENCE", "UNSUPPORTED_SOURCE_REFERENCE_TYPE"}
        )
    )
    _count(summary.get("undated_current_events"))
    _require(
        consistency["exact_media_contents_consulted"]
        == bool(sum(counts.get(k, 0) for k in SOURCE_MEDIA_POSITIVE))
    )
    expected_index: list[Object] = []
    positives: list[Object] = []
    observed: dict[str, int] = {}
    for position, item in enumerate(links["items"]):
        _require(set(item) == {"event", "source_reference", "resolution", "limitations"})
        event = item["event"]
        _event(event, index["parsed_records"])
        _technical(event["platform"])
        _technical(event["event_kind"])
        bounds = window["window"]
        _require(_utc(bounds["start"]) <= _utc(event["occurred_at_utc"]) < _utc(bounds["end"]))
        _require(
            all(bounds[k] is None or bounds[k] == event[k] for k in ("platform", "event_kind"))
        )
        reference = item["source_reference"]
        resolution = _object(item["resolution"], {"classification": str, "status": str})
        status = resolution["status"]
        _require(resolution["classification"] == "DERIVED" and status in SOURCE_MEDIA_STATUSES)
        observed[status] = observed.get(status, 0) + 1
        has_reference = status not in {
            "NO_SOURCE_MEDIA_REFERENCE",
            "UNSUPPORTED_SOURCE_REFERENCE_TYPE",
        }
        _require((reference is not None) == has_reference)
        if has_reference:
            _object(
                reference,
                {
                    key: str
                    for key in (
                        "classification",
                        "parsed_record_id",
                        "platform",
                        "parser_id",
                        "parser_version",
                        "source_field_locator",
                    )
                },
            )
            _require(
                set(reference)
                == {
                    "classification",
                    "parsed_record_id",
                    "platform",
                    "parser_id",
                    "parser_version",
                    "source_field_locator",
                }
            )
            _require(
                reference["classification"] == "OBSERVED"
                and reference["parsed_record_id"] == event["parsed_record_id"]
            )
            _require(reference["platform"] == event["platform"] == "meta")
            _require(
                (reference["parser_id"], reference["parser_version"])
                == ("meta.recently_deleted_content", "1.1.0")
            )
            _require(
                re.fullmatch(
                    r"\$/\d+/label_values/\d+/media/\d+/uri", reference["source_field_locator"]
                )
                is not None
            )
        if status in SOURCE_MEDIA_POSITIVE:
            _require(
                set(resolution)
                == {
                    "classification",
                    "status",
                    "archive_member_id",
                    "evidence_file_id",
                    "size_bytes",
                    "archive_member_sha256",
                    "bytes_verified",
                    "exact_media_content",
                }
            )
            _object(
                resolution,
                {"archive_member_id": str, "evidence_file_id": str, "archive_member_sha256": str},
            )
            _require(resolution["bytes_verified"] is True)
            _count(resolution["size_bytes"])
            origin = index["parsed_records"][event["parsed_record_id"]]
            _require(
                resolution["evidence_file_id"] == origin["evidence_file_id"]
                and resolution["evidence_file_id"] in index["evidence_files"]
            )
            content = resolution["exact_media_content"]
            if status == "LINK_EXACT_MEDIA_CONTENT":
                _object(content, {"content_sha256": str, "media_kind": str, "media_format": str})
                _require(
                    set(content)
                    == {
                        "content_sha256",
                        "size_bytes",
                        "media_kind",
                        "media_format",
                        "occurrence_count",
                    }
                )
                _require(
                    content["content_sha256"] == resolution["archive_member_sha256"]
                    and _count(content.get("size_bytes")) == resolution["size_bytes"]
                )
                _require(_count(content.get("occurrence_count")) >= 1)
                _require(
                    content["media_kind"] in {"image", "video"}
                    and content["media_format"]
                    in {"jpeg", "png", "gif", "webp", "heif", "heic", "avif"}
                )
            else:
                _require(content is None)
            positives.append(
                {
                    "candidate_type": "source_media_provenance_link",
                    "classification": "DERIVED",
                    "technical_basis": links["policy"],
                    "references": {
                        "source_media_item_index": position,
                        "event_id": event["event_id"],
                    },
                    "limitations_ref": "global_limitations",
                }
            )
        else:
            _require(set(resolution) == {"classification", "status"})
        _strings(item["limitations"])
        expected_index.append(
            {
                "pointer": f"analysis_window.source_media_links.items[{position}]",
                "parsed_record_id": event["parsed_record_id"],
                "archive_member_id": resolution.get("archive_member_id"),
                "evidence_file_id": resolution.get("evidence_file_id"),
            }
        )
    _require(all(count <= counts.get(status, 0) for status, count in observed.items()))
    if not summary["truncated"]:
        _require(
            observed == counts and len({i["event"]["event_id"] for i in links["items"]}) == eligible
        )
    _require(index["source_media_links"] == expected_index)
    section = _prefix(s["finding_candidates"].get("source_media_provenance_link"))
    _require(section.get("unit") == "candidate_projections" and section["items"] == positives)
    _require(section["total"] == sum(counts.get(k, 0) for k in SOURCE_MEDIA_POSITIVE))


def _source_media_statement(item: Object, window_id: str) -> str:
    event, resolution = item["event"], item["resolution"]
    context = (
        f"Na janela {window_id}, evento técnico UTC {_utc(event['occurred_at_utc'])}, "
        f"{_technical(event['platform'])}/{_technical(event['event_kind'])}: "
        f"{resolution['status']}. Referência OBSERVED; vínculo DERIVED. "
    )
    if resolution["status"] == "LINK_ARCHIVE_MEMBER_ONLY":
        return (
            context + "Membro de arquivo verificado, sem correspondência em ExactMediaContent "
            "sob a policy atual."
        )
    content = resolution["exact_media_content"]
    return context + (
        f"Correspondência em ExactMediaContent, bytes verificados; "
        f"occurrence_count={content['occurrence_count']}; "
        f"{content['media_kind']}/{content['media_format']}."
    )


def validate_snapshot(value: Any) -> Object:
    s = _object(
        value,
        {
            k: dict
            for k in (
                "snapshot",
                "consistency",
                "scope",
                *CASE_WIDE,
                "finding_candidates",
                "gap_inputs",
                "provenance_index",
            )
        },
    )
    _require("analysis_window" in s)
    meta = _object(s["snapshot"], {"case_id": str, "engine_version": str})
    for name, expected in (
        ("snapshot_id", "report.data_snapshot"),
        ("feature_class", "DERIVED"),
        ("evidence_schema_version", 5),
    ):
        _require(type(meta.get(name)) is type(expected) and meta[name] == expected)
    _require(
        meta.get("snapshot_version") in ("1.0.0", "1.1.0"), "REPORT_UNSUPPORTED_SNAPSHOT_VERSION"
    )
    _require(bool(meta["case_id"]))
    _version(meta["engine_version"])
    consistency = s["consistency"]
    _require(
        consistency.get("database_consistency") == "single_read_snapshot"
        and consistency.get("media_consistency") == "verified_read_only_components"
        and consistency.get("media_catalogs") == "separate_read_snapshots"
        and consistency.get("atomic_database_filesystem") is False
    )
    _object(
        s["scope"],
        {"executed_components": list, "limits": dict, "underlying_classifications": dict},
    )
    _strings(s["scope"]["executed_components"])
    _require(
        s["scope"]["underlying_classifications"]
        == {"parsed_records": "OBSERVED", "normalized_events": "DERIVED"}
    )
    _policies(s["policies"])
    inv = _object(s["inventory"], {"tables": dict})
    _require(inv.get("unit") == "physical_rows")
    for name in TABLES:
        _count(inv["tables"].get(name))
    for table, fields in COVERAGE.items():
        coverage = _object(s["coverage"].get(table), {"items": list})
        _require(coverage.get("unit") == "physical_rows")
        for row in coverage["items"]:
            _object(row, {k: str for k in fields})
            _count(row.get("count"))
            for key in fields:
                (_version if key.endswith("_version") else _technical)(row[key])
    current = _counts(s["current_events"], "current_events", ("total", "dated", "undated"))
    _policy(current, "policy_id", "policy_version")
    _require(current["total"] == current["dated"] + current["undated"])
    _object(current, {"by_platform_event_kind": list})
    for row in current["by_platform_event_kind"]:
        _object(row, {"platform": str, "event_kind": str})
        _technical(row["platform"])
        _technical(row["event_kind"])
        for key in ("total", "dated", "undated"):
            _count(row.get(key))
        _require(row["total"] == row["dated"] + row["undated"])
    for key in ("total", "dated", "undated"):
        _require(sum(r[key] for r in current["by_platform_event_kind"]) == current[key])
    exact = _counts(
        s["exact_candidates"], "eligible_persisted_candidates", ("total", "device", "network")
    )
    _require(exact["total"] == exact["device"] + exact["network"])
    _counts(exact.get("supports"), "persisted_support_rows", ("total",))
    _media(s["media"])
    _require(s["media"]["perceptual"]["policy"] == s["policies"]["perceptual_hash"])
    index = _object(s["provenance_index"], {"parsed_records": dict, "evidence_files": dict})
    for key, origin in index["parsed_records"].items():
        _object(
            origin,
            {
                "parsed_record_id": str,
                "source_record_id": str,
                "source_locator": str,
                "evidence_file_id": str,
                "evidence_sha256": str,
            },
        )
        _require(key == origin["parsed_record_id"] and origin.get("classification") == "OBSERVED")
    for value in index["evidence_files"].values():
        _object(value, {"cataloged_sha256": str})
    if s["analysis_window"] is not None:
        _window(s["analysis_window"], index["parsed_records"])
    _findings(s)
    if meta["snapshot_version"] == "1.1.0":
        _source_media(s)
    else:
        _require(
            "source_media_links" not in s["policies"]
            and (s["analysis_window"] is None or "source_media_links" not in s["analysis_window"])
        )
    gaps = _object(s["gap_inputs"], {"whatsapp_parser_available": bool})
    runs = _counts(gaps.get("parser_runs"), "physical_rows", ("UNSUPPORTED", "FAILED"))
    for status in ("UNSUPPORTED", "FAILED"):
        _require(
            runs[status]
            == sum(
                r["count"] for r in s["coverage"]["parser_runs"]["items"] if r["status"] == status
            )
        )
    _require(
        _counts(gaps.get("undated_current_events"), "current_events", ("count",))["count"]
        == current["undated"]
    )
    _require(
        _counts(gaps.get("unrecognized_media"), "cataloged_occurrences", ("count",))["count"]
        == s["media"]["inventory"]["unrecognized_occurrences"]
    )
    phash = _counts(
        gaps.get("perceptual_status_counts"), "exact_contents", ("failed", "unsupported")
    )
    for key in ("failed", "unsupported"):
        _require(phash[key] == s["media"]["perceptual"][key + "_count"])
    _strings(gaps.get("known_capability_limits"))
    truncated = _strings(gaps.get("truncated_components"))
    expected_truncated = (
        []
        if s["analysis_window"] is None
        else sorted(k for k in COMPONENTS if s["analysis_window"][k]["truncated"])
    )
    if meta["snapshot_version"] == "1.0.0":
        _object(gaps, {"media_event_link_available": bool})
    else:
        _require("media_event_link_available" not in gaps)
        if (
            s["analysis_window"] is not None
            and s["analysis_window"]["source_media_links"]["summary"]["truncated"]
        ):
            expected_truncated = sorted([*expected_truncated, "source_media_links"])
    _require(truncated == expected_truncated)
    return s


def _unique_object(pairs: list[tuple[str, Any]]) -> Object:
    result: Object = {}
    for key, value in pairs:
        _require(key not in result, "REPORT_INVALID_JSON")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise EvidenceError("REPORT_INVALID_JSON")


def _decode_snapshot_json(content: bytes) -> Object:
    """Shared strict JSON stage; policy dispatch may precede schema validation.

    Resource exhaustion deliberately propagates to the caller: the historical
    loader maps RecursionError to REPORT_INVALID_JSON, dossier maps it to a budget.
    """
    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (UnicodeError, json.JSONDecodeError):
        raise EvidenceError("REPORT_INVALID_JSON") from None
    return _object(value)


def decode_snapshot(content: bytes) -> Object:
    """Decode and validate captured bytes, without I/O or a snapshot count guard."""
    return validate_snapshot(_decode_snapshot_json(content))


def load_snapshots(paths: Sequence[Path]) -> list[Object]:
    _require(1 <= len(paths) <= MAX_SNAPSHOTS, "REPORT_SNAPSHOT_COUNT")
    result = []
    for path in paths:
        try:
            with path.open("rb") as stream:
                content = stream.read(MAX_SNAPSHOT_BYTES + 1)
            _require(len(content) <= MAX_SNAPSHOT_BYTES, "REPORT_SNAPSHOT_SIZE_LIMIT")
            result.append(decode_snapshot(content))
        except (UnicodeError, json.JSONDecodeError, RecursionError):
            raise EvidenceError("REPORT_INVALID_JSON") from None
        except OSError:
            raise EvidenceError("REPORT_SNAPSHOT_READ_ERROR") from None
    return result


@dataclass(frozen=True)
class TechnicalReference:
    local_id: str
    snapshot: str
    pointer: str


@dataclass(frozen=True)
class ReportFinding:
    finding_id: str
    candidate_type: str
    classification: str
    statement: str
    technical_basis: Object
    provenance_basis: TechnicalReference
    limitations: str


@dataclass(frozen=True)
class TechnicalGap:
    gap_id: str
    category: str
    statement: str
    technical_basis: str
    scope: str
    limitation: str


@dataclass(frozen=True)
class ReportWindow:
    window_id: str
    scope: Object
    component_counts: Object
    overlap_distribution: Object
    truncated_components: tuple[str, ...]


@dataclass(frozen=True)
class ConsolidatedReportModel:
    metadata: Object
    methodology: Object
    evidence_scope: Object
    coverage: Object
    technical_counts: Object
    media_summary: Object
    windows: tuple[ReportWindow, ...]
    findings: tuple[ReportFinding, ...]
    limitations: tuple[str, ...]
    gaps: tuple[TechnicalGap, ...]
    technical_reference_map: tuple[TechnicalReference, ...]


def _statement(kind: str, refs: Object, window_id: str) -> str:
    if kind == "exact_media_duplicate":
        return (
            f"Conteúdo byte a byte idêntico foi verificado em "
            f"{len(refs['occurrences'])} ocorrências catalogadas no snapshot."
        )
    if kind == "window_exact_candidate":
        return (
            f"Na janela {window_id}, um candidate técnico persistido do tipo "
            f"{refs['candidate_kind']} "
            f"foi referenciado por {len(refs['event_ids'])} current event(s) da projeção retornada."
        )
    if kind == "temporal_pair_candidate":
        return (
            f"Na janela {window_id}, dois current events retornados estão separados por "
            f"{refs['delta_microseconds']} microssegundos dentro do limite de consulta informado."
        )
    shared = refs["shared_exact_candidates"]
    device, network = len(shared["device_candidate_ids"]), len(shared["network_candidate_ids"])
    if not device and not network:
        statement = (
            f"Na janela {window_id}, o par temporal não possui membership exata compartilhada "
            "retornada sob a policy 6B para device/network, no prefixo desta consulta."
        )
    else:
        parts = []
        if device:
            parts.append(f"{device} candidate(s) exato(s) device")
        if network:
            parts.append(f"{network} candidate(s) exato(s) network")
        statement = (
            f"Na janela {window_id}, o par temporal possui membership técnica compartilhada em "
            + " e ".join(parts)
            + ", no prefixo retornado sob a policy 6B."
        )
    if refs["same_parsed_record"]:
        statement += (
            " Os eventos referenciam o mesmo ParsedRecord; isso não constitui duas "
            "fontes independentes."
        )
    return statement


def _gaps(anchor: Object, has_links: bool = False) -> tuple[TechnicalGap, ...]:
    inputs = anchor["gap_inputs"]
    rows = []
    if inputs["parser_runs"]["UNSUPPORTED"] > 0:
        count = inputs["parser_runs"]["UNSUPPORTED"]
        rows.append(
            (
                "B",
                f"Foi registrada execução de parser com status UNSUPPORTED no catálogo "
                f"técnico: {count} linhas físicas de parser runs.",
                "gap_inputs.parser_runs.UNSUPPORTED",
                "O snapshot não permite afirmar o conteúdo dessas fontes nem completude "
                "de cobertura.",
            )
        )
    if inputs["undated_current_events"]["count"] > 0:
        count = inputs["undated_current_events"]["count"]
        rows.append(
            (
                "C",
                f"Há {count} current events sob a policy vigente sem UTC suficiente para "
                f"inclusão na timeline datada.",
                "gap_inputs.undated_current_events",
                "Isso não demonstra ausência de atividade; timestamps originais "
                "permanecem na provenance.",
            )
        )
    if (
        anchor["media"]["contents"]["exact_content_count"] > 0
        and anchor["current_events"]["total"] > 0
        and not inputs.get("media_event_link_available", False)
    ):
        rows.append(
            (
                "D",
                "O motor contém dados técnicos de mídia e eventos, mas não possui "
                "vínculo aprovado media-event nesta versão.",
                "media.contents.exact_content_count; current_events.total; "
                "gap_inputs.media_event_link_available",
                "Não se atribui qualquer mídia a evento específico; a limitação não "
                "identifica uma fonte externa necessária.",
            )
        )
    if anchor["snapshot"]["snapshot_version"] == "1.1.0":
        rows = [row for row in rows if row[0] != "D"]
        if has_links or (
            anchor["media"]["contents"]["exact_content_count"] and anchor["current_events"]["total"]
        ):
            rows.append(
                (
                    "D",
                    SOURCE_MEDIA_PARTIAL if has_links else SOURCE_MEDIA_ABSENT,
                    "analysis_window.source_media_links",
                    SOURCE_MEDIA_LIMITATION,
                )
            )
    return tuple(
        TechnicalGap(
            f"G-{index:03d}",
            category,
            statement,
            basis,
            "Snapshots fornecidos"
            if category == "D" and anchor["snapshot"]["snapshot_version"] == "1.1.0"
            else "Anchor / case-wide",
            limitation,
        )
        for index, (category, statement, basis, limitation) in enumerate(rows, 1)
    )


def consolidate_snapshots(snapshots: Sequence[Object]) -> ConsolidatedReportModel:
    _require(1 <= len(snapshots) <= MAX_SNAPSHOTS, "REPORT_SNAPSHOT_COUNT")
    return build_consolidated_model(snapshots)


def build_consolidated_model(snapshots: Sequence[Object]) -> ConsolidatedReportModel:
    """Pure semantic core; callers own operational count and byte budgets."""
    _require(len(snapshots) >= 1, "REPORT_SNAPSHOT_COUNT")
    validated = [validate_snapshot(s) for s in snapshots]
    _require(
        len({s["snapshot"]["snapshot_version"] for s in validated}) == 1,
        "REPORT_MIXED_SNAPSHOT_VERSIONS",
    )
    anchors = [s for s in validated if s["analysis_window"] is None]
    _require(len(anchors) == 1, "REPORT_ANCHOR_COUNT")
    anchor = anchors[0]
    version = anchor["snapshot"]["snapshot_version"]
    keys = set()
    ordered = []
    for s in validated:
        _require(
            all(
                s["snapshot"][k] == anchor["snapshot"][k]
                for k in (
                    "case_id",
                    "engine_version",
                    "snapshot_version",
                    "evidence_schema_version",
                )
            ),
            "REPORT_SNAPSHOT_SET_CHANGED",
        )
        _require(all(s[k] == anchor[k] for k in CASE_WIDE), "REPORT_SNAPSHOT_SET_CHANGED")
        _require(
            all(
                s["gap_inputs"][k] == anchor["gap_inputs"][k]
                for k in GAP_FIELDS
                + (("media_event_link_available",) if version == "1.0.0" else ())
            ),
            "REPORT_SNAPSHOT_SET_CHANGED",
        )
        _require(
            s["finding_candidates"]["exact_media_duplicate"]
            == anchor["finding_candidates"]["exact_media_duplicate"]
            and s["finding_candidates"]["global_limitations"]
            == anchor["finding_candidates"]["global_limitations"],
            "REPORT_SNAPSHOT_SET_CHANGED",
        )
        if s["analysis_window"] is not None:
            key = _window(s["analysis_window"], s["provenance_index"]["parsed_records"])
            _require(key not in keys, "REPORT_DUPLICATE_ANALYSIS_WINDOW")
            keys.add(key)
            ordered.append((key, s))
    ordered.sort(key=lambda item: item[0])
    findings: list[ReportFinding] = []
    windows = []

    def include(s: Object, kind: str, label: str) -> None:
        section = s["finding_candidates"][kind]
        for index, candidate in enumerate(section["items"]):
            finding_id = f"F-{len(findings) + 1:03d}"
            limits = LIMITATION
            if kind.startswith("temporal"):
                limits += " O raio é limite de consulta; delta menor não indica maior força."
            if section["truncated"]:
                limits += (
                    f" Componente truncado: total={section['total']}, "
                    f"returned={section['returned']}, "
                    "truncated=true; unidade: candidate_projections do componente de origem."
                )
            findings.append(
                ReportFinding(
                    finding_id,
                    kind,
                    "DERIVED",
                    _statement(kind, candidate["references"], label),
                    deepcopy(candidate["technical_basis"]),
                    TechnicalReference(
                        finding_id, label, f"finding_candidates.{kind}.items[{index}]"
                    ),
                    limits,
                )
            )

    # Case-wide duplicates are identical in every input; present the anchor copy once.
    include(anchor, "exact_media_duplicate", "Anchor")
    for index, (key, s) in enumerate(ordered, 1):
        label = f"W-{index:03d}"
        w = s["analysis_window"]
        counts = {}
        for name in COMPONENTS:
            component = w[name]
            if name == "incident_window":
                total, returned, unit = "matched_total", "returned", "current_events"
            elif name == "incident_candidates":
                total, returned, unit = (
                    "matched_candidates",
                    "returned_candidates",
                    "persisted_candidates",
                )
            else:
                total, returned, unit = "matched_pairs", "returned_pairs", "temporal_pairs"
            counts[name] = {
                "unit": unit,
                "total": component[total],
                "returned": component[returned],
                "truncated": component["truncated"],
            }
        pairs = w["temporal_exact_overlap"]["items"]
        flags = [
            (
                bool(p["shared_exact_candidates"]["device_candidate_ids"]),
                bool(p["shared_exact_candidates"]["network_candidate_ids"]),
            )
            for p in pairs
        ]
        distribution = {
            "unit": "returned_temporal_pairs",
            "returned_pairs": len(pairs),
            "device": sum(d for d, n in flags),
            "network": sum(n for d, n in flags),
            "both": sum(d and n for d, n in flags),
            "neither": sum(not d and not n for d, n in flags),
        }
        scope = {
            "start": key[0],
            "end": key[1],
            "platform": w["window"]["platform"],
            "event_kind": w["window"]["event_kind"],
            "max_delta_seconds": key[-1],
            "undated_current_events": w["incident_window"]["undated_current_events"],
            "eligible_events": w["temporal_proximity"]["eligible_events"],
        }
        windows.append(
            ReportWindow(
                label, scope, counts, distribution, tuple(s["gap_inputs"]["truncated_components"])
            )
        )
        if version == "1.1.0":
            summary = w["source_media_links"]["summary"]
            counts["source_media_links"] = {
                "unit": summary["unit"],
                "total": summary["matched_total"],
                "returned": summary["returned"],
                "truncated": summary["truncated"],
                "status_counts": deepcopy(summary["status_counts"]),
            }
        for kind in WINDOW_TYPES:
            include(s, kind, label)
    source_findings: list[ReportFinding] = []
    if version == "1.1.0":
        for index, (_, s) in enumerate(ordered, 1):
            label = f"W-{index:03d}"
            links = s["analysis_window"]["source_media_links"]
            for candidate in s["finding_candidates"]["source_media_provenance_link"]["items"]:
                item_index = candidate["references"]["source_media_item_index"]
                item = links["items"][item_index]
                finding_id = f"F-{len(findings) + len(source_findings) + 1:03d}"
                limits = LIMITATION + " " + SOURCE_MEDIA_LIMITATION
                if links["summary"]["truncated"]:
                    limits += (
                        " Projeção source-media truncada; "
                        "achados limitados aos positivos do prefixo."
                    )
                source_findings.append(
                    ReportFinding(
                        finding_id,
                        "source_media_provenance_link",
                        "DERIVED",
                        _source_media_statement(item, label),
                        deepcopy(links["policy"]),
                        TechnicalReference(
                            finding_id,
                            label,
                            f"analysis_window.source_media_links.items[{item_index}]",
                        ),
                        limits,
                    )
                )
        findings.extend(source_findings)
    media = deepcopy(anchor["media"])
    media["contents"].pop("duplicates")
    limitations = [
        LIMITATION,
        "As contagens de cobertura não demonstram completude da realidade.",
        "A igualdade das seções case-wide verifica coerência dos inputs; não "
        "certifica um instante atômico global.",
        "As verificações de mídia foram realizadas pela 8A1 com leituras e "
        "catálogos separados; a 8A2 não as repete.",
        f"Parser runs FAILED: {anchor['gap_inputs']['parser_runs']['FAILED']} "
        f"linhas físicas; falha não gera categoria de lacuna automaticamente.",
        f"Mídia não reconhecida: "
        f"{anchor['gap_inputs']['unrecognized_media']['count']} ocorrências "
        f"catalogadas.",
        "Ausência no snapshot ou no prefixo não demonstra inexistência de "
        "dados, atividade ou vínculo fora do escopo.",
    ]
    if version == "1.1.0":
        limitations.append(SOURCE_MEDIA_LIMITATION)
    if not anchor["gap_inputs"]["whatsapp_parser_available"]:
        limitations.append("Não há parser WhatsApp implementado nesta versão.")
    return ConsolidatedReportModel(
        metadata={
            "report_policy_id": REPORT_ID,
            "report_policy_version": version,
            "feature_class": "DERIVED",
            "snapshot_policy_id": "report.data_snapshot",
            "snapshot_policy_version": version,
            "evidence_schema_version": 5,
            "engine_version": anchor["snapshot"]["engine_version"],
        },
        methodology=deepcopy(anchor["policies"]),
        evidence_scope=deepcopy(anchor["inventory"]),
        coverage=deepcopy(anchor["coverage"]),
        technical_counts={
            "current_events": deepcopy(anchor["current_events"]),
            "exact_candidates": deepcopy(anchor["exact_candidates"]),
            "parser_runs": deepcopy(anchor["gap_inputs"]["parser_runs"]),
        },
        media_summary=media,
        windows=tuple(windows),
        findings=tuple(findings),
        limitations=tuple(limitations),
        gaps=_gaps(anchor, bool(source_findings)),
        technical_reference_map=tuple(f.provenance_basis for f in findings),
    )


def _table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    def cell(value: object) -> str:
        text = str(value).lower() if type(value) is bool else str(value)
        return text.replace("\\", "\\\\").replace("|", "\\|").replace("_", "\\_")

    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *("| " + " | ".join(cell(v) for v in row) + " |" for row in rows),
        ]
    )


def _coverage_table(model: ConsolidatedReportModel, name: str) -> str:
    fields = COVERAGE[name]
    rows = model.coverage[name]["items"]
    return _table(
        (*fields, "Linhas físicas"),
        [tuple(row[k] for k in fields) + (row["count"],) for row in rows],
    )


def _basis(value: Object) -> str:
    if "projection_policy_id" in value:
        return (
            "Igualdade SHA-256/tamanho verificada na 8A1; report.data_snapshot / "
            f"{_version(value['projection_policy_version'])}."
        )
    if "correlator_id" in value:
        return (
            f"{_technical(value['correlator_id'])} / {_version(value['correlator_version'])}; "
            f"{_technical(value['rule_id'])} / {_version(value['rule_version'])}."
        )
    return f"{_technical(value['policy_id'])} / {_version(value['policy_version'])}."


def render_markdown(model: ConsolidatedReportModel) -> str:
    """Render only validated technical fields and fixed templates, never arbitrary payloads."""
    m = model
    current = m.technical_counts["current_events"]
    exact = m.technical_counts["exact_candidates"]
    media = m.media_summary
    bodies: list[str] = []
    bodies.append(
        f"Policy do relatório: {REPORT_ID} / {m.metadata['report_policy_version']}. "
        "Projeção DERIVED.\n\n"
        f"Snapshot: report.data_snapshot / {m.metadata['snapshot_policy_version']}. "
        "Evidence schema: v5. Engine: "
        f"{m.metadata['engine_version']}."
    )
    bodies.append(
        f"Consolidação de um anchor sem janela e {len(m.windows)} janela(s) "
        f"técnica(s) fornecida(s) pelo operador. "
        "A seleção inclui todos os candidates dos prefixos retornados. "
        "Duplicatas case-wide são apresentadas uma vez, pelo anchor. "
        "Nenhuma nova análise de evidência é executada."
    )
    bodies.append(
        "Documento técnico de organização e rastreabilidade, sem certificação pericial. "
        "ParsedRecord permanece OBSERVED; NormalizedEvent e achados automáticos "
        "permanecem DERIVED. "
        "Não são gerados achados REPORTED ou HYPOTHESIS. " + LIMITATION
    )
    bodies.append(
        "Materiais representados nos snapshots; esta execução lê somente os JSONs fornecidos.\n\n"
        + _table(
            ("Tabela catalogada", "Linhas físicas"),
            [(name, m.evidence_scope["tables"][name]) for name in TABLES],
        )
    )
    policies = m.methodology
    policy_rows = [
        (
            policies["current_event_policy"]["policy_id"],
            policies["current_event_policy"]["policy_version"],
        )
    ]
    for name, prefix in (
        ("eligible_normalizers", "normalizer"),
        ("observers", "observer"),
        ("exact_rules", "rule"),
    ):
        policy_rows.extend((p[prefix + "_id"], p[prefix + "_version"]) for p in policies[name])
    for name, prefix in (
        ("exact_correlator", "correlator"),
        ("temporal_proximity", "policy"),
        ("temporal_exact_overlap", "policy"),
    ):
        policy_rows.append((policies[name][prefix + "_id"], policies[name][prefix + "_version"]))
    if "source_media_links" in policies:
        policy_rows.append(("source_media.provenance_link", "1.0.0"))
    bodies.append(
        "Policies declaradas nos snapshots; disponibilidade não implica "
        "execução de componente sem janela. "
        "A 8A2 valida e projeta esses resultados, sem recalcular normalização, "
        "pares ou memberships.\n\n" + _table(("Policy/componente", "Versão"), policy_rows)
    )
    bodies.append(
        "O motor possui mecanismos de SHA-256 e verificação contra baseline catalogada. "
        "Este relatório não executa verify nem afirma um resultado de verify ausente do snapshot. "
        "Não estabelece autenticidade anterior à aquisição.\n\n"
        "Os componentes DB da 8A1 compartilham um read snapshot; mídia utiliza "
        "leituras verificadas separadas. "
        "Não há atomicidade DB/filesystem. Cada F-ID aponta para uma posição "
        "estruturada de snapshot no apêndice. "
        "O snapshot preserva IDs, locators e hashes para drill-down até o catálogo e a fonte; "
        "este relatório não replica seus valores. Snapshots e relatórios reais "
        "permanecem fora do Git."
    )
    bodies.append(
        "Histórico de execuções de parser, sem alegação de cobertura completa da realidade.\n\n"
        + _coverage_table(m, "parser_runs")
    )
    bodies.append(
        f"Linhas físicas de normalized_events: {m.evidence_scope['tables']['normalized_events']}. "
        f"Current events sob {_technical(current['policy_id'])} / "
        f"{_version(current['policy_version'])}: {current['total']}. "
        f"Current events datados: {current['dated']}; current events sem UTC "
        f"suficiente: {current['undated']}. "
        "As unidades físicas e current são distintas; versões históricas não se "
        "tornam atuais pela recência.\n\n"
        + _table(
            ("Plataforma", "Event kind", "Current events", "Current datados", "Current sem UTC"),
            [
                (r["platform"], r["event_kind"], r["total"], r["dated"], r["undated"])
                for r in current["by_platform_event_kind"]
            ],
        )
        + "\n\n"
        + _coverage_table(m, "normalization_runs")
    )
    bodies.append(
        "Observações técnicas de dispositivo catalogadas; não representam "
        "resolução de entidade física.\n\n" + _coverage_table(m, "device_observations")
    )
    bodies.append(
        "Observações técnicas de rede catalogadas; nenhuma atribuição de pessoa "
        "ou localização é produzida.\n\n" + _coverage_table(m, "network_observations")
    )
    bodies.append(
        f"Candidates persistidos elegíveis: {exact['total']}; device: "
        f"{exact['device']}; network: {exact['network']}. "
        f"Supports elegíveis: {exact['supports']['total']} linhas persistidas de suporte. "
        "Contagens de suporte não medem força probatória.\n\n"
        + _coverage_table(m, "correlation_candidates")
    )
    window_text = []
    for w in m.windows:
        s = w.scope
        window_text.append(
            f"### {w.window_id}\n\nUTC [{s['start']}, {s['end']}); "
            f"platform={s['platform'] if s['platform'] is not None else 'sem filtro'}; "
            f"event-kind={s['event_kind'] if s['event_kind'] is not None else 'sem filtro'}; "
            f"limite de consulta={s['max_delta_seconds']} segundos. "
            f"Current events elegíveis datados: {s['eligible_events']}; "
            f"current events sem UTC sob os filtros: {s['undated_current_events']}.\n\n"
            + _table(
                ("Componente", "Unidade", "total", "returned", "truncated"),
                [
                    (name, row["unit"], row["total"], row["returned"], row["truncated"])
                    for name, row in w.component_counts.items()
                ],
            )
            + (
                "\n\n**Há truncamento nesta janela; o prefixo retornado não representa "
                "todo o universo correspondente.**"
                if w.truncated_components
                else ""
            )
        )
    bodies.append(
        "\n\n".join(window_text)
        or "Nenhuma janela foi fornecida; isso não afirma ausência de atividade."
    )
    bodies.append(
        "O raio é limite de consulta. Delta menor não indica maior força. "
        "Proximidade temporal não demonstra causalidade, sessão, pessoa ou "
        "dispositivo.\n\n"
        + _table(
            ("Janela", "matched_pairs", "returned_pairs", "truncated"),
            [
                (
                    w.window_id,
                    w.component_counts["temporal_proximity"]["total"],
                    w.component_counts["temporal_proximity"]["returned"],
                    w.component_counts["temporal_proximity"]["truncated"],
                )
                for w in m.windows
            ],
        )
    )
    bodies.append(
        "Distribuição técnica exclusivamente do PREFIXO de pares retornados. "
        "Device e network permanecem separados; "
        "as contagens incluem interseção e não devem ser somadas como suportes independentes.\n\n"
        + _table(
            (
                "Janela",
                "matched_pairs",
                "returned_pairs",
                "truncated",
                "Device",
                "Network",
                "Ambos",
                "Nenhum",
            ),
            [
                (
                    w.window_id,
                    w.component_counts["temporal_exact_overlap"]["total"],
                    w.overlap_distribution["returned_pairs"],
                    w.component_counts["temporal_exact_overlap"]["truncated"],
                    *(w.overlap_distribution[k] for k in ("device", "network", "both", "neither")),
                )
                for w in m.windows
            ],
        )
    )
    media_rows = [
        (k, v, "ocorrências catalogadas") for k, v in media["inventory"].items() if type(v) is int
    ]
    media_rows += [
        (k, v, "conteúdos exatos") for k, v in media["contents"].items() if type(v) is int
    ]
    p = media["perceptual"]
    bodies.append(
        "Igualdade de conteúdo não identifica upload, envio ou origem histórica. "
        f"pHash: {_technical(p['policy']['algorithm_id'])} / "
        f"{_version(p['policy']['algorithm_version'])}; "
        f"SUCCESS: {p['success_count']}; FAILED: {p['failed_count']}; "
        f"UNSUPPORTED: {p['unsupported_count']} conteúdos exatos. "
        "Nenhum valor perceptual ou comparação de similaridade é publicado.\n\n"
        + _table(("Medida", "Contagem", "Unidade"), media_rows)
        + "\n\n"
        + _table(
            ("Status pHash", "Formato", "Conteúdos exatos"),
            [(r["status"], r["media_format"], r["count"]) for r in p["by_status_format"]],
        )
    )
    if m.metadata["report_policy_version"] == "1.1.0":
        bodies[-1] += (
            "\n\nReferência de fonte OBSERVED; resolução/link DERIVED. " + SOURCE_MEDIA_LIMITATION
        )
        bodies[-1] += "\n\n" + _table(
            ("Janela", "Status source-media", "Items no universo completo"),
            [
                (w.window_id, status, count)
                for w in m.windows
                for status, count in sorted(
                    w.component_counts["source_media_links"]["status_counts"].items()
                )
            ],
        )
    finding_text = []
    for f in m.findings:
        finding_text.append(
            f"### {f.finding_id} — {f.candidate_type}\n\nClassificação: {f.classification}.\n\n"
            f"{f.statement}\n\nBase técnica: {_basis(f.technical_basis)}\n\n"
            f"Provenance: {f.provenance_basis.snapshot}, referência {f.finding_id} "
            f"no apêndice.\n\nLimitações: {f.limitations}"
        )
    bodies.append(
        "\n\n".join(finding_text)
        or "Nenhum finding candidate foi retornado nos snapshots fornecidos; "
        "conclusão limitada a esse conjunto."
    )
    bodies.append("\n".join("- " + text for text in m.limitations))
    gap_text = [
        f"### {g.gap_id} — Categoria {g.category}\n\n{g.statement}\n\n"
        f"Base técnica: `{g.technical_basis}`. Escopo: {g.scope}.\n\nLimitação: {g.limitation}"
        for g in m.gaps
    ]
    bodies.append(
        (
            "\n\n".join(gap_text)
            or "Nenhuma lacuna B/C/D é gerada pelas regras mecânicas sobre os snapshots fornecidos."
        )
        + "\n\nCategorias A, E e F não são automatizadas: inexistência não é "
        "demonstrada por ausência no snapshot; "
        "nova fonte e hipótese exigem pergunta e contexto externos. FAILED e "
        "ausência de parser WhatsApp não geram lacuna automaticamente."
    )
    bodies.append(
        "- Aprofundar a provenance dos achados conforme a pergunta investigativa.\n"
        "- Revisar fontes com UNSUPPORTED quando registradas.\n"
        "- Ampliar janela somente mediante pergunta investigativa documentada.\n"
        "- Considerar nova fonte apenas quando uma pergunta concreta exigir.\n\n"
        "O escopo de WhatsApp permanece condicionado à análise contextual das lacunas. "
        "A ausência de parser não fundamenta, por si, sua implementação ou necessidade."
    )
    bodies.append(
        "Anchor identifica o único snapshot sem janela; W-IDs identificam as "
        "janelas em ordem canônica. "
        "F/W/G são referências locais de apresentação, não entidades persistidas. "
        "O ponteiro deve ser resolvido no snapshot externo correspondente; "
        "nenhum nome de arquivo de input é publicado.\n\n"
        + _table(
            ("Finding", "Snapshot lógico", "Ponteiro"),
            [(r.local_id, r.snapshot, r.pointer) for r in m.technical_reference_map],
        )
    )
    assert len(bodies) == len(SECTIONS)
    return (
        f"# {TITLE}\n\n"
        + "\n\n".join(
            f"## {index}. {title}\n\n{body}"
            for index, (title, body) in enumerate(zip(SECTIONS, bodies, strict=True), 1)
        )
        + "\n"
    )


def consolidated_report(paths: Sequence[Path]) -> str:
    return render_markdown(consolidate_snapshots(load_snapshots(paths)))
