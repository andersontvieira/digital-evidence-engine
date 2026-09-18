import json
from dataclasses import replace

import pytest

from evidence_engine.normalization.framework import NormalizerContext
from evidence_engine.normalization.normalizers import CONTRACTS, NORMALIZERS
from evidence_engine.normalization.time import normalize_time


def context(parser_id, payload=None, timestamp=1700000000, annotations=None):
    return NormalizerContext(
        parser_id,
        "1.0.0",
        CONTRACTS[parser_id][0],
        timestamp,
        payload or {"timestamp": timestamp},
        annotations or [],
    )


@pytest.mark.parametrize("parser_id", CONTRACTS)
def test_exact_parser_version_record_type_dispatch(parser_id):
    normalizer = next(n for n in NORMALIZERS if parser_id.startswith(n.platform))
    c = context(parser_id)
    assert normalizer.supports(c.parser_id, c.parser_version, c.record_type)
    assert normalizer.normalize(c).event.event_kind == CONTRACTS[parser_id][1]
    assert not normalizer.supports(c.parser_id, "future", c.record_type)
    assert not normalizer.supports(c.parser_id, c.parser_version, "other_type")
    assert not normalizer.supports("unknown", "1.0.0", c.record_type)
    assert all(
        not n.supports("apple.device_inventory", "1.0.0", "apple_device_inventory")
        for n in NORMALIZERS
    )
    assert all(
        not n.supports("meta.instagram_messages", "1.0.0", "instagram_conversation")
        for n in NORMALIZERS
    )


@pytest.mark.parametrize(
    "raw,unit,status,utc",
    [
        (0, "seconds", "normalized", "1970-01-01T00:00:00.000000Z"),
        (1700000000123, "milliseconds", "normalized", "2023-11-14T22:13:20.123000Z"),
        (-1, "seconds", "normalized", "1969-12-31T23:59:59.000000Z"),
        ("2024-01-02T03:04:05Z", None, "normalized", "2024-01-02T03:04:05.000000Z"),
        ("2024-01-02T03:04:05+02:30", None, "normalized", "2024-01-02T00:34:05.000000Z"),
        ("2024-01-02 03:04:05 UTC", None, "normalized", "2024-01-02T03:04:05.000000Z"),
        ("2024-01-02T03:04:05", None, "raw_only", None),
        ("2024-01-02", None, "raw_only", None),
        ("1700000000", "seconds", "raw_only", None),
        (1700000000, None, "raw_only", None),
        (True, "seconds", "raw_only", None),
        (10**100, "seconds", "raw_only", None),
        ("2024-99-99T03:04:05Z", None, "raw_only", None),
        ("2024-01-02T03:04:05+01:99", None, "raw_only", None),
        (None, None, "missing", None),
        ("", None, "missing", None),
    ],
)
def test_timestamp_contracts(raw, unit, status, utc):
    result = normalize_time(raw, unit)
    assert (result.status, result.utc) == (status, utc)


def test_no_timezone_from_environment(monkeypatch):
    import os
    import time

    previous = os.environ.get("TZ")
    try:
        for zone in ("UTC", "America/Sao_Paulo", "Pacific/Honolulu"):
            monkeypatch.setenv("TZ", zone)
            if hasattr(time, "tzset"):
                time.tzset()
            assert normalize_time(0, "seconds").utc == "1970-01-01T00:00:00.000000Z"
            assert normalize_time("2024-01-02T03:04:05").status == "raw_only"
    finally:
        if previous is None:
            monkeypatch.delenv("TZ")
        else:
            monkeypatch.setenv("TZ", previous)
        if hasattr(time, "tzset"):
            time.tzset()


def test_meta_raw_fields_and_timestamp_roles():
    payload = {
        "timestamp_ms": 1700000000123,
        "ip": "synthetic-invalid-ip",
        "device_id": "SYNTHETIC-DEVICE",
        "action": "synthetic action",
        "status": 0,
    }
    result = NORMALIZERS[0].normalize(
        context("meta.instagram_messages", payload, payload["timestamp_ms"])
    )
    assert result.event.time_basis == "epoch_milliseconds"
    assert result.event.ip_raw == "synthetic-invalid-ip"
    assert result.event.status_raw == 0
    assert result.event.device_identifier_raw == "SYNTHETIC-DEVICE"
    assert result.event.action_raw == "synthetic action"
    # Unknown time role cannot borrow the semantics of a nested annotation.
    c = context("meta.profile_activity", {"string_map_data": {"Time": {"value": 1700000000}}})
    assert NORMALIZERS[0].normalize(c).event.time_status == "raw_only"


