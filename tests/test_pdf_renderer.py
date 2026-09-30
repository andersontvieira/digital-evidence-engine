"""Synthetic dossier rendering, independent structure checks and decoded pixels."""

import hashlib
import inspect
import os
import subprocess
import sys
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.pdfbase import pdfmetrics

from evidence_engine.dossier import pdf_limits as limits
from evidence_engine.dossier import pdf_renderer as r
from evidence_engine.dossier import pdf_validation as v
from evidence_engine.dossier import rendering
from evidence_engine.dossier.pdf_environment import register_fonts
from evidence_engine.dossier.pdf_model import Heading, Table, parse_presentation_bytes
from evidence_engine.errors import EvidenceError
from evidence_engine.reports import consolidated
from tests.test_dossier_canonical import current_snapshots, many_windows, validate
from tests.test_dossier_projection import project
from tests.test_pdf_foundation import mutate_dictionary
from tests.test_pdf_model import document

pytestmark = pytest.mark.skipif(
    not Path("/opt/digital-evidence-engine/render-environment.json").is_file(),
    reason="Requires qualified Dockerfile.pdf Linux/amd64 environment",
)

PDF_SHA256 = "c2365cdf93c11e9ce55347b3a8126036c393befb030e3aa2ce0b7e12cede67f2"
# Hash of the ordered concatenation of each page's decoded RGB SHA-256 (ASCII).
PIXEL_SEQUENCE_SHA256 = (
    "a3b521279af0383c0593ca11e7ea105aefe35757b5da084090b5b56b20627779",
    "4415bc9ea298319c3508bceee51eda0e775a306065247d5b3fc91d87f3528a49",
)


def representative(many=False):
    # Test input producer only: the PDF renderer never imports or calls assembly.
    values = many_windows() if many else current_snapshots()
    content = consolidated.render_markdown(consolidated.build_consolidated_model(values)).encode()
    return rendering.render_dossier_markdown(project(validate(values, content)))


def extreme():
    header = "| " + " | ".join(f"Coluna {i}" for i in range(7)) + " |\n"
    table = header + "| " + " | ".join(["---"] * 7) + " |\n"
    table += "\n".join(
        "| " + " | ".join(f"R{i}C{j} ação " + "t" * 40 for j in range(7)) + " |" for i in range(25)
    )
    return document(
        "### Contexto sintético\n\n"
        + "Parágrafo longo ç ã &amp; &lt;tag&gt; " * 170
        + "\n\n- Item curto\n- "
        + "item " * 60
        + "\n\n"
        + table
        + "\n\n[Índice de anexos](annex-index.md)"
    )


def plan(data):
    register_fonts()
    return r._Layout(parse_presentation_bytes(data, "dossier")).build()


def check(data):
    expected = plan(data).expected
    pdf = r.render_dossier_pdf(data)
    result = v.validate_pdf_bytes(pdf, expected)
    return pdf, expected, result


@pytest.mark.parametrize(
    "data",
    [document(), representative(), representative(True), extreme()],
    ids=["minimal", "representative", "many-windows", "extreme"],
)
def test_complete_dossier_structure_and_text(data):
    pdf, expected, result = check(data)
    reader = PdfReader(BytesIO(pdf), strict=True)
    assert pdf.startswith(b"%PDF-1.4") and result.page_count >= 3
    assert set(reader.metadata) == {"/Title", "/Subject", "/Creator", "/Producer"}
    assert "/ID" not in reader.trailer
    assert reader.trailer["/Root"]["/Lang"] == "pt-BR"
    assert len(expected.outlines) == 15 and len(expected.links) == 14
    assert all(depth == 1 for _, _, depth in expected.outlines[1:])
    assert len(reader.outline) == 2 and len(reader.outline[1]) == 14
    for page, text in enumerate(result.extracted_text, 1):
        assert text.endswith(f"Dossiê técnico\nPágina {page}\n")
    if b"annex-index.md" in data:
        assert "Índice de anexos (annex-index.md)" in "".join(result.extracted_text)
    assert sum(len(p.get("/Annots", [])) for p in reader.pages) == 14
    assert all(p.get("/Annots") is None for p in reader.pages[1:])


