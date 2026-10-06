"""8B2-F synthetic qualification at difficult presentation boundaries."""

import hashlib
import os
import subprocess
import sys

import pytest

from evidence_engine.dossier import pdf_limits as limits
from evidence_engine.dossier import pdf_model as model
from evidence_engine.dossier import pdf_renderer as renderer
from evidence_engine.dossier import pdf_validation as validation
from evidence_engine.dossier.pdf_environment import register_fonts
from evidence_engine.dossier.pdf_model import Heading, Table, parse_presentation_bytes
from evidence_engine.errors import EvidenceError
from tests import test_pdf_consolidated_renderer as consolidated
from tests import test_pdf_renderer as dossier

pytestmark = dossier.pytestmark

ASCII_TOKEN_LENGTH = 1024
DOSSIER_FILL_LINES = 47
MAX_VALID_ROW_WORDS = 52
FIRST_INVALID_ROW_WORDS = 53
MIN_VALIDATION_NODES = 801
MIN_VALIDATION_DEPTH = 19
ALLOWED_ESCAPES = "\\`*_{}[]()#|!"
ESCAPED_MARKDOWN = " ".join("\\" + character for character in ALLOWED_ESCAPES)
ESCAPED_TEXT = " ".join(ALLOWED_ESCAPES)

PDF_FINGERPRINTS = (
    (10, 150026, "a58f54ad2eff5cf7f142b1979471dfb4ca0bce9f1103527841da98c91fafa3cf"),
    (12, 333859, "45768275fc7e8a1d2dc223e7889ff01bed46b1feafcd10d56e9c22a8a7cf837d"),
)
PIXEL_FINGERPRINTS = (
    (
        "330788be4b5b295dac19881953fcc31cdff62b83a9c9b7e4b9d5ecda6a29ee73",
        "e4cfa2c661d911b1972d209d4398021914b4c1078a61eebed0073cea338d1d0b",
        "a5c26c53a9fb217a7bd7af0a45f53cb251f600db50276ec4efc9c5c07cf9abec",
        "7600964dd48a82d3f4f9203a194701bac644c1a50e4cc1d2021f8eb17210aca0",
        "c9730ea1526f3338325e35ce5bde649f9158613fb8b15b6d1af653d96ac11a0a",
        "549c1f1f17af24bd9996cbe6fd5b6e5e18b9d937db303208832d741322ecc0df",
        "bb2ad0cf47f0ec67a1b4cec90006665f5781c9187420557035f1a4cef7db5b1a",
        "2e8a62148bfe45105ba8e7eb9eb78d62af4a45024bde79318fea1621405d299a",
        "8d0d842c36ae5018bf4a3ce0b81c202148215530a08562ecf0933c482604fba5",
        "c5cf1b09bc164ba50acaec6e97696b37efae069e19798899b70efbe15af1cf6f",
    ),
    (
        "5aea322d41a57620f5f7d961864b17c59f972d5bd0f466063a5fe0a7c2105a20",
        "c6cdb8abd5cca2936c27eab5b40303c8f488e38785db92913ac64e383b852391",
        "2a04a38a46d4f4f74b207149322f9c38d6d0062998b29437a2b51f62246866c3",
        "d6121e7e16578ca6f1b660b7114fd92766baf604f0737f2dbbbbfd247afcee9c",
        "e13d00857484108f793204ca53b6a78cc27ee23aefb40a98776c3faed2e1eb77",
        "5a1e95a5c311ad71ae16a6d3792efa8273612095eb4a962ade8e28b3efa1e64e",
        "a91cb5373cfc00623a32f3a67619795681b8a02d96a1308411c0f11a657072e0",
        "175efdd2ed225545918c136fc6d7916b6909530f6d97f391f407d7d7e82ae872",
        "4d5ea88522187c4f461c0ae48430a8085a58971709b09fdc7124d43f22fc17a9",
        "84b9722a380005c0bb780e634583c9597f0b4ba978888772e13a6acd6a043ee4",
        "c89280e5f8d00ae0c893678085fa44b0ea4ac359bd2e5db08cdaf1f5ff571549",
        "4ae775e5714bab03edc1511315d35a8ec795ac89ed340324b4e95cc36d6a8ff6",
    ),
)
PIXEL_SEQUENCE_SHA256 = (
    "d4320a379148a0ee59d9718d9dd1711097b71e216b7f2dbc241f277de5ef2b71",
    "709113ceace2c5ea62d18bc2fa24efb2c7139c8d70cc92beec132082fc64e5da",
)