def test_meta_uses_existing_annotations_without_parsing_new_user_agent_codes():
    annotations = [
        {"kind": "observed_field", "field": "device_id", "value": "SYNTHETIC-DEVICE"},
        {"kind": "observed_field", "field": "ip_address", "value": "203.0.113.20"},
        {"kind": "observed_field", "field": "event_type", "value": "Synthetic activity"},
        {"kind": "model_code_from_user_agent", "value": "iPhone99_9"},
    ]
    c = context("meta.profile_activity", annotations=annotations)
    event = NORMALIZERS[0].normalize(c).event
    assert event.device_model_raw == "iPhone99_9"
    assert event.device_identifier_raw == "SYNTHETIC-DEVICE"
    assert event.ip_raw == "203.0.113.20"
    ambiguous = annotations + [
        {"kind": "observed_field", "field": "device_id", "value": "SYNTHETIC-OTHER"}
    ]
    result = NORMALIZERS[0].normalize(replace(c, annotations=ambiguous))
    assert result.event.device_identifier_raw is None and "AMBIGUOUS_FIELD" in result.warnings


def test_google_only_copies_projected_model_codes():
    c = context(
        "google.subscriber_info",
        {
            "Timestamp": "raw",
            "IP Address": "synthetic-invalid",
            "Raw User Agents": "Agent iPhone99_9",
            "Activity Type": "Synthetic action",
        },
        timestamp="raw",
    )
    assert NORMALIZERS[1].normalize(c).event.device_model_raw is None
    result = NORMALIZERS[1].normalize(
        replace(c, annotations=[{"kind": "model_code_from_user_agent", "value": "iPhone99_9"}])
    )
    assert result.event.device_model_raw == "iPhone99_9"
    assert result.event.ip_raw == "synthetic-invalid"


def test_apple_does_not_infer_location_device_kind_status_or_timezone():
    c = context(
        "apple.sign_on_activity",
        {
            "Device Identifier": "000001",
            "IP Address": "",
            "Signon Status": "0",
            "StoreFront Name": "Synthetic location",
        },
        timestamp="2024-01-02T03:04:05",
    )
    e = NORMALIZERS[2].normalize(c).event
    assert e.status_raw == "0" and e.device_identifier_raw == "000001"
    assert e.time_status == "raw_only" and e.occurred_at_utc is None
    assert e.device_model_raw is None and e.ip_raw == ""
    assert "UDID" not in str(e) and "location" not in str(e)
    media = context(
        "apple.media_device_activity",
        {
            "Device Hardware Model": "iPhone99,9",
            "Device Identifier": "000002",
            "Event Type": "Synthetic",
            "IP": "",
        },
    )
    assert NORMALIZERS[2].normalize(media).event.device_model_raw == "iPhone99,9"


def test_existing_synthetic_array_contracts():
    from pathlib import Path

    from evidence_engine.ingest.instagram.parsers import PARSERS
    from evidence_engine.ingest.parsing.framework import ParserContext

    root = Path(__file__).parent / "fixtures/synthetic/meta_arrays"
    for parser in PARSERS[:2]:
        document = json.loads(
            (root / (parser.filename[:-5] + "_array_label_values.json")).read_text(encoding="utf-8")
        )
        parsed = parser.parse(ParserContext(parser.filename), document)
        for r in parsed.records:
            event = (
                NORMALIZERS[0]
                .normalize(
                    NormalizerContext(
                        parser.parser_id,
                        parser.parser_version,
                        r.record_type,
                        r.timestamp_raw,
                        r.payload,
                        r.annotations,
                    )
                )
                .event
            )
            assert event.time_status == ("missing" if r.timestamp_raw is None else "normalized")
            assert event.occurred_at_utc == normalize_time(r.timestamp_raw, "seconds").utc
