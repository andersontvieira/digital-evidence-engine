import hashlib
import json

import pytest

from evidence_engine.correlation.exact import DEVICE_RULE, NETWORK_RULE, exact_groups
from evidence_engine.models.entities import DeviceObservation, NetworkObservation


def device(index=0, **changes):
    values = dict(
        id=f"synthetic-observation-{index:04d}",
        parsed_record_id=f"synthetic-record-{index:04d}",
        observation_ordinal=0,
        observer_id="device.observer",
        observer_version="1.0.0",
        fact_kind="identifier",
        namespace="meta.device_id",
        value_raw='"SYNTHETIC-ID-001"',
    )
    return DeviceObservation(**(values | changes))


def network(index=0, **changes):
    values = dict(
        id=f"synthetic-network-{index:04d}",
        parsed_record_id=f"synthetic-record-{index:04d}",
        observation_ordinal=0,
        observer_id="network.observer",
        observer_version="1.0.0",
        ip_raw='"203.0.113.10"',
        ip_canonical="203.0.113.10",
        ip_version=4,
        platform="meta",
        source_role="meta.activity_ip",
    )
    return NetworkObservation(**(values | changes))


@pytest.mark.parametrize("count", [1, 2, 3, 259])
def test_device_group_cardinality_and_no_pairwise(count):
    rows = [
        device(
            i, fact_kind="model", namespace="google.user_agent.model_code", value_raw='"iPhone99_9"'
        )
        for i in range(count)
    ]
    groups = exact_groups(reversed(rows))
    assert len(groups) == (1 if count >= 2 else 0)
    if groups:
        assert groups[0].candidate_kind == "device" and groups[0].rule_id == DEVICE_RULE
        assert groups[0].observations == tuple(rows)
        assert len(groups[0].observations) == count


@pytest.mark.parametrize(
    "change",
    [
        {"value_raw": '"synthetic-id-001"'},
        {"value_raw": '"SYNTHETIC-ID-001 "'},
        {"value_raw": '"SYNTHETICID001"'},
        {"namespace": "apple.device_identifier"},
        {"fact_kind": "model"},
        {"observer_version": "2.0.0"},
        {"observer_id": "other.observer"},
    ],
)
def test_device_differences_and_unapproved_versions_do_not_join(change):
    assert exact_groups([device(), device(1, **change)]) == ()


@pytest.mark.parametrize(
    "left,right",
    [('"iPhone99_9"', '"iPhone99,9"'), ('"A"', '"\\u0041"'), ("1", '"1"'), ('"X"', ' "X"')],
)
def test_raw_comparison_is_persisted_text_not_decoded_value(left, right):
    assert exact_groups([device(value_raw=left), device(1, value_raw=right)]) == ()


def test_serial_singleton_and_digest_contract():
    assert exact_groups([device(namespace="apple.serial_number")]) == ()
    group = exact_groups([device(1), device()])[0]
    serialized = json.dumps(
        [
            "exact-match-key",
            1,
            DEVICE_RULE,
            "1.0.0",
            "identifier",
            "meta.device_id",
            '"SYNTHETIC-ID-001"',
        ],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert group.key_digest == hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    assert group.key_digest == exact_groups([device(), device(1)])[0].key_digest


def test_namespace_groups_remain_independent():
    rows = [
        device(i, namespace=ns)
        for i, ns in enumerate(["meta.device_id"] * 2 + ["apple.device_identifier"] * 2)
    ]
    groups = exact_groups(rows)
    assert len(groups) == 2 and len({g.key_digest for g in groups}) == 2
    assert all(len({o.namespace for o in g.observations}) == 1 for g in groups)


@pytest.mark.parametrize("count", [1, 2, 3, 300])
def test_network_cardinality(count):
    groups = exact_groups([network(i) for i in range(count)])
    assert len(groups) == (1 if count >= 2 else 0)
    if groups:
        assert groups[0].candidate_kind == "network" and groups[0].rule_id == NETWORK_RULE
        assert len(groups[0].observations) == count


def test_ipv6_raw_roles_platforms_do_not_change_persisted_canonical_key():
    rows = [
        network(ip_raw='"2001:0DB8:0:0:0:0:0:1"', ip_canonical="2001:db8::1", ip_version=6),
        network(
            1,
            ip_raw='"2001:db8::1"',
            ip_canonical="2001:db8::1",
            ip_version=6,
            platform="apple",
            source_role="apple.signon_ip",
        ),
    ]
    group = exact_groups(rows)[0]
    assert len(group.observations) == 2
    serialized = json.dumps(
        ["exact-match-key", 1, NETWORK_RULE, "1.0.0", 6, "2001:db8::1"], separators=(",", ":")
    )
    assert group.key_digest == hashlib.sha256(serialized.encode()).hexdigest()


@pytest.mark.parametrize(
    "change",
    [
        {"ip_canonical": "198.51.100.20"},
        {"ip_version": 6},
        {"ip_canonical": None, "ip_version": None},
        {"ip_version": 5},
        {"observer_version": "2.0.0"},
        {"observer_id": "other.observer"},
    ],
)
def test_network_exclusions(change):
    assert exact_groups([network(), network(1, **change)]) == ()


def test_invalid_raw_never_groups_and_domains_are_separate():
    assert (
        exact_groups(
            [network(i, ip_canonical=None, ip_version=None, ip_raw='"invalid"') for i in range(3)]
        )
        == ()
    )
    groups = exact_groups(
        [
            device(0, value_raw="203.0.113.10"),
            device(1, value_raw="203.0.113.10"),
            network(),
            network(1),
        ]
    )
    assert len(groups) == 2
    assert all(
        all(
            isinstance(o, DeviceObservation if g.candidate_kind == "device" else NetworkObservation)
            for o in g.observations
        )
        for g in groups
    )


def test_support_order_uses_record_then_ordinal_then_id():
    rows = [
        device(2, parsed_record_id="same", observation_ordinal=1),
        device(1, parsed_record_id="same", observation_ordinal=0),
        device(0, parsed_record_id="same", observation_ordinal=0),
    ]
    assert [o.id for o in exact_groups(rows)[0].observations] == [device(i).id for i in range(3)]
