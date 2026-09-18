from dataclasses import replace

import pytest

from evidence_engine.ingest.parsing.framework import ParseError, child_locator
from evidence_engine.observations.framework import ObservationContext, field_value
from evidence_engine.observations.observers import OBSERVERS

DEVICE, NETWORK = OBSERVERS


def context(parser, payload, annotations=None):
    types = {
        "meta.profile_activity": "profile_activity",
        "meta.recently_deleted_content": "recently_deleted_content",
        "google.subscriber_info": "google_security_activity",
        "google.change_history": "google_account_change",
        "apple.device_inventory": "apple_device_inventory",
        "apple.sign_on_activity": "apple_sign_on_activity",
        "apple.media_device_activity": "apple_media_device_activity",
    }
    return ObservationContext(
        parser, "1.0.0", types[parser], "$/rows/0", payload, annotations or []
    )


def test_meta_explicit_fields_annotations_and_no_text_scanning():
    ctx = context(
        "meta.profile_activity",
        {
            "device_id": "SYNTHETIC-DEVICE-ID-001",
            "user_agent": "agent iPhone99,9",
            "caption": "SYNTHETIC-OTHER iPhone88,8 203.0.113.10",
        },
        [
            {
                "kind": "observed_field",
                "field": "device_id",
                "value": "SYNTHETIC-DEVICE-ID-001",
                "source_locator": "$/rows/0/device_id",
            },
            {
                "kind": "model_code_from_user_agent",
                "value": "iPhone99,9",
                "source_locator": "$/rows/0/user_agent",
            },
        ],
    )
    facts = DEVICE.observe(ctx).observations
    assert [(f.namespace, f.value_raw) for f in facts] == [
        ("meta.device_id", "SYNTHETIC-DEVICE-ID-001"),
        ("meta.user_agent.model_code", "iPhone99,9"),
    ]
    assert DEVICE.observe(ctx).observations == facts
    assert NETWORK.observe(ctx).observations == ()
    assert (
        DEVICE.observe(
            context("meta.recently_deleted_content", {"caption": ctx.payload["caption"]})
        ).observations
        == ()
    )
    for observer in OBSERVERS:
        assert not observer.supports("meta.instagram_messages", "1.0.0", "instagram_message")
        assert not observer.supports(ctx.parser_id, "9.9.9", ctx.record_type)
        assert not observer.supports(ctx.parser_id, ctx.parser_version, "other")


def test_meta_annotation_locator_escaping_and_typed_value():
    locator = child_locator("$/rows/0", "device~/id")
    ctx = context(
        "meta.profile_activity",
        {"device~/id": 0},
        [{"kind": "observed_field", "field": "device_id", "value": 0, "source_locator": locator}],
    )
    fact = DEVICE.observe(ctx).observations[0]
    assert fact.value_raw == 0 and type(fact.value_raw) is int
    assert fact.source_field_locator == "$/rows/0/device~0~1id"
    assert field_value(ctx, locator) == 0
    for bad in ("$/rows/1/device~0~1id", "$/rows/0/nonexistent"):
        with pytest.raises((ValueError, ParseError)):
            DEVICE.observe(replace(ctx, annotations=[dict(ctx.annotations[0], source_locator=bad)]))
    with pytest.raises(ValueError):
        DEVICE.observe(replace(ctx, annotations=[dict(ctx.annotations[0], value="0")]))


def test_google_distinct_tokens_first_occurrence_only_in_allowed_field():
    ctx = context(
        "google.subscriber_info",
        {"Raw User Agents": "(iPhone99_9) iPhone88_8 iPhone99_9", "caption": "iPhone77_7"},
    )
    assert [f.value_raw for f in DEVICE.observe(ctx).observations] == ["iPhone99_9", "iPhone88_8"]
    assert all(
        f.source_field_locator == "$/rows/0/Raw User Agents"
        for f in DEVICE.observe(ctx).observations
    )
    assert DEVICE.observe(context("google.change_history", ctx.payload)).observations == ()


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "iPhone99,9",
        "xiPhone99_9",
        "iPhone99_9x",
        "iPhone99_9_1",
        "iPhone９９_9",
        "iPhone99_９",
        "iphone99_9",
        "iPhone99_9,1",
        "iPhone 99 Pro",
        "éiPhone99_9",
    ],
)
def test_google_rejects_similar_tokens(raw):
    assert (
        DEVICE.observe(context("google.subscriber_info", {"Raw User Agents": raw})).observations
        == ()
    )


