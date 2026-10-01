"""Synthetic consolidated presentation, independent validation and B preservation."""

import hashlib
import inspect
import os
import subprocess
import sys
from dataclasses import replace
from io import BytesIO

import pytest
from pypdf import PdfReader
from reportlab.pdfbase import pdfmetrics

from evidence_engine.dossier import pdf_limits as limits
from evidence_engine.dossier import pdf_renderer as r
from evidence_engine.dossier import pdf_validation as v
from evidence_engine.dossier.pdf_environment import register_fonts
from evidence_engine.dossier.pdf_model import (
    DOSSIER_TITLE,
    REPORT_SECTIONS,
    REPORT_TITLE,
    Heading,
    Table,
    parse_presentation_bytes,
)
from evidence_engine.errors import EvidenceError
from evidence_engine.reports import consolidated
from tests import test_pdf_renderer as dossier
from tests.test_dossier_canonical import current_snapshots, many_windows
from tests.test_pdf_foundation import mutate_dictionary
from tests.test_pdf_model import document

pytestmark = dossier.pytestmark

# Qualified synthetic fixtures; decoded RGB page hashes concatenated as ASCII.
PDF_FINGERPRINTS = (
    (17, 229162, "81a2e238ddde30ab435e2069decf55a973e08058c37f92958489ce1836344227"),
    (7, 219747, "9df405048a2d11ca992d568ff33d1a014c638a35238f9cf4e0b1a56818b10133"),
)
PIXEL_SEQUENCE_SHA256 = (
    "194bf73adb3e4111d2a063e6fb2001791957e8bbce5e6c0e2dc6ee340d24e852",
    "31495af761544f820fdd2da81de3125665a22a1cb9ba170025854d3f64d60c4b",
)


def minimal(body="Texto sintético."):
    return document(body, "consolidated-report")


def representative(many=False):
    # Only tests produce Markdown; the production PDF API consumes opaque bytes.
    values = many_windows() if many else current_snapshots()
    return consolidated.render_markdown(consolidated.build_consolidated_model(values)).encode()


def table(columns, rows, long=False):
    header = "| " + " | ".join(f"H{i}" for i in range(columns)) + " |\n"
    separator = "| " + " | ".join(["---"] * columns) + " |\n"
    return (
        header
        + separator
        + "\n".join(
            "| "
            + " | ".join(
                f"R{i}C{j}" + ("_synthetic_" + "t" * 40 if long else "") for j in range(columns)
            )
            + " |"
            for i in range(rows)
        )
    )


def extreme():
    return minimal(
        "### W-001\n\n"
        + "Parágrafo ç ã &amp; &lt;tag&gt; " * 170
        + "\n\n### F-001 — synthetic_candidate\n\n"
        + "**Aviso sintético de truncamento.** `policy_id_v1`\n\n"
        + "- Item curto\n- "
        + "item " * 60
        + "\n\n### G-001 — Categoria synthetic\n\n"
        + table(8, 25, long=True)
        + "\n\n| A | B |\n| --- | --- |\n|  espaços  | a\\|b\\_c\\\\d |"
    )


def plan(data):
    register_fonts()
    return r._Layout(parse_presentation_bytes(data, "consolidated-report")).build()


def check(data):
    expected = plan(data).expected
    pdf = r.render_consolidated_report_pdf(data)
    return pdf, expected, v.validate_pdf_bytes(pdf, expected)