def _document(kind: model.DocumentKind, bodies: dict[int, str]) -> bytes:
    title, sections = (
        (model.DOSSIER_TITLE, model.DOSSIER_SECTIONS)
        if kind == "dossier"
        else (model.REPORT_TITLE, model.REPORT_SECTIONS)
    )
    return (
        f"# {title}\n\n"
        + "\n\n".join(
            f"## {number}. {section}\n\n{bodies.get(number, 'Texto sintético.')}"
            for number, section in enumerate(sections, 1)
        )
        + "\n"
    ).encode()


def _table(headers: list[str], rows: list[list[str]]) -> str:
    return (
        "| "
        + " | ".join(headers)
        + " |\n| "
        + " | ".join(["---"] * len(headers))
        + " |\n"
        + "\n".join("| " + " | ".join(row) + " |" for row in rows)
    )


def _long_headers(columns: int) -> list[str]:
    return [f"Cabeçalho técnico sintético prolongado {column}" for column in range(columns)]


def dossier_pagination_extreme() -> bytes:
    """Frozen at 47 lines: prior page ends at y=80.046; section 14 spills."""
    first = (
        "### Limite sintético "
        + "contexto-extremo-" * 18
        + "\n\n"
        + "Parágrafo sintético longo com ação e contexto explícito. " * 380
        + "\n\n- "
        + "item-sintético " * 120
        + "\n\n"
        + "T" * ASCII_TOKEN_LENGTH
        + "\n\nEscapes preservados: "
        + ESCAPED_MARKDOWN
    )
    return _document(
        "dossier",
        {
            1: first,
            13: "\n".join(
                f"Linha de qualificação sintética {number}." for number in range(DOSSIER_FILL_LINES)
            ),
            14: "Marcador final sintético.",
        },
    )


def _boundary_row_table(words: int) -> str:
    return _table(
        _long_headers(8),
        [["palavra " * words, *["x"] * 7]],
    )


def consolidated_table_extreme() -> bytes:
    """Eight-column wrapping plus the valid 16-column resource boundary."""
    rows = [
        [f"R{row}C{column}_" + "I" * 48 + " contexto sintético prolongado" for column in range(8)]
        for row in range(48)
    ]
    sixteen = _table(
        [f"H{column:02d}" for column in range(16)],
        [["x"] * 16],
    )
    first = (
        "### W-EXTREMO — "
        + "heading-sintético-prolongado-" * 16
        + "\n\n"
        + "Prosa sintética longa para qualificação de apresentação. " * 100
        + "\n\n"
        + _table(_long_headers(8), rows)
        + "\n\n"
        + _boundary_row_table(MAX_VALID_ROW_WORDS)
        + "\n\n"
        + sixteen
    )
    return _document("consolidated-report", {1: first})


def _plan(data: bytes, kind: model.DocumentKind) -> renderer._Plan:
    register_fonts()
    return renderer._Layout(parse_presentation_bytes(data, kind)).build()


def _check(data: bytes, kind: model.DocumentKind):
    plan = _plan(data, kind)
    pdf = (
        renderer.render_dossier_pdf(data)
        if kind == "dossier"
        else renderer.render_consolidated_report_pdf(data)
    )
    checked = validation.validate_pdf_bytes(pdf, plan.expected)
    return pdf, plan, checked


