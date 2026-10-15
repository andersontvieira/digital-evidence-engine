"""Small, fully synthetic portfolio workflow over the existing engine services."""

import csv
import hashlib
import io
import json
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from evidence_engine import __version__
from evidence_engine.correlation.overlap import temporal_exact_overlap
from evidence_engine.correlation.service import correlate_exact
from evidence_engine.correlation.temporal import temporal_candidates
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.ingest.parsing.framework import JSONValue
from evidence_engine.ingest.parsing.service import parse_apple, parse_google, parse_instagram
from evidence_engine.normalization.service import normalize_events
from evidence_engine.observations.service import observe_device_network
from evidence_engine.reports.snapshot import report_snapshot

DEMO_START = "2024-01-02T03:04:00Z"
DEMO_END = "2024-01-02T03:05:00Z"
DEMO_RADIUS_SECONDS = 5
OUTPUT_FILES = (
    "README.md",
    "pipeline-summary.json",
    "technical-report.md",
    "technical-snapshot.json",
    "SHA256SUMS.txt",
)


@dataclass(frozen=True)
class DemoResult:
    sources_cataloged: int
    archive_members_cataloged: int
    parsed_records: int
    normalized_events: int
    device_observations: int
    network_observations: int
    exact_candidates: int
    temporal_pairs: int
    exact_signal_pairs: int
    temporal_only_pairs: int
    files_written: int


def _json_bytes(value: JSONValue) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii")