@pytest.mark.parametrize("data", [minimal(), representative(), representative(True), extreme()])
def test_complete_report_structure_and_text(data):
    pdf, expected, result = check(data)
    reader = PdfReader(BytesIO(pdf), strict=True)
    assert reader.metadata.title == REPORT_TITLE
    assert set(reader.metadata) == {"/Title", "/Subject", "/Creator", "/Producer"}
    assert "/ID" not in reader.trailer and reader.trailer["/Root"]["/Lang"] == "pt-BR"
    assert len(expected.destinations) == len(expected.outlines) == 21
    assert len(expected.links) == len(expected.link_boxes) == 20
    assert expected.outlines[0] == (REPORT_TITLE, 0, 0)
    assert [title for title, _, _ in expected.outlines[1:]] == [
        f"{i}. {title}" for i, title in enumerate(REPORT_SECTIONS, 1)
    ]
    assert all(depth == 1 for _, _, depth in expected.outlines[1:])
    assert len(reader.outline) == 2 and len(reader.outline[1]) == 20
    assert sum(len(page.get("/Annots", [])) for page in reader.pages) == 20
    toc_pages = {
        p
        for p, runs in enumerate(expected.text_runs)
        if any(run.role == "toc_label" for run in runs)
    }
    assert toc_pages <= {0, 1}
    assert expected.destinations[1][0] == max(toc_pages) + 1
    for page, text in enumerate(result.extracted_text, 1):
        assert text.endswith(f"Relatório técnico consolidado\nPágina {page}\n")
    h3 = [b for b in expected.presentation.blocks if isinstance(b, Heading) and b.level == 3]
    for block in h3:
        assert "".join(s.text for s in block.spans) not in [o[0] for o in expected.outlines]


@pytest.mark.parametrize("columns,rows", [(2, 0), *[(n, 45) for n in (2, 3, 4, 5, 6, 8)]])
def test_equal_columns_repeated_headers_and_indivisible_rows(columns, rows):
    data = minimal(table(columns, rows, long=True))
    _, expected, _ = check(data)
    layout = plan(data)
    widths = r._Layout.columns(columns)
    assert sum(widths) == pytest.approx(r.WIDTH)
    assert max(widths) - min(widths) <= 0.0011
    assert any(run.role == "repeat" for page in expected.text_runs for run in page) == bool(rows)
    for boxes in layout.boxes:
        for box in boxes:
            assert r.LEFT <= box.x < box.x + box.width <= r.RIGHT + 0.001
            assert r.BOTTOM <= box.bottom < box.bottom + box.height <= r.TOP + 0.001
    for index, block in enumerate(expected.presentation.blocks):
        if isinstance(block, Table):
            for row in range(1, len(block.rows) + 1):
                pages = {
                    p
                    for p, runs in enumerate(expected.text_runs)
                    for run in runs
                    if run.source is not None and run.source[:2] == (index, row)
                }
                assert len(pages) == 1


def test_spans_escapes_and_long_tokens_preserved():
    data = minimal(
        "**negrito** `literal_a` foo_bar "
        + "X" * 400
        + "\n\n- item\n\n| A | B |\n| --- | --- |\n|  espaços  | a\\|b\\_c\\\\d |"
    )
    _, expected, _ = check(data)
    runs = [run for page in expected.text_runs for run in page if run.role == "body"]
    text = "".join(run.text for run in runs)
    assert " espaços " in text and "a|b_c\\d" in text and "foo_bar" in text
    assert text.count("X") == 400
    assert any(run.text == "literal_a" and run.font == "DejaVuSansMono" for run in runs)
    assert any(run.text == "negrito" and run.font == "DejaVuSans-Bold" for run in runs)


def test_oversized_row_and_page_budget(monkeypatch):
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_UNSUPPORTED_LAYOUT$"):
        r.render_consolidated_report_pdf(
            minimal(table(8, 0) + "| " + "long " * 2000 + " | a | b | c | d | e | f | g |")
        )
    monkeypatch.setattr(limits, "MAX_PAGES", 1)
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_RESOURCE_LIMIT$"):
        r.render_consolidated_report_pdf(minimal())