def test_dossier_pagination_escape_and_heading_boundaries():
    data = dossier_pagination_extreme()
    parsed = parse_presentation_bytes(data, "dossier")
    pdf, plan, checked = _check(data, "dossier")
    assert checked.page_count == 10
    assert model._ESCAPES == frozenset(ALLOWED_ESCAPES)

    expected_text = "".join(
        span.text
        for block in parsed.blocks
        if isinstance(block, model.Paragraph)
        for span in block.spans
    )
    assert ESCAPED_TEXT in expected_text
    assert expected_text.count("T") >= ASCII_TOKEN_LENGTH

    h3_index = next(
        index
        for index, block in enumerate(parsed.blocks)
        if isinstance(block, Heading) and block.level == 3
    )
    h3_runs = [
        run for page in plan.expected.text_runs for run in page if run.source == (h3_index, -1, -1)
    ]
    assert len({run.y for run in h3_runs}) >= 4

    previous_body = [run for run in plan.expected.text_runs[-2] if run.role == "body"]
    assert min(run.y for run in previous_body) == pytest.approx(80.046)
    final_content = [
        run for run in plan.expected.text_runs[-1] if run.role not in ("header", "footer")
    ]
    assert [run.text for run in final_content] == [
        "14. Mapa de provenance e índice de anexos",
        "Marcador final sintético.",
    ]
    assert pdf


def test_consolidated_wrapped_tables_and_maximum_valid_row():
    data = consolidated_table_extreme()
    parsed = parse_presentation_bytes(data, "consolidated-report")
    pdf, plan, checked = _check(data, "consolidated-report")
    tables = [
        (index, block) for index, block in enumerate(parsed.blocks) if isinstance(block, Table)
    ]
    assert [len(table.header.cells) for _, table in tables] == [8, 8, 16]
    assert len(tables[0][1].rows) == 48
    assert checked.page_count >= 10

    first_index = tables[0][0]
    header_lines = {
        run.y
        for page in plan.expected.text_runs
        for run in page
        if run.source == (first_index, 0, 0)
    }
    assert len(header_lines) > 1
    assert any(run.role == "repeat" for page in plan.expected.text_runs for run in page)
    assert sum(renderer._Layout.columns(16)) == pytest.approx(renderer.WIDTH)

    boundary_index, boundary = tables[1]
    layout = renderer._Layout(parsed)
    boundary_rows = layout.table_rows(boundary)
    assert layout.row_height(boundary_rows[0]) == 66
    assert layout.row_height(boundary_rows[1]) == 630
    assert sum(map(layout.row_height, boundary_rows)) == 696
    assert all(
        len(
            {
                page_number
                for page_number, runs in enumerate(plan.expected.text_runs)
                if any(
                    run.source is not None and run.source[:2] == (boundary_index, row_number)
                    for run in runs
                )
            }
        )
        == 1
        for row_number in range(2)
    )
    assert pdf


def test_first_invalid_row_fails_closed():
    data = _document(
        "consolidated-report",
        {1: _boundary_row_table(FIRST_INVALID_ROW_WORDS)},
    )
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_UNSUPPORTED_LAYOUT$"):
        renderer.render_consolidated_report_pdf(data)


def test_column_resource_boundary_16_and_17():
    sixteen = _table([f"H{i:02d}" for i in range(16)], [["x"] * 16])
    data = _document("consolidated-report", {1: sixteen})
    pdf, _, checked = _check(data, "consolidated-report")
    assert checked.page_count >= 3 and pdf

    seventeen = _table([f"H{i:02d}" for i in range(17)], [["x"] * 17])
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_RESOURCE_LIMIT$"):
        parse_presentation_bytes(
            _document("consolidated-report", {1: seventeen}), "consolidated-report"
        )


def test_page_object_and_depth_budget_boundaries(monkeypatch):
    data = _document("dossier", {1: "Texto sintético."})
    pdf, plan, checked = _check(data, "dossier")
    production_page_limit = limits.MAX_PAGES

    monkeypatch.setattr(limits, "MAX_PAGES", checked.page_count)
    validation.validate_pdf_bytes(pdf, plan.expected)
    monkeypatch.setattr(limits, "MAX_PAGES", checked.page_count - 1)
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_RESOURCE_LIMIT$"):
        validation.validate_pdf_bytes(pdf, plan.expected)

    monkeypatch.setattr(limits, "MAX_PAGES", production_page_limit)
    # Frozen traversal thresholds for this minimal PDF; 800/18 are N-1 failures.
    monkeypatch.setattr(limits, "MAX_OBJECTS", MIN_VALIDATION_NODES)
    validation.validate_pdf_bytes(pdf, plan.expected)
    monkeypatch.setattr(limits, "MAX_OBJECTS", MIN_VALIDATION_NODES - 1)
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_RESOURCE_LIMIT$"):
        validation.validate_pdf_bytes(pdf, plan.expected)

    monkeypatch.setattr(limits, "MAX_OBJECTS", 1_000_000)
    monkeypatch.setattr(limits, "MAX_DEPTH", MIN_VALIDATION_DEPTH)
    validation.validate_pdf_bytes(pdf, plan.expected)
    monkeypatch.setattr(limits, "MAX_DEPTH", MIN_VALIDATION_DEPTH - 1)
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_RESOURCE_LIMIT$"):
        validation.validate_pdf_bytes(pdf, plan.expected)


