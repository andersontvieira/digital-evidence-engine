"""Two closed human presentation profiles: supplied Markdown -> deterministic PDF."""

import math
import unicodedata
from dataclasses import dataclass, field, replace
from functools import lru_cache

from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]

from evidence_engine.dossier import pdf_limits as limits
from evidence_engine.dossier.pdf_environment import FONT_NAMES, register_fonts, verify_environment
from evidence_engine.dossier.pdf_model import (
    BulletList,
    DocumentKind,
    Heading,
    Paragraph,
    PresentationDocument,
    Span,
    Table,
    parse_presentation_bytes,
)
from evidence_engine.dossier.pdf_reportlab_adapter import A4, ControlledCanvas
from evidence_engine.dossier.pdf_validation import PdfExpectation, PdfTextRun, validate_pdf_bytes
from evidence_engine.errors import EvidenceError

MM = 72 / 25.4
LEFT = round(20 * MM, 3)
RIGHT = round(A4[0] - 20 * MM, 3)
TOP = round(A4[1] - 25 * MM, 3)
BOTTOM = round(25 * MM, 3)
WIDTH = round(170 * MM, 3)
HEIGHT = TOP - BOTTOM


@dataclass(frozen=True)
class _Style:
    size: float
    leading: float
    before: float = 0
    after: float = 6
    bold: bool = False


_BODY = _Style(10.5, 14)
_H1 = _Style(18, 22, 0, 14, True)
_H2 = _Style(13, 17, 14, 8, True)
_H3 = _Style(11, 14, 10, 6, True)
_TOC = _Style(9, 12, 0, 0)
_CELL = _Style(9, 12, 0, 0)
_HEADER_CELL = _Style(9, 12, 0, 0, True)
type _Key = tuple[int, int, int]


@dataclass(frozen=True)
class _Piece:
    text: str
    font: str
    size: float
    start: int
    end: int
    width: float


@dataclass(frozen=True)
class _Line:
    pieces: tuple[_Piece, ...]


@dataclass(frozen=True)
class _Box:
    x: float
    bottom: float
    width: float
    height: float
    header: bool


@dataclass
class _Page:
    runs: list[PdfTextRun] = field(default_factory=list)
    boxes: list[_Box] = field(default_factory=list)


@dataclass(frozen=True)
class _Plan:
    expected: PdfExpectation
    boxes: tuple[tuple[_Box, ...], ...]