@pytest.mark.parametrize("columns,rows", [(2, 0), (2, 100), (7, 45)])
def test_table_rows_headers_width_and_continuation(columns, rows):
    header = "| " + " | ".join(f"H{i}" for i in range(columns)) + " |\n"
    body = header + "| " + " | ".join(["---"] * columns) + " |\n"
    body += "\n".join(
        "| " + " | ".join(f"R{i}C{j}" for j in range(columns)) + " |" for i in range(rows)
    )
    data = document(body)
    pdf, expected, _ = check(data)
    layout = plan(data)
    assert sum(r._Layout.columns(columns)) == pytest.approx(r.WIDTH)
    for boxes in layout.boxes:
        for box in boxes:
            assert box.x >= r.LEFT and box.x + box.width <= r.RIGHT + 0.001
            assert box.bottom >= r.BOTTOM and box.bottom + box.height <= r.TOP + 0.001
    if rows > 40:
        assert any(run.role == "repeat" for runs in expected.text_runs for run in runs)
    else:
        assert not any(run.role == "repeat" for runs in expected.text_runs for run in runs)
    assert pdf


def test_wrapping_styles_entities_preserves_every_character():
    data = document(
        "ação &amp;lt; &lt;tag&gt; **negrito** `literal_a` "
        + "X" * 400
        + "\nsegunda linha\n\n| A | B |\n| --- | --- |\n|  espaços  | a\\|b |"
    )
    _, expected, _ = check(data)
    runs = [run for page in expected.text_runs for run in page if run.role == "body"]
    assert any(run.font == "DejaVuSansMono" and run.size == 9 for run in runs)
    assert any(run.text == "negrito" and run.font == "DejaVuSans-Bold" for run in runs)
    # One delimiter-padding space on each side belongs to the closed grammar.
    assert " espaços " in "".join(run.text for run in runs)
    assert sum(run.text.count("X") for run in runs) == 400


@pytest.mark.parametrize(
    "text", ["missing \U0010ffff", "combining a\u0301", "control\x00", "bidi\u202e"]
)
def test_unsupported_complete_content_fails_closed(text):
    # Includes table and H3 paths, not only the old two-page probe.
    for body in (text, "### " + text, "| A | B |\n| --- | --- |\n| " + text + " | dado |"):
        with pytest.raises(
            EvidenceError, match="^DOSSIER_PDF_(FONT_UNSUPPORTED|UNSUPPORTED_MARKDOWN)$"
        ):
            r.render_dossier_pdf(document(body))


def test_multiple_unicode_subsets():
    # Qualified DejaVu characters spanning more than one dynamic subset.
    text = "".join(chr(code) for code in range(0x100, 0x250))
    check(document(text))


def test_oversized_logical_row_fails():
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_UNSUPPORTED_LAYOUT$"):
        r.render_dossier_pdf(
            document("| A | B |\n| --- | --- |\n| " + "long " * 2000 + " | curto |")
        )


def test_page_budget_before_creation(monkeypatch):
    monkeypatch.setattr(limits, "MAX_PAGES", 2)
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_RESOURCE_LIMIT$"):
        plan(document())


def test_paragraph_widows_and_list_bullet_boundary():
    register_fonts()
    parsed = parse_presentation_bytes(document("um\ndois\ntrês"), "dossier")
    layout = r._Layout(parsed)
    layout.y = r.BOTTOM + 28
    layout.paragraph(parsed.blocks[2].spans, (2, -1, -1), r._BODY)
    assert not layout.pages[0].runs and len(layout.pages[1].runs) == 3
    data = document("\n\n".join(["texto"] * 31) + "\n\n- " + "palavra " * 26)
    _, expected, _ = check(data)
    for runs in expected.text_runs:
        for run in runs:
            if run.role == "bullet":
                following = next(
                    other for other in runs if other.role == "body" and other.source == run.source
                )
                assert following.y == run.y