def _csv_bytes(headers: tuple[str, ...], row: tuple[str, ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(headers)
    writer.writerow(row)
    return stream.getvalue().encode("utf-8")


def _synthetic_sources() -> dict[str, bytes]:
    """Generate fixed source bytes; values are conspicuously synthetic and reserved."""
    meta = _json_bytes(
        {
            "profile_account_insights": [
                {
                    "action": "SYNTHETIC_DEMO_PROFILE_CHANGE",
                    "device_id": "SYNTHETIC-DEMO-DEVICE-SHARED",
                    "ip": "192.0.2.10",
                    "timestamp": 1704164645,
                }
            ]
        }
    )
    google = (
        b'<html><head><meta charset="UTF-8"><title>Synthetic demo</title></head>'
        b"<body><table>"
        b"<tr><th>Timestamp</th><th>IP Address</th><th>Change Type</th>"
        b"<th>Old Value</th><th>New Value</th></tr>"
        b"<tr><td>2024-01-02 03:04:06 Z</td><td>192.0.2.10</td>"
        b"<td>SYNTHETIC_DEMO_ACCOUNT_CHANGE</td>"
        b"<td>synthetic-old@example.invalid</td>"
        b"<td>synthetic-new@example.invalid</td></tr>"
        b"</table></body></html>\n"
    )
    apple_headers = (
        "Application",
        "Apple ID Number",
        "Device Identifier",
        "IP Address",
        "Logged In Date",
        "Signon Status",
        "StoreFront Name",
    )
    apple = _csv_bytes(
        apple_headers,
        (
            "SYNTHETIC-DEMO-APPLICATION",
            "SYNTHETIC-DEMO-ACCOUNT",
            "SYNTHETIC-DEMO-DEVICE-UNIQUE",
            "203.0.113.77",
            "2024-01-02T03:04:07Z",
            "SYNTHETIC_DEMO_SUCCESS",
            "SYNTHETIC-DEMO-STOREFRONT",
        ),
    )
    return {
        "profile_activity.json": meta,
        "ChangeHistory.html": google,
        "Informações da Conta Apple e do dispositivo/Apple ID SignOn Information.csv": apple,
    }


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            archive.writestr(info, entries[name])
    return stream.getvalue()


def _write_sources(case_root: Path) -> None:
    originals = case_root / "originals"
    originals.mkdir()
    sources = _synthetic_sources()
    (originals / "profile_activity.json").write_bytes(sources.pop("profile_activity.json"))
    (originals / "synthetic-multiplatform-export.zip").write_bytes(_zip_bytes(sources))


def _integer(mapping: dict[str, JSONValue], key: str) -> int:
    value = mapping[key]
    if type(value) is not int:
        raise EvidenceError("Synthetic demo projection mismatch")
    return value


def _pipeline(case_root: Path) -> tuple[DemoResult, dict[str, JSONValue], dict[str, JSONValue]]:
    _write_sources(case_root)
    ingestion = ingest(case_root)
    parsed = [parse_instagram(case_root), parse_google(case_root), parse_apple(case_root)]
    normalization = normalize_events(case_root)
    observations = observe_device_network(case_root)
    exact = correlate_exact(case_root)
    temporal = temporal_candidates(
        case_root,
        start=DEMO_START,
        end=DEMO_END,
        max_delta_seconds=DEMO_RADIUS_SECONDS,
    )
    overlap = temporal_exact_overlap(
        case_root,
        start=DEMO_START,
        end=DEMO_END,
        max_delta_seconds=DEMO_RADIUS_SECONDS,
    )
    snapshot = report_snapshot(
        case_root,
        start=DEMO_START,
        end=DEMO_END,
        max_delta_seconds=DEMO_RADIUS_SECONDS,
    )
    if any(item.errors for item in parsed) or any(
        item.errors for item in (normalization, observations, exact)
    ):
        raise EvidenceError("Synthetic demo pipeline failed")
    exact_signal_pairs = sum(
        bool(
            item.shared_exact_candidates.device_candidate_ids
            or item.shared_exact_candidates.network_candidate_ids
        )
        for item in overlap.items
    )
    temporal_only_pairs = overlap.returned_pairs - exact_signal_pairs
    if exact.candidates_created < 1 or exact_signal_pairs < 1 or temporal_only_pairs < 1:
        raise EvidenceError("Synthetic demo scenario did not exercise required relationships")

    evidence_index = cast(dict[str, JSONValue], snapshot.provenance_index["evidence_files"])
    hashes = []
    for value in evidence_index.values():
        entry = cast(dict[str, JSONValue], value)
        digest = entry.get("cataloged_sha256")
        if not isinstance(digest, str):
            raise EvidenceError("Synthetic demo provenance mismatch")
        hashes.append(digest)
    current_events = cast(dict[str, JSONValue], snapshot.current_events)
    exact_candidates = cast(dict[str, JSONValue], snapshot.exact_candidates)
    inventory_tables = cast(dict[str, JSONValue], snapshot.inventory["tables"])
    result = DemoResult(
        sources_cataloged=ingestion.files_added,
        archive_members_cataloged=_integer(inventory_tables, "archive_members"),
        parsed_records=sum(item.records_parsed for item in parsed),
        normalized_events=normalization.events_normalized,
        device_observations=observations.device_observations_created,
        network_observations=observations.network_observations_created,
        exact_candidates=exact.candidates_created,
        temporal_pairs=temporal.returned_pairs,
        exact_signal_pairs=exact_signal_pairs,
        temporal_only_pairs=temporal_only_pairs,
        files_written=len(OUTPUT_FILES),
    )
    summary: dict[str, JSONValue] = {
        "contract": "demo.pipeline_summary/1.0.0",
        "engine_version": __version__,
        "scenario": "fully-synthetic",
        "stages": {
            "ingestion": {
                "cataloged_originals": result.sources_cataloged,
                "cataloged_archive_members": result.archive_members_cataloged,
            },
            "transformation": {
                "parser_families": 3,
                "parsed_records": result.parsed_records,
                "normalized_events": result.normalized_events,
            },
            "observation": {
                "device_observations": result.device_observations,
                "network_observations": result.network_observations,
            },
            "correlation": {
                "exact_candidates": result.exact_candidates,
                "temporal_pairs": result.temporal_pairs,
                "temporal_pairs_with_exact_signal": result.exact_signal_pairs,
                "temporal_pairs_without_exact_signal": result.temporal_only_pairs,
            },
        },
    }
    cataloged_hashes = [cast(JSONValue, value) for value in sorted(hashes)]
    lineage: dict[str, JSONValue] = {
        "cataloged_source_count": len(hashes),
        "cataloged_source_sha256": cataloged_hashes,
        "referenced_parsed_records": len(snapshot.provenance_index["parsed_records"]),
    }
    technical: dict[str, JSONValue] = {
        "contract": "demo.technical_snapshot/1.0.0",
        "classification": "DERIVED",
        "source_policy": {
            "data_class": "SYNTHETIC",
            "external_case_access": False,
            "network_access": False,
        },
        "report_contract": {
            "snapshot_id": snapshot.snapshot["snapshot_id"],
            "snapshot_version": snapshot.snapshot["snapshot_version"],
            "evidence_schema_version": snapshot.snapshot["evidence_schema_version"],
        },
        "lineage": lineage,
        "current_events": {
            "total": _integer(current_events, "total"),
            "dated": _integer(current_events, "dated"),
            "undated": _integer(current_events, "undated"),
            "by_platform_event_kind": current_events["by_platform_event_kind"],
        },
        "exact_candidates": {
            "total": _integer(exact_candidates, "total"),
            "device": _integer(exact_candidates, "device"),
            "network": _integer(exact_candidates, "network"),
        },
        "analysis_window": {
            "start": DEMO_START,
            "end": DEMO_END,
            "max_delta_seconds": DEMO_RADIUS_SECONDS,
            "eligible_events": temporal.eligible_events,
            "matched_pairs": temporal.matched_pairs,
            "truncated": temporal.truncated,
        },
        "demonstrated_relationships": {
            "exact_technical_equality": exact_signal_pairs > 0,
            "temporal_proximity_without_exact_equality": temporal_only_pairs > 0,
            "absence_of_technical_bridge_is_explicit": temporal_only_pairs > 0,
        },
    }
    return result, summary, technical


def _readme(result: DemoResult) -> bytes:
    return (
        "# Digital Evidence Engine — Synthetic Demo\n\n"
        "This directory was produced from programmatically generated synthetic data only.\n"
        "The temporary case database, originals, and working files were removed after the run.\n\n"
        "The scenario exercises JSON, HTML, and CSV parsing; canonical normalization; device and\n"
        "network observation; exact-signal grouping; temporal proximity; provenance; and the\n"
        "read-only report snapshot pipeline.\n\n"
        "Correlation entries are technical candidates. They do not establish identity, "
        "authorship,\n"
        "session, intent, causality, or a legal conclusion.\n\n"
        f"Produced {result.normalized_events} normalized events, {result.exact_candidates} exact "
        f"candidate group, and {result.temporal_pairs} temporal candidate pairs.\n"
    ).encode()


def _report(result: DemoResult) -> bytes:
    return (
        "# Synthetic Technical Report\n\n"
        "## Scope\n\n"
        "Entirely synthetic, offline demonstration of the existing engine pipeline.\n\n"
        "## Ingestion and transformation\n\n"
        f"- Cataloged originals: {result.sources_cataloged}\n"
        f"- Cataloged archive members: {result.archive_members_cataloged}\n"
        f"- Parsed records: {result.parsed_records}\n"
        f"- Normalized events: {result.normalized_events}\n\n"
        "## Observations\n\n"
        f"- Device observations: {result.device_observations}\n"
        f"- Network observations: {result.network_observations}\n\n"
        "## Correlation candidates\n\n"
        f"- Exact candidate groups: {result.exact_candidates}\n"
        f"- Temporal candidate pairs: {result.temporal_pairs}\n"
        f"- Temporal pairs with a shared exact signal: {result.exact_signal_pairs}\n"
        f"- Temporal pairs without a shared exact signal: {result.temporal_only_pairs}\n\n"
        "## Interpretation boundary\n\n"
        "Exact equality and temporal proximity are DERIVED technical candidates. A missing exact\n"
        "bridge remains explicit. No candidate establishes identity, authorship, intent, session,\n"
        "causality, or legal significance.\n"
    ).encode()


def _artifacts(
    result: DemoResult, summary: dict[str, JSONValue], technical: dict[str, JSONValue]
) -> dict[str, bytes]:
    artifacts = {
        "README.md": _readme(result),
        "pipeline-summary.json": _json_bytes(summary),
        "technical-report.md": _report(result),
        "technical-snapshot.json": _json_bytes(technical),
    }
    sums = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in sorted(artifacts.items())
    )
    return artifacts | {"SHA256SUMS.txt": sums.encode("ascii")}


def _publish(output_dir: Path, artifacts: dict[str, bytes]) -> None:
    if output_dir.exists():
        raise EvidenceError("Demo output directory already exists")
    if not output_dir.parent.is_dir():
        raise EvidenceError("Demo output parent must already exist")
    output_dir.mkdir()
    try:
        for name in OUTPUT_FILES:
            with (output_dir / name).open("xb") as stream:
                stream.write(artifacts[name])
    except Exception:
        for name in OUTPUT_FILES:
            (output_dir / name).unlink(missing_ok=True)
        output_dir.rmdir()
        raise


def run_demo(output_dir: Path) -> DemoResult:
    """Run the fixed scenario in temporary state and publish only deterministic projections."""
    output_dir = output_dir.absolute()
    if output_dir.exists():
        raise EvidenceError("Demo output directory already exists")
    with tempfile.TemporaryDirectory(prefix="dee-portfolio-demo-") as temporary:
        case_root = Path(temporary).resolve()
        result, summary, technical = _pipeline(case_root)
        artifacts = _artifacts(result, summary, technical)
    _publish(output_dir, artifacts)
    return result
