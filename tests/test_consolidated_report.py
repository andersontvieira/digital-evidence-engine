"""Entirely synthetic snapshot inputs; the renderer has no catalog dependency."""

import json
import re
from copy import deepcopy
from dataclasses import asdict
from itertools import permutations
from unittest.mock import Mock

import pytest
from typer._click.utils import strip_ansi
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.reports import consolidated as report
from evidence_engine.reports.snapshot import report_snapshot
from tests.perceptual_samples import encoded, pattern
from tests.test_media_inventory import tree_state
from tests.test_temporal_overlap import END, START, group
from tests.test_temporal_overlap import catalog as catalog


def json_value(value):
    return json.loads(json.dumps(value))


@pytest.fixture
def snapshots(catalog):
    for name in ("synthetic-first.png", "synthetic-copy.png"):
        (catalog.root / "originals" / name).write_bytes(encoded(pattern()))
    ingest(catalog.root)
    group(catalog, "device", [0, 1, 2], "synthetic-device")
    group(catalog, "network", [1, 2, 3], "synthetic-network")
    anchor = json_value(asdict(report_snapshot(catalog.root)))
    window = json_value(
        asdict(report_snapshot(catalog.root, start=START, end=END, max_delta_seconds=10))
    )
    filtered = json_value(
        asdict(
            report_snapshot(
                catalog.root, start=START, end=END, max_delta_seconds=1, platform="meta"
            )
        )
    )
    return anchor, window, filtered


def write_snapshots(tmp_path, snapshots):
    paths = []
    for index, value in enumerate(snapshots):
        path = tmp_path / f"synthetic-input-{index}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths.append(path)
    return paths


def invoke(paths):
    return CliRunner().invoke(
        app,
        ["report", "consolidated", *(arg for path in paths for arg in ("--snapshot", str(path)))],
    )


def test_twenty_sections_title_anchor_and_all_findings(snapshots):
    model = report.consolidate_snapshots(snapshots)
    text = report.render_markdown(model)
    assert text.startswith("# " + report.TITLE + "\n")
    assert re.findall(r"^## (\d+)\. ", text, re.M) == [str(i) for i in range(1, 21)]
    assert all(f"## {i}. {title}" in text for i, title in enumerate(report.SECTIONS, 1))
    expected = snapshots[0]["finding_candidates"]["exact_media_duplicate"]["returned"]
    expected += sum(
        s["finding_candidates"][k]["returned"] for s in snapshots[1:] for k in report.WINDOW_TYPES
    )
    assert len(model.findings) == expected
    assert [f.finding_id for f in model.findings] == [f"F-{i:03d}" for i in range(1, expected + 1)]
    assert [w.window_id for w in model.windows] == ["W-001", "W-002"]
    assert all(f.classification == "DERIVED" for f in model.findings)
    assert sum(f.candidate_type == "exact_media_duplicate" for f in model.findings) == 1
    assert "Laudo Pericial" not in text and "Perícia Digital Certificada" not in text


def test_input_order_and_model_are_deterministic_without_mutation(snapshots):
    before = deepcopy(snapshots)
    expected = report.consolidate_snapshots(snapshots)
    for order in permutations(snapshots):
        result = report.consolidate_snapshots(order)
        assert result == expected
        assert report.render_markdown(result).encode() == report.render_markdown(expected).encode()
    assert snapshots == before


def test_cli_repeat_utf8_lf_and_no_write(tmp_path, snapshots):
    paths = write_snapshots(tmp_path, snapshots)
    before = tree_state(tmp_path)
    a, b = invoke(paths), invoke(paths[::-1])
    assert a.exit_code == b.exit_code == 0, a.output
    assert a.stdout_bytes == b.stdout_bytes
    assert b"\r" not in a.stdout_bytes and a.stdout_bytes.endswith(b"\n")
    assert "Relatório Técnico" in a.stdout_bytes.decode("utf-8")
    assert tree_state(tmp_path) == before
    assert str(tmp_path) not in a.stdout


