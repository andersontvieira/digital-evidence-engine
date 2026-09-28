"""Synthetic captured bytes only; reuse the frozen pre-8A4.1 report fixture."""

import ast
import builtins
import hashlib
import inspect
import json
import re
from copy import deepcopy
from dataclasses import FrozenInstanceError
from itertools import permutations
from pathlib import Path

import pytest
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.dossier import validation as dossier
from evidence_engine.errors import EvidenceError
from evidence_engine.reports import consolidated as report

LEGACY = Path(__file__).parent / "fixtures/report_legacy"


def legacy_snapshots():
    return json.loads((LEGACY / "snapshots.json").read_bytes())


def current_snapshots():
    """Test-only 1.1 projection with empty source-media coverage, no case query."""
    values = legacy_snapshots()
    policy = {"policy_id": "source_media.provenance_link", "policy_version": "1.0.0"}
    for snapshot in values:
        snapshot["snapshot"]["snapshot_version"] = "1.1.0"
        snapshot["policies"]["source_media_links"] = deepcopy(policy)
        snapshot["scope"]["limits"]["source_media_items"] = 1000
        snapshot["gap_inputs"].pop("media_event_link_available")
        snapshot["provenance_index"]["source_media_links"] = []
        for finding in snapshot["finding_candidates"]["exact_media_duplicate"]["items"]:
            finding["technical_basis"]["projection_policy_version"] = "1.1.0"
        window = snapshot["analysis_window"]
        if window is None:
            continue
        snapshot["scope"]["executed_components"].append("source_media_links")
        current_policy = snapshot["policies"]["current_event_policy"]
        window["source_media_links"] = {
            "policy": policy
            | {
                "feature_class": "DERIVED",
                "relation_kind": "source_media.exact_provenance_link",
                "current_event_policy_id": current_policy["policy_id"],
                "current_event_policy_version": current_policy["policy_version"],
            },
            "scope": window["window"] | {"limit": 1000},
            "consistency": {
                "database_consistency": "single_read_snapshot",
                "database_scope": "events_references_provenance_members_and_media_inventory",
                "filesystem_consistency": "verified_stable_reads",
                "atomic_database_filesystem": False,
                "exact_media_contents_consulted": False,
            },
            "summary": {
                "unit": "event_source_reference_items",
                "status_counts_scope": "all_matched_items",
                "status_counts": {},
                "matched_total": 0,
                "returned": 0,
                "truncated": False,
                "eligible_events": 0,
                "source_references": 0,
                "undated_current_events": snapshot["current_events"]["undated"],
            },
            "items": [],
        }
        snapshot["finding_candidates"]["source_media_provenance_link"] = {
            "unit": "candidate_projections",
            "total": 0,
            "returned": 0,
            "truncated": False,
            "items": [],
        }
    return values


def report_bytes(values):
    return report.render_markdown(report.consolidate_snapshots(values)).encode("utf-8")


def captured(values):
    return tuple(
        dossier.CapturedSnapshot(f"synthetic-{i}", json.dumps(value).encode("utf-8"))
        for i, value in enumerate(values)
    )


def validate(values, content=None):
    return dossier.validate_canonical_set(
        report_content=report_bytes(values) if content is None else content,
        snapshots=captured(values),
    )


def rejects(values, code="CANONICAL_SET_INVALID", content=b"opaque synthetic report"):
    with pytest.raises(EvidenceError) as error:
        validate(values, content)
    assert str(error.value) == f"DOSSIER_{code}"


@pytest.mark.parametrize("size", [1, 2, 3])
def test_valid_sets_permutation_labels_and_preserved_bytes(size):
    values = current_snapshots()[:size]
    before = deepcopy(values)
    inputs = captured(values)
    content = report_bytes(values)
    expected = dossier.validate_canonical_set(report_content=content, snapshots=inputs)
    assert expected.report_content is content
    assert expected.model == report.consolidate_snapshots(values)
    assert expected.snapshots[0].reference == "Anchor"
    assert [v.reference for v in expected.snapshots[1:]] == [
        w.window_id for w in expected.model.windows
    ]
    for order in permutations(inputs):
        result = dossier.validate_canonical_set(report_content=content, snapshots=order)
        assert result == expected
        assert {s.local_label: s.snapshot for s in result.snapshots} == {
            item.local_label: json.loads(item.content) for item in inputs
        }
    assert values == before  # Includes unchanged arrays inside the selected snapshots.
    with pytest.raises(FrozenInstanceError):
        expected.report_content = b"changed"
    with pytest.raises(FrozenInstanceError):
        expected.snapshots[0].local_label = "changed"


