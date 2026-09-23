"""Synthetic 1.1 integration and frozen pre-change 1.0 report regression."""

import builtins
import hashlib
import json
import re
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from itertools import permutations
from pathlib import Path
from unittest.mock import Mock

import pytest

from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.paths import CasePaths
from evidence_engine.media import source_links
from evidence_engine.query.catalog import read_catalog
from evidence_engine.reports import consolidated as report
from evidence_engine.reports import snapshot
from tests.test_source_media_links import END, START
from tests.test_source_media_links import link_case as link_case

LEGACY = Path(__file__).parent / "fixtures/report_legacy"
WINDOW = {"start": START, "end": END, "max_delta_seconds": 10}


def value(root, **kwargs):
    return json.loads(json.dumps(asdict(snapshot.report_snapshot(root, **kwargs))))


@pytest.fixture
def report_set(link_case):
    return [
        value(link_case),
        value(link_case, **WINDOW),
        value(link_case, **WINDOW, platform="meta", event_kind="communication.message"),
    ]


def legacy(values):
    """Test-only down-projection to compare old finding order on identical data."""
    values = deepcopy(values)
    for s in values:
        s["snapshot"]["snapshot_version"] = "1.0.0"
        s["policies"].pop("source_media_links")
        s["scope"]["limits"].pop("source_media_items")
        if s["analysis_window"] is not None:
            s["scope"]["executed_components"].remove("source_media_links")
            s["analysis_window"].pop("source_media_links")
            s["finding_candidates"].pop("source_media_provenance_link")
        s["provenance_index"].pop("source_media_links")
        s["gap_inputs"]["media_event_link_available"] = False
        for f in s["finding_candidates"]["exact_media_duplicate"]["items"]:
            f["technical_basis"]["projection_policy_version"] = "1.0.0"
    return values


def test_frozen_legacy_markdown_byte_identical():
    inputs = json.loads((LEGACY / "snapshots.json").read_bytes())
    expected = (LEGACY / "report.md").read_bytes()
    for order in (inputs, inputs[::-1]):
        model = report.consolidate_snapshots(order)
        assert model.metadata["report_policy_version"] == "1.0.0"
        assert report.render_markdown(model).encode("utf-8") == expected


def test_version_dispatch_and_legacy_order(report_set):
    previous = report.consolidate_snapshots(legacy(report_set))
    current = report.consolidate_snapshots(report_set)
    assert current.metadata["report_policy_version"] == "1.1.0"
    assert [
        (f.finding_id, f.candidate_type, f.statement, f.provenance_basis)
        for f in current.findings[: len(previous.findings)]
    ] == [
        (f.finding_id, f.candidate_type, f.statement, f.provenance_basis) for f in previous.findings
    ]
    added = current.findings[len(previous.findings) :]
    assert len(added) == 5
    assert all(f.candidate_type == "source_media_provenance_link" for f in added)
    assert [w.window_id for w in previous.windows] == [w.window_id for w in current.windows]
    assert [w.scope for w in previous.windows] == [w.scope for w in current.windows]
    with pytest.raises(EvidenceError, match="REPORT_MIXED_SNAPSHOT_VERSIONS"):
        report.consolidate_snapshots([legacy(report_set)[0], report_set[1]])


@pytest.mark.parametrize("version", ["0.0.0", "1.2.0", "2.0.0", None, 1, {}])
def test_unknown_version_rejected(report_set, version):
    report_set[0]["snapshot"]["snapshot_version"] = version
    with pytest.raises(EvidenceError, match="REPORT_UNSUPPORTED_SNAPSHOT_VERSION"):
        report.consolidate_snapshots(report_set)