@pytest.mark.parametrize(
    "field,value",
    [
        ("snapshot_id", "wrong"),
        ("snapshot_version", "9.0.0"),
        ("evidence_schema_version", 6),
        ("evidence_schema_version", True),
        ("feature_class", "OBSERVED"),
        ("case_id", None),
        ("engine_version", "not a version"),
    ],
)
def test_invalid_metadata(snapshots, field, value):
    anchor = deepcopy(snapshots[0])
    anchor["snapshot"][field] = value
    with pytest.raises(EvidenceError):
        report.consolidate_snapshots([anchor])


@pytest.mark.parametrize(
    "section",
    [
        "snapshot",
        "consistency",
        "scope",
        "policies",
        "inventory",
        "coverage",
        "current_events",
        "exact_candidates",
        "media",
        "analysis_window",
        "finding_candidates",
        "gap_inputs",
        "provenance_index",
    ],
)
def test_missing_required_section(snapshots, section):
    anchor = deepcopy(snapshots[0])
    del anchor[section]
    with pytest.raises(EvidenceError, match="REPORT_INVALID_SNAPSHOT"):
        report.consolidate_snapshots([anchor])


@pytest.mark.parametrize("value", [None, [], "invalid", True, 12])
def test_bad_root_type(value):
    with pytest.raises(EvidenceError):
        report.validate_snapshot(value)


@pytest.mark.parametrize("content", [b"{", b"[]", b"\xff", b'{"x":NaN}', b'{"x":1,"x":2}'])
def test_invalid_json(tmp_path, content):
    path = tmp_path / "synthetic-invalid.json"
    path.write_bytes(content)
    result = invoke([path])
    assert result.exit_code == 2 and not result.stdout
    assert str(path) not in result.output


def test_missing_and_excessive_inputs(tmp_path, monkeypatch):
    assert invoke([]).exit_code == 2
    assert invoke([tmp_path / "missing.json"]).exit_code == 2
    with pytest.raises(EvidenceError, match="REPORT_SNAPSHOT_COUNT"):
        report.load_snapshots([tmp_path / "missing.json"] * 21)
    monkeypatch.setattr(report, "MAX_SNAPSHOT_BYTES", 1)
    path = tmp_path / "synthetic-too-large.json"
    path.write_text("{}")
    with pytest.raises(EvidenceError, match="REPORT_SNAPSHOT_SIZE_LIMIT"):
        report.load_snapshots([path])


def test_exactly_one_anchor(snapshots):
    for values in (snapshots[1:], [snapshots[0], deepcopy(snapshots[0])]):
        with pytest.raises(EvidenceError, match="REPORT_ANCHOR_COUNT"):
            report.consolidate_snapshots(values)


@pytest.mark.parametrize(
    "field,value", [("case_id", "synthetic-different-case"), ("engine_version", "9.8.7")]
)
def test_different_metadata_in_set(snapshots, field, value):
    anchor, window, _ = deepcopy(snapshots)
    window["snapshot"][field] = value
    with pytest.raises(EvidenceError, match="REPORT_SNAPSHOT_SET_CHANGED"):
        report.consolidate_snapshots([anchor, window])


@pytest.mark.parametrize("section", report.CASE_WIDE)
def test_changed_case_wide_section(snapshots, section):
    anchor, window, _ = deepcopy(snapshots)
    window[section]["synthetic_extra_metadata"] = 1
    with pytest.raises(EvidenceError, match="REPORT_SNAPSHOT_SET_CHANGED"):
        report.consolidate_snapshots([anchor, window])


@pytest.mark.parametrize("field", report.GAP_FIELDS)
def test_changed_case_wide_gap_input_rejected(snapshots, field):
    anchor, window, _ = deepcopy(snapshots)
    value = window["gap_inputs"][field]
    if type(value) is bool:
        window["gap_inputs"][field] = not value
    elif type(value) is list:
        value.append("SYNTHETIC_CAPABILITY_LIMIT")
    else:
        value["synthetic_extra_metadata"] = 1
    with pytest.raises(EvidenceError, match="REPORT_SNAPSHOT_SET_CHANGED"):
        report.consolidate_snapshots([anchor, window])


