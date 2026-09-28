"""Synthetic canonical inputs; human projection never captures selected files."""

import ast
import builtins
import inspect
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from pathlib import Path

import pytest

from evidence_engine.dossier import projection as p
from evidence_engine.dossier import rendering as r
from evidence_engine.errors import EvidenceError
from evidence_engine.reports import consolidated as report
from tests.test_dossier_canonical import captured, current_snapshots, many_windows, validate
from tests.test_dossier_selection import item, minimal, parse
from tests.test_report_media_links import report_set as report_set
from tests.test_source_media_links import link_case as link_case


def selection_document(canonical):
    value = minimal()
    value["canonical_inputs"] = [item("consolidated_report", "report")] + [
        item(label=s.local_label) for s in canonical.snapshots
    ]
    return value


@pytest.fixture
def canonical():
    return validate(current_snapshots())


def project(canonical, document=None):
    return p.project_dossier(
        selection=parse(selection_document(canonical) if document is None else document),
        canonical=canonical,
    )


def sections(content):
    parts = content.decode().split("\n## ")
    return {int(part.split(".", 1)[0]): part for part in parts[1:]}


@pytest.mark.parametrize(
    "group,role",
    [
        ("supplemental_inputs", "technical_review"),
        ("supplemental_inputs", "structured_support"),
        ("validation_artifacts", "validation_report"),
        ("visual_exhibits", "contextual_visual"),
    ],
)
def test_only_administrative_section_changes(canonical, group, role):
    document = selection_document(canonical)
    baseline = sections(r.render_dossier_markdown(project(canonical, document)))
    document[group] = [item(role, "synthetic-extra", "claims/likely-author-synthetic.private")]
    output = r.render_dossier_markdown(project(canonical, document))
    changed = sections(output)
    assert baseline[4] != changed[4]
    assert {k: v for k, v in baseline.items() if k != 4} == {
        k: v for k, v in changed.items() if k != 4
    }
    assert b"likely-author-synthetic" not in output
    assert b"Imagem sint" not in output
    for entry in document["canonical_inputs"] + document[group]:
        entry["expected_sha256"] = "a" * 64
        entry["input_reference"] = "other/private-claim-" + entry["local_label"]
    if group == "visual_exhibits":
        document[group][0]["display_caption"] = "Nota: contexto sintético alterado."
    assert r.render_dossier_markdown(project(canonical, document)) == output


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "duplicate", "report", "mapping", "label"]
)
def test_selection_canonical_consistency(canonical, mutation):
    selected = parse(selection_document(canonical))
    inputs = selected.canonical_inputs
    if mutation == "missing":
        selected = replace(selected, canonical_inputs=inputs[:-1])
    elif mutation == "extra":
        selected = replace(
            selected, canonical_inputs=inputs + (replace(inputs[-1], local_label="extra"),)
        )
    elif mutation == "duplicate":
        selected = replace(selected, canonical_inputs=inputs + (inputs[-1],))
    elif mutation == "report":
        selected = replace(
            selected, canonical_inputs=tuple(i for i in inputs if i.role != "consolidated_report")
        )
    elif mutation == "mapping":
        canonical = replace(canonical, snapshots=canonical.snapshots + (canonical.snapshots[-1],))
    else:
        canonical = replace(
            canonical,
            snapshots=(
                replace(canonical.snapshots[0], local_label="extra"),
                *canonical.snapshots[1:],
            ),
        )
    with pytest.raises(EvidenceError, match="^DOSSIER_CANONICAL_SET_INVALID$"):
        p.project_dossier(selection=selected, canonical=canonical)


def test_optionals_are_explicit_and_not_generated(canonical):
    document = selection_document(canonical)
    plain = sections(r.render_dossier_markdown(project(canonical, document)))
    assert "Data documental" not in plain[1] and "Referência opaca" not in plain[1]
    document.update(issued_date="2025-04-03", case_reference="synthetic-token")
    result = sections(r.render_dossier_markdown(project(canonical, document)))
    assert "2025-04-03" in result[1] and "synthetic-token" in result[1]
    assert "fornecida pelo operador" in result[1]
    assert "Não é tempo de evidência nem generated_at" in result[1]
    assert all(result[k] == plain[k] for k in range(2, 15))