def test_frozen_legacy_and_pre_refactor_current_bytes():
    old = legacy_snapshots()
    current = current_snapshots()
    for values in (old, current):
        model = report.build_consolidated_model(values)
        assert model == report.consolidate_snapshots(values)
        assert model == report.build_consolidated_model(values[::-1])
        text = report.render_markdown(model)
        assert len(re.findall(r"^## \d+\.", text, re.M)) == 20
        assert [f.finding_id for f in model.findings] == [
            f"F-{i:03d}" for i in range(1, len(model.findings) + 1)
        ]
        assert [w.window_id for w in model.windows] == ["W-001", "W-002"]
        assert [g.gap_id for g in model.gaps] == [
            f"G-{i:03d}" for i in range(1, len(model.gaps) + 1)
        ]
    assert report_bytes(old) == (LEGACY / "report.md").read_bytes()
    # Recorded BEFORE the 8B1-B product refactor using this synthetic 1.1 fixture.
    assert len(report_bytes(current)) == 33632
    assert hashlib.sha256(report_bytes(current)).hexdigest() == (
        "2716b14473b8480ace50b57b0ad377d7443ffbd917d8baf33def6c3d08f87ee7"
    )


def many_windows():
    anchor, window, _ = current_snapshots()
    values = [anchor]
    for index in range(20):
        copy = deepcopy(window)
        w = copy["analysis_window"]
        for scope in (
            w["window"],
            w["temporal_proximity"]["window"],
            w["temporal_exact_overlap"]["window"],
            w["source_media_links"]["scope"],
        ):
            scope["end"] = f"{2030 + index}-01-01T00:00:00Z"
        values.append(copy)
    return values


def test_over_twenty_pure_core_and_dossier_accept_legacy_apis_reject(tmp_path, monkeypatch):
    values = many_windows()
    model = report.build_consolidated_model(values)
    assert len(model.windows) == 20
    content = report.render_markdown(model).encode("utf-8")
    result = validate(values, content)
    assert len(result.snapshots) == 21 and result.model == model
    assert report.MAX_SNAPSHOTS == 20
    with pytest.raises(EvidenceError, match="^REPORT_SNAPSHOT_COUNT$"):
        report.consolidate_snapshots(values)

    # Rejection must precede even the first file open; no test input file needed.
    def forbidden(*args, **kwargs):
        raise AssertionError("legacy count guard must precede open")

    monkeypatch.setattr(Path, "open", forbidden)
    paths = [tmp_path / f"synthetic-{i}.json" for i in range(21)]
    with pytest.raises(EvidenceError, match="^REPORT_SNAPSHOT_COUNT$"):
        report.load_snapshots(paths)
    cli = CliRunner().invoke(
        app, ["report", "consolidated", *[arg for p in paths for arg in ("--snapshot", str(p))]]
    )
    assert cli.exit_code == 2 and "REPORT_SNAPSHOT_COUNT" in cli.output
    assert not cli.stdout


def test_pure_core_still_requires_nonempty_input():
    with pytest.raises(EvidenceError, match="^REPORT_SNAPSHOT_COUNT$"):
        report.build_consolidated_model([])


def test_semantic_duplicate_window_normalizes_utc_only_for_comparison():
    values = current_snapshots()
    duplicate = deepcopy(values[1])
    window = duplicate["analysis_window"]
    for scope in (
        window["window"],
        window["temporal_proximity"]["window"],
        window["temporal_exact_overlap"]["window"],
        window["source_media_links"]["scope"],
    ):
        for bound in ("start", "end"):
            scope[bound] = scope[bound].replace("Z", ".000000Z")
    rejects([*values, duplicate])