def test_duplicate_semantic_windows(snapshots):
    anchor, window, _ = deepcopy(snapshots)
    duplicate = deepcopy(window)
    for scope in (
        duplicate["analysis_window"]["window"],
        duplicate["analysis_window"]["temporal_proximity"]["window"],
        duplicate["analysis_window"]["temporal_exact_overlap"]["window"],
        duplicate["analysis_window"]["source_media_links"]["scope"],
    ):
        scope["start"] = START
        scope["end"] = END
    with pytest.raises(EvidenceError, match="REPORT_DUPLICATE_ANALYSIS_WINDOW"):
        report.consolidate_snapshots([anchor, window, duplicate])


def test_no_database_case_or_media_access(tmp_path, snapshots, monkeypatch):
    paths = write_snapshots(tmp_path, snapshots)
    forbidden = Mock(side_effect=AssertionError("renderer opened evidence infrastructure"))
    for target in (
        "evidence_engine.query.catalog.read_catalog",
        "evidence_engine.storage.database.open_database",
        "evidence_engine.media.inventory.inventory_media",
        "evidence_engine.media.perceptual.perceptual_hashes",
        "evidence_engine.ingest.generic.hashing.original_reader",
        "evidence_engine.reports.snapshot.report_snapshot",
        "evidence_engine.cli.report.report_snapshot",
        "sqlite3.connect",
    ):
        monkeypatch.setattr(target, forbidden)
    assert invoke(paths).exit_code == 0
    forbidden.assert_not_called()
    assert not any(
        token in report.__dict__
        for token in ("read_catalog", "CasePaths", "report_snapshot", "sqlite3")
    )


def test_templates_include_all_overlap_distributions_and_neither(snapshots):
    model = report.consolidate_snapshots(snapshots)
    statements = [f.statement for f in model.findings]
    assert any("conteúdo byte a byte idêntico" in s.lower() for s in statements)
    assert any("do tipo device" in s for s in statements)
    assert any("microssegundos" in s for s in statements)
    assert any(
        "device" in s and "network" in s and "possui membership técnica" in s for s in statements
    )
    assert any("não possui membership exata compartilhada retornada" in s for s in statements)
    d = model.windows[0].overlap_distribution
    assert all(d[k] > 0 for k in ("device", "network", "both", "neither"))
    text = report.render_markdown(model)
    for forbidden in (
        "same user",
        "mesmo usuário",
        "mesmo aparelho",
        "same device",
        "culpado",
        "fraude",
        "crime",
        "confidence",
        "score",
    ):
        assert forbidden not in text
    assert "PREFIXO" in text and "matched_pairs" in text


def test_findings_and_counts_cannot_disagree(snapshots):
    anchor, window, _ = deepcopy(snapshots)
    window["finding_candidates"]["temporal_pair_candidate"]["items"][0]["references"][
        "delta_microseconds"
    ] += 1
    with pytest.raises(EvidenceError):
        report.consolidate_snapshots([anchor, window])
    anchor["current_events"]["total"] = True
    with pytest.raises(EvidenceError):
        report.consolidate_snapshots([anchor])


def test_truncation_retained_in_window_and_findings(snapshots):
    anchor, window, _ = deepcopy(snapshots)
    for key, kind in (
        ("temporal_proximity", "temporal_pair_candidate"),
        ("temporal_exact_overlap", "temporal_exact_overlap_candidate"),
    ):
        c = window["analysis_window"][key]
        c["items"] = c["items"][:1]
        c["returned_pairs"] = 1
        c["truncated"] = True
        f = window["finding_candidates"][kind]
        f["items"] = f["items"][:1]
        f["returned"] = 1
        f["truncated"] = True
    window["gap_inputs"]["truncated_components"] = ["temporal_exact_overlap", "temporal_proximity"]
    model = report.consolidate_snapshots([anchor, window])
    assert all(
        "truncated=true" in f.limitations
        for f in model.findings
        if f.candidate_type.startswith("temporal")
    )
    assert "Há truncamento nesta janela" in report.render_markdown(model)