@pytest.mark.parametrize("mutation", ["omit", "duplicate", "reorder", "change"])
@pytest.mark.parametrize("target", ["paragraph", "cell"])
def test_reject_source_corruption(mutation, target):
    original = plan(minimal("conteúdo preservado" if target == "paragraph" else table(2, 1)))
    pages = [list(page) for page in original.expected.text_runs]
    page, index = next(
        (p, i)
        for p, runs in enumerate(pages)
        for i, run in enumerate(runs)
        if run.source == ((2, -1, -1) if target == "paragraph" else (2, 1, 0))
    )
    runs = pages[page]
    if mutation == "omit":
        runs.pop(index)
    elif mutation == "duplicate":
        runs.insert(index, runs[index])
    elif mutation == "reorder":
        runs[index - 1], runs[index] = runs[index], runs[index - 1]
    else:
        runs[index] = replace(runs[index], text="corrompido")
    changed = replace(original.expected, text_runs=tuple(tuple(p) for p in pages))
    pdf = r._paint(replace(original, expected=changed))
    # Neither a corrupted plan nor an altered PDF can stand in for source text.
    for expectation in (changed, original.expected):
        with pytest.raises(EvidenceError, match="PDF_VALIDATION_FAILURE"):
            v.validate_pdf_bytes(pdf, expectation)


@pytest.mark.parametrize(
    "mutation",
    [
        "kind",
        "title",
        "header",
        "footer",
        "toc_page",
        "outlines",
        "destinations",
        "links",
        "repeat",
    ],
)
def test_reject_wrong_profile_and_navigation(mutation):
    original = plan(extreme())
    expected = original.expected
    if mutation == "kind":
        expected = replace(expected, presentation=replace(expected.presentation, kind="dossier"))
    elif mutation == "title":
        expected = replace(expected, title=DOSSIER_TITLE)
    elif mutation in ("outlines", "destinations", "links"):
        expected = replace(expected, **{mutation: getattr(expected, mutation)[::-1]})
    else:
        pages = [list(page) for page in expected.text_runs]
        p, i = next(
            (p, i)
            for p, runs in enumerate(pages)
            for i, run in enumerate(runs)
            if run.role == mutation
        )
        pages[p][i] = replace(
            pages[p][i], text="Dossiê técnico" if mutation == "header" else "wrong"
        )
        expected = replace(expected, text_runs=tuple(tuple(p) for p in pages))
    with pytest.raises(EvidenceError, match="PDF_VALIDATION_FAILURE"):
        v.validate_pdf_bytes(r._paint(original), expected)


@pytest.mark.parametrize("kind", ["consolidated-report", "arbitrary"])
def test_dossier_cannot_be_relabelled(kind):
    original = dossier.plan(document())
    expected = replace(
        original.expected, presentation=replace(original.expected.presentation, kind=kind)
    )
    with pytest.raises(EvidenceError, match="PDF_VALIDATION_FAILURE"):
        v.validate_pdf_bytes(r._paint(original), expected)


@pytest.mark.parametrize(
    "body",
    [
        "[Índice de anexos](annex-index.md)",
        "![image](x)",
        "<b>html</b>",
        "1. ordered",
        "```\ncode\n```",
    ],
)
def test_no_grammar_expansion(body):
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_UNSUPPORTED_MARKDOWN$"):
        r.render_consolidated_report_pdf(minimal(body))


def test_no_source_regeneration_or_private_coupling():
    source = inspect.getsource(r)
    assert all(
        token not in source
        for token in (
            "build_consolidated_model",
            "render_markdown",
            "consolidated_report(",
            "read_bytes",
            "open(",
            "._doc",
            "._code",
            ".face",
            "PdfWriter",
            "sqlalchemy",
        )
    )
    with pytest.raises(EvidenceError, match="UNSUPPORTED_MARKDOWN"):
        r.render_consolidated_report_pdf(document())
    with pytest.raises(EvidenceError, match="UNSUPPORTED_MARKDOWN"):
        r.render_dossier_pdf(minimal())


@pytest.mark.parametrize(
    "addition",
    [
        b"/OpenAction << /S /JavaScript /JS (synthetic) >>",
        b"/Metadata (synthetic)",
        b"/AA << /S /URI /URI (https://example.invalid) >>",
    ],
)
def test_active_content_still_rejected(addition):
    pdf, expected, _ = check(minimal())
    with pytest.raises(EvidenceError, match="PDF_VALIDATION_FAILURE"):
        v.validate_pdf_bytes(mutate_dictionary(pdf, "/Root", addition), expected)