@pytest.mark.parametrize(
    "change",
    [
        "empty",
        "no_anchor",
        "two_anchors",
        "duplicate_window",
        "case_wide",
        "policy",
        "schema",
        "case_id",
        "engine_version",
    ],
)
def test_invalid_canonical_sets(change):
    values = current_snapshots()
    if change == "empty":
        values = []
    elif change == "no_anchor":
        values = values[1:]
    elif change == "two_anchors":
        values.append(deepcopy(values[0]))
    elif change == "duplicate_window":
        values.append(deepcopy(values[1]))
    elif change == "case_wide":
        values[1]["inventory"]["tables"]["ingestion_runs"] += 1
    elif change == "policy":
        values[1]["policies"]["source_media_links"]["policy_version"] = "9.0.0"
    elif change == "schema":
        values[1]["snapshot"]["evidence_schema_version"] = 6
    else:
        values[1]["snapshot"][change] = "synthetic-other" if change == "case_id" else "9.0.0"
    rejects(values)


@pytest.mark.parametrize(
    "versions,code",
    [
        (["1.0.0"] * 3, "UNSUPPORTED_POLICY_VERSION"),
        (["9.0.0"] * 3, "UNSUPPORTED_POLICY_VERSION"),
        (["1.0.0", "1.1.0", "1.1.0"], "CANONICAL_SET_INVALID"),
        (["1.1.0", "9.0.0", "9.0.0"], "CANONICAL_SET_INVALID"),
        (["8.0.0", "9.0.0", "9.0.0"], "CANONICAL_SET_INVALID"),
    ],
)
def test_version_dispatch(versions, code):
    values = legacy_snapshots() if set(versions) == {"1.0.0"} else current_snapshots()
    for value, version in zip(values, versions, strict=True):
        value["snapshot"]["snapshot_version"] = version
    rejects(values, code)


@pytest.mark.parametrize(
    "raw",
    [
        b"{",
        b"[]",
        b"\xff",
        b"\xef\xbb\xbf{}",
        b'{"a":1,"a":2}',
        b'{"a":{"b":1,"b":2}}',
        b'{"a":NaN}',
        b'{"a":Infinity}',
        b'{"a":-Infinity}',
        b"{}",
    ],
)
def test_bad_json_and_legacy_decoder_error_parity(tmp_path, raw):
    path = tmp_path / "synthetic-snapshot.json"
    path.write_bytes(raw)
    with pytest.raises(EvidenceError) as decoded:
        report.decode_snapshot(raw)
    with pytest.raises(EvidenceError) as loaded:
        report.load_snapshots([path])
    assert str(decoded.value) == str(loaded.value)
    with pytest.raises(EvidenceError, match="^DOSSIER_CANONICAL_SET_INVALID$"):
        dossier.validate_canonical_set(
            report_content=b"opaque", snapshots=[dossier.CapturedSnapshot("anchor", raw)]
        )


def test_decoder_and_loader_valid_parity_and_size_limit(tmp_path, monkeypatch):
    for values in (legacy_snapshots(), current_snapshots()):
        data = json.dumps(values[0]).encode()
        path = tmp_path / "synthetic-anchor.json"
        path.write_bytes(data)
        monkeypatch.setattr(report, "MAX_SNAPSHOT_BYTES", len(data))
        assert report.load_snapshots([path]) == [report.decode_snapshot(data)] == [values[0]]
        monkeypatch.setattr(report, "MAX_SNAPSHOT_BYTES", len(data) - 1)
        with pytest.raises(EvidenceError, match="^REPORT_SNAPSHOT_SIZE_LIMIT$"):
            report.load_snapshots([path])


@pytest.mark.parametrize(
    "change", ["character", "space", "final_lf", "crlf", "bom", "opaque_markers", "order"]
)
def test_report_bytes_never_normalized_or_parsed(change):
    values = current_snapshots()
    original = report_bytes(values)
    changes = {
        "character": b"X" + original[1:],
        "space": original + b" ",
        "final_lf": original.rstrip(b"\n"),
        "crlf": original.replace(b"\n", b"\r\n"),
        "bom": b"\xef\xbb\xbf" + original,
        "opaque_markers": b"report.consolidated/1.1.0 F-001 W-001 G-001 approved",
        "order": b"\n".join(reversed(original.split(b"\n"))),
    }
    rejects(values, "CANONICAL_REPORT_MISMATCH", changes[change])