def test_copy_boundary_all_nested_values_are_immutable(canonical):
    projected = project(canonical)
    saved = deepcopy(projected)
    output = r.render_dossier_markdown(projected)
    canonical.model.metadata.clear()
    canonical.model.methodology.clear()
    canonical.model.coverage.clear()
    canonical.model.technical_counts.clear()
    canonical.model.media_summary.clear()
    canonical.model.evidence_scope.clear()
    for window in canonical.model.windows:
        window.scope.clear()
        window.component_counts.clear()
    for finding in canonical.model.findings:
        finding.technical_basis.clear()
    for snapshot in canonical.snapshots:
        snapshot.snapshot.clear()
    assert projected == saved and r.render_dossier_markdown(projected) == output

    def visit(value):
        assert not isinstance(value, (dict, list, set))
        if is_dataclass(value):
            for field in fields(value):
                with pytest.raises(FrozenInstanceError):
                    setattr(value, field.name, None)
                visit(getattr(value, field.name))
        elif isinstance(value, tuple):
            for child in value:
                visit(child)
        else:
            assert isinstance(value, (str, int, bool, type(None)))

    visit(projected)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("platform", "<unsafe>"),
        ("event_kind", "raw|unsafe"),
        ("platform", "synthetic@example.invalid"),
        ("event_kind", "a" * 64),
        ("occurred_at_utc", "not-utc"),
    ],
)
def test_event_display_privacy_mapping(canonical, field, bad):
    event = canonical.snapshots[1].snapshot["analysis_window"]["incident_window"]["items"][0]
    event[field] = bad
    if field != "occurred_at_utc":
        # Prove the historical canonical validator really accepts this raw event field.
        report.validate_snapshot(canonical.snapshots[1].snapshot)
    with pytest.raises(EvidenceError, match="^DOSSIER_PRIVACY_CONTRACT_VIOLATION$"):
        project(canonical)


def test_chronology_keeps_window_order_overlap_and_original_positions(canonical):
    projected = project(canonical)
    assert [w.window_id for w in projected.windows] == [
        w.window_id for w in canonical.model.windows
    ]
    ids_by_window = []
    for window, snapshot in zip(projected.windows, canonical.snapshots[1:], strict=True):
        raw = snapshot.snapshot["analysis_window"]["incident_window"]["items"]
        ids_by_window.append({row["event_id"] for row in raw})
        assert len(window.incidents) == len(raw)
        for index, (row, event) in enumerate(zip(window.incidents, raw, strict=True)):
            assert (row.occurred_at_utc, row.platform, row.event_kind) == (
                report._utc(event["occurred_at_utc"]),
                event["platform"],
                event["event_kind"],
            )
            assert row.pointer == f"analysis_window.incident_window.items[{index}]"
            assert {f.name for f in fields(row)} == {
                "occurred_at_utc",
                "platform",
                "event_kind",
                "pointer",
            }
    assert ids_by_window[0] & ids_by_window[1]
    text = sections(r.render_dossier_markdown(projected))[6]
    assert text.index("### W-001") < text.index("### W-002")
    groups = text.split("### ")[1:]
    assert len(groups) == len(projected.windows)
    for group, window, snapshot in zip(
        groups, projected.windows, canonical.snapshots[1:], strict=True
    ):
        assert group.startswith(window.window_id + "\n")
        scope_row = (
            f"| {window.start} | {window.end} | {window.platform or 'sem filtro'} | "
            f"{r.escape_text(window.event_kind or 'sem filtro')} | {window.max_delta_seconds} | "
            f"{window.undated_current_events} | {window.eligible_events} |"
        )
        assert scope_row in group
        counts_header = "| Componente | Unidade | Total | Retornado | Truncado |"
        incident_header = "| UTC | Plataforma | Event kind | Posição no snapshot |"
        assert group.index(scope_row) < group.index(counts_header) < group.index(incident_header)
        positions = []
        for count in window.counts:
            line = (
                f"| {r.escape_text(count.component)} | {r.escape_text(count.unit)} | "
                f"{count.total} | {count.returned} | {'sim' if count.truncated else 'não'} |"
            )
            positions.append(group.index(line))
        assert positions == sorted(positions) and positions[-1] < group.index(incident_header)
        pointers = [group.index(r.escape_text(row.pointer)) for row in window.incidents]
        assert pointers == sorted(pointers)
        for event in snapshot.snapshot["analysis_window"]["incident_window"]["items"]:
            assert event["event_id"] not in text and event["parsed_record_id"] not in text
        assert "status_counts" not in group and "Status counts" not in group


