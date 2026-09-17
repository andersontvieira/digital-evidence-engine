"""Deterministic table projection for the two supported Takeout HTML artifacts.

No browser, network, external entities, scripts, or recovery of broken table markup.
"""

from html.parser import HTMLParser

from evidence_engine.ingest.parsing.framework import MAX_SOURCE_BYTES, JSONValue, ParseError

MAX_TABLES = 1000
MAX_ROWS = 101_000
MAX_COLUMNS = 256
INLINE_TAGS = {
    "span",
    "b",
    "strong",
    "i",
    "em",
    "a",
    "div",
    "p",
    "ul",
    "li",
    "code",
    "pre",
    "small",
    "sup",
    "sub",
    "s",
    "u",
}


class TableReader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[JSONValue] = []
        self.table: list[list[tuple[str, str]]] | None = None
        self.row: list[tuple[str, str]] | None = None
        self.cell_tag: str | None = None
        self.parts: list[str] = []
        self.inline: list[str] = []
        self.groups: list[str] = []
        self.row_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            if self.table is not None:
                raise ParseError("NESTED_HTML_TABLE")
            if len(self.tables) >= MAX_TABLES:
                raise ParseError("HTML_TABLE_LIMIT")
            self.table = []
            return
        if self.table is None:
            return
        if tag in {"thead", "tbody", "tfoot"}:
            if self.row is not None or self.groups:
                raise ParseError("INVALID_HTML_TABLE")
            self.groups.append(tag)
        elif tag == "tr":
            if self.row is not None:
                raise ParseError("INVALID_HTML_ROW")
            self.row_count += 1
            if self.row_count > MAX_ROWS:
                raise ParseError("HTML_ROW_LIMIT")
            self.row = []
        elif tag in {"th", "td"}:
            if self.row is None or self.cell_tag is not None:
                raise ParseError("INVALID_HTML_CELL")
            if len(self.row) >= MAX_COLUMNS:
                raise ParseError("HTML_COLUMN_LIMIT")
            if any(name in {"rowspan", "colspan"} and value != "1" for name, value in attrs):
                raise ParseError("UNSUPPORTED_HTML_SPAN")
            self.cell_tag = tag
            self.parts = []
        elif tag == "br" and self.cell_tag is not None:
            self.parts.append("\n")
        elif tag in INLINE_TAGS and self.cell_tag is not None:
            self.inline.append(tag)
            if len(self.inline) > 64:
                raise ParseError("HTML_DEPTH_LIMIT")
        else:
            raise ParseError("UNSUPPORTED_HTML_TABLE_MARKUP")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag != "br":
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.table is None:
            if tag in {"table", "tr", "td", "th", "thead", "tbody", "tfoot"}:
                raise ParseError("INVALID_HTML_TABLE")
            return
        if tag in {"td", "th"}:
            if self.row is None or self.cell_tag != tag or self.inline:
                raise ParseError("INVALID_HTML_CELL")
            self.row.append((tag, "".join(self.parts)))
            self.cell_tag = None
            self.parts = []
        elif tag == "tr":
            if self.row is None or self.cell_tag is not None:
                raise ParseError("INVALID_HTML_ROW")
            self.table.append(self.row)
            self.row = None
        elif tag in {"thead", "tbody", "tfoot"}:
            if self.row is not None or self.groups != [tag]:
                raise ParseError("INVALID_HTML_TABLE")
            self.groups.clear()
        elif tag == "table":
            if self.row is not None or self.groups:
                raise ParseError("INVALID_HTML_TABLE")
            self.tables.append(project_table(self.table))
            self.table = None
        elif tag in INLINE_TAGS and self.inline and self.inline[-1] == tag:
            self.inline.pop()
        else:
            raise ParseError("INVALID_HTML_TABLE_MARKUP")

    def handle_data(self, data: str) -> None:
        if self.cell_tag is not None:
            self.parts.append(data)
        elif self.table is not None and data.strip():
            raise ParseError("TEXT_OUTSIDE_HTML_CELL")

    def handle_decl(self, decl: str) -> None:
        if decl.lower() != "doctype html":
            raise ParseError("UNSUPPORTED_HTML_DECLARATION")

    def unknown_decl(self, data: str) -> None:
        raise ParseError("UNSUPPORTED_HTML_DECLARATION")


def project_table(rows: list[list[tuple[str, str]]]) -> dict[str, JSONValue]:
    if not rows or not rows[0] or any(tag != "th" for tag, _ in rows[0]):
        # A headerless table cannot select either parser. Keep its table index.
        return {"headers": [], "rows": []}
    headers = [text for _, text in rows[0]]
    if len(set(headers)) != len(headers) or any(not h.strip() for h in headers):
        raise ParseError("AMBIGUOUS_HTML_HEADERS")
    records: list[JSONValue] = []
    for row in rows[1:]:
        if len(row) != len(headers) or any(tag != "td" for tag, _ in row):
            raise ParseError("INVALID_HTML_ROW_WIDTH_OR_KIND")
        records.append({key: cell[1] for key, cell in zip(headers, row, strict=True)})
    return {"headers": list(headers), "rows": records}


def table_document(data: bytes) -> JSONValue:
    """Decode UTF-8, HTML character references and explicit br breaks only.

    Locators address this projection: $/tables/<document index>/rows/<data row>.
    Original bytes, markup, attributes and whitespace remain in the source file.
    """
    if len(data) > MAX_SOURCE_BYTES:
        raise ParseError("SOURCE_SIZE_LIMIT")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError as error:
        raise ParseError("INVALID_HTML_ENCODING") from error
    if "\x00" in text:
        raise ParseError("INVALID_HTML_ENCODING")
    reader = TableReader()
    reader.feed(text)
    if reader.rawdata:
        raise ParseError("TRUNCATED_HTML")
    reader.close()
    if reader.table is not None:
        raise ParseError("UNCLOSED_HTML_TABLE")
    return {"tables": reader.tables}
