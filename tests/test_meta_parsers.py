import json
from pathlib import Path

import pytest

from evidence_engine.ingest.instagram.parsers import PARSERS
from evidence_engine.ingest.parsing.framework import (
    ParseError,
    ParserContext,
    child_locator,
    resolve_locator,
    strict_json,
)

FIXTURES = Path(__file__).parent / "fixtures/synthetic/meta"
MESSAGE_PATH = "messages/inbox/synthetic_thread/message_1.json"


def fixture(name: str):
    return strict_json((FIXTURES / name).read_bytes())


@pytest.mark.parametrize(
    "index,path",
    [(0, "profile_activity.json"), (1, "recently_deleted_content.json"), (2, MESSAGE_PATH)],
)
def test_parser_selection_requires_path_and_schema(index: int, path: str) -> None:
    document = fixture(path)
    context = ParserContext("synthetic-export/" + path)
    assert [p.parser_id for p in PARSERS if p.supports(context, document)] == [
        PARSERS[index].parser_id
    ]
    assert not PARSERS[index].supports(context, {"unrelated": [{"timestamp": 1700000000}]})
    assert not PARSERS[index].supports(ParserContext("synthetic-unrelated.json"), document)


def test_profile_values_and_annotations_are_not_interpretations() -> None:
    document = fixture("profile_activity.json")
    result = PARSERS[0].parse(ParserContext("profile_activity.json"), document)
    first, mapped, absent = result.records
    assert first.timestamp_raw == 1700000000
    assert first.payload == document["profile_account_insights"][0]
    assert first.payload["port"] == 443
    assert first.payload["previous_value"] == "synthetic previous"
    assert first.payload["new_value"] == "synthetic new"
    assert first.payload["device_id"] == "SYNTHETIC-DEVICE-001"
    assert {a["kind"] for a in first.annotations} == {"ip_syntax", "model_code_from_user_agent"}
    model = next(a for a in first.annotations if a["kind"] == "model_code_from_user_agent")
    assert model["value"] == "iPhone15,2"
    assert model["source_locator"].endswith("/user_agent")
    assert "iPhone 14" not in json.dumps(first.payload)
    assert mapped.timestamp_raw == "synthetic time without timezone"
    assert absent.timestamp_raw is None and set(absent.payload) == {"device_id"}
    assert "INVALID_IP_SYNTAX" in {w.code for w in result.warnings}


def test_recently_deleted_preserves_false_missing_and_no_cross_source_data() -> None:
    result = PARSERS[1].parse(
        ParserContext("recently_deleted_content.json"), fixture("recently_deleted_content.json")
    )
    first, second = [r.payload for r in result.records]
    assert first["published"] is True and second["published"] is False
    assert first["caption"] == "Legenda sintética — ação 🧪"
    assert "caption" not in second
    for item in (first, second):
        assert "ip" not in item and "model" not in item and "user_agent" not in item


def test_messages_preserve_conversation_encoding_and_literal_attachment_text() -> None:
    document = fixture(MESSAGE_PATH)
    result = PARSERS[2].parse(ParserContext(MESSAGE_PATH), document)
    conversation, first, second, third = result.records
    assert conversation.payload["title"] == document["title"]
    assert conversation.payload["participants"] == document["participants"]
    assert "messages" not in conversation.payload
    assert first.payload["content"] == "Você enviou um anexo."
    assert "photos" not in first.payload and "recipient" not in first.payload
    assert first.timestamp_raw == 1700000000123
    assert second.payload == document["messages"][1]
    assert third.payload["content"] == "synthetic mojibake: OlÃ¡"
    for record in result.records[1:]:
        assert resolve_locator(document, record.source_locator) == record.payload


def test_locator_escaping_and_noncanonical_rejection() -> None:
    document = {"synthetic~/key": [{"timestamp": 1}]}
    locator = child_locator(child_locator("$", "synthetic~/key"), 0)
    assert locator == "$/synthetic~0~1key/0"
    assert resolve_locator(document, locator) == {"timestamp": 1}
    for bad in ("filename.json", "$/synthetic~0~1key/00", "$/synthetic~2key", "$/absent"):
        with pytest.raises(ParseError, match="LOCATOR"):
            resolve_locator(document, bad)


@pytest.mark.parametrize("data", [b"{", b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'"\xff"'])
def test_strict_json_rejects_ambiguous_or_invalid_input(data: bytes) -> None:
    with pytest.raises(ParseError):
        strict_json(data)


def test_bom_is_decoding_only_and_unicode_values_are_preserved() -> None:
    data = '\ufeff{"synthetic":"Olá 🧪 OlÃ¡"}'.encode()
    assert strict_json(data) == {"synthetic": "Olá 🧪 OlÃ¡"}


def test_warning_locators_unknown_fields_and_ambiguous_timestamp() -> None:
    document = {
        "profile_account_insights": [{"timestamp": 1, "timestamp_ms": 2, "synthetic~/field": False}]
    }
    result = PARSERS[0].parse(ParserContext("profile_activity.json"), document)
    assert result.records[0].timestamp_raw is None
    assert {w.code for w in result.warnings} == {"UNEXPECTED_FIELD", "MULTIPLE_TIMESTAMPS_RAW_ONLY"}
    warning = next(w for w in result.warnings if w.code == "UNEXPECTED_FIELD")
    assert resolve_locator(document, warning.source_locator) is False


def test_thread_metadata_disagreement_is_warning_not_inferred_recipient() -> None:
    document = fixture(MESSAGE_PATH)
    document["thread_path"] = "messages/inbox/synthetic_other"
    result = PARSERS[2].parse(ParserContext(MESSAGE_PATH), document)
    assert "THREAD_PATH_MISMATCH" in {w.code for w in result.warnings}
    assert result.records[0].payload["thread_path"] == document["thread_path"]
    assert all("recipient" not in record.payload for record in result.records)


def test_noncanonical_paths_never_select_meta() -> None:
    document = fixture("profile_activity.json")
    for path in (
        "../profile_activity.json",
        "/profile_activity.json",
        "C:/profile_activity.json",
        "synthetic//profile_activity.json",
        "synthetic/./profile_activity.json",
        "synthetic\\profile_activity.json",
    ):
        assert not PARSERS[0].supports(ParserContext(path), document)


def test_nested_array_locator_with_escaped_keys_and_unicode() -> None:
    document = {"synthetic~/ação": [[{"~/🧪": "synthetic value"}]]}
    locator = child_locator(child_locator(child_locator("$", "synthetic~/ação"), 0), 0)
    assert resolve_locator(document, locator) == {"~/🧪": "synthetic value"}
    assert resolve_locator(document, child_locator(locator, "~/🧪")) == "synthetic value"


def test_json_depth_boundary_without_large_fixture() -> None:
    assert strict_json(b"[" * 64 + b"0" + b"]" * 64) is not None
    with pytest.raises(ParseError, match="DEPTH_LIMIT"):
        strict_json(b"[" * 65 + b"0" + b"]" * 65)


@pytest.mark.parametrize(
    "index,path",
    [(0, "profile_activity.json"), (1, "recently_deleted_content.json"), (2, MESSAGE_PATH)],
)
def test_parser_record_limits_include_conversation(index: int, path: str, monkeypatch) -> None:
    monkeypatch.setattr("evidence_engine.ingest.instagram.parsers.MAX_RECORDS", 1)
    with pytest.raises(ParseError, match="RECORD_LIMIT"):
        PARSERS[index].parse(ParserContext(path), fixture(path))
