"""Synthetic presentation, deterministic output, boundaries and injection guards."""

import re
from dataclasses import fields, replace
from itertools import permutations

import pytest

from evidence_engine.dossier import projection as p
from evidence_engine.dossier import rendering as r
from evidence_engine.dossier.validation import validate_canonical_set
from evidence_engine.errors import EvidenceError
from tests.test_dossier_canonical import captured, current_snapshots, report_bytes, validate
from tests.test_dossier_projection import project, sections, selection_document
from tests.test_dossier_selection import item, parse

EXPECTED_SECTIONS = (
    "Identificação do documento",
    "Finalidade",
    "Escopo e limitações",
    "Fontes e materiais técnicos",
    "Metodologia técnica",
    "Cronologia técnica relevante",
    "Atividades digitais relevantes",
    "Relações técnicas entre fontes e mídias",
    "Comunicações e anexos",
    "Contexto técnico de dispositivos",
    "Contexto técnico de rede",
    "Atividades e alterações de conta",
    "O que os dados estabelecem e o que não estabelecem",
    "Mapa de provenance e índice de anexos",
)


@pytest.fixture
def canonical():
    return validate(current_snapshots())


def entries():
    return (
        p.AnnexIndexEntry(
            "report",
            "consolidated_report",
            "CANONICAL_TECHNICAL",
            "technical/canonical/consolidated-report.md",
        ),
        p.AnnexIndexEntry(
            "anchor",
            "report_snapshot",
            "CANONICAL_TECHNICAL",
            "technical/canonical/snapshots/anchor.json",
        ),
        p.AnnexIndexEntry(
            "review",
            "technical_review",
            "SUPPLEMENTAL_TECHNICAL",
            "technical/supplemental/review.md",
        ),
        p.AnnexIndexEntry(
            "support",
            "structured_support",
            "SUPPLEMENTAL_TECHNICAL",
            "technical/structured/support.json",
        ),
        p.AnnexIndexEntry(
            "validation",
            "validation_report",
            "VALIDATION_ARTIFACT",
            "technical/validation/validation.md",
        ),
        p.AnnexIndexEntry(
            "visual",
            "contextual_visual",
            "VISUAL_EXHIBIT",
            "exhibits/visual/visual.jpg",
            "Nota: imagem sintética.",
        ),
    )


def test_exact_headings_and_serialization(canonical):
    output = r.render_dossier_markdown(project(canonical))
    assert output.decode().startswith("# Dossiê Técnico de Organização de Evidências Digitais\n")
    assert re.findall(r"^## (.+)$", output.decode(), re.M) == [
        f"{i}. {title}" for i, title in enumerate(EXPECTED_SECTIONS, 1)
    ]
    for content in (output, r.render_annex_index(entries()), r.render_annex_index(())):
        assert content.endswith(b"\n") and not content.endswith(b"\n\n")
        assert b"\r" not in content and not content.startswith(b"\xef\xbb\xbf")
        assert content.decode("utf-8").encode("utf-8") == content


def test_permutations_and_environment_do_not_change_bytes(canonical, monkeypatch):
    baseline = r.render_dossier_markdown(project(canonical))
    document = selection_document(canonical)
    values = current_snapshots()
    inputs, report = captured(values), report_bytes(values)
    for order in permutations(inputs):
        validated = validate_canonical_set(report_content=report, snapshots=order)
        for selection_order in (document["canonical_inputs"], document["canonical_inputs"][::-1]):
            selected = parse(document | {"canonical_inputs": selection_order})
            assert (
                r.render_dossier_markdown(
                    p.project_dossier(selection=selected, canonical=validated)
                )
                == baseline
            )
    monkeypatch.setenv("CASE_ROOT", "FORBIDDEN-SYNTHETIC-ENV")
    monkeypatch.setenv("LANG", "synthetic.invalid")
    assert r.render_dossier_markdown(project(canonical)) == baseline
    assert r.render_annex_index(entries()) == r.render_annex_index(entries()[::-1])


