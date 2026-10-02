"""Independent read-only validation of foundation and both closed human profiles."""

import logging
import re
import warnings
from dataclasses import dataclass
from io import BytesIO
from typing import Any, cast

from pypdf import PdfReader
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DictionaryObject,
    IndirectObject,
    StreamObject,
    read_object,
)

from evidence_engine.dossier import pdf_limits as limits
from evidence_engine.dossier.pdf_model import (
    DOSSIER_SECTIONS,
    DOSSIER_TITLE,
    REPORT_SECTIONS,
    REPORT_TITLE,
    BulletList,
    Heading,
    Paragraph,
    PresentationDocument,
    Table,
)
from evidence_engine.errors import EvidenceError

_INFO = {
    "/Subject": "Apresentação técnica de artefato aprovado; sem nova análise.",
    "/Creator": "Digital Evidence Engine dossier.pdf_export/1.0.0",
    "/Producer": "Digital Evidence Engine dossier.pdf_export/1.0.0",
}
_FORBIDDEN = frozenset(
    {
        "/JavaScript",
        "/JS",
        "/OpenAction",
        "/AA",
        "/URI",
        "/GoToR",
        "/Launch",
        "/EmbeddedFiles",
        "/Filespec",
        "/AF",
        "/AcroForm",
        "/XFA",
        "/Encrypt",
        "/Metadata",
        "/RichMedia",
        "/Movie",
        "/Sound",
        "/Sig",
        "/Signature",
        "/SubmitForm",
        "/ImportData",
        "/Rendition",
        "/3D",
        "/XObject",
        "/ObjStm",
        "/XRef",
        "/Collection",
    }
)


@dataclass(frozen=True)
class PdfTextRun:
    text: str
    x: float
    y: float
    font: str
    size: float
    role: str = "body"
    source: tuple[int, int, int] | None = None
    start: int = 0
    end: int = 0
    toc_entry: int = 0


@dataclass(frozen=True)
class PdfExpectation:
    title: str
    page_text: tuple[str, ...]
    # Fixed ordinal destinations: (title, page index, parent depth).
    outlines: tuple[tuple[str, int, int], ...]
    links: tuple[tuple[int, int], ...]
    presentation: PresentationDocument | None = None
    text_runs: tuple[tuple[PdfTextRun, ...], ...] = ()
    destinations: tuple[tuple[int, float, float], ...] = ()
    link_destinations: tuple[tuple[int, float, float], ...] = ()
    link_boxes: tuple[tuple[float, float, float, float], ...] = ()


@dataclass(frozen=True)
class PdfValidation:
    page_count: int
    object_count: int
    extracted_text: tuple[str, ...]