def test_extreme_determinism_processes_roots_and_aba(tmp_path):
    fixtures = (
        ("dossier", dossier_pagination_extreme()),
        ("consolidated-report", consolidated_table_extreme()),
    )
    local = []
    for kind, data in fixtures:
        render = (
            renderer.render_dossier_pdf
            if kind == "dossier"
            else renderer.render_consolidated_report_pdf
        )
        first = render(data)
        assert render(data) == first
        local.append(first)
    assert renderer.render_dossier_pdf(fixtures[0][1]) == local[0]

    code = (
        "import hashlib,sys; "
        "from evidence_engine.dossier.pdf_limits import impose_worker_limits; "
        "from evidence_engine.dossier.pdf_renderer import "
        "render_dossier_pdf,render_consolidated_report_pdf; "
        "impose_worker_limits(); data=sys.stdin.buffer.read(); "
        "render=render_dossier_pdf if sys.argv[1]=='dossier' "
        "else render_consolidated_report_pdf; "
        "print(hashlib.sha256(render(data)).hexdigest())"
    )
    for fixture_index, (kind, data) in enumerate(fixtures):
        expected = hashlib.sha256(local[fixture_index]).hexdigest()
        for repetition in range(2):
            root = tmp_path / f"{fixture_index}-{repetition}"
            root.mkdir()
            result = subprocess.run(
                [sys.executable, "-c", code, kind],
                input=data,
                cwd=root,
                env={**os.environ, "TMPDIR": str(root)},
                capture_output=True,
                check=True,
                timeout=120,
            )
            assert not result.stderr
            assert result.stdout.decode().strip() == expected

    assert tuple(
        (len(_check(data, kind)[0]), hashlib.sha256(_check(data, kind)[0]).hexdigest())
        for kind, data in fixtures
    ) == tuple((size, digest) for _, size, digest in PDF_FINGERPRINTS)


def _pixel_hashes(pdf: bytes) -> tuple[str, ...]:
    import pypdfium2 as pdfium

    hashes = []
    with pdfium.PdfDocument(pdf) as document:
        for page in document:
            bitmap = page.render(scale=2, fill_color=(255, 255, 255, 255), rev_byteorder=True)
            try:
                image = bitmap.to_pil().convert("RGB")
                assert image.size == (1191, 1684)
                assert image.getextrema()[0][0] == 0
                hashes.append(hashlib.sha256(image.tobytes()).hexdigest())
            finally:
                bitmap.close()
                page.close()
    return tuple(hashes)


@pytest.mark.parametrize(
    "fixture_index,kind,data",
    [
        (0, "dossier", dossier_pagination_extreme()),
        (1, "consolidated-report", consolidated_table_extreme()),
    ],
    ids=["dossier-pagination", "consolidated-tables"],
)
def test_extreme_pdfium_geometry_and_fingerprints(fixture_index, kind, data):
    pdf, plan, checked = _check(data, kind)
    expected = PDF_FINGERPRINTS[fixture_index]
    assert (checked.page_count, len(pdf), hashlib.sha256(pdf).hexdigest()) == expected

    # Existing independent geometry helper checks glyph/body/cell bounds and overlap.
    assert (
        consolidated.pixel_fingerprint(pdf, plan.expected) == PIXEL_SEQUENCE_SHA256[fixture_index]
    )
    first = _pixel_hashes(pdf)
    second = _pixel_hashes(pdf)
    assert first == second == PIXEL_FINGERPRINTS[fixture_index]
    assert (
        hashlib.sha256("".join(first).encode("ascii")).hexdigest()
        == PIXEL_SEQUENCE_SHA256[fixture_index]
    )