class _Layout:
    def __init__(self, document: PresentationDocument) -> None:
        if document.kind not in ("dossier", "consolidated-report"):
            limits.fail("UNSUPPORTED_MARKDOWN")
        self.document = document
        self.pages: list[_Page] = []
        self.y = TOP
        self.destinations: list[tuple[int, float, float]] = []
        self.outlines: list[tuple[str, int, int]] = []
        self.width_of = lru_cache(maxsize=4096)(
            lambda text, font, size: float(pdfmetrics.stringWidth(text, font, size))
        )
        self.new_page()

    def new_page(self) -> None:
        if len(self.pages) >= limits.MAX_PAGES:
            limits.fail("RESOURCE_LIMIT")
        self.pages.append(_Page())
        self.y = TOP

    def wrap(self, spans: tuple[Span, ...], style: _Style, width: float) -> tuple[_Line, ...]:
        text = "".join(span.text for span in spans)
        if any(
            unicodedata.combining(c)
            or (unicodedata.category(c) in ("Cc", "Cf", "Cs") and c != "\n")
            for c in text
        ):
            limits.fail("FONT_UNSUPPORTED")
        # Styles are derived from the closed DTO, never passed through mini-markup.
        styles: list[tuple[int, int, str, float]] = []
        offset = 0
        for span in spans:
            font = FONT_NAMES[
                4 if span.kind == "literal" else 1 if style.bold or span.kind == "bold" else 0
            ]
            size = 9.0 if span.kind == "literal" else style.size
            styles.append((offset, offset + len(span.text), font, size))
            offset += len(span.text)
        if not text:
            return (_Line((_Piece("", FONT_NAMES[1 if style.bold else 0], style.size, 0, 0, 0),)),)
        positions: list[tuple[str, float, float]] = []
        for start, end, font, size in styles:
            for char in text[start:end]:
                positions.append(
                    (font, size, 0 if char == "\n" else self.width_of(char, font, size))
                )
        result: list[_Line] = []
        start = 0
        while start < len(text):
            end, last_space, used = start, start, 0.0
            while end < len(text):
                if text[end] == "\n":
                    end += 1
                    break
                next_width = positions[end][2]
                if used + next_width > width + 0.000001:
                    if end == start:
                        limits.fail("UNSUPPORTED_LAYOUT")
                    if last_space > start:
                        end = last_space
                    break
                used += next_width
                end += 1
                if text[end - 1] == " ":
                    last_space = end
            pieces: list[_Piece] = []
            cursor = start
            while cursor < end:
                font, size, _ = positions[cursor]
                stop = cursor + 1
                while stop < end and positions[stop][:2] == (font, size):
                    stop += 1
                visible = text[cursor:stop].removesuffix("\n")
                pieces.append(
                    _Piece(visible, font, size, cursor, stop, self.width_of(visible, font, size))
                )
                cursor = stop
            result.append(_Line(tuple(pieces)))
            start = end
        return tuple(result)

    def line(
        self,
        line: _Line,
        x: float,
        top: float,
        source: _Key | None,
        role: str = "body",
        toc_entry: int = 0,
    ) -> None:
        ascent = max(float(pdfmetrics.getAscentDescent(p.font, p.size)[0]) for p in line.pieces)
        for piece in line.pieces:
            self.pages[-1].runs.append(
                PdfTextRun(
                    piece.text,
                    round(x, 3),
                    round(top - ascent, 3),
                    piece.font,
                    piece.size,
                    role,
                    source,
                    piece.start,
                    piece.end,
                    toc_entry,
                )
            )
            x += piece.width

    def paragraph(
        self, spans: tuple[Span, ...], source: _Key, style: _Style, indent: float = 0
    ) -> None:
        lines = self.wrap(spans, style, WIDTH - indent)
        self.y -= style.before
        cursor = 0
        while cursor < len(lines):
            available = max(0, math.floor((self.y - BOTTOM + 0.000001) / style.leading))
            remaining = len(lines) - cursor
            take = min(available, remaining)
            if take < remaining and remaining - take == 1:
                take -= 1
            if take <= 0 or (take < remaining and take < 2):
                self.new_page()
                continue
            for line in lines[cursor : cursor + take]:
                self.line(line, LEFT + indent, self.y, source)
                self.y -= style.leading
            cursor += take
            if cursor < len(lines):
                self.new_page()
        self.y -= style.after

    def table_rows(self, table: Table) -> tuple[tuple[tuple[_Line, ...], ...], ...]:
        widths = self.columns(len(table.header.cells))
        return tuple(
            tuple(
                self.wrap(cell.spans, _HEADER_CELL if row_index == 0 else _CELL, width - 6)
                for cell, width in zip(row.cells, widths, strict=True)
            )
            for row_index, row in enumerate((table.header, *table.rows))
        )

    @staticmethod
    def columns(count: int) -> tuple[float, ...]:
        total = round(WIDTH * 1000)
        base, remainder = divmod(total, count)
        return tuple((base + (i < remainder)) / 1000 for i in range(count))

    @staticmethod
    def row_height(row: tuple[tuple[_Line, ...], ...]) -> float:
        return max(len(cell) for cell in row) * 12 + 6

    def draw_row(
        self,
        index: int,
        row_index: int,
        row: tuple[tuple[_Line, ...], ...],
        widths: tuple[float, ...],
        repeated: bool = False,
    ) -> None:
        height = self.row_height(row)
        x = LEFT
        for column, (cell, width) in enumerate(zip(row, widths, strict=True)):
            self.pages[-1].boxes.append(
                _Box(round(x, 3), round(self.y - height, 3), width, height, row_index == 0)
            )
            for line_index, line in enumerate(cell):
                self.line(
                    line,
                    x + 3,
                    self.y - 3 - 12 * line_index,
                    (index, row_index, column),
                    "repeat" if repeated else "body",
                )
            x += width
        self.y -= height

    def table(self, index: int, table: Table) -> None:
        rows = self.table_rows(table)
        header_height = self.row_height(rows[0])
        first = header_height + (self.row_height(rows[1]) if len(rows) > 1 else 0)
        if first > HEIGHT:
            limits.fail("UNSUPPORTED_LAYOUT")
        if self.y - first < BOTTOM:
            self.new_page()
        widths = self.columns(len(table.header.cells))
        self.draw_row(index, 0, rows[0], widths)
        for row_index, row in enumerate(rows[1:], 1):
            height = self.row_height(row)
            if header_height + height > HEIGHT:
                limits.fail("UNSUPPORTED_LAYOUT")
            if self.y - height < BOTTOM:
                self.new_page()
                self.draw_row(index, 0, rows[0], widths, repeated=True)
            self.draw_row(index, row_index, row, widths)
        self.y -= 6

    def keep_height(self, index: int) -> float:
        height = 0.0
        for block in self.document.blocks[index:]:
            if isinstance(block, Heading):
                style = _H2 if block.level == 2 else _H3
                height += (
                    style.before
                    + len(self.wrap(block.spans, style, WIDTH)) * style.leading
                    + style.after
                )
            elif isinstance(block, Table):
                rows = self.table_rows(block)
                return (
                    height
                    + self.row_height(rows[0])
                    + (self.row_height(rows[1]) if len(rows) > 1 else 0)
                )
            elif isinstance(block, Paragraph):
                return height + self.first_lines(block.spans, WIDTH) * _BODY.leading
            elif isinstance(block, BulletList):
                if block.items:
                    return (
                        height
                        + self.first_lines(block.items[0].spans, WIDTH - 5 * MM) * _BODY.leading
                    )
        return height

    def first_lines(self, spans: tuple[Span, ...], width: float) -> int:
        count = len(self.wrap(spans, _BODY, width))
        # Three lines cannot be divided without leaving a one-line widow.
        return count if count <= 3 else 2

    def mark(self, text: str, depth: int) -> None:
        self.destinations.append((len(self.pages) - 1, LEFT, round(self.y, 3)))
        self.outlines.append((text, len(self.pages) - 1, depth))

    def build(self) -> _Plan:
        heading = self.document.blocks[0]
        if not isinstance(heading, Heading) or heading.level != 1:
            limits.fail("UNSUPPORTED_MARKDOWN")
        self.mark(self.document.title, 0)
        self.paragraph(heading.spans, (0, -1, -1), _H1)
        self.line(
            self.wrap((Span("text", "Sumário", 0, 0),), _TOC, WIDTH)[0],
            LEFT,
            self.y,
            None,
            "toc_title",
        )
        self.y -= 18
        toc: list[tuple[int, int, float, tuple[float, float, float, float]]] = []
        headings = [b for b in self.document.blocks if isinstance(b, Heading) and b.level == 2]
        for ordinal, toc_heading in enumerate(headings, 1):
            lines = self.wrap(toc_heading.spans, _TOC, WIDTH - 36)
            height = len(lines) * 12
            if self.y - height < BOTTOM:
                if len(self.pages) >= 2:
                    limits.fail("UNSUPPORTED_LAYOUT")
                self.new_page()
            top = self.y
            for line in lines:
                self.line(line, LEFT, self.y, None, "toc_label", ordinal)
                self.y -= 12
            toc.append(
                (len(self.pages) - 1, ordinal, top, (LEFT, round(self.y, 3), RIGHT, round(top, 3)))
            )
            # Placeholder width is reserved; actual digits do not influence wrapping.
            self.line(
                self.wrap((Span("text", "0000", 0, 0),), _TOC, 36)[0],
                RIGHT - self.width_of("0000", FONT_NAMES[0], 9),
                top,
                None,
                "toc_page",
                ordinal,
            )
        self.new_page()
        for index, block in enumerate(self.document.blocks[1:], 1):
            if isinstance(block, Heading):
                needed = self.keep_height(index)
                if needed > HEIGHT:
                    limits.fail("UNSUPPORTED_LAYOUT")
                if self.y - needed < BOTTOM:
                    self.new_page()
                if block.level == 2:
                    self.mark("".join(s.text for s in block.spans), 1)
                self.paragraph(block.spans, (index, -1, -1), _H2 if block.level == 2 else _H3)
            elif isinstance(block, Paragraph):
                self.paragraph(block.spans, (index, -1, -1), _BODY)
            elif isinstance(block, Table):
                self.table(index, block)
            elif isinstance(block, BulletList):
                for item_index, item in enumerate(block.items):
                    # The bullet is presentation syntax, not a new source character.
                    if (
                        self.y - self.first_lines(item.spans, WIDTH - 5 * MM) * _BODY.leading
                        < BOTTOM
                    ):
                        self.new_page()
                    self.pages[-1].runs.append(
                        PdfTextRun(
                            "•",
                            LEFT,
                            round(
                                self.y - float(pdfmetrics.getAscentDescent(FONT_NAMES[0], 10.5)[0]),
                                3,
                            ),
                            FONT_NAMES[0],
                            10.5,
                            "bullet",
                            (index, item_index, -1),
                        )
                    )
                    self.paragraph(item.spans, (index, item_index, -1), _BODY, 5 * MM)
        links = []
        link_destinations = []
        link_boxes = []
        for page, ordinal, _, box in toc:
            destination = self.destinations[ordinal]
            number = str(destination[0] + 1)
            runs = self.pages[page].runs
            for i, run in enumerate(runs):
                if run.role == "toc_page" and run.toc_entry == ordinal:
                    runs[i] = replace(
                        run,
                        text=number,
                        x=round(RIGHT - self.width_of(number, run.font, run.size), 3),
                    )
            links.append((page, destination[0]))
            link_destinations.append(destination)
            link_boxes.append(box)
        for page_number, layout_page in enumerate(self.pages, 1):
            footer = f"Página {page_number}"
            layout_page.runs.extend(
                (
                    PdfTextRun(
                        "Dossiê técnico"
                        if self.document.kind == "dossier"
                        else "Relatório técnico consolidado",
                        LEFT,
                        round(A4[1] - 12 * MM, 3),
                        FONT_NAMES[0],
                        9,
                        "header",
                    ),
                    PdfTextRun(
                        footer,
                        round(RIGHT - self.width_of(footer, FONT_NAMES[0], 9), 3),
                        round(12 * MM, 3),
                        FONT_NAMES[0],
                        9,
                        "footer",
                    ),
                )
            )
        all_runs = tuple(tuple(p.runs) for p in self.pages)
        expected = PdfExpectation(
            self.document.title,
            tuple("" for _ in all_runs),
            tuple(self.outlines),
            tuple(links),
            self.document,
            all_runs,
            tuple(self.destinations),
            tuple(link_destinations),
            tuple(link_boxes),
        )
        return _Plan(expected, tuple(tuple(p.boxes) for p in self.pages))


