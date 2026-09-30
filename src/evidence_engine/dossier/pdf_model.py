"""Closed, bounded presentation grammar. No rendering or source-package access."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from evidence_engine.dossier import pdf_limits as limits

type DocumentKind = Literal["dossier", "consolidated-report"]
type SpanKind = Literal["text", "literal", "bold", "index"]

# Presentation constants only. Tests compare these to the two approved renderers.
DOSSIER_TITLE = "Dossiê Técnico de Organização de Evidências Digitais"
REPORT_TITLE = "Relatório Técnico Consolidado de Análise e Organização de Evidências Digitais"
DOSSIER_SECTIONS = (
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
REPORT_SECTIONS = (
    "Identificação do documento",
    "Objetivo e escopo",
    "Natureza e limitações do trabalho",
    "Materiais/evidências analisados",
    "Metodologia técnica",
    "Preservação, integridade e provenance",
    "Fontes e cobertura de parsing",
    "Normalização temporal",
    "Observações técnicas de dispositivo",
    "Observações técnicas de rede",
    "Candidates por igualdade exata",
    "Timeline e janelas relevantes",
    "Temporal Proximity Candidates",
    "Temporal + Exact Signal Overlap",
    "Análise técnica de mídia",
    "Achados técnicos consolidados",
    "Limitações e afirmações não estabelecidas",
    "Lacunas de evidência",
    "Próximas análises/aquisições recomendadas",
    "Apêndice técnico / mapa de provenance",
)
_ESCAPES = frozenset("\\`*_{}[]()#|!")
_ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">"}
_INDEX = "[Índice de anexos](annex-index.md)"
_BIDI = frozenset(
    chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A), 0x061C, 0x200E, 0x200F)
)


@dataclass(frozen=True)
class Span:
    kind: SpanKind
    text: str
    line: int
    column: int


@dataclass(frozen=True)
class Heading:
    level: int
    spans: tuple[Span, ...]
    line: int


@dataclass(frozen=True)
class Paragraph:
    spans: tuple[Span, ...]
    line: int


@dataclass(frozen=True)
class ListItem:
    spans: tuple[Span, ...]
    line: int


@dataclass(frozen=True)
class BulletList:
    items: tuple[ListItem, ...]
    line: int


@dataclass(frozen=True)
class TableCell:
    spans: tuple[Span, ...]
    line: int
    column: int


@dataclass(frozen=True)
class TableRow:
    cells: tuple[TableCell, ...]
    line: int


@dataclass(frozen=True)
class Table:
    header: TableRow
    rows: tuple[TableRow, ...]
    line: int


type Block = Heading | Paragraph | BulletList | Table


@dataclass(frozen=True)
class PresentationDocument:
    kind: DocumentKind
    title: str
    blocks: tuple[Block, ...]


def _reject() -> None:
    limits.fail("UNSUPPORTED_MARKDOWN")


def _spans(text: str, line: int, column: int, kind: DocumentKind) -> tuple[Span, ...]:
    result: list[Span] = []
    plain: list[str] = []
    start = 0

    def flush() -> None:
        if plain:
            result.append(Span("text", "".join(plain), line, column + start))
            plain.clear()

    i = 0
    while i < len(text):
        if not plain:
            start = i
        ch = text[i]
        if ch == "\\":
            if i + 1 >= len(text) or text[i + 1] not in _ESCAPES:
                _reject()
            plain.append(text[i + 1])
            i += 2
            continue
        entity = next((e for e in _ENTITIES if text.startswith(e, i)), None)
        if entity:
            plain.append(_ENTITIES[entity])
            i += len(entity)
            continue
        if ch == "&" and re.match(r"&(?:#[xX]?[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);", text[i:]):
            _reject()
        if text.startswith(_INDEX, i) and kind == "dossier":
            flush()
            result.append(Span("index", "Índice de anexos (annex-index.md)", line, column + i))
            i += len(_INDEX)
            continue
        marker = "`" if ch == "`" else "**" if text.startswith("**", i) else None
        if marker:
            end = text.find(marker, i + len(marker))
            if end < 0 or end == i + len(marker):
                _reject()
            inner = text[i + len(marker) : end]
            if marker == "**":
                decoded = _spans(inner, line, column + i + 2, kind)
                if any(s.kind != "text" for s in decoded):
                    _reject()
                inner = "".join(s.text for s in decoded)
            flush()
            result.append(Span("literal" if marker == "`" else "bold", inner, line, column + i))
            i = end + len(marker)
            continue
        if (
            ch == "*"
            or text.startswith("![", i)
            or (ch == "<" and re.match(r"</?[A-Za-z!]|<[^ >]+:[^ >]+>", text[i:]))
        ):
            _reject()
        if ch == "[" and re.match(r"\[[^\]]*\](?:\(|\[)", text[i:]):
            _reject()
        plain.append(ch)
        i += 1
    flush()
    return tuple(result)


def _cells(text: str, line: int, kind: DocumentKind) -> tuple[TableCell, ...]:
    if not text.startswith("| ") or not text.endswith(" |"):
        _reject()
    boundaries = [0]
    slashes = 0
    for i, ch in enumerate(text[1:], 1):
        if ch == "|" and slashes % 2 == 0:
            boundaries.append(i)
        slashes = slashes + 1 if ch == "\\" else 0
    if boundaries[-1] != len(text) - 1:
        _reject()
    if len(boundaries) - 1 > limits.MAX_COLUMNS:
        limits.fail("RESOURCE_LIMIT")
    result = []
    for a, b in zip(boundaries[:-1], boundaries[1:], strict=True):
        # Only the renderer's single delimiter space is syntax. Extra spaces are data.
        if text[a + 1 : a + 2] != " " or text[b - 1 : b] != " ":
            _reject()
        result.append(TableCell(_spans(text[a + 2 : b - 1], line, a + 3, kind), line, a + 3))
    return tuple(result)


def parse_presentation_bytes(data: bytes, kind: DocumentKind) -> PresentationDocument:
    if len(data) > limits.MAX_MARKDOWN_BYTES:
        limits.fail("RESOURCE_LIMIT")
    if kind not in ("dossier", "consolidated-report"):
        _reject()
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeError:
        limits.fail("UNSUPPORTED_MARKDOWN")
    if text.startswith("\ufeff") or any(
        c in _BIDI or (unicodedata.category(c) in ("Cc", "Cs") and c != "\n") for c in text
    ):
        _reject()
    title, sections = (
        (DOSSIER_TITLE, DOSSIER_SECTIONS) if kind == "dossier" else (REPORT_TITLE, REPORT_SECTIONS)
    )
    lines = text.split("\n")
    if lines[0] != "# " + title:
        _reject()
    blocks: list[Block] = [Heading(1, (Span("text", title, 1, 3),), 1)]
    i, section, count, cells, rows_count = 1, 0, 1, 0, 0

    def charge(n: int = 1) -> None:
        nonlocal count
        count += n
        if count > limits.MAX_BLOCKS:
            limits.fail("RESOURCE_LIMIT")

    while i < len(lines):
        raw = lines[i]
        line = i + 1
        if raw == "":
            i += 1
            continue
        charge()
        if raw.startswith("## "):
            if section >= len(sections) or raw != f"## {section + 1}. {sections[section]}":
                _reject()
            section += 1
            blocks.append(Heading(2, _spans(raw[3:], line, 4, kind), line))
            i += 1
        elif raw.startswith("### ") and section:
            blocks.append(Heading(3, _spans(raw[4:], line, 5, kind), line))
            i += 1
        elif raw.startswith("|") and section:
            header = TableRow(_cells(raw, line, kind), line)
            if i + 1 >= len(lines):
                _reject()
            separator = _cells(lines[i + 1], line + 1, kind)
            if len(separator) != len(header.cells) or any(
                "".join(s.text for s in c.spans) != "---" for c in separator
            ):
                _reject()
            cells += len(header.cells)
            if cells > limits.MAX_CELLS:
                limits.fail("RESOURCE_LIMIT")
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                row = TableRow(_cells(lines[i], i + 1, kind), i + 1)
                if len(row.cells) != len(header.cells):
                    _reject()
                rows_count += 1
                cells += len(row.cells)
                if rows_count > limits.MAX_ROWS or cells > limits.MAX_CELLS:
                    limits.fail("RESOURCE_LIMIT")
                rows.append(row)
                i += 1
            blocks.append(Table(header, tuple(rows), line))
        elif raw.startswith("- ") and section:
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                charge()
                items.append(ListItem(_spans(lines[i][2:], i + 1, 3, kind), i + 1))
                i += 1
            blocks.append(BulletList(tuple(items), line))
        else:
            if not section:
                _reject()
            spans: list[Span] = []
            while (
                i < len(lines) and lines[i] and not lines[i].startswith(("## ", "### ", "|", "- "))
            ):
                raw = lines[i]
                if re.match(r"(?:\s|#|>|```|~~~|\d+[.)] |\+ |---+$|\[.*\]:)", raw):
                    _reject()
                if spans:
                    spans.append(Span("text", "\n", i + 1, 1))
                spans.extend(_spans(raw, i + 1, 1, kind))
                i += 1
            blocks.append(Paragraph(tuple(spans), line))
    if section != len(sections):
        _reject()
    return PresentationDocument(kind, title, tuple(blocks))