def test_missing_or_extra_window_report_fails():
    values = current_snapshots()
    rejects(values, "CANONICAL_REPORT_MISMATCH", report_bytes(values[:2]))
    rejects(values[:2], "CANONICAL_REPORT_MISMATCH", report_bytes(values))


def test_unselected_bytes_are_unknown_to_validator():
    values = current_snapshots()[:1]
    expected = validate(values)
    unrelated = b"unselected synthetic snapshot bytes"
    assert validate(values) == expected
    unrelated += b" changed"
    assert unrelated and validate(values) == expected


@pytest.mark.parametrize(
    "budget", ["MAX_SNAPSHOT_BYTES", "MAX_TOTAL_SNAPSHOT_BYTES", "MAX_CONSOLIDATED_REPORT_BYTES"]
)
def test_byte_budgets_at_boundary_and_one_over(monkeypatch, budget):
    values = current_snapshots()
    inputs = captured(values)
    content = report_bytes(values)
    size = {
        "MAX_SNAPSHOT_BYTES": max(len(i.content) for i in inputs),
        "MAX_TOTAL_SNAPSHOT_BYTES": sum(len(i.content) for i in inputs),
        "MAX_CONSOLIDATED_REPORT_BYTES": len(content),
    }[budget]
    monkeypatch.setattr(dossier, budget, size)
    dossier.validate_canonical_set(report_content=content, snapshots=inputs)
    monkeypatch.setattr(dossier, budget, size - 1)
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        dossier.validate_canonical_set(report_content=content, snapshots=inputs)


@pytest.mark.parametrize("error", [MemoryError, RecursionError])
@pytest.mark.parametrize(
    "phase", ["_decode_snapshot_json", "build_consolidated_model", "render_markdown"]
)
def test_resource_exhaustion_is_sanitized(monkeypatch, error, phase):
    inputs = captured(current_snapshots())

    def exhausted(*args, **kwargs):
        raise error("synthetic private marker")

    monkeypatch.setattr(dossier, phase, exhausted)
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        dossier.validate_canonical_set(report_content=b"opaque", snapshots=inputs)


def test_recursion_legacy_loader_semantics_preserved(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.json"
    path.write_bytes(b"{}")

    def exhausted(*args, **kwargs):
        raise RecursionError("synthetic private marker")

    monkeypatch.setattr(report.json, "loads", exhausted)
    with pytest.raises(EvidenceError, match="^REPORT_INVALID_JSON$"):
        report.load_snapshots([path])


def test_unsafe_display_maps_to_privacy():
    values = current_snapshots()
    values[1]["analysis_window"]["window"]["platform"] = "synthetic unsafe display"
    rejects(values, "PRIVACY_CONTRACT_VIOLATION")


def test_duplicate_labels_are_not_silently_merged():
    inputs = captured(current_snapshots())
    inputs = (inputs[0], dossier.CapturedSnapshot(inputs[0].local_label, inputs[1].content))
    with pytest.raises(EvidenceError, match="^DOSSIER_CANONICAL_SET_INVALID$"):
        dossier.validate_canonical_set(report_content=b"opaque", snapshots=inputs)


def test_pure_import_boundary_and_no_filesystem(monkeypatch):
    source = ast.parse(inspect.getsource(dossier))
    allowed = {
        "json",
        "math",
        "warnings",
        "io",
        "PIL",
        "evidence_engine.dossier",
        "evidence_engine.media.signatures",
        "collections.abc",
        "dataclasses",
        "evidence_engine.errors",
        "evidence_engine.reports.consolidated",
    }
    for node in ast.walk(source):
        if isinstance(node, ast.ImportFrom):
            assert node.module in allowed
        elif isinstance(node, ast.Import):
            assert all(alias.name in allowed for alias in node.names)
    values = current_snapshots()
    content, inputs = report_bytes(values), captured(values)

    def forbidden(*args, **kwargs):
        raise AssertionError("filesystem access forbidden")

    monkeypatch.setattr(builtins, "open", forbidden)
    for name in ("open", "stat", "lstat", "resolve"):
        monkeypatch.setattr(Path, name, forbidden)
    assert (
        dossier.validate_canonical_set(report_content=content, snapshots=inputs).report_content
        is content
    )
