import json
from pathlib import Path

import pytest

from evidence_engine.ingest.google.html import table_document
from evidence_engine.ingest.google.parsers import PARSERS
from evidence_engine.ingest.parsing.framework import ParseError, ParserContext, resolve_locator

FIXTURES = Path(__file__).parent / "fixtures/synthetic/google"
NAMES = ["SubscriberInfo.html", "ChangeHistory.html"]


def fixture(index):
    return (FIXTURES / NAMES[index]).read_bytes()


def parse(index, data=None):
    return PARSERS[index].parse(ParserContext(NAMES[index]), table_document(data or fixture(index)))


@pytest.mark.parametrize("index", [0, 1])
def test_google_selection_requires_compatible_path_and_headers(index):
    document = table_document(fixture(index))
    for prefix in ["", "synthetic.", "Takeout/Google Account/synthetic."]:
        assert PARSERS[index].supports(ParserContext(prefix + NAMES[index]), document)
    for path in [
        "Other.html",
        "../" + NAMES[index],
        "/" + NAMES[index],
        "C:/" + NAMES[index],
        "synthetic//" + NAMES[index],
        "synthetic\\" + NAMES[index],
    ]:
        assert not PARSERS[index].supports(ParserContext(path), document)
    for data in [
        b"<p>unrelated HTML</p>",
        b"<table><tr><th>Timestamp</th></tr></table>",
        fixture(1 - index),
    ]:
        assert not PARSERS[index].supports(ParserContext(NAMES[index]), table_document(data))


def test_security_cells_are_raw_with_literal_annotations_and_entities():
    result = parse(0)
    assert len(result.records) == 4
    first, ipv6, invalid, empty = result.records
    assert first.source_locator == "$/tables/1/rows/0"
    assert first.timestamp_raw == "2024-01-02T03:04:05Z"
    assert first.payload == {
        "Timestamp": "2024-01-02T03:04:05Z",
        "IP Address": "203.0.113.10",
        "Activity Type": "Synthetic Login",
        "Interactive": "true",
        "Initiating Service": "Synthetic Service",
        "Geo": "Synthetic Region",
        "Raw User Agents": "SyntheticAgent iPhone99,9",
        "Challenges (timestamp, outcome, dusi)": "Synthetic & challenge 🧪\nação",
    }
    assert {a.get("version") for a in first.annotations if a["kind"] == "ip_syntax"} == {4}
    assert {a.get("version") for a in ipv6.annotations if a["kind"] == "ip_syntax"} == {6}
    assert {a["value"] for a in ipv6.annotations if a["kind"] == "model_code_from_user_agent"} == {
        "iPhone99,8",
        "iPhone99,9",
    }
    assert invalid.payload["IP Address"] == "synthetic-invalid-ip"
    assert invalid.timestamp_raw == "synthetic time without timezone"
    assert empty.timestamp_raw == "" and empty.payload["IP Address"] == ""
    assert [w.code for w in result.warnings] == ["INVALID_IP_SYNTAX"]
    assert "marketing" not in json.dumps(first.annotations)


def test_change_history_equal_times_are_separate_and_values_not_inferred():
    result = parse(1)
    assert len(result.records) == 4
    first, second, third, fourth = result.records
    assert first.timestamp_raw == second.timestamp_raw
    assert first.source_locator != second.source_locator
    assert first.payload["Old Value"] == "+55 00 00000-0000"
    assert second.payload["New Value"] == "synthetic-new@example.invalid"
    assert third.payload["Old Value"] == third.payload["New Value"] == ""
    assert fourth.payload["New Value"] == ""
    assert all(a["kind"] == "ip_syntax" for r in result.records for a in r.annotations)


@pytest.mark.parametrize("index", [0, 1])
def test_every_locator_resolves_from_original_html(index):
    document = table_document(fixture(index))
    for r in parse(index).records:
        assert resolve_locator(document, r.source_locator) == r.payload
        for a in r.annotations:
            value = resolve_locator(document, a["source_locator"])
            assert (
                a["value"] in value
                if a["kind"] == "model_code_from_user_agent"
                else value == r.payload["IP Address"]
            )


