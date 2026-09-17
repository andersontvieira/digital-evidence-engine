import copy
import hashlib
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from evidence_engine.ingest.generic.service import ingest
from evidence_engine.ingest.instagram.parsers import PARSERS
from evidence_engine.ingest.parsing.framework import ParseError, ParserContext, resolve_locator
from evidence_engine.ingest.parsing.service import parse_instagram
from evidence_engine.models.entities import ArchiveMember, EvidenceFile, ParsedRecord, SourceRecord
from evidence_engine.storage.database import open_database

FIXTURES = Path(__file__).parent / "fixtures/synthetic/meta_arrays"
NAMES = ["profile_activity", "recently_deleted_content"]


def fixture(index):
    return json.loads((FIXTURES / (NAMES[index] + "_array_label_values.json")).read_bytes())


def parse(index, document):
    return PARSERS[index].parse(ParserContext(NAMES[index] + ".json"), document)


def fields(record):
    return {a["field"]: a["value"] for a in record.annotations if a["kind"] == "observed_field"}


@pytest.mark.parametrize("index", [0, 1])
def test_arrays_preserve_items_and_every_annotation_locator(index):
    document = fixture(index)
    before = copy.deepcopy(document)
    assert PARSERS[index].supports(ParserContext(NAMES[index] + ".json"), document)
    result = parse(index, document)
    assert len(result.records) == len(document)
    for i, record in enumerate(result.records):
        assert record.source_locator == f"$/{i}"
        assert resolve_locator(document, record.source_locator) == record.payload == document[i]
        for annotation in record.annotations:
            raw = resolve_locator(document, annotation["source_locator"])
            if annotation["kind"] == "observed_field":
                assert type(raw) is type(annotation["value"])
                assert raw == annotation["value"]
            elif annotation["kind"] == "model_code_from_user_agent":
                assert annotation["value"] in raw
    assert document == before


def test_profile_fields_timestamp_roles_and_no_positional_semantics():
    document = fixture(0)
    result = parse(0, document)
    first, absent = result.records
    assert first.timestamp_raw == 1700000000
    assert fields(first) == {
        "last_login": 1699999000,
        "event_type": "synthetic_profile_change",
        "ip_address": "203.0.113.10",
        "port": "443",
        "application": "Synthetic App",
        "application_version": "synthetic-1",
        "user_agent": "SyntheticAgent iPhone99,9",
        "language": "synthetic-language",
        "cookie": "synthetic-cookie",
        "device_id": "SYNTHETIC-DEVICE-001",
        "profile_field": "synthetic_profile_field",
        "new_value": "synthetic_user 🧪",
        "previous_value": "synthetic_previous",
    }
    assert absent.timestamp_raw is None
    assert fields(absent) == {"location": "Synthetic Location"}
    assert "UNKNOWN_LABEL" in {w.code for w in result.warnings}
    assert any(a["kind"] == "ip_syntax" and a["version"] == 4 for a in first.annotations)
    assert any(a.get("value") == "iPhone99,9" for a in first.annotations)
    document[0]["label_values"].reverse()
    assert fields(parse(0, document).records[0]) == fields(first)


def test_deleted_raw_flags_caption_and_media_without_cross_source_annotations():
    first, second = parse(1, fixture(1)).records
    assert fields(first)["published"] == "true"
    assert fields(second)["published"] == "false"
    assert fields(first)["caption"] == "Synthetic Caption — ação 🧪"
    assert "caption" not in fields(second)
    assert fields(first)["uri"] == "https://example.invalid/media/1"
    assert fields(second)["device_id"] == "SYNTHETIC-DEVICE-002"
    assert fields(first)["duration"] == "5"
    for record in (first, second):
        assert not ({"ip", "ip_address", "model", "user_agent"} & fields(record).keys())
        assert all(a["kind"] == "observed_field" for a in record.annotations)


@pytest.mark.parametrize("raw", [True, False, "true", "false", None, "synthetic-unknown"])
def test_published_scalar_is_never_coerced(raw):
    result = parse(1, [{"label_values": [{"label": "Publicado", "value": raw}]}])
    actual = fields(result.records[0])["published"]
    assert actual == raw and type(actual) is type(raw)


@pytest.mark.parametrize("index", [0, 1])
def test_absent_label_values_is_not_unrelated_array_support(index):
    assert not PARSERS[index].supports(ParserContext(NAMES[index] + ".json"), [{"timestamp": 1}])
    with pytest.raises(ParseError, match="INVALID_LABEL_VALUES"):
        parse(index, [{"label_values": []}, {"timestamp": 1}])
    empty = parse(index, [{"label_values": []}]).records[0]
    assert empty.timestamp_raw is None and empty.annotations == []


@pytest.mark.parametrize("value", [None, {}, "synthetic", 7, True])
def test_non_array_label_values_rejected(value):
    with pytest.raises(ParseError, match="INVALID_LABEL_VALUES"):
        parse(0, [{"label_values": value}])


@pytest.mark.parametrize(
    "entry",
    [
        None,
        [],
        {"label": []},
        {"label": "App", "value": {}},
        {"label": "Detalhes", "dict": {}},
        {"label": "App", "string_map_data": {"value": "synthetic"}},
    ],
)
def test_unknown_shapes_warn_without_guessing(entry):
    result = parse(0, [{"label_values": [entry]}])
    assert result.warnings and result.records[0].payload["label_values"] == [entry]
    assert result.records[0].annotations == []