def test_every_finding_preserved_without_raw_basis(canonical):
    for finding in canonical.model.findings:
        finding.technical_basis["ignored_payload"] = "SYNTHETIC-RAW-BASIS"
    projected = project(canonical)
    assert len(projected.findings) == len(canonical.model.findings)
    for actual, expected in zip(projected.findings, canonical.model.findings, strict=True):
        assert (
            actual.finding_id,
            actual.candidate_type,
            actual.classification,
            actual.statement,
            actual.limitations,
        ) == (
            expected.finding_id,
            expected.candidate_type,
            expected.classification,
            expected.statement,
            expected.limitations,
        )
        assert actual.technical_basis == report._basis(expected.technical_basis)
        assert actual.reference.pointer == expected.provenance_basis.pointer
    text = sections(r.render_dossier_markdown(projected))[7]
    positions = [text.index("### " + f.finding_id + "\n") for f in projected.findings]
    assert positions == sorted(positions)
    assert "SYNTHETIC-RAW-BASIS" not in text


def test_unknown_finding_kind_fails_closed(canonical):
    first = replace(canonical.model.findings[0], candidate_type="unknown_future_kind")
    canonical = replace(canonical, model=replace(canonical.model, findings=(first,)))
    with pytest.raises(EvidenceError, match="^DOSSIER_CANONICAL_SET_INVALID$"):
        project(canonical)


def test_source_media_existing_positive_findings(report_set):
    canonical = validate(report_set)
    projected = project(canonical)
    kinds = [f.candidate_type for f in projected.findings]
    assert kinds[-5:] == ["source_media_provenance_link"] * 5
    assert "source_media_provenance_link" not in kinds[:-5]
    result = sections(r.render_dossier_markdown(projected))
    for w, original in zip(projected.windows, canonical.model.windows, strict=True):
        assert {s.name: s.count for s in w.source_media_statuses} == original.component_counts[
            "source_media_links"
        ]["status_counts"]
    for finding in projected.findings[-5:]:
        assert finding.finding_id in result[8]
        assert r.escape_text(finding.statement) in result[7]
    assert "não significa arquivo inválido nem implica vídeo" in result[8]
    assert "não envios, publicações, destinatários ou ações" in result[8]
    assert "não estabelece upload, envio, exclusão ou autoria" in result[8]
    # Values in the validated technical payload remain out of the human surface.
    output = r.render_dossier_markdown(projected).decode()
    for snapshot in canonical.snapshots:
        for origin in snapshot.snapshot["provenance_index"]["parsed_records"].values():
            for key in ("evidence_file_id", "archive_member_id"):
                if origin.get(key):
                    assert origin[key] not in output


def test_supports_total_never_read_and_device_network_separate(canonical):
    exact = canonical.model.technical_counts["exact_candidates"]
    exact["supports"]["total"] = 987654321
    exact["device"], exact["network"] = 12341, 56781
    projected = project(canonical)
    output = r.render_dossier_markdown(projected)
    assert b"987654321" not in output and "987654321" not in repr(projected)
    result = sections(output)
    assert "12341" in result[10] and "56781" not in result[10]
    assert "56781" in result[11] and "12341" not in result[11]
    del exact["supports"]  # Projection has no dependency on the global support object.
    assert project(canonical) == projected


def test_more_than_twenty_snapshots_are_projected_without_omission():
    from evidence_engine.dossier.validation import validate_canonical_set

    values = many_windows()
    model = report.build_consolidated_model(values)
    canonical = validate_canonical_set(
        report_content=report.render_markdown(model).encode(), snapshots=captured(values)
    )
    projection = project(canonical)
    assert len(projection.snapshots) == 21 and len(projection.windows) == 20
    assert [w.window_id for w in projection.windows] == [w.window_id for w in model.windows]
    assert "W-020" in sections(r.render_dossier_markdown(projection))[6]


def test_scope_prefix_and_gaps_follow_section_allowlists(canonical):
    window = canonical.model.windows[0]
    window.component_counts["incident_window"].update(total=137, returned=2, truncated=True)
    changed = replace(window, truncated_components=("incident_window",))
    canonical = replace(
        canonical, model=replace(canonical.model, windows=(changed, *canonical.model.windows[1:]))
    )
    projection = project(canonical)
    assert projection.windows[0].counts[0].total == 137
    assert projection.windows[0].counts[0].returned == 2
    rendered = sections(r.render_dossier_markdown(projection))
    text = rendered[3]
    assert "| 137 | 2 | sim |" not in text
    assert "| Componente | Unidade | Total | Retornado | Truncado |" not in text
    assert "| 137 | 2 | sim |" in rendered[6]
    assert "Componentes truncados; achados limitados ao prefixo" in text
    for limit in projection.limitations:
        assert r.escape_text(limit) in text
    for w in projection.windows:
        assert w.window_id in text and w.start in text and w.end in text
        assert r.escape_text(w.platform or "sem filtro") in text
        assert r.escape_text(w.event_kind or "sem filtro") in text
    for gap in canonical.model.gaps:
        assert gap.gap_id not in text and r.escape_text(gap.statement) not in text
        assert r.escape_text(gap.technical_basis) not in text
        if gap.category == "D":
            assert r.escape_text(gap.statement) in rendered[13]
    # Gap-only fields cannot influence section 3, including limitations that
    # differ from the independent canonical model limitations.
    changed_gaps = tuple(
        replace(
            g,
            statement="synthetic-gap-statement",
            limitation="synthetic-gap-limitation",
            scope="synthetic-gap-scope",
            technical_basis="synthetic-gap-basis",
        )
        for g in projection.gaps
    )
    assert sections(r.render_dossier_markdown(replace(projection, gaps=changed_gaps)))[3] == text