def test_empty_anchor_only_has_all_sections_without_invented_chronology():
    canonical = validate(current_snapshots()[:1])
    result = sections(r.render_dossier_markdown(project(canonical)))
    assert len(result) == 14
    assert r.EMPTY in result[6] and "### W-" not in result[6]
    assert r.EMPTY in result[9]
    assert "não houve comunicação" not in result[9]
    assert r.ATTACHMENTS in result[9] and r.WHATSAPP in result[9]


def test_communications_and_account_literal_filters_keep_units_and_positions(canonical):
    kinds = [
        "communication.message",
        "communication.message.extra",
        "account.profile_activity",
        "account.security_activity",
        "account.change",
        "account.sign_on",
        "account.other",
    ]
    canonical.model.technical_counts["current_events"]["by_platform_event_kind"] = [
        {"platform": "synthetic", "event_kind": kind, "total": 10 + i, "dated": 9 + i, "undated": 1}
        for i, kind in enumerate(kinds)
    ]
    for snapshot in canonical.snapshots[1:]:
        raw = snapshot.snapshot["analysis_window"]["incident_window"]["items"]
        template = raw[0]
        raw[:] = [template | {"event_kind": kind} for kind in kinds]
    projection = project(canonical)
    result = sections(r.render_dossier_markdown(projection))
    assert "communication.message | 10 | 9 | 1" in result[9]
    assert "communication.message.extra" not in result[9] and "account." not in result[9]
    assert r.WHATSAPP in result[9] and r.ATTACHMENTS in result[9]
    for i, kind in enumerate(kinds[2:6], 2):
        assert r.escape_text(kind) in result[12]
        assert f"| {10 + i} | {9 + i} | 1 |" in result[12]
        assert result[12].count(r.escape_text(f"analysis_window.incident_window.items[{i}]")) == 2
    assert "account.other" not in result[12] and "communication.message" not in result[12]
    assert "não somar" in result[12] and "sem deduplicar" in result[12]


def test_section_thirteen_is_scoped_neutral_template(canonical):
    text = sections(r.render_dossier_markdown(project(canonical)))[13]
    assert (
        "Os artefatos canônicos selecionados representam os achados referenciados neste "
        "dossiê, dentro dos escopos e prefixos declarados." in text
    )
    for required in (
        "identidade humana",
        "autoria",
        "titularidade de conta",
        "propriedade de dispositivo",
        "sessão",
        "causalidade",
        "conclusão jurídica",
        "SOURCE_LIMITATION",
        r.WHATSAPP,
        r.SCOPE_LIMIT,
    ):
        assert required in text
    for prohibited in (
        "score",
        "confidence",
        "autoria provável",
        "culpa",
        "inocência",
        "suficiência jurídica",
        "admissibilidade",
        "pessoa operou dispositivo",
    ):
        assert prohibited not in text


def test_dynamic_text_is_data_not_markdown(canonical):
    injection = "& <tag> `code` *a* _b_ {c} [link](target) # | ! \\ tail"
    finding = replace(canonical.model.findings[0], statement=injection, limitations=injection)
    model = replace(canonical.model, findings=(finding,))
    text = r.render_dossier_markdown(project(replace(canonical, model=model))).decode()
    expected = (
        "&amp; &lt;tag&gt; \\`code\\` \\*a\\* \\_b\\_ \\{c\\} "
        "\\[link\\]\\(target\\) \\# \\| \\! \\\\ tail"
    )
    assert r.escape_text(injection) == expected
    assert expected in text and injection not in text
    assert len(re.findall(r"^## ", text, re.M)) == 14