class _ParserWarnings(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.seen = False

    def emit(self, record: logging.LogRecord) -> None:
        # Never retain or expose parser payload/path diagnostics.
        self.seen = True


def _require(condition: bool) -> None:
    if not condition:
        limits.fail("PDF_VALIDATION_FAILURE")


def _layout(text: str) -> str:
    return re.sub(r"[ \n]+", " ", text).strip(" ")


def _check_presentation(expected: PdfExpectation) -> None:
    """Account for every source code point independently of the painting loop."""
    document = expected.presentation
    assert document is not None
    # Select contractual expectations from the kind, never from renderer counts.
    sections: tuple[str, ...]
    if document.kind == "dossier":
        title, sections, header, count = DOSSIER_TITLE, DOSSIER_SECTIONS, "Dossiê técnico", 14
    elif document.kind == "consolidated-report":
        title, sections, header, count = (
            REPORT_TITLE,
            REPORT_SECTIONS,
            "Relatório técnico consolidado",
            20,
        )
    else:
        limits.fail("PDF_VALIDATION_FAILURE")
    _require(document.title == expected.title == title and len(sections) == count)
    sources: dict[tuple[int, int, int], str] = {}
    headings: list[tuple[int, str]] = []
    tables: dict[int, Table] = {}
    for index, block in enumerate(document.blocks):
        if isinstance(block, (Heading, Paragraph)):
            text = "".join(s.text for s in block.spans)
            sources[index, -1, -1] = text
            if isinstance(block, Heading) and block.level in (1, 2):
                headings.append((index, text))
        elif isinstance(block, BulletList):
            for item_index, item in enumerate(block.items):
                sources[index, item_index, -1] = "".join(s.text for s in item.spans)
        elif isinstance(block, Table):
            tables[index] = block
            for row_index, row in enumerate((block.header, *block.rows)):
                for column, cell in enumerate(row.cells):
                    sources[index, row_index, column] = "".join(s.text for s in cell.spans)
    _require(
        [text for _, text in headings]
        == [title, *(f"{i}. {section}" for i, section in enumerate(sections, 1))]
    )
    _require(len(expected.text_runs) == len(expected.page_text))
    _require(len(expected.destinations) == len(expected.outlines) == count + 1)
    _require(
        len(expected.links) == len(expected.link_boxes) == len(expected.link_destinations) == count
    )
    ranks = {key: i for i, key in enumerate(sources)}
    offsets = dict.fromkeys(sources, 0)
    seen_sources: set[tuple[int, int, int]] = set()
    source_pages: dict[tuple[int, int, int], set[int]] = {}
    repeats: dict[tuple[int, tuple[int, int, int]], int] = {}
    toc_labels: dict[int, str] = {}
    toc_numbers: dict[int, str] = {}
    toc_pages: set[int] = set()
    toc_titles = 0
    bullets: list[tuple[int, int, int] | None] = []
    last_rank = -1
    for page, runs in enumerate(expected.text_runs):
        _require(bool(runs))
        chrome: list[str] = []
        page_sources: list[tuple[int, tuple[int, int, int], str]] = []
        for position, run in enumerate(runs):
            _require(
                run.font
                in (
                    "DejaVuSans",
                    "DejaVuSans-Bold",
                    "DejaVuSans-Oblique",
                    "DejaVuSans-BoldOblique",
                    "DejaVuSansMono",
                    "DejaVuSansMono-Bold",
                )
                and run.size >= 9
            )
            if run.role in ("body", "repeat"):
                _require(run.source in sources)
                assert run.source is not None
                source = sources[run.source]
                _require(0 <= run.start <= run.end <= len(source))
                _require(run.text == source[run.start : run.end].removesuffix("\n"))
                _require(56.68 <= run.x <= 538.60 and 70.85 <= run.y <= 771.03)
                page_sources.append((position, run.source, run.role))
                source_pages.setdefault(run.source, set()).add(page)
                if run.role == "body":
                    _require(ranks[run.source] >= last_rank and run.start == offsets[run.source])
                    offsets[run.source] = run.end
                    seen_sources.add(run.source)
                    last_rank = ranks[run.source]
                else:
                    _require(run.source[0] in tables and run.source[1] == 0)
                    _require(run.source in seen_sources)
                    key = (page, run.source)
                    _require(run.start == repeats.get(key, 0))
                    repeats[key] = run.end
            elif run.role in ("header", "footer"):
                _require(run.source is None and run.size == 9 and run.font == "DejaVuSans")
                _require(run.text == (header if run.role == "header" else f"Página {page + 1}"))
                _require(abs(run.y - (807.874 if run.role == "header" else 34.016)) <= 0.01)
                chrome.append(run.role)
            elif run.role == "toc_title":
                _require(run.text == "Sumário" and run.source is None and page == 0)
                toc_titles += 1
                toc_pages.add(page)
            elif run.role in ("toc_label", "toc_page"):
                _require(run.source is None and 1 <= run.toc_entry <= count and page < 2)
                _require(run.size == 9 and run.font == "DejaVuSans")
                toc_pages.add(page)
                target = toc_labels if run.role == "toc_label" else toc_numbers
                target[run.toc_entry] = target.get(run.toc_entry, "") + run.text
            elif run.role == "bullet":
                _require(run.text == "•" and run.source in sources)
                assert run.source is not None
                _require(isinstance(document.blocks[run.source[0]], BulletList))
                bullets.append(run.source)
            else:
                _require(False)
        _require(chrome == ["header", "footer"])
        # Every page carrying a logical table row carries precisely its header.
        for table_index, table in tables.items():
            row_positions = [
                p for p, key, _ in page_sources if key[0] == table_index and key[1] > 0
            ]
            header_positions = [
                p for p, key, _ in page_sources if key[0] == table_index and key[1] == 0
            ]
            if row_positions:
                _require(bool(header_positions) and max(header_positions) < min(row_positions))
                header_keys = {
                    key for _, key, _ in page_sources if key[0] == table_index and key[1] == 0
                }
                _require(
                    header_keys == {(table_index, 0, col) for col in range(len(table.header.cells))}
                )
            if header_positions and table.rows:
                _require(bool(row_positions))
        _require(any(r.role in ("body", "toc_label") for r in runs))
    _require(seen_sources == set(sources))
    _require(all(offsets[key] == len(text) for key, text in sources.items()))
    _require(all(end == len(sources[key]) for (_, key), end in repeats.items()))
    for index, table in tables.items():
        for row_index, row in enumerate(table.rows, 1):
            # A logical row (including all wrapped cells) must stay on one page.
            pages = set().union(
                *(source_pages[index, row_index, col] for col in range(len(row.cells)))
            )
            _require(len(pages) == 1)
    expected_bullets = [key for key in sources if isinstance(document.blocks[key[0]], BulletList)]
    _require(bullets == expected_bullets)
    _require(toc_titles == 1 and set(toc_labels) == set(toc_numbers) == set(range(1, count + 1)))
    _require(expected.destinations[1][0] == max(toc_pages) + 1)
    for ordinal, (index, text) in enumerate(headings):
        page, _, _ = expected.destinations[ordinal]
        _require(source_pages[index, -1, -1] == {page})
        _require(expected.outlines[ordinal] == (text, page, 0 if ordinal == 0 else 1))
        if ordinal:
            _require(toc_labels[ordinal] == text and toc_numbers[ordinal] == str(page + 1))
            _require(expected.link_destinations[ordinal - 1] == expected.destinations[ordinal])


def _check_page_text(page: Any, runs: tuple[PdfTextRun, ...]) -> None:
    observed: list[tuple[str, float, float, str, float]] = []
    has_text_operator = False

    def before(operator: bytes, operands: Any, cm: Any, tm: Any) -> None:
        nonlocal has_text_operator
        if operator == b"BT":
            has_text_operator = False
        elif operator == b"Tj":
            has_text_operator = True

    def visit(text: str, cm: list[float], tm: list[float], font: Any, size: float) -> None:
        if not text:
            return
        # pypdf may infer a separator at Tm/Tf before any string was drawn.
        # It is not PDF text. Whitespace from actual Tj operators is retained.
        if not has_text_operator and text.strip(" \n") == "":
            return
        _require(font is not None and list(cm) == [1, 0, 0, 1, 0, 0])
        base_font = str(font.get("/BaseFont"))
        _require(re.match(r"/[A-Z]{6}\+", base_font) is not None)
        logical_font = base_font[8:]
        position = (float(tm[4]), float(tm[5]), logical_font, size)
        # A public drawString may switch dynamic subsets inside one text matrix.
        # Join only contiguous fragments at that exact matrix/font/size, never
        # across cells, lines or pages and never by stripping source whitespace.
        if observed and observed[-1][1:] == position and not observed[-1][0].endswith("\n"):
            observed[-1] = (observed[-1][0] + text, *position)
        else:
            observed.append((text, *position))

    page.extract_text(visitor_text=visit, visitor_operand_before=before)
    visible = [run for run in runs if run.text]
    _require(len(observed) == len(visible))
    for actual, run in zip(observed, visible, strict=True):
        text, x, y, font, size = actual
        if "\x00" in text or "\ufffd" in text and "\ufffd" not in run.text:
            limits.fail("FONT_UNSUPPORTED")
        _require(text in (run.text, run.text + "\n"))
        _require(abs(x - run.x) <= 0.01 and abs(y - run.y) <= 0.01)
        _require(abs(size - run.size) <= 0.001)
        _require(font == run.font)


def _check_drawing(content: ContentStream) -> None:
    """Permit only the renderer's black text and pre-text table rectangles."""
    fill = 0.0
    painted_text = False
    for operands, operator in content.operations:
        if operator == b"cm":
            _require(list(operands) == [1, 0, 0, 1, 0, 0])
        elif operator in (b"q", b"Q"):
            _require(False)
        elif operator in (b"w", b"G"):
            _require(list(operands) == [0.5])
        elif operator == b"g":
            _require(len(operands) == 1 and float(operands[0]) in (0, 0.9, 1))
            fill = float(operands[0])
        elif operator == b"Tj":
            _require(fill == 0)
            painted_text = True
        elif operator == b"re":
            _require(not painted_text and fill in (0.9, 1) and len(operands) == 4)
            x, y, width, height = (float(v) for v in operands)
            _require(width > 0 and height > 0)
            _require(56.68 <= x < x + width <= 538.60)
            _require(70.85 <= y < y + height <= 771.03)
        elif operator == b"B*":
            _require(not painted_text and fill in (0.9, 1))


def _known_dictionary(value: DictionaryObject) -> bool:
    """Closed foundation profile; later layout slices must qualify any extension."""
    fields = set(value)
    shapes = {
        "/Catalog": {"/Type", "/Pages", "/Lang", "/Outlines", "/PageMode"},
        "/Pages": {"/Type", "/Count", "/Kids"},
        "/Page": {
            "/Type",
            "/Annots",
            "/Contents",
            "/MediaBox",
            "/CropBox",
            "/Parent",
            "/Resources",
            "/Rotate",
            "/Trans",
        },
        "/Font": {
            "/Type",
            "/BaseFont",
            "/FirstChar",
            "/FontDescriptor",
            "/LastChar",
            "/Name",
            "/Subtype",
            "/ToUnicode",
            "/Widths",
        },
        "/FontDescriptor": {
            "/Type",
            "/Ascent",
            "/CapHeight",
            "/Descent",
            "/Flags",
            "/FontBBox",
            "/FontFile2",
            "/FontName",
            "/ItalicAngle",
            "/MissingWidth",
            "/StemV",
        },
        "/Outlines": {"/Type", "/Count", "/First", "/Last"},
        "/Annot": {"/Type", "/Subtype", "/Border", "/Contents", "/Dest", "/Rect", "/A"},
    }
    kind = value.get("/Type")
    if kind is not None:
        return isinstance(kind, str) and kind in shapes and fields <= shapes[kind]
    if isinstance(value, StreamObject):
        return fields <= {"/Length1", "/Filter"}
    if not fields:
        return True  # Empty /Trans emitted by the qualified Canvas.
    if "/Title" in fields and "/Parent" in fields:
        return fields <= {
            "/Title",
            "/Parent",
            "/Dest",
            "/First",
            "/Last",
            "/Count",
            "/Next",
            "/Prev",
        }
    if all(re.fullmatch(r"/F[1-9][0-9]*\+[0-9]+", name) for name in fields):
        return True
    return fields in (
        {"/Root", "/Info", "/Size"},
        {"/Title", "/Subject", "/Creator", "/Producer"},
        {"/Font", "/ProcSet"},
        {"/S", "/D"},
    )


def _validate(data: bytes, expected: PdfExpectation) -> PdfValidation:
    if expected.presentation is not None:
        _check_presentation(expected)
    _require(data.startswith(b"%PDF-1.4\n"))
    end = re.search(rb"startxref\s+(\d+)\s+%%EOF\n?\Z", data)
    _require(end is not None)
    assert end is not None
    xref_position = int(end[1])
    _require(data[xref_position : xref_position + 5] == b"xref\n")
    # The qualified renderer emits exactly one classic contiguous xref table.
    xref = re.fullmatch(
        rb"xref\n0 (\d+)\n((?:\d{10} \d{5} [nf] \n)+)trailer\n([\s\S]+)",
        data[xref_position : end.start()],
    )
    _require(xref is not None)
    assert xref is not None
    entries = xref[2].splitlines()
    _require(len(entries) == int(xref[1]) and entries[0] == b"0000000000 65535 f ")
    if len(entries) > limits.MAX_OBJECTS:
        limits.fail("RESOURCE_LIMIT")
    reader = PdfReader(BytesIO(data), strict=True)
    _require(set(reader.trailer) == {"/Root", "/Info", "/Size"})
    _require(reader.trailer.get("/Size") == len(entries))
    offsets = []
    for number, entry in enumerate(entries[1:], 1):
        offset = int(entry[:10])
        offsets.append(offset)
        _require(entry[11:] == b"00000 n ")
        _require(data[offset:].startswith(f"{number} 0 obj\n".encode()))
        _require(reader.xref.get(0, {}).get(number) == offset)
    _require(offsets == sorted(set(offsets)))
    # Decode all declared objects. Reject orphan payloads and gaps between objects.
    for number, (start, stop) in enumerate(
        zip(offsets, offsets[1:] + [xref_position], strict=True), 1
    ):
        stream = BytesIO(data)
        reader.get_object(IndirectObject(number, 0, reader))
        stream.seek(start + len(f"{number} 0 obj\n".encode()))
        read_object(stream, reader)
        _require(data[stream.tell() : stop].strip() == b"endobj")
    _require(re.fullmatch(rb"%PDF-1\.4\n%[^\r\n]*\n", data[: offsets[0]]) is not None)
    root = reader.trailer["/Root"]
    _require(isinstance(root, DictionaryObject) and root.get("/Type") == "/Catalog")
    assert isinstance(root, DictionaryObject)
    _require(root.get("/Lang") == "pt-BR")
    _require(set(root) <= {"/Type", "/Pages", "/Lang", "/Outlines", "/PageMode"})
    info = reader.trailer["/Info"]
    _require(isinstance(info, DictionaryObject))
    assert isinstance(info, DictionaryObject)
    _require(dict(cast(dict[str, Any], info)) == {"/Title": expected.title, **_INFO})

    pending: list[tuple[Any, int]] = [(reader.trailer, 0)]
    seen: set[tuple[int, int]] = set()
    nodes = 0
    decoded_bytes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > limits.MAX_OBJECTS or depth > limits.MAX_DEPTH:
            limits.fail("RESOURCE_LIMIT")
        if isinstance(value, IndirectObject):
            key = (value.idnum, value.generation)
            if key in seen:
                continue
            seen.add(key)
            value = value.get_object()
        if isinstance(value, DictionaryObject):
            _require(_known_dictionary(value))
            _require(not (set(value) & _FORBIDDEN))
            _require(
                value.get("/Type") not in _FORBIDDEN and value.get("/Subtype") not in _FORBIDDEN
            )
            if "/S" in value:
                _require(value.get("/S") == "/GoTo")
            if isinstance(value, StreamObject):
                _require(value.get("/Filter") in (None, "/FlateDecode"))
                decoded_bytes += len(value.get_data())
                if decoded_bytes > limits.MAX_PDF_BYTES:
                    limits.fail("RESOURCE_LIMIT")
            pending.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, ArrayObject):
            pending.extend((v, depth + 1) for v in value)
    _require(seen == {(i, 0) for i in range(1, len(entries))})

    pages = reader.pages
    if len(pages) > limits.MAX_PAGES:
        limits.fail("RESOURCE_LIMIT")
    _require(1 <= len(pages) == len(expected.page_text))
    page_ids = {
        page.indirect_reference.idnum: i for i, page in enumerate(pages) if page.indirect_reference
    }
    _require(len(page_ids) == len(pages))
    links: list[tuple[int, int]] = []
    link_destinations: list[tuple[int, float, float]] = []
    link_boxes: list[tuple[float, float, float, float]] = []
    texts = []
    for i, page in enumerate(pages):
        content = ContentStream(page.get_contents(), reader)
        operators = {b"cm", b"BT", b"ET", b"Tf", b"TL", b"Tm", b"Tj", b"T*", b"q", b"Q"}
        if expected.presentation is not None:
            operators |= {b"w", b"g", b"G", b"n", b"re", b"B*"}
            _check_drawing(content)
        _require(all(op in operators for _, op in content.operations))
        _require(not page.get("/Trans"))
        _require(page.get("/Rotate", 0) == 0)
        for box in (page.mediabox, page.cropbox):
            _require(
                all(
                    abs(float(a) - b) <= 0.01
                    for a, b in zip(box, (0, 0, 595.276, 841.890), strict=True)
                )
            )
        resources = cast(DictionaryObject, page["/Resources"])
        _require("/Font" in resources)
        for ref in cast(DictionaryObject, resources["/Font"]).values():
            font = ref.get_object()
            _require(font.get("/Subtype") == "/TrueType")
            _require("/ToUnicode" in font and "/FontDescriptor" in font)
            _require("/FontFile2" in font["/FontDescriptor"])
            _require(bool(font["/ToUnicode"].get_data()))
        for annotation_ref in page.get("/Annots", []):
            annotation = annotation_ref.get_object()
            _require(annotation.get("/Subtype") == "/Link")
            _require(
                set(annotation)
                <= {"/Type", "/Subtype", "/Rect", "/Border", "/Dest", "/Contents", "/A"}
            )
            destination = annotation.get("/Dest")
            if destination is None:
                action = annotation["/A"]
                _require(set(action) == {"/S", "/D"} and action["/S"] == "/GoTo")
                destination = action["/D"]
            _require(
                isinstance(destination, ArrayObject) and isinstance(destination[0], IndirectObject)
            )
            links.append((i, page_ids[destination[0].idnum]))
            if expected.presentation is not None:
                _require(len(destination) == 5 and destination[1] == "/XYZ")
                link_destinations.append(
                    (page_ids[destination[0].idnum], float(destination[2]), float(destination[3]))
                )
                rect = annotation["/Rect"]
                _require(len(rect) == 4)
                link_boxes.append((float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])))
        extracted = page.extract_text()
        if expected.presentation is None:
            _require(_layout(extracted) == _layout(expected.page_text[i]))
        else:
            _check_page_text(page, expected.text_runs[i])
        texts.append(extracted)
    _require(tuple(links) == expected.links)
    if expected.presentation is not None:
        _require(tuple(link_destinations) == expected.link_destinations)
        _require(tuple(link_boxes) == expected.link_boxes)
    outlines: list[tuple[str, int, int]] = []
    destinations: list[tuple[int, float, float]] = []

    def walk(items: list[Any], depth: int) -> None:
        if depth > limits.MAX_DEPTH:
            limits.fail("RESOURCE_LIMIT")
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
            else:
                page_number = reader.get_destination_page_number(item)
                _require(page_number is not None)
                assert page_number is not None
                outlines.append((item.title, int(page_number), depth))
                if expected.presentation is not None:
                    _require(item["/Type"] == "/XYZ")
                    destinations.append(
                        (int(page_number), float(item["/Left"]), float(item["/Top"]))
                    )

    walk(reader.outline, 0)
    _require(tuple(outlines) == expected.outlines)
    if expected.presentation is not None:
        _require(tuple(destinations) == expected.destinations)
    return PdfValidation(len(pages), len(seen), tuple(texts))


def validate_pdf_bytes(data: bytes, expected: PdfExpectation) -> PdfValidation:
    """No writer, repair, filesystem, subprocess or source-document reconstruction."""
    phase: limits.Phase | None = None
    if expected.presentation is not None:
        phase = (
            "VALIDATE_DOSSIER"
            if expected.presentation.kind == "dossier"
            else "VALIDATE_CONSOLIDATED"
        )
    with limits.phase_boundary(phase):
        return _validate_pdf_bytes(data, expected)


def _validate_pdf_bytes(data: bytes, expected: PdfExpectation) -> PdfValidation:
    if len(data) > limits.MAX_PDF_BYTES:
        limits.fail("RESOURCE_LIMIT")
    handler = _ParserWarnings()
    logger = logging.getLogger("pypdf")
    logger.addHandler(handler)
    try:
        with warnings.catch_warnings(record=True) as caught:
            result = _validate(data, expected)
        if handler.seen or caught:
            limits.fail("PDF_VALIDATION_FAILURE")
        return result
    except EvidenceError:
        raise
    except MemoryError:
        limits.fail("RESOURCE_LIMIT")
    except Exception:
        limits.fail("PDF_VALIDATION_FAILURE")
    finally:
        logger.removeHandler(handler)