def test_heading_chain_and_first_table_row_stay_together():
    data = document(
        "\n\n".join(["texto"] * 30) + "\n\n### Contexto\n\n| A | B |\n| --- | --- |\n| a | b |"
    )
    _, expected, _ = check(data)
    for index, block in enumerate(expected.presentation.blocks):
        if isinstance(block, Heading) and block.level == 3:
            page = next(
                i
                for i, runs in enumerate(expected.text_runs)
                if any(run.source == (index, -1, -1) for run in runs)
            )
            assert any(run.source == (index + 1, 1, 0) for run in expected.text_runs[page])


@pytest.mark.parametrize("mutation", ["omit", "duplicate", "reorder", "change"])
def test_validator_rejects_plan_loss_duplication_reordering(mutation):
    original = plan(document("conteúdo verificável"))
    pages = [list(runs) for runs in original.expected.text_runs]
    target = next(i for i, run in enumerate(pages[1]) if run.source == (2, -1, -1))
    if mutation == "omit":
        pages[1].pop(target)
    elif mutation == "duplicate":
        pages[1].insert(target, pages[1][target])
    elif mutation == "reorder":
        pages[1][target - 1], pages[1][target] = pages[1][target], pages[1][target - 1]
    else:
        pages[1][target] = replace(pages[1][target], text="outra versão")
    expected = replace(original.expected, text_runs=tuple(tuple(p) for p in pages))
    with pytest.raises(EvidenceError, match="PDF_VALIDATION_FAILURE"):
        v.validate_pdf_bytes(r._paint(replace(original, expected=expected)), expected)


@pytest.mark.parametrize("mutation", ["number", "destination", "header", "footer", "repeat"])
def test_validator_rejects_navigation_and_chrome_corruption(mutation):
    original = plan(extreme())
    expected = original.expected
    if mutation == "destination":
        expected = replace(expected, link_destinations=expected.link_destinations[::-1])
    else:
        pages = [list(runs) for runs in expected.text_runs]
        role = "toc_page" if mutation == "number" else mutation
        page, index = next(
            (p, i) for p, runs in enumerate(pages) for i, run in enumerate(runs) if run.role == role
        )
        pages[page][index] = replace(pages[page][index], text="corrompido")
        expected = replace(expected, text_runs=tuple(tuple(p) for p in pages))
    with pytest.raises(EvidenceError, match="PDF_VALIDATION_FAILURE"):
        v.validate_pdf_bytes(r._paint(original), expected)


@pytest.mark.parametrize(
    "addition",
    [
        b"/OpenAction << /S /JavaScript /JS (synthetic) >>",
        b"/Metadata (synthetic)",
        b"/AA << /S /URI /URI (https://example.invalid) >>",
    ],
)
def test_dossier_profile_keeps_active_content_rejection(addition):
    pdf, expected, _ = check(document())
    with pytest.raises(EvidenceError, match="PDF_VALIDATION_FAILURE"):
        v.validate_pdf_bytes(mutate_dictionary(pdf, "/Root", addition), expected)


def test_two_pass_divergence_fails(monkeypatch):
    original = r._Layout.build
    count = 0

    def divergent(self):
        nonlocal count
        count += 1
        result = original(self)
        return result if count == 1 else replace(result, boxes=())

    monkeypatch.setattr(r._Layout, "build", divergent)
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_RENDER_FAILURE$"):
        r.render_dossier_pdf(document())


def test_no_source_capture_or_private_vendor_coupling():
    source = inspect.getsource(r)
    assert all(
        token not in source
        for token in (
            "._doc",
            "._code",
            ".face",
            "read_bytes",
            "open(",
            "PdfWriter",
            "storage",
            "sqlalchemy",
            "assemble_dossier",
        )
    )


def test_validator_rejects_white_text(monkeypatch):
    original = plan(document())
    base = r.ControlledCanvas

    class WhiteTextCanvas(base):
        def setFillGray(self, gray, alpha=None):
            super().setFillGray(1 if gray == 0 else gray, alpha)

    monkeypatch.setattr(r, "ControlledCanvas", WhiteTextCanvas)
    with pytest.raises(EvidenceError, match="PDF_VALIDATION_FAILURE"):
        v.validate_pdf_bytes(r._paint(original), original.expected)


