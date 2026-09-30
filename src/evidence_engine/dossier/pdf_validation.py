"""Independent read-only validator for the foundation's closed synthetic PDF profile."""

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
class PdfExpectation:
    title: str
    page_text: tuple[str, ...]
    # Fixed ordinal destinations: (title, page index, parent depth).
    outlines: tuple[tuple[str, int, int], ...]
    links: tuple[tuple[int, int], ...]


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
    texts = []
    for i, page in enumerate(pages):
        content = ContentStream(page.get_contents(), reader)
        _require(
            all(
                op in (b"cm", b"BT", b"ET", b"Tf", b"TL", b"Tm", b"Tj", b"T*", b"q", b"Q")
                for _, op in content.operations
            )
        )
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
        extracted = page.extract_text()
        _require(_layout(extracted) == _layout(expected.page_text[i]))
        texts.append(extracted)
    _require(tuple(links) == expected.links)
    outlines: list[tuple[str, int, int]] = []

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

    walk(reader.outline, 0)
    _require(tuple(outlines) == expected.outlines)
    return PdfValidation(len(pages), len(seen), tuple(texts))


def validate_pdf_bytes(data: bytes, expected: PdfExpectation) -> PdfValidation:
    """No writer, repair, filesystem, subprocess or source-document reconstruction."""
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
