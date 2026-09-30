"""Synthetic closed grammar tests; no case access or PDF generation."""

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from evidence_engine.dossier import pdf_limits as limits
from evidence_engine.dossier import pdf_model as m
from evidence_engine.dossier import rendering
from evidence_engine.errors import EvidenceError
from evidence_engine.reports import consolidated
from tests.test_dossier_canonical import current_snapshots, many_windows, validate
from tests.test_dossier_projection import project


def document(body="Texto sintético.", kind="dossier"):
    title, sections = (
        (m.DOSSIER_TITLE, m.DOSSIER_SECTIONS)
        if kind == "dossier"
        else (m.REPORT_TITLE, m.REPORT_SECTIONS)
    )
    return (
        f"# {title}\n\n"
        + "\n\n".join(
            f"## {i}. {section}\n\n{body if i == 1 else 'Texto.'}"
            for i, section in enumerate(sections, 1)
        )
        + "\n"
    ).encode()


@pytest.mark.parametrize("many", [False, True])
def test_both_real_renderers_and_constants(many):
    values = many_windows() if many else current_snapshots()
    report = consolidated.render_markdown(consolidated.build_consolidated_model(values)).encode()
    canonical = validate(values, report)
    dossier = rendering.render_dossier_markdown(project(canonical))
    assert m.parse_presentation_bytes(dossier, "dossier").title == rendering.TITLE
    assert m.parse_presentation_bytes(report, "consolidated-report").title == consolidated.TITLE
    assert m.DOSSIER_SECTIONS == rendering.SECTIONS
    assert m.REPORT_SECTIONS == consolidated.SECTIONS


def test_spans_escapes_entities_and_positions():
    body = (
        r"Nota: &amp;lt;tag&amp;gt; &lt;tag&gt; \*literal\* foo_bar **negrito** `a_*` "
        "[Índice de anexos](annex-index.md)"
    )
    parsed = m.parse_presentation_bytes(document(body), "dossier")
    block = parsed.blocks[2]
    assert isinstance(block, m.Paragraph)
    assert (
        "".join(s.text for s in block.spans)
        == "Nota: &lt;tag&gt; <tag> *literal* foo_bar negrito a_* Índice de anexos (annex-index.md)"
    )
    assert [s.kind for s in block.spans if s.kind != "text"] == ["bold", "literal", "index"]
    assert block.line == 5 and block.spans[0].column == 1
    with pytest.raises(FrozenInstanceError):
        parsed.title = "changed"


def test_lists_h3_table_pipe_parity_and_whitespace():
    body = "### Subtítulo\n\n- um\n- dois\n\n| A | B |\n| --- | --- |\n|  espaços  | a\\|b\\\\ |"
    parsed = m.parse_presentation_bytes(document(body), "dossier")
    table = next(b for b in parsed.blocks if isinstance(b, m.Table))
    assert "".join(s.text for s in table.rows[0].cells[0].spans) == " espaços "
    assert "".join(s.text for s in table.rows[0].cells[1].spans) == "a|b\\"
    assert any(isinstance(b, m.BulletList) and len(b.items) == 2 for b in parsed.blocks)


@pytest.mark.parametrize(
    "body",
    [
        "<script>x</script>",
        "![x](a)",
        "[x](https://example.invalid)",
        "<https://example.invalid>",
        "```x\nx\n```",
        "~~~",
        "#### heading",
        "> quote",
        "  - nested",
        "1. list",
        "+ list",
        "---",
        "*italic*",
        "`open",
        "**open",
        "| A | B |\n| --- | --- |\n| short |",
        "bad\\q",
        "&quot;unsupported entity&quot;",
        "&#65;",
        "[ref]: target",
    ],
)
def test_unsupported_is_not_dropped(body):
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_UNSUPPORTED_MARKDOWN$"):
        m.parse_presentation_bytes(document(body), "dossier")


@pytest.mark.parametrize(
    "payload",
    [b"\xef\xbb\xbf", b"\xff", b"\x00", b"\r", b"\t", "\u202e".encode(), "\u2066".encode()],
)
def test_strict_encoding_and_controls(payload):
    with pytest.raises(EvidenceError, match="UNSUPPORTED_MARKDOWN"):
        m.parse_presentation_bytes(payload + document(), "dossier")


@pytest.mark.parametrize(
    "change",
    [
        lambda b: b.replace(b"# ", b"# wrong ", 1),
        lambda b: b.replace(b"## 2.", b"## 1."),
        lambda b: b.replace(b"## 14.", b"## 15."),
        lambda b: b.replace(b"\n", b"\r\n"),
    ],
)
def test_document_contract(change):
    with pytest.raises(EvidenceError, match="UNSUPPORTED_MARKDOWN"):
        m.parse_presentation_bytes(change(document()), "dossier")


def test_byte_limit_boundary(monkeypatch):
    data = document()
    monkeypatch.setattr(limits, "MAX_MARKDOWN_BYTES", len(data))
    m.parse_presentation_bytes(data, "dossier")
    with pytest.raises(EvidenceError, match="RESOURCE_LIMIT"):
        m.parse_presentation_bytes(data + b"\n", "dossier")


def test_block_limit_boundary(monkeypatch):
    monkeypatch.setattr(limits, "MAX_BLOCKS", 29)
    m.parse_presentation_bytes(document(), "dossier")
    with pytest.raises(EvidenceError, match="RESOURCE_LIMIT"):
        m.parse_presentation_bytes(document("first\n\nsecond"), "dossier")


@pytest.mark.parametrize(
    "limit,value,body",
    [
        ("MAX_COLUMNS", 1, "| a |\n| --- |\n| b |"),
        ("MAX_ROWS", 1, "| a |\n| --- |\n| b |"),
        ("MAX_CELLS", 2, "| a |\n| --- |\n| b |"),
    ],
)
def test_table_limit_boundary(monkeypatch, limit, value, body):
    monkeypatch.setattr(limits, limit, value)
    m.parse_presentation_bytes(document(body), "dossier")
    excessive = (
        body.replace("| a |", "| a | c |")
        .replace("| --- |", "| --- | --- |")
        .replace("| b |", "| b | d |")
        if limit == "MAX_COLUMNS"
        else body + "\n| c |"
    )
    with pytest.raises(EvidenceError, match="RESOURCE_LIMIT"):
        m.parse_presentation_bytes(document(excessive), "dossier")


def test_pdf_import_boundary_and_private_surface():
    folder = Path(__file__).parents[1] / "src/evidence_engine/dossier"
    forbidden = (
        "sqlalchemy",
        "evidence_engine.storage",
        "evidence_engine.case",
        "evidence_engine.parsers",
        "evidence_engine.ingest",
        "evidence_engine.reports",
        "evidence_engine.analysis",
    )
    for path in folder.glob("pdf_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith(forbidden)
                if module == "reportlab.pdfbase.pdfdoc":
                    assert path.name == "pdf_reportlab_adapter.py"
                    assert {n.name for n in node.names} == {
                        "PDFDictionary",
                        "PDFDocument",
                        "PDFInfo",
                        "PDFString",
                        "PDFTrailer",
                    }
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("_ID", "__class__")
                if node.attr == "signature":
                    assert isinstance(node.value, ast.Name) and node.value.id == "inspect"
    for path in folder.glob("*.py"):
        if not path.name.startswith("pdf_"):
            assert "dossier.pdf_" not in path.read_text(encoding="utf-8")
