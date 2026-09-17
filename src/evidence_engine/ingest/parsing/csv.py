"""Bounded UTF-8 comma CSV projection with logical, zero-based row locators."""

import csv
import io

from evidence_engine.ingest.parsing.framework import (
    MAX_RECORDS,
    MAX_SOURCE_BYTES,
    JSONValue,
    ParseError,
)

MAX_COLUMNS = 256


def csv_document(data: bytes) -> JSONValue:
    if len(data) > MAX_SOURCE_BYTES:
        raise ParseError("SOURCE_SIZE_LIMIT")
    try:
        text = data.decode("utf-8-sig")
        if "\x00" in text:
            raise ParseError("INVALID_CSV")
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=",", strict=True)
        headers = next(reader, None)
        if not headers or any(not header for header in headers):
            raise ParseError("CSV_MISSING_HEADER")
        if len(headers) > MAX_COLUMNS:
            raise ParseError("CSV_COLUMN_LIMIT")
        if len(set(headers)) != len(headers):
            raise ParseError("CSV_DUPLICATE_HEADER")
        rows: list[JSONValue] = []
        for cells in reader:
            if len(rows) >= MAX_RECORDS:
                raise ParseError("RECORD_LIMIT")
            if len(cells) != len(headers):
                raise ParseError("CSV_ROW_WIDTH")
            rows.append(dict(zip(headers, cells, strict=True)))
        return {"headers": list(headers), "rows": rows}
    except (UnicodeError, csv.Error) as error:
        raise ParseError("INVALID_CSV") from error