def test_missing_values_duplicates_invalid_ip_and_unrecognized_labels():
    document = [
        {
            "label_values": [
                {"label": "Endereço IP", "value": "not-an-ip"},
                {"label": "App"},
                {"label": "Tipo", "value": "synthetic-a"},
                {"label": "Tipo", "value": "synthetic-b"},
                {"label": "Synthetic unknown", "value": "iPhone99,9 203.0.113.10"},
            ]
        }
    ]
    result = parse(0, document)
    assert {"INVALID_IP_SYNTAX", "LABEL_VALUE_ABSENT", "DUPLICATE_LABEL", "UNKNOWN_LABEL"} <= {
        w.code for w in result.warnings
    }
    record = result.records[0]
    assert len([a for a in record.annotations if a.get("field") == "event_type"]) == 2
    assert not any(a["kind"] == "model_code_from_user_agent" for a in record.annotations)


def test_string_map_remains_opaque_in_array_and_legacy_contract_preserves_escaping():
    mapped = {"synthetic~/field": {"value": "Unicode ação 🧪"}}
    document = [{"label_values": [], "string_map_data": mapped}]
    # Unapproved array containers must not inherit legacy semantics.
    result = parse(0, document)
    assert result.records[0].payload["string_map_data"] == mapped
    assert result.warnings
    for warning in result.warnings:
        resolve_locator(document, warning.source_locator)
    legacy = {
        "profile_account_insights": [
            {
                "string_map_data": {
                    "User Agent": {"value": "iPhone99,9"},
                    "synthetic~/field": {"synthetic~/key": "ação 🧪"},
                }
            }
        ]
    }
    result = parse(0, legacy)
    warning = next(w for w in result.warnings if "~0~1" in w.source_locator)
    assert resolve_locator(legacy, warning.source_locator) == "ação 🧪"


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        [None],
        [{"media_metadata": []}],
        [{"media_metadata": {"photo_metadata": {"exif_data": [None]}}}],
    ],
)
def test_bad_media_shapes_warn_and_preserve(value):
    document = [{"label_values": [{"label": "Mídia", "media": value}]}]
    result = parse(1, document)
    assert result.warnings and result.records[0].payload == document[0]


@pytest.mark.parametrize("index", [0, 1])
def test_array_limits_and_noncanonical_selection(index, monkeypatch):
    document = fixture(index)
    assert not PARSERS[index].supports(ParserContext("../" + NAMES[index] + ".json"), document)
    monkeypatch.setattr("evidence_engine.ingest.instagram.parsers.MAX_RECORDS", 1)
    with pytest.raises(ParseError, match="RECORD_LIMIT"):
        parse(index, document)


@pytest.mark.parametrize("index", [0, 1])
def test_versions_preserve_old_records_and_array_provenance(case_root, index):
    name = NAMES[index] + ".json"
    legacy_document = json.loads((FIXTURES.parent / "meta" / name).read_bytes())
    old_source = case_root / "originals" / name
    old_source.write_text(json.dumps(legacy_document), encoding="utf-8")
    archive = case_root / "originals/synthetic-array.zip"
    document = fixture(index)
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(name, json.dumps(document))
    ingest(case_root)
    legacy = replace(PARSERS[index], parser_version="1.0.0")
    # Use the old object contract only for the legacy observation set.
    from evidence_engine.ingest.instagram.parsers import MetaListParser

    class LegacyContract:
        parser_id = legacy.parser_id
        parser_version = "1.0.0"
        matches_path = legacy.matches_path
        parse = legacy.parse

        def supports(self, context, value):
            return isinstance(value, dict) and legacy.supports(context, value)

    assert isinstance(legacy, MetaListParser)
    assert parse_instagram(case_root, (LegacyContract(),)).errors == 0
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as session:
        old = {
            r.id: (r.payload_json, r.source_record_id)
            for r in session.scalars(select(ParsedRecord))
        }
    first = parse_instagram(case_root, (PARSERS[index],))
    assert first.errors == 0 and first.records_parsed == len(old) + len(document)
    with Session(engine) as session:
        for record_id, expected in old.items():
            record = session.get(ParsedRecord, record_id)
            assert (record.payload_json, record.source_record_id) == expected
            assert record.parser_version == "1.0.0"
        current_ids = set(session.scalars(select(ParsedRecord.id)))
        for record in session.scalars(
            select(ParsedRecord).where(ParsedRecord.source_locator == "$/0")
        ):
            source = session.get(SourceRecord, record.source_record_id)
            member = session.get(ArchiveMember, source.archive_member_id)
            evidence = session.get(EvidenceFile, member.evidence_file_id)
            assert evidence.sha256 == hashlib.sha256(archive.read_bytes()).hexdigest()
            assert source.location == record.source_locator
            assert source.parser_version == record.parser_version == "1.1.0"
            assert resolve_locator(document, record.source_locator) == json.loads(
                record.payload_json
            )
    second = parse_instagram(case_root, (PARSERS[index],))
    assert second.records_parsed == 0 and second.records_existing == first.records_parsed
    with Session(engine) as session:
        assert set(session.scalars(select(ParsedRecord.id))) == current_ids
    engine.dispose()