@pytest.mark.parametrize("kind", ["omit", "duplicate", "reorder"])
def test_actual_pdf_text_must_match_original_plan(kind):
    original = plan(document("conteúdo preservado"))
    pages = [list(runs) for runs in original.expected.text_runs]
    index = next(i for i, run in enumerate(pages[1]) if run.source == (2, -1, -1))
    if kind == "omit":
        pages[1].pop(index)
    elif kind == "duplicate":
        pages[1].insert(index, pages[1][index])
    else:
        pages[1][index - 1], pages[1][index] = pages[1][index], pages[1][index - 1]
    changed = replace(original.expected, text_runs=tuple(tuple(p) for p in pages))
    with pytest.raises(EvidenceError, match="PDF_VALIDATION_FAILURE"):
        v.validate_pdf_bytes(r._paint(replace(original, expected=changed)), original.expected)


def test_determinism_ten_processes_aba_and_temporary_directories(tmp_path):
    data = representative()
    first = r.render_dossier_pdf(data)
    assert hashlib.sha256(first).hexdigest() == PDF_SHA256
    assert first == r.render_dossier_pdf(data)
    assert r.render_dossier_pdf(document("B sintético")) != first
    assert r.render_dossier_pdf(data) == first
    code = (
        "import sys,hashlib; from evidence_engine.dossier.pdf_limits import impose_worker_limits; "
        "from evidence_engine.dossier.pdf_renderer import render_dossier_pdf; "
        "impose_worker_limits(); "
        "print(hashlib.sha256(render_dossier_pdf(sys.stdin.buffer.read())).hexdigest())"
    )
    for index in range(10):
        scratch = tmp_path / str(index)
        scratch.mkdir()
        result = subprocess.run(
            [sys.executable, "-c", code],
            input=data,
            cwd=scratch,
            env={**os.environ, "TMPDIR": str(scratch)},
            capture_output=True,
            timeout=120,
            check=True,
        )
        assert not result.stderr
        assert result.stdout.decode().strip() == hashlib.sha256(first).hexdigest()


@pytest.mark.parametrize(
    "fixture_index,data", enumerate([representative(), extreme()]), ids=["compact", "extreme"]
)
def test_pdfium_pixels_and_glyph_geometry(fixture_index, data):
    import pypdfium2 as pdfium

    pdf, expected, _ = check(data)
    fingerprints = []
    for _ in range(2):
        current = []
        with pdfium.PdfDocument(pdf) as doc:
            for page_index, page in enumerate(doc):
                text = page.get_textpage()
                try:
                    for char in range(text.count_chars()):
                        x0, y0, x1, y1 = text.get_charbox(char)
                        if x0 == x1 or y0 == y1:
                            continue
                        assert 55 <= x0 < x1 <= 540
                        assert 31 <= y0 < y1 <= 818
                finally:
                    text.close()
                bitmap = page.render(scale=2, fill_color=(255, 255, 255, 255), rev_byteorder=True)
                try:
                    image = bitmap.to_pil().convert("RGB")
                    assert image.size == (1191, 1684)
                    assert image.getextrema()[0][0] == 0  # no blank pages
                    current.append(hashlib.sha256(image.tobytes()).hexdigest())
                finally:
                    bitmap.close()
                    page.close()
                # Measured text cells never extend outside their body region.
                for run in expected.text_runs[page_index]:
                    if run.role in ("body", "repeat"):
                        end = run.x + pdfmetrics.stringWidth(run.text, run.font, run.size)
                        assert end <= r.RIGHT + 0.01
                        source = expected.presentation.blocks[run.source[0]]
                        if isinstance(source, Table):
                            widths = r._Layout.columns(len(source.header.cells))
                            column_left = r.LEFT + sum(widths[: run.source[2]])
                            assert run.x >= column_left + 3 - 0.001
                            assert end <= column_left + widths[run.source[2]] - 3 + 0.001
        fingerprints.append(current)
    assert fingerprints[0] == fingerprints[1]
    assert (
        hashlib.sha256("".join(fingerprints[0]).encode("ascii")).hexdigest()
        == PIXEL_SEQUENCE_SHA256[fixture_index]
    )