def test_statuses_projection_and_raw_exclusion(report_set):
    anchor, window, unsupported = report_set
    assert anchor["analysis_window"] is None
    links = window["analysis_window"]["source_media_links"]
    assert links["summary"]["status_counts"] == {
        "LINK_EXACT_MEDIA_CONTENT": 4,
        "LINK_ARCHIVE_MEMBER_ONLY": 1,
        "NO_CATALOG_MEMBER_MATCH": 1,
        "NO_SOURCE_MEDIA_REFERENCE": 1,
        "UNSUPPORTED_SOURCE_REFERENCE_TYPE": 1,
    }
    assert unsupported["finding_candidates"]["source_media_provenance_link"]["returned"] == 0
    assert unsupported["analysis_window"]["source_media_links"]["summary"]["status_counts"] == {
        "UNSUPPORTED_SOURCE_REFERENCE_TYPE": 1
    }
    encoded = json.dumps(links)
    for forbidden in (
        "reference_value",
        "member_path",
        "media/a.jpg",
        "media/video.mp4",
        "payload",
        "Synthetic attachment marker",
        "synthetic-thread",
    ):
        assert forbidden not in encoded
    for item in links["items"]:
        assert item["resolution"]["classification"] == "DERIVED"
        if item["source_reference"]:
            assert item["source_reference"]["classification"] == "OBSERVED"


def test_snapshot_same_connection_scope_determinism_and_integrity(link_case, monkeypatch):
    before = (link_case / "database/evidence.db").read_bytes()
    connections = []
    captured = []
    primitive = snapshot.source_links_in_snapshot

    @contextmanager
    def opener(root):
        with read_catalog(root) as connection:
            connections.append(connection)
            yield connection

    def query(paths, connection, **kwargs):
        assert connection.in_transaction()
        assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 1
        assert "max_delta_seconds" not in kwargs
        captured.append((connection, kwargs))
        return primitive(paths, connection, **kwargs)

    monkeypatch.setattr(snapshot, "read_catalog", opener)
    monkeypatch.setattr(snapshot, "source_links_in_snapshot", query)
    monkeypatch.setattr(source_links, "read_catalog", Mock(side_effect=AssertionError("extra DB")))
    kwargs = WINDOW | {"platform": "meta", "event_kind": "content.activity"}
    first = value(link_case, **kwargs)
    second = value(link_case, **kwargs)
    assert first == second
    assert len(connections) == len(captured) == 2
    assert all(c is seen[0] for c, seen in zip(connections, captured, strict=True))
    assert captured[0][1] == {
        "start_utc": "2024-01-01T00:00:00.000000Z",
        "end_utc": "2024-01-01T00:01:00.000000Z",
        "platform": "meta",
        "event_kind": "content.activity",
        "limit": 1000,
    }
    assert (link_case / "database/evidence.db").read_bytes() == before
    assert first["consistency"]["atomic_database_filesystem"] is False


def test_primitive_preserves_public_8a4_output(link_case):
    public = source_links.query_source_links(link_case, start=START, end=END)
    with read_catalog(link_case) as connection:
        inner = source_links.source_links_in_snapshot(
            CasePaths.load(link_case),
            connection,
            start_utc=public["scope"]["start"],
            end_utc=public["scope"]["end"],
            platform=None,
            event_kind=None,
            limit=500,
        )
    assert inner == public


@pytest.mark.parametrize("limit", [1, 3, 4, 6, 7, 8])
def test_prefix_full_counts_and_positive_findings(link_case, monkeypatch, limit):
    full = value(link_case, **WINDOW)
    monkeypatch.setattr(snapshot, "SOURCE_MEDIA_LIMIT", limit)
    limited = value(link_case, **WINDOW)
    links = limited["analysis_window"]["source_media_links"]
    whole = full["analysis_window"]["source_media_links"]
    assert links["items"] == whole["items"][:limit]
    assert links["summary"]["matched_total"] == 8
    assert links["summary"]["status_counts"] == whole["summary"]["status_counts"]
    assert links["summary"]["truncated"] == (limit < 8)
    findings = limited["finding_candidates"]["source_media_provenance_link"]
    assert findings["total"] == 5
    assert findings["returned"] == sum(
        i["resolution"]["status"] in report.SOURCE_MEDIA_POSITIVE for i in links["items"]
    )
    report.validate_snapshot(limited)