def test_apple_inventory_atomic_fields_and_exclusions():
    ctx = context(
        "apple.device_inventory",
        {
            "Device Serial Number": "SYNTHETIC-SERIAL-001",
            "Device IMEI": "000000000000000",
            "Device MEID": "00000000000000",
            "Device Model Name": "iPhone99,9",
            "Device ICCID": "SYNTHETIC-SIM",
            "Phone Number": "SYNTHETIC-PHONE",
        },
    )
    facts = DEVICE.observe(ctx).observations
    assert [f.namespace for f in facts] == [
        "apple.serial_number",
        "apple.imei",
        "apple.meid",
        "apple.hardware_model",
    ]
    assert [f.fact_kind for f in facts] == ["identifier", "identifier", "identifier", "model"]
    assert facts[1].value_raw == "000000000000000"
    assert all(field_value(ctx, f.source_field_locator) == f.value_raw for f in facts)


@pytest.mark.parametrize(
    "raw", [None, "", " ", "N/A", " Not Available ", "Not Applicable", "null", "None", "-"]
)
def test_apple_absence_markers_do_not_make_device_facts(raw):
    assert (
        DEVICE.observe(
            context("apple.device_inventory", {"Device Model Name": raw, "Device MEID": raw})
        ).observations
        == ()
    )


@pytest.mark.parametrize(
    "parser,field,role",
    [
        ("meta.profile_activity", "ip_address", "meta.activity_ip"),
        ("meta.recently_deleted_content", "ip", "meta.activity_ip"),
        ("google.subscriber_info", "IP Address", "google.activity_ip"),
        ("google.change_history", "IP Address", "google.change_ip"),
        ("apple.device_inventory", "Device Last Heartbeat IP", "apple.heartbeat_ip"),
        ("apple.sign_on_activity", "IP Address", "apple.signon_ip"),
        ("apple.media_device_activity", "IP", "apple.media_ip"),
    ],
)
def test_network_roles_and_explicit_occurrences(parser, field, role):
    ctx = context(parser, {field: "203.0.113.10"})
    fact = NETWORK.observe(ctx).observations[0]
    assert (fact.source_role, fact.ip_raw, fact.ip_canonical, fact.ip_version) == (
        role,
        "203.0.113.10",
        "203.0.113.10",
        4,
    )
    assert field_value(ctx, fact.source_field_locator) == fact.ip_raw
    assert NETWORK.observe(context(parser, {field: ""})).observations == ()
    assert NETWORK.observe(context(parser, {})).observations == ()


@pytest.mark.parametrize("raw", ["invalid", " 203.0.113.10 ", "999.1.1.1", 123, False])
def test_invalid_ip_preserved_without_integer_reinterpretation(raw):
    result = NETWORK.observe(context("google.subscriber_info", {"IP Address": raw}))
    fact = result.observations[0]
    assert fact.ip_raw == raw and type(fact.ip_raw) is type(raw)
    assert fact.ip_canonical is None and fact.ip_version is None
    assert result.warnings == ("INVALID_IP_SYNTAX",)


def test_ipv6_canonicalization_and_apple_media_no_propagation():
    raw = "2001:0DB8:0000:0000:0000:0000:0000:0001"
    signon = context(
        "apple.sign_on_activity", {"Device Identifier": "SYNTHETIC-ID", "IP Address": raw}
    )
    media = context(
        "apple.media_device_activity",
        {"Device Identifier": "SYNTHETIC-ID", "Device Hardware Model": "iPhone99,9", "IP": ""},
    )
    fact = NETWORK.observe(signon).observations[0]
    assert (fact.ip_raw, fact.ip_canonical, fact.ip_version) == (raw, "2001:db8::1", 6)
    assert len(DEVICE.observe(signon).observations) == 1
    assert [f.namespace for f in DEVICE.observe(media).observations] == [
        "apple.device_identifier",
        "apple.hardware_model",
    ]
    assert NETWORK.observe(media).observations == ()


def test_meta_string_map_and_ip_annotation_resolve_own_field():
    ctx = context(
        "meta.profile_activity",
        {
            "string_map_data": {
                "Device ID": {"value": "SYNTHETIC-ID"},
                "IP Address": {"value": "198.51.100.20"},
            }
        },
    )
    assert len(DEVICE.observe(ctx).observations) == 1
    assert NETWORK.observe(ctx).observations[0].ip_raw == "198.51.100.20"
    ctx = context(
        "meta.profile_activity",
        {"label_values": [{"value": "198.51.100.20"}]},
        [
            {
                "kind": "observed_field",
                "field": "ip_address",
                "value": "198.51.100.20",
                "source_locator": "$/rows/0/label_values/0/value",
            }
        ],
    )
    fact = NETWORK.observe(ctx).observations[0]
    assert field_value(ctx, fact.source_field_locator) == fact.ip_raw