def test_dictionary_enumeration_and_unknown_fields_are_not_output_sources(canonical):
    expected = r.render_dossier_markdown(project(canonical))

    def reorder(value):
        if isinstance(value, dict):
            items = tuple(value.items())[::-1]
            value.clear()
            for key, child in items:
                reorder(child)
                value[key] = child
            value["ignored_private_payload"] = "SYNTHETIC-NOT-A-DISPLAY-FIELD"
        elif isinstance(value, (list, tuple)):
            for child in value:
                reorder(child)

    # Only objects with explicit display allowlists; no unknown status enum added.
    for value in (
        canonical.model.metadata,
        canonical.model.methodology,
        canonical.model.evidence_scope,
        canonical.model.coverage,
        canonical.model.technical_counts,
        canonical.model.media_summary,
    ):
        reorder(value)
    assert r.render_dossier_markdown(project(canonical)) == expected


def test_privacy_sentinels_in_ignored_raw_fields(canonical):
    sentinels = [
        "f0000000-1111-4222-8333-444444444444",
        "bc" * 32,
        "198.51.100.77",
        "2001:db8::8877",
        "synthetic@example.invalid",
        "+55 (00) 90000-7788",
        "SYNTHETIC-DEVICE-ID",
        "source://synthetic/locator",
        "private/archive/member.synthetic",
        "RAW-SYNTHETIC-MESSAGE",
    ]
    for snapshot in canonical.snapshots:
        # Accepted raw strings and extension fields are not human display fields.
        snapshot.snapshot["snapshot"]["case_id"] = sentinels[0]
        if snapshot.snapshot["analysis_window"]:
            for event in snapshot.snapshot["analysis_window"]["incident_window"]["items"]:
                event["raw_payload"] = dict(zip(range(len(sentinels)), sentinels, strict=True))
                event["sender"] = sentinels[4]
                event["body"] = sentinels[-1]
        report.validate_snapshot(snapshot.snapshot)
    document = selection_document(canonical)
    document["supplemental_inputs"] = [
        item("technical_review", "extra", "private/INPUT-REFERENCE-SENTINEL.md")
    ]
    output = r.render_dossier_markdown(project(canonical, document)).decode()
    for sentinel in (*sentinels, "INPUT-REFERENCE-SENTINEL"):
        assert sentinel not in output


def test_provenance_destinations(canonical):
    projection = project(canonical)
    text = sections(r.render_dossier_markdown(projection))[14]
    for s in canonical.snapshots:
        assert (
            f"| {s.reference} | {s.local_label} | "
            f"technical/canonical/snapshots/{s.local_label}.json |" in text
        )
    for ref in canonical.model.technical_reference_map:
        assert ref.local_id in text and r.escape_text(ref.pointer) in text
    assert "[Índice de anexos](annex-index.md)" in text
    assert "technical/canonical/consolidated-report.md" in text


def test_import_boundary_and_runtime_no_io(canonical, monkeypatch):
    for module in (p, r):
        tree = ast.parse(inspect.getsource(module))
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        permitted = {
            "json",
            "re",
            "dataclasses",
            "collections.abc",
            "evidence_engine.errors",
            "evidence_engine.dossier.projection",
        }
        if module is p:
            permitted |= {
                "evidence_engine.dossier.selection",
                "evidence_engine.dossier.validation",
                "evidence_engine.reports.consolidated",
            }
        assert set(imports) <= permitted
    selected = parse(selection_document(canonical))
    entry = p.AnnexIndexEntry(
        "report",
        "consolidated_report",
        "CANONICAL_TECHNICAL",
        "technical/canonical/consolidated-report.md",
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden filesystem access")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        for name in ("open", "stat", "lstat", "resolve"):
            patch.setattr(Path, name, forbidden)
        projection = p.project_dossier(selection=selected, canonical=canonical)
        assert r.render_dossier_markdown(projection)
        assert r.render_annex_index((entry,))