def test_determinism_processes_directories_and_both_profiles(tmp_path):
    data = representative()
    first = r.render_consolidated_report_pdf(data)
    dossier_data = dossier.representative()
    dossier_pdf = r.render_dossier_pdf(dossier_data)
    assert hashlib.sha256(dossier_pdf).hexdigest() == dossier.PDF_SHA256
    assert r.render_consolidated_report_pdf(data) == first
    assert r.render_dossier_pdf(dossier_data) == dossier_pdf
    assert r.render_consolidated_report_pdf(data) == first
    code = (
        "import sys,hashlib; from evidence_engine.dossier.pdf_limits import impose_worker_limits; "
        "from evidence_engine.dossier.pdf_renderer import render_consolidated_report_pdf; "
        "impose_worker_limits(); "
        "print(hashlib.sha256(render_consolidated_report_pdf(sys.stdin.buffer.read())).hexdigest())"
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


def pixel_fingerprint(pdf, expected):
    import pypdfium2 as pdfium

    fingerprints = []
    with pdfium.PdfDocument(pdf) as doc:
        for page_index, page in enumerate(doc):
            text = page.get_textpage()
            try:
                for char in range(text.count_chars()):
                    x0, y0, x1, y1 = text.get_charbox(char)
                    if x0 == x1 or y0 == y1:
                        continue
                    assert 55 <= x0 < x1 <= 540 and 31 <= y0 < y1 <= 818
            finally:
                text.close()
            bitmap = page.render(scale=2, fill_color=(255, 255, 255, 255), rev_byteorder=True)
            try:
                image = bitmap.to_pil().convert("RGB")
                assert image.size == (1191, 1684) and image.getextrema()[0][0] == 0
                fingerprints.append(hashlib.sha256(image.tobytes()).hexdigest())
            finally:
                bitmap.close()
                page.close()
            runs = expected.text_runs[page_index]
            for run in runs:
                if run.role not in ("body", "repeat"):
                    continue
                end = run.x + pdfmetrics.stringWidth(run.text, run.font, run.size)
                assert r.LEFT - 0.01 <= run.x <= end <= r.RIGHT + 0.01
                ascent, descent = pdfmetrics.getAscentDescent(run.font, run.size)
                assert run.y + descent >= r.BOTTOM - 0.01
                assert run.y + ascent <= r.TOP + 0.01
                source = expected.presentation.blocks[run.source[0]]
                if isinstance(source, Table):
                    widths = r._Layout.columns(len(source.header.cells))
                    left = r.LEFT + sum(widths[: run.source[2]])
                    assert run.x >= left + 3 - 0.001
                    assert end <= left + widths[run.source[2]] - 3 + 0.001
            # Distinct body text boxes must not intersect (adjacent styled runs allowed).
            boxes = []
            for run in runs:
                if not run.text or run.role == "bullet":
                    continue
                ascent, descent = pdfmetrics.getAscentDescent(run.font, run.size)
                box = (
                    run.x,
                    run.y + descent,
                    run.x + pdfmetrics.stringWidth(run.text, run.font, run.size),
                    run.y + ascent,
                )
                for previous in boxes:
                    assert not (
                        min(box[2], previous[2]) - max(box[0], previous[0]) > 0.01
                        and min(box[3], previous[3]) - max(box[1], previous[1]) > 0.01
                    )
                boxes.append(box)
    return hashlib.sha256("".join(fingerprints).encode("ascii")).hexdigest()


@pytest.mark.parametrize("index,data", enumerate([representative(), extreme()]))
def test_pdfium_and_pdf_fingerprints(index, data):
    pdf, expected, result = check(data)
    assert (result.page_count, len(pdf), hashlib.sha256(pdf).hexdigest()) == PDF_FINGERPRINTS[index]
    assert pixel_fingerprint(pdf, expected) == PIXEL_SEQUENCE_SHA256[index]
    assert pixel_fingerprint(pdf, expected) == PIXEL_SEQUENCE_SHA256[index]