def test_human_report_privacy_semantics_and_determinism(report_set, monkeypatch):
    forbidden = Mock(side_effect=AssertionError("renderer accessed evidence/filesystem"))
    monkeypatch.setattr(snapshot, "report_snapshot", forbidden)
    monkeypatch.setattr(source_links, "query_source_links", forbidden)
    monkeypatch.setattr(source_links, "source_links_in_snapshot", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    model = report.consolidate_snapshots(report_set)
    text = report.render_markdown(model)
    for order in permutations(report_set):
        assert report.render_markdown(report.consolidate_snapshots(order)).encode() == text.encode()
    assert len(re.findall(r"^## \d+\.", text, re.M)) == 20
    assert "cobertura de source-media linkage permanece parcial" in text
    assert "não possui vínculo aprovado" not in text
    assert "sem vínculo media-event aprovado" not in text
    assert "ocorrências catalogadas do mesmo conteúdo exato" in text
    assert "não número de envios, publicações, destinatários ou ações humanas" in text
    assert "sem correspondência em ExactMediaContent sob a policy atual" in text
    assert "SOURCE_LIMITATION" in text
    assert "SPECIFIC_TECHNICAL_BASIS" not in text
    for token in (
        "reference_value",
        "media/a.jpg",
        "media/video.mp4",
        "synthetic-thread",
        "Synthetic participant",
        "Synthetic attachment marker",
        "member_path",
    ):
        assert token not in text
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f-]{27,}|[0-9a-f]{64}", text)
    for finding in model.findings:
        if finding.candidate_type == "source_media_provenance_link":
            assert finding.provenance_basis.pointer.startswith(
                "analysis_window.source_media_links.items["
            )
    forbidden.assert_not_called()


def test_no_link_wording_is_limited_to_inputs(report_set):
    model = report.consolidate_snapshots([report_set[0], report_set[2]])
    assert not any(f.candidate_type == "source_media_provenance_link" for f in model.findings)
    assert "Nenhum link source-media aplicável foi retornado no conjunto" in report.render_markdown(
        model
    )


@pytest.mark.parametrize(
    "change",
    [
        "raw_uri",
        "member_path",
        "bad_status",
        "classification",
        "bytes",
        "content_size",
        "occurrence_bool",
        "scope",
        "radius",
        "counts",
        "pointer",
        "finding",
        "policy",
        "content_format",
        "reference_locator",
        "missing_resolution",
    ],
)
def test_malformed_source_media_rejected(report_set, change):
    s = report_set[1]
    links = s["analysis_window"]["source_media_links"]
    item = links["items"][0]
    if change == "raw_uri":
        item["source_reference"]["reference_value"] = "synthetic-private-uri"
    elif change == "member_path":
        item["resolution"]["member_path"] = "synthetic-private-path"
    elif change == "bad_status":
        item["resolution"]["status"] = "PUBLISHED"
    elif change == "classification":
        item["source_reference"]["classification"] = "REPORTED"
    elif change == "bytes":
        item["resolution"]["bytes_verified"] = False
    elif change == "content_size":
        item["resolution"]["exact_media_content"]["size_bytes"] += 1
    elif change == "occurrence_bool":
        item["resolution"]["exact_media_content"]["occurrence_count"] = True
    elif change == "scope":
        links["scope"]["platform"] = "apple"
    elif change == "radius":
        links["scope"]["max_delta_seconds"] = 10
    elif change == "counts":
        links["summary"]["status_counts"]["LINK_EXACT_MEDIA_CONTENT"] += 1
    elif change == "pointer":
        s["provenance_index"]["source_media_links"][0]["pointer"] = "wrong"
    elif change == "finding":
        s["finding_candidates"]["source_media_provenance_link"]["items"][0]["references"][
            "source_media_item_index"
        ] = 7
    elif change == "policy":
        links["policy"]["policy_version"] = "2.0.0"
    elif change == "content_format":
        item["resolution"]["exact_media_content"]["media_format"] = "private-value"
    elif change == "reference_locator":
        item["source_reference"]["source_field_locator"] = "C:/private"
    else:
        item.pop("resolution")
    with pytest.raises(EvidenceError):
        report.consolidate_snapshots(report_set)


def test_fixture_is_unchanged_by_rendering():
    before = hashlib.sha256((LEGACY / "snapshots.json").read_bytes()).digest()
    report.consolidate_snapshots(json.loads((LEGACY / "snapshots.json").read_bytes()))
    assert hashlib.sha256((LEGACY / "snapshots.json").read_bytes()).digest() == before