def _paint(plan: _Plan) -> bytes:
    output = limits.BoundedPdfBuffer()
    canvas = ControlledCanvas(output, plan.expected.title)
    for page_number, runs in enumerate(plan.expected.text_runs):
        for ordinal, (page, x, y) in enumerate(plan.expected.destinations):
            if page == page_number:
                canvas.bookmarkPage(f"heading-{ordinal}", fit="XYZ", left=x, top=y, zoom=0)
                canvas.addOutlineEntry(
                    plan.expected.outlines[ordinal][0],
                    f"heading-{ordinal}",
                    level=0 if ordinal == 0 else 1,
                )
        canvas.setLineWidth(0.5)
        canvas.setStrokeGray(0.5)
        for box in plan.boxes[page_number]:
            canvas.setFillGray(0.9 if box.header else 1)
            canvas.rect(box.x, box.bottom, box.width, box.height, stroke=1, fill=1)
        canvas.setFillGray(0)
        for run in runs:
            if run.text:
                canvas.setFont(run.font, run.size)
                canvas.drawString(run.x, run.y, run.text)
        for ordinal, ((page, _), link_box) in enumerate(
            zip(plan.expected.links, plan.expected.link_boxes, strict=True), 1
        ):
            if page == page_number:
                canvas.linkRect("", f"heading-{ordinal}", link_box, relative=0, thickness=0)
        canvas.showPage()
    canvas.save()
    return output.getvalue()


def render_dossier_pdf(data: bytes) -> bytes:
    """Render supplied dossier Markdown only; no source paths, package or case I/O."""
    return _render_pdf(data, "dossier")


def render_consolidated_report_pdf(data: bytes) -> bytes:
    """Render supplied canonical report Markdown without rebuilding its narrative."""
    return _render_pdf(data, "consolidated-report")


def _render_pdf(data: bytes, kind: DocumentKind) -> bytes:
    try:
        with limits.phase_boundary(
            "RENDER_DOSSIER" if kind == "dossier" else "RENDER_CONSOLIDATED"
        ):
            verify_environment()
            document = parse_presentation_bytes(data, kind)
            register_fonts()
            first = _Layout(document).build()
            second = _Layout(document).build()
            if first != second:
                limits.fail("RENDER_FAILURE")
            pdf = _paint(second)
        validate_pdf_bytes(pdf, second.expected)
        return pdf
    except EvidenceError:
        raise
    except (MemoryError, RecursionError):
        limits.fail("RESOURCE_LIMIT")
    except Exception:
        limits.fail("RENDER_FAILURE")