def test_gap_rules_b_c_d_and_no_a_e_f(snapshots):
    anchor = deepcopy(snapshots[0])
    anchor["gap_inputs"]["parser_runs"]["UNSUPPORTED"] = 2
    anchor["coverage"]["parser_runs"]["items"].append(
        {
            "parser_id": "synthetic.parser",
            "parser_version": "1.0.0",
            "status": "UNSUPPORTED",
            "count": 2,
        }
    )
    current = anchor["current_events"]
    current["dated"] -= 1
    current["undated"] += 1
    row = next(r for r in current["by_platform_event_kind"] if r["dated"])
    row["dated"] -= 1
    row["undated"] += 1
    anchor["gap_inputs"]["undated_current_events"]["count"] += 1
    anchor["inventory"]["tables"]["normalized_events"] += 4
    model = report.consolidate_snapshots([anchor])
    assert [g.category for g in model.gaps] == ["B", "C", "D"]
    assert [g.gap_id for g in model.gaps] == ["G-001", "G-002", "G-003"]
    text = report.render_markdown(model)
    assert f"normalized_events: {anchor['inventory']['tables']['normalized_events']}" in text
    assert f": {current['total']}. Current events datados" in text
    assert "WhatsApp é necessário" not in text


def test_failed_and_whatsapp_absence_do_not_generate_gap_b(snapshots):
    anchor = deepcopy(snapshots[0])
    anchor["gap_inputs"]["parser_runs"]["FAILED"] = 1
    anchor["coverage"]["parser_runs"]["items"].append(
        {"parser_id": "synthetic.parser", "parser_version": "1.0.0", "status": "FAILED", "count": 1}
    )
    model = report.consolidate_snapshots([anchor])
    assert [g.category for g in model.gaps] == ["D"]
    assert "Não há parser WhatsApp implementado nesta versão." in report.render_markdown(model)


def test_empty_catalog_anchor_is_usable(case_root):
    ingest(case_root)
    anchor = json_value(asdict(report_snapshot(case_root)))
    model = report.consolidate_snapshots([anchor])
    assert not model.findings and not model.gaps and not model.windows
    assert len(re.findall(r"^## \d+\.", report.render_markdown(model), re.M)) == 20


def test_privacy_and_logical_pointers(snapshots, tmp_path):
    snapshots = deepcopy(snapshots)
    marker = "SYNTHETIC_PRIVATE_MESSAGE_DO_NOT_RENDER"
    for value in snapshots:
        value["provenance_index"]["synthetic_unused_payload"] = marker
    text = report.consolidated_report(write_snapshots(tmp_path, snapshots))
    assert marker not in text and str(tmp_path) not in text
    source = json.dumps(snapshots)
    secrets = re.findall(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}|\b[a-f0-9]{64}\b", source)
    assert secrets and all(value not in text for value in secrets)
    assert "synthetic-candidate" not in text
    for f in report.consolidate_snapshots(snapshots).findings:
        assert f.provenance_basis.pointer in text.replace("\\_", "_")


@pytest.mark.parametrize(
    "malicious", ["/case/originals/secret", "x\n## Injected", "x|value", "name@example.test"]
)
def test_unsafe_display_filters_rejected(snapshots, malicious):
    anchor, window, _ = deepcopy(snapshots)
    for bounds in (
        window["analysis_window"]["window"],
        window["analysis_window"]["temporal_proximity"]["window"],
        window["analysis_window"]["temporal_exact_overlap"]["window"],
    ):
        bounds["platform"] = malicious
    with pytest.raises(EvidenceError, match="REPORT_UNSAFE_DISPLAY_VALUE"):
        report.consolidate_snapshots([anchor, window])


def test_cli_help_has_snapshot_and_no_case_root():
    result = CliRunner().invoke(app, ["report", "consolidated", "--help"])
    assert result.exit_code == 0
    output = strip_ansi(result.stdout)
    assert "--snapshot" in output and "--case-root" not in output