@pytest.mark.parametrize(
    "control", ["\n", "\r", "\t", "\x00", "\x7f", "\x85", "\u202e", "\u2066", "\u2028", "\ud800"]
)
def test_dynamic_controls_rejected(canonical, control):
    with pytest.raises(EvidenceError, match="^DOSSIER_PRIVACY_CONTRACT_VIOLATION$"):
        r.escape_text("synthetic" + control)
    model = replace(canonical.model, limitations=("synthetic" + control,))
    with pytest.raises(EvidenceError, match="^DOSSIER_PRIVACY_CONTRACT_VIOLATION$"):
        project(replace(canonical, model=model))


def test_annex_order_roles_purposes_caption_boundary():
    more = entries() + (
        p.AnnexIndexEntry(
            "window",
            "report_snapshot",
            "CANONICAL_TECHNICAL",
            "technical/canonical/snapshots/window.json",
        ),
    )
    text = r.render_annex_index(more[::-1]).decode()
    assert re.findall(r"^## (.+)$", text, re.M) == [
        *(r.escape_text(c) for c in p.CLASS_ORDER),
        "Arquivos gerados previstos no pacote directory-v1",
    ]
    assert re.findall(r"^### (.+)$", text, re.M) == [
        "report",
        "anchor",
        "window",
        "support",
        "review",
        "validation",
        "visual",
    ]
    for purpose in r.PURPOSES.values():
        assert purpose in text
    assert "Nota: imagem sintética.\n\n" + r.CAPTION_WARNING in text
    assert {f.name for f in fields(p.AnnexIndexEntry)} == {
        "local_label",
        "role",
        "source_class",
        "package_path",
        "display_caption",
    }


@pytest.mark.parametrize("selected", [(), entries()])
def test_generated_outputs_are_separate_fixed_administrative_layout(selected):
    text = r.render_annex_index(selected).decode()
    heading = "## Arquivos gerados previstos no pacote directory-v1"
    assert text.count(heading) == 1
    groups, administrative = text.split(heading)
    paths = (
        "human/dossier.md",
        "human/annex-index.md",
        "technical/selection-metadata.json",
        "integrity/manifest.json",
        "integrity/SHA256SUMS.txt",
    )
    assert re.findall(r"^- (.+)$", administrative, re.M) == list(paths)
    for path in paths:
        assert text.count(path) == 1 and path not in groups
    assert "### " not in administrative and "|" not in administrative
    assert not any(c in administrative for c in p.CLASS_ORDER)
    assert not any(entry.local_label in administrative for entry in selected)
    assert "saídas previstas para geração na montagem futura" in administrative
    assert "não são artefatos de evidência selecionados" in administrative
    assert "não afirma que os arquivos já existem" in administrative
    assert re.search(r"\b[0-9a-f]{64}\b|\b[0-9]{4}-[0-9]{2}-[0-9]{2}\b", administrative) is None
    assert "generated_at" not in administrative
    if selected:
        assert groups.rfind("## VISUAL") > groups.rfind("## VALIDATION")
    else:
        assert groups == "# Índice de anexos\n\n"


@pytest.mark.parametrize("extension", ["jpg", "png"])
def test_visual_destinations_require_explicit_validated_extension(extension):
    entry = replace(entries()[-1], package_path=f"exhibits/visual/visual.{extension}")
    assert entry.package_path.encode() in r.render_annex_index((entry,))


@pytest.mark.parametrize(
    "path",
    [
        "exhibits/visual/visual.pdf",
        "exhibits/visual/visual.jpeg",
        "exhibits/visual/visual.PNG",
        "exhibits/visual/other.png",
        "exhibits/visual/visual.gif",
        "../visual.png",
        "C:/private/visual.png",
        "exhibits/visual/../visual.png",
        "exhibits\\visual\\visual.png",
        "https://example.invalid/visual.png",
        "exhibits/visual/visual.png:stream",
    ],
)
def test_invalid_visual_destinations(path):
    with pytest.raises(EvidenceError, match="^DOSSIER_INVALID_PATH$"):
        replace(entries()[-1], package_path=path)


