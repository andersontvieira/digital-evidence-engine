from pathlib import Path

import pytest

from evidence_engine.ingest.apple.parsers import PARSERS
from evidence_engine.ingest.parsing.csv import csv_document
from evidence_engine.ingest.parsing.framework import (
    ParseError,
    ParserContext,
    child_locator,
    resolve_locator,
)

FIXTURES = Path(__file__).parent / "fixtures/synthetic/apple"
PATHS = [
    "Informações da Conta Apple e do dispositivo/Apple ID Device Information.csv",
    "Informações da Conta Apple e do dispositivo/Apple ID SignOn Information.csv",
    "Apple_Media_Services/Stores Activity/Other Activity/Purchase Server Events.csv",
]


def fixture(index):
    return (FIXTURES / PATHS[index].split("/")[-1]).read_bytes()


def parse(index, data=None):
    return PARSERS[index].parse(
        ParserContext(PATHS[index]), csv_document(fixture(index) if data is None else data)
    )


@pytest.mark.parametrize("index", range(3))
def test_selection_requires_exact_path_and_required_headers(index):
    document = csv_document(fixture(index))
    parser = PARSERS[index]
    assert parser.supports(ParserContext(PATHS[index]), document)
    for path in [
        PATHS[index].split("/")[-1],
        "other/" + PATHS[index],
        "../" + PATHS[index],
        "/" + PATHS[index],
        PATHS[index].replace("/", "\\"),
    ]:
        assert not parser.matches_path(ParserContext(path))
        assert not parser.supports(ParserContext(path), document)
    assert not parser.supports(ParserContext(PATHS[index]), csv_document(b"Unrelated\nsynthetic\n"))
    assert not parser.supports(ParserContext(PATHS[index]), csv_document(fixture((index + 1) % 3)))


@pytest.mark.parametrize("index", range(3))
def test_bom_logical_locators_and_annotations_resolve(index):
    document = csv_document(b"\xef\xbb\xbf" + fixture(index))
    result = parse(index, b"\xef\xbb\xbf" + fixture(index))
    for n, record in enumerate(result.records):
        assert record.source_locator == f"$/rows/{n}"
        assert record.record_index == n
        raw = resolve_locator(document, record.source_locator)
        assert all(raw[key] == value for key, value in record.payload.items())
        for annotation in record.annotations:
            assert isinstance(resolve_locator(document, annotation["source_locator"]), str)


def test_device_identifiers_and_times_are_verbatim():
    record = parse(0).records[0]
    assert record.payload["Device IMEI"] == "000000000000000"
    assert record.payload["Device ICCID"] == "00000000000000000001"
    assert record.payload["Device Model Name"] == "Not Available"
    assert record.payload["Device Phone Number"] == ""
    assert record.timestamp_raw == "2024-01-02T03:04:05"
    assert record.payload["Device Added Date"] == "2024-01-01T01:02:03"
    assert record.annotations[0]["field"] == "Device Last Heartbeat Timestamp"


def test_sign_on_newline_status_ip_syntax_and_duplicate_occurrences():
    result = parse(1)
    first, ipv6, invalid, empty, duplicate = result.records
    assert first.payload["Application"] == "Synthetic Application\nwith newline"
    assert first.payload["Apple ID Number"] == "000001"
    assert first.payload["Signon Status"] == "000"
    assert first.annotations[1]["version"] == 4
    assert ipv6.annotations[1]["version"] == 6
    assert ipv6.timestamp_raw == "2024-01-02T03:04:05+02:00"
    assert invalid.payload["IP Address"] == "synthetic-invalid-ip"
    assert [(w.code, w.source_locator) for w in result.warnings] == [
        ("INVALID_IP_SYNTAX", "$/rows/2/IP Address")
    ]
    assert empty.payload == duplicate.payload
    assert empty.source_locator != duplicate.source_locator
    assert empty.timestamp_raw == ""
    assert empty.payload["Device Identifier"] == ""


def test_media_projection_excludes_commercial_fields_and_preserves_literal_model():
    first, second = parse(2).records
    assert first.payload["Device Hardware Model"] == "iPhone99,9"
    assert first.payload["User Agent"] == 'SyntheticAgent, "quoted"'
    assert first.payload["IP"] == ""
    assert second.payload["Device Hardware Model"] == ""
    assert len(first.payload) == 12
    assert "SYNTHETIC-EXCLUDED" not in str(first.payload)
    assert not any("UDID" in key for key in first.payload)
    assert PARSERS[2].supports(
        ParserContext(
            PATHS[2].replace("Apple_Media_Services/", "Apple_Media_Services/Apple Media Services/")
        ),
        csv_document(fixture(2)),
    )


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"A,A\nx,y\n",
        b"A,B\nx\n",
        b"A\nx,y\n",
        b'A\n"unterminated',
        b'A\n"closed"junk\n',
        b"A\n\xff",
        b"A\n\x00",
        b",B\nx,y\n",
        b"A,B\n\n",
    ],
)
def test_invalid_csv_rejected_without_recovery(data):
    with pytest.raises(ParseError):
        csv_document(data)


def test_empty_source_optional_columns_and_pointer_escaping():
    assert parse(1, fixture(1).split(b"\n")[0] + b"\n").records == []
    doc = csv_document(b"Synthetic~/header\n  raw text  \n")
    assert resolve_locator(doc, child_locator("$/rows/0", "Synthetic~/header")) == "  raw text  "
    data = (
        b"Device Identifier,Device Hardware Model,Device Hardware Family,Event Time,"
        b"Event Type,Application Name,IP\nx,,family,raw,event,app,\n"
    )
    record = parse(2, data).records[0]
    assert "Metrics Event Time" not in record.payload


@pytest.mark.parametrize("limit", ["MAX_SOURCE_BYTES", "MAX_RECORDS", "MAX_COLUMNS"])
def test_csv_limits(limit, monkeypatch):
    monkeypatch.setattr("evidence_engine.ingest.parsing.csv." + limit, 1)
    with pytest.raises(ParseError, match="LIMIT"):
        csv_document(fixture(1))


def test_parser_record_limit(monkeypatch):
    monkeypatch.setattr("evidence_engine.ingest.apple.parsers.MAX_RECORDS", 1)
    with pytest.raises(ParseError, match="RECORD_LIMIT"):
        parse(1)