def test_headers_select_by_name_not_column_or_table_position():
    data = fixture(1).replace(
        b"<th>Old Value</th><th>New Value</th>", b"<th>New Value</th><th>Old Value</th>"
    )
    assert parse(1, data).records[0].payload["New Value"] == "+55 00 00000-0000"
    # Identical tables and rows are distinct occurrences, never deduplicated.
    result = parse(1, fixture(1) + fixture(1))
    assert len(result.records) == 8 and len({r.source_locator for r in result.records}) == 8


def test_optional_history_columns_absent_and_unknown_column_escaped():
    data = (
        b"<table><tr><th>Timestamp</th><th>IP Address</th><th>Change Type</th>"
        b"<th>Synthetic~/extra</th></tr><tr><td>raw</td><td></td>"
        b"<td>Synthetic</td><td>extra</td></tr></table>"
    )
    result = parse(1, data)
    assert "Old Value" not in result.records[0].payload
    assert "New Value" not in result.records[0].payload
    assert result.warnings[0].source_locator.endswith("Synthetic~0~1extra")
    assert resolve_locator(table_document(data), result.warnings[0].source_locator) == "extra"


@pytest.mark.parametrize(
    "data",
    [
        b"<table><tr><th>A</th></tr><tr><td>incomplete",
        b"<table><tr><th>A</th></tr><tr><td>a</td><td>b</td></tr></table>",
        b"<table><tr><th>A</th><th>A</th></tr></table>",
        b"<table><tr><th>A</th></tr><tr><td><b>x</td></tr></table>",
        b"<table><tr><th>A</th></tr><tr><td><script>unsafe</script></td></tr></table>",
        b'<table><tr><th>A</th></tr><tr><td colspan="2">x</td></tr></table>',
        b"<table><tr><th>A</th></tr><tr><td><table></table></td></tr></table>",
        b"<table><tr><th>A</th></tr><tr><td>a</th></tr></table>",
        b"<table><tr><th>A</th></tr><tr><td>a<tr></table>",
        b"<table>stray text</table>",
        b'<!DOCTYPE html SYSTEM "file:///synthetic-private">',
        b"\xff",
        b"\x00",
    ],
)
def test_malformed_or_ambiguous_html_is_not_recovered(data):
    with pytest.raises(ParseError):
        table_document(data)


def test_empty_matching_table_and_verbatim_whitespace():
    data = b"<table><tr><th>Timestamp</th><th>IP Address</th><th>Change Type</th></tr></table>"
    assert parse(1, data).records == []
    modified = fixture(1).replace(b"2024-01-02T03:04:05Z", b" 2024-01-02T03:04:05Z ")
    assert parse(1, modified).records[0].timestamp_raw == " 2024-01-02T03:04:05Z "


def test_resource_limits(monkeypatch):
    monkeypatch.setattr("evidence_engine.ingest.google.html.MAX_SOURCE_BYTES", 8)
    with pytest.raises(ParseError, match="SOURCE_SIZE_LIMIT"):
        table_document(fixture(0))
    monkeypatch.setattr("evidence_engine.ingest.google.html.MAX_SOURCE_BYTES", 32 * 1024 * 1024)
    monkeypatch.setattr("evidence_engine.ingest.google.parsers.MAX_RECORDS", 1)
    with pytest.raises(ParseError, match="RECORD_LIMIT"):
        parse(0)


def test_html_entities_do_not_create_markup_or_decode_twice():
    data = fixture(1).replace(
        b"synthetic-new@example.invalid", b"&lt;b&gt;&amp;lt;synthetic&#x1F9EA;"
    )
    assert parse(1, data).records[1].payload["New Value"] == "<b>&lt;synthetic🧪"


@pytest.mark.parametrize("suffix", [b"<table", b"<!-- unfinished", b"<script>unfinished"])
def test_truncated_markup_after_valid_table_rejects_entire_document(suffix):
    with pytest.raises(ParseError, match="TRUNCATED_HTML"):
        table_document(fixture(1) + suffix)


@pytest.mark.parametrize("limit", ["MAX_TABLES", "MAX_ROWS", "MAX_COLUMNS"])
def test_structural_limits_are_enforced(limit, monkeypatch):
    monkeypatch.setattr("evidence_engine.ingest.google.html." + limit, 1)
    with pytest.raises(ParseError, match="LIMIT"):
        table_document(fixture(0))