@pytest.mark.parametrize("index", range(5))
def test_nonvisual_wrong_path_and_caption_rejected(index):
    entry = entries()[index]
    with pytest.raises(EvidenceError, match="^DOSSIER_INVALID_PATH$"):
        replace(entry, package_path="technical/incorrect.md")
    with pytest.raises(EvidenceError, match="^DOSSIER_PRIVACY_CONTRACT_VIOLATION$"):
        replace(entry, display_caption="Contexto sintético.")


@pytest.mark.parametrize("index", range(6))
def test_role_class_matrix_rejected(index):
    with pytest.raises(EvidenceError, match="^DOSSIER_INVALID_ROLE_CLASS$"):
        replace(entries()[index], source_class="ORIGINAL_EVIDENCE")


def test_duplicate_labels_destinations_and_casefold():
    report, anchor, _, _, _, visual = entries()
    with pytest.raises(EvidenceError, match="^DOSSIER_INVALID_PATH$"):
        r.render_annex_index((report, replace(report, local_label="other")))
    with pytest.raises(EvidenceError, match="^DOSSIER_INVALID_SELECTION$"):
        r.render_annex_index(
            (
                anchor,
                replace(visual, local_label="anchor", package_path="exhibits/visual/anchor.jpg"),
            )
        )
    # Uppercase path aliases fail the exact logical allowlist even before indexing.
    with pytest.raises(EvidenceError, match="^DOSSIER_INVALID_PATH$"):
        replace(report, package_path=report.package_path.upper())
    with pytest.raises(EvidenceError, match="^DOSSIER_INVALID_PATH$"):
        r.render_annex_index((visual, visual))


@pytest.mark.parametrize(
    "caption", [None, "https://example.invalid", "[link](target)", "raw\nheading", "<html>"]
)
def test_unsafe_or_missing_visual_caption(caption):
    with pytest.raises(
        EvidenceError, match="^DOSSIER_(PRIVACY_CONTRACT_VIOLATION|INVALID_SELECTION)$"
    ):
        replace(entries()[-1], display_caption=caption)


@pytest.mark.parametrize("kind", ["dossier", "index"])
def test_generated_byte_limit_independent_exact_boundary_utf8_and_final_lf(
    canonical, monkeypatch, kind
):
    projection = project(canonical)

    def render():
        return (
            r.render_dossier_markdown(projection)
            if kind == "dossier"
            else r.render_annex_index(entries())
        )

    expected = render()
    assert len(expected) > len(expected.decode())
    monkeypatch.setattr(r, "MAX_GENERATED_FILE_BYTES", len(expected))
    assert render() == expected
    monkeypatch.setattr(r, "MAX_GENERATED_FILE_BYTES", len(expected) - 1)
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        render()
    monkeypatch.setattr(r, "MAX_GENERATED_FILE_BYTES", len(expected.decode()))
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        render()


def test_builder_rejects_before_storing_chunk(monkeypatch):
    monkeypatch.setattr(r, "MAX_GENERATED_FILE_BYTES", 3)
    builder = r._Builder()
    builder.block("é")
    assert builder.finish() == "é\n".encode()
    before = tuple(builder.chunks)
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        builder.append("x")
    assert tuple(builder.chunks) == before and builder.size == 3


def test_visual_caption_changes_only_index(canonical):
    document = selection_document(canonical)
    document["visual_exhibits"] = [item("contextual_visual", "visual")]
    baseline = r.render_dossier_markdown(project(canonical, document))
    a = entries()[-1]
    b = replace(a, display_caption="Foto: contexto explícito.")
    document["visual_exhibits"][0]["display_caption"] = b.display_caption
    assert r.render_dossier_markdown(project(canonical, document)) == baseline
    assert r.render_annex_index((a,)) != r.render_annex_index((b,))


def test_rendering_api_has_no_source_inputs(canonical):
    projection = project(canonical)
    with pytest.raises(AttributeError):
        r.render_dossier_markdown(canonical)
    with pytest.raises(AttributeError):
        r.render_dossier_markdown(canonical.model)
    assert r.render_dossier_markdown(projection)
