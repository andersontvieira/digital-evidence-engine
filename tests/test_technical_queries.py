import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.correlation.service import correlate_exact
from evidence_engine.errors import EvidenceError
from evidence_engine.models.entities import (
    CorrelationCandidate,
    CorrelationSupport,
    DeviceObservation,
    NetworkObservation,
)
from evidence_engine.normalization.normalizers import PlatformNormalizer
from evidence_engine.normalization.service import normalize_events
from evidence_engine.query.provenance import query_provenance
from evidence_engine.query.search import query_device, query_network
from evidence_engine.storage.database import open_database
from tests.test_correlation_service import seeded
from tests.test_normalization_service import populated
from tests.test_timeline import database_bytes

VALUE = "SYNTHETIC-DEVICE-X"
NS = "meta.synthetic.identifier"
DEVICE_FIELDS = {
    "observation_id",
    "parsed_record_id",
    "platform",
    "fact_kind",
    "namespace",
    "source_field_locator",
    "source_field_name",
    "observation_ordinal",
    "candidate_ids",
}
NETWORK_FIELDS = {
    "observation_id",
    "parsed_record_id",
    "platform",
    "source_role",
    "ip_version",
    "source_field_locator",
    "source_field_name",
    "observation_ordinal",
    "candidate_ids",
}


def clone(session, source, **changes):
    values = {
        c.name: getattr(source, c.name)
        for c in source.__table__.columns
        if c.name not in {"id", "created_at"}
    }
    obj = type(source)(**(values | changes))
    session.add(obj)
    return obj


@pytest.fixture
def technical_case(case_root):
    seeded(case_root, count=2, archive=True)
    normalize_events(case_root)
    engine = open_database(case_root / "database/evidence.db")
    with Session(engine) as s:
        devices = list(s.scalars(select(DeviceObservation).order_by(DeviceObservation.id)))
        networks = list(s.scalars(select(NetworkObservation).order_by(NetworkObservation.id)))
        for i, d in enumerate(devices):
            d.namespace = NS
            d.value_raw = json.dumps(VALUE if i < 2 else f"SYNTHETIC-SINGLE-{i}")
            d.platform = "google" if i == 1 else "meta"
        d = devices[0]
        variants = [
            {"namespace": "google.synthetic.identifier"},
            {"value_raw": json.dumps(VALUE.lower())},
            {"value_raw": json.dumps("123")},
            {"value_raw": "123"},
            {"value_raw": json.dumps("iPhone99_9"), "fact_kind": "model"},
            {"observer_version": "1.1.0"},
            {"observer_id": "future.observer"},
            {"value_raw": json.dumps(VALUE + " ")},
            {"value_raw": json.dumps(VALUE.replace("-", "_"))},
        ]
        for i, changes in enumerate(variants, 10):
            clone(s, d, observation_ordinal=i, **changes)
        for i, n in enumerate(networks):
            n.ip_raw = json.dumps("203.0.113.10" if i < 2 else f"198.51.100.{20 + i}")
            n.ip_canonical = json.loads(n.ip_raw)
            n.platform = "google" if i == 1 else "meta"
            n.source_role = "login" if i == 1 else "observed"
        n = networks[0]
        for i, raw in enumerate(("2001:db8::1", "2001:0db8:0:0:0:0:0:1"), 10):
            clone(
                s,
                n,
                observation_ordinal=i,
                ip_raw=json.dumps(raw),
                ip_canonical="2001:db8::1",
                ip_version=6,
            )
        clone(s, n, observation_ordinal=20, observer_version="1.1.0")
        clone(s, n, observation_ordinal=21, observer_id="future.observer")
        s.commit()
    engine.dispose()
    assert correlate_exact(case_root).errors == 0
    return case_root


def command(root, *args):
    return CliRunner().invoke(app, ["query", *args, "--case-root", str(root)])


def lookup(root, kind, object_id, **kwargs):
    return query_provenance(root, kind=kind, object_id=object_id, **kwargs)


def read_rows(root, table):
    with sqlite3.connect(
        f"file:{(root / 'database/evidence.db').as_posix()}?mode=ro", uri=True
    ) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM " + table)]


def assert_memberships(root, items, kind):
    supports = read_rows(root, "correlation_supports")
    for item in items:
        expected = sorted(
            s["candidate_id"]
            for s in supports
            if s[kind + "_observation_id"] == item["observation_id"]
        )
        assert item["candidate_ids"] == expected


def test_device_exact_projection_order_membership_and_deterministic_cli(technical_case):
    root = technical_case
    result = query_device(root, namespace=NS, value=VALUE)
    assert result["matched_total"] == result["returned"] == 2 and not result["truncated"]
    items = result["items"]
    assert all(set(i) == DEVICE_FIELDS for i in items)
    assert items == sorted(
        items,
        key=lambda i: (
            i["platform"],
            i["parsed_record_id"],
            i["observation_ordinal"],
            i["observation_id"],
        ),
    )
    assert_memberships(root, items, "device")
    assert all(i["candidate_ids"] for i in items)
    first = command(root, "device", "--namespace", NS, "--value", VALUE)
    second = command(root, "device", "--namespace", NS, "--value", VALUE)
    assert first.exit_code == second.exit_code == 0 and first.stdout_bytes == second.stdout_bytes
    assert VALUE not in first.output and "value_raw" not in first.output


@pytest.mark.parametrize(
    "value,count",
    [
        ("123", 1),
        ("true", 0),
        (VALUE.lower(), 1),
        (VALUE + " ", 1),
        (VALUE.replace("-", "_"), 1),
        (VALUE + ",", 0),
        ("iPhone99_9", 1),
    ],
)
def test_device_literal_typing_and_spelling(technical_case, value, count):
    result = query_device(technical_case, namespace=NS, value=value)
    assert result["matched_total"] == count
    if value == "123":
        row = next(
            r
            for r in read_rows(technical_case, "device_observations")
            if r["id"] == result["items"][0]["observation_id"]
        )
        assert row["value_raw"] == '"123"'


@pytest.mark.parametrize(
    "filters,count",
    [
        ({"platform": "meta"}, 1),
        ({"platform": "google"}, 1),
        ({"platform": "absent"}, 0),
        ({"fact_kind": "identifier"}, 2),
        ({"fact_kind": "model"}, 0),
    ],
)
def test_device_filters(technical_case, filters, count):
    assert (
        query_device(technical_case, namespace=NS, value=VALUE, **filters)["matched_total"] == count
    )


def test_device_namespace_singleton_and_limit(technical_case):
    root = technical_case
    other = query_device(root, namespace="google.synthetic.identifier", value=VALUE)
    assert other["matched_total"] == 1 and other["items"][0]["candidate_ids"] == []
    full = query_device(root, namespace=NS, value=VALUE)
    short = query_device(root, namespace=NS, value=VALUE, limit=1)
    assert short == dict(matched_total=2, returned=1, truncated=True, items=full["items"][:1])
    assert query_device(root, namespace="absent", value=VALUE)["items"] == []


def test_network_exact_projection_order_membership_determinism(technical_case):
    root = technical_case
    full = query_network(root, ip="203.0.113.10")
    assert full["matched_total"] == full["returned"] == 2 and not full["truncated"]
    assert all(set(i) == NETWORK_FIELDS for i in full["items"])
    assert full["items"] == sorted(
        full["items"],
        key=lambda i: (
            i["platform"],
            i["parsed_record_id"],
            i["observation_ordinal"],
            i["observation_id"],
        ),
    )
    assert_memberships(root, full["items"], "network")
    assert all(i["candidate_ids"] for i in full["items"])
    first = command(root, "network", "--ip", "203.0.113.10")
    second = command(root, "network", "--ip", "203.0.113.10")
    assert first.exit_code == second.exit_code == 0 and first.stdout_bytes == second.stdout_bytes
    assert (
        "203.0.113.10" not in first.output
        and "ip_raw" not in first.output
        and "ip_canonical" not in first.output
    )
    short = query_network(root, ip="203.0.113.10", limit=1)
    assert short == dict(matched_total=2, returned=1, truncated=True, items=full["items"][:1])


def test_network_ipv6_input_and_singleton(technical_case):
    root = technical_case
    a = query_network(root, ip="2001:db8::1")
    b = query_network(root, ip="2001:0DB8:0:0:0:0:0:1")
    assert a == b and a["matched_total"] == 2
    singleton = query_network(root, ip="198.51.100.22")
    assert singleton["matched_total"] == 1 and singleton["items"][0]["candidate_ids"] == []


@pytest.mark.parametrize(
    "filters,count",
    [
        ({"platform": "meta"}, 1),
        ({"platform": "google"}, 1),
        ({"source_role": "observed"}, 1),
        ({"source_role": "login"}, 1),
        ({"source_role": "absent"}, 0),
    ],
)
def test_network_filters(technical_case, filters, count):
    assert query_network(technical_case, ip="203.0.113.10", **filters)["matched_total"] == count


def assert_origin(root, origin):
    record = next(
        r for r in read_rows(root, "parsed_records") if r["id"] == origin["parsed_record_id"]
    )
    source = next(
        r for r in read_rows(root, "source_records") if r["id"] == record["source_record_id"]
    )
    assert (
        origin["source_record_id"] == source["id"]
        and origin["source_locator"] == record["source_locator"]
    )
    if source["archive_member_id"]:
        member = next(
            r for r in read_rows(root, "archive_members") if r["id"] == source["archive_member_id"]
        )
        assert origin["origin_kind"] == "archive_member"
        assert (
            origin["archive_member_sha256"] == member["sha256"]
            and origin["member_path"] == member["member_path"]
        )
        assert origin["archive_member_id"] == member["id"]
        evidence_id = member["evidence_file_id"]
    else:
        assert origin["origin_kind"] == "evidence_file"
        assert (
            origin["member_path"]
            is origin["archive_member_id"]
            is origin["archive_member_sha256"]
            is None
        )
        evidence_id = source["evidence_file_id"]
    evidence = next(r for r in read_rows(root, "evidence_files") if r["id"] == evidence_id)
    assert origin["evidence_file_id"] == evidence_id
    assert (
        origin["evidence_sha256"] == evidence["sha256"]
        and origin["evidence_relative_path"] == evidence["relative_path"]
    )


def test_parsed_record_direct_and_archive_origins_no_payload(technical_case):
    root = technical_case
    origins = set()
    for record in read_rows(root, "parsed_records"):
        result = lookup(root, "parsed-record", record["id"])
        assert set(result) == {
            "parsed_record_id",
            "parser_id",
            "parser_version",
            "record_type",
            "source_locator",
            "provenance",
        }
        assert_origin(root, result["provenance"])
        origins.add(result["provenance"]["origin_kind"])
        assert "payload" not in json.dumps(result) and "timestamp_raw" not in json.dumps(result)
    assert origins == {"evidence_file", "archive_member"}


def test_event_current_and_historical_without_sibling_links(case_root):
    populated(case_root)
    normalize_events(case_root)
    normalize_events(case_root, (PlatformNormalizer("google", "1.0.0"),))
    observed = set()
    for row in read_rows(case_root, "normalized_events"):
        result = lookup(case_root, "event", row["id"])
        expected = not (row["platform"] == "google" and row["normalizer_version"] == "1.0.0")
        assert result["current_policy_match"] is expected
        assert set(result) == {
            "event_id",
            "parsed_record_id",
            "platform",
            "event_kind",
            "normalizer_id",
            "normalizer_version",
            "occurred_at_utc",
            "time_status",
            "time_basis",
            "current_policy_match",
            "provenance",
        }
        observed.add((row["platform"], row["normalizer_version"]))
        assert_origin(case_root, result["provenance"])
    assert observed == {
        ("meta", "1.0.0"),
        ("apple", "1.0.0"),
        ("google", "1.0.0"),
        ("google", "1.1.0"),
    }


@pytest.mark.parametrize(
    "kind,table,fields",
    [
        ("device", "device_observations", DEVICE_FIELDS),
        ("network", "network_observations", NETWORK_FIELDS),
    ],
)
def test_observation_provenance_all_versions_membership_and_projection(
    technical_case, kind, table, fields
):
    root = technical_case
    for row in read_rows(root, table):
        result = lookup(root, kind + "-observation", row["id"])
        assert set(result) == fields | {"observer_id", "observer_version", "provenance"}
        assert result["observer_version"] == row["observer_version"]
        assert_origin(root, result["provenance"])
        assert_memberships(root, [result], kind)
        assert "value_raw" not in result and "ip_raw" not in result and "ip_canonical" not in result
        text = json.dumps(result)
        assert VALUE not in text and "203.0.113.10" not in text and "payload" not in text


def test_candidate_domains_support_order_limits_and_json(technical_case):
    root = technical_case
    for row in read_rows(root, "correlation_candidates"):
        result = lookup(root, "candidate", row["id"], limit=1000)
        supports = sorted(
            (s for s in read_rows(root, "correlation_supports") if s["candidate_id"] == row["id"]),
            key=lambda s: s["support_ordinal"],
        )
        assert result["support_count"] == result["returned_supports"] == len(supports)
        assert not result["supports_truncated"]
        assert [s["support_id"] for s in result["supports"]] == [s["id"] for s in supports]
        for s in result["supports"]:
            assert s["observation_kind"] == row["candidate_kind"]
            assert_origin(root, s["provenance"])
        small = lookup(root, "candidate", row["id"], limit=1)
        assert small["supports"] == result["supports"][:1] and small["supports_truncated"]
        first = command(root, "provenance", "--kind", "candidate", "--id", row["id"])
        second = command(root, "provenance", "--kind", "candidate", "--id", row["id"])
        assert (
            first.exit_code == second.exit_code == 0 and first.stdout_bytes == second.stdout_bytes
        )
        assert (
            VALUE not in first.output
            and "203.0.113.10" not in first.output
            and "payload" not in first.output
        )


def test_candidate_259_supports_default_and_full(case_root):
    seeded(case_root, count=259)
    correlate_exact(case_root)
    row = next(
        r for r in read_rows(case_root, "correlation_candidates") if r["candidate_kind"] == "device"
    )
    default = lookup(case_root, "candidate", row["id"])
    assert default["returned_supports"] == 100 and default["supports_truncated"]
    full = command(
        case_root, "provenance", "--kind", "candidate", "--id", row["id"], "--limit", "500"
    )
    assert full.exit_code == 0
    result = json.loads(full.stdout)
    assert (
        result["support_count"] == result["returned_supports"] == 259
        and not result["supports_truncated"]
    )
    assert [s["support_ordinal"] for s in result["supports"]] == list(range(259))
    assert all(s["observation_kind"] == "device" for s in result["supports"])


VALID_COMMANDS = [
    ["device", "--namespace", NS, "--value", VALUE],
    ["network", "--ip", "203.0.113.10"],
    ["provenance", "--kind", "event", "--id", str(uuid4())],
]


@pytest.mark.parametrize(
    "args",
    [
        ["device", "--value", VALUE],
        ["device", "--namespace", NS],
        ["device", "--namespace", NS, "--value", VALUE, "--fact-kind", "invalid"],
        ["network", "--ip", "SENSITIVE-INVALID-IP"],
        ["provenance", "--kind", "event", "--id", "bad"],
        ["provenance", "--kind", "events", "--id", str(uuid4())],
        *[args + ["--limit", limit] for args in VALID_COMMANDS for limit in ("0", "10001")],
        ["provenance", "--kind", "candidate", "--id", str(uuid4()), "--limit", "1001"],
    ],
)
def test_cli_invalid_arguments_no_sensitive_echo(case_root, args):
    result = command(case_root, *args)
    assert result.exit_code == 2 and "Traceback" not in result.output
    assert VALUE not in result.output and "SENSITIVE-INVALID-IP" not in result.output


@pytest.mark.parametrize(
    "kind", ["event", "parsed-record", "device-observation", "network-observation", "candidate"]
)
def test_not_found_uuid(technical_case, kind):
    result = command(technical_case, "provenance", "--kind", kind, "--id", str(uuid4()))
    assert result.exit_code == 2 and json.loads(result.stdout) == {"status": "NOT_FOUND"}


@pytest.mark.parametrize("args", VALID_COMMANDS)
def test_missing_catalog_not_created(case_root, args):
    before = set(case_root.rglob("*"))
    result = command(case_root, *args)
    assert result.exit_code == 2 and set(case_root.rglob("*")) == before


@pytest.mark.parametrize("args", VALID_COMMANDS)
def test_new_commands_refuse_wal_using_existing_opener(technical_case, args):
    root = technical_case
    with sqlite3.connect(root / "database/evidence.db") as c:
        c.execute("PRAGMA journal_mode=WAL")
    before = database_bytes(root)
    result = command(root, *args)
    assert result.exit_code == 2 and "DELETE journal mode" in result.output
    assert database_bytes(root) == before


def test_all_queries_snapshot_query_only_no_raw_select_or_evidence_reads(
    technical_case, monkeypatch
):
    root = technical_case
    event_id = read_rows(root, "normalized_events")[0]["id"]
    before = database_bytes(root)
    original_open = Path.open
    checked = []

    def no_originals(path, *args, **kwargs):
        assert "originals" not in path.parts and "working" not in path.parts
        return original_open(path, *args, **kwargs)

    def inspect_query(connection, cursor, statement, parameters, context, executemany):
        if statement.lower().startswith("select") and "sqlite_master" not in statement.lower():
            projection = statement.lower().split("from")[0]
            assert not any(
                k in projection
                for k in ("value_raw", "ip_raw", "ip_canonical", "payload_json", "annotations_json")
            )
            assert cursor.connection.execute("PRAGMA query_only").fetchone()[0] == 1
            assert cursor.connection.in_transaction
            checked.append(statement)

    event.listen(Engine, "before_cursor_execute", inspect_query)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(Path, "open", no_originals)
            assert query_device(root, namespace=NS, value=VALUE)["returned"] == 2
            assert query_network(root, ip="203.0.113.10")["returned"] == 2
            assert lookup(root, "event", event_id)
    finally:
        event.remove(Engine, "before_cursor_execute", inspect_query)
    assert checked and database_bytes(root) == before


@pytest.mark.parametrize("corruption", ["both", "neither", "missing_source", "missing_evidence"])
def test_broken_origin_fails_without_partial_result(technical_case, corruption):
    root = technical_case
    record = read_rows(root, "parsed_records")[0]
    with sqlite3.connect(root / "database/evidence.db") as c:
        c.execute("PRAGMA ignore_check_constraints=ON")
        if corruption == "missing_source":
            c.execute(
                "UPDATE parsed_records SET source_record_id=? WHERE id=?",
                (str(uuid4()), record["id"]),
            )
        else:
            evidence_id = str(uuid4()) if corruption in {"both", "missing_evidence"} else None
            archive_id = str(uuid4()) if corruption == "both" else None
            c.execute(
                "UPDATE source_records SET evidence_file_id=?,archive_member_id=? WHERE id=?",
                (evidence_id, archive_id, record["source_record_id"]),
            )
    with pytest.raises(EvidenceError, match="PROVENANCE_INTEGRITY_ERROR"):
        lookup(root, "parsed-record", record["id"])


@pytest.mark.parametrize("args", VALID_COMMANDS)
def test_schema_v4_rejected_without_migration(case_root, args):
    from tests.test_correlation_schema import v4_catalog

    v4_catalog(case_root)
    before = database_bytes(case_root)
    result = command(case_root, *args)
    assert result.exit_code == 2 and "schema v5" in result.output
    assert database_bytes(case_root) == before


def test_search_default_limit_100_and_maximum(case_root):
    seeded(case_root, count=101)
    device = read_rows(case_root, "device_observations")[0]
    for result in (
        query_device(case_root, namespace=device["namespace"], value="SYNTHETIC-ID-001"),
        query_network(case_root, ip="203.0.113.10"),
    ):
        assert result["matched_total"] == 101 and result["returned"] == 100 and result["truncated"]
    assert query_network(case_root, ip="203.0.113.10", limit=10000)["returned"] == 101


def test_multiple_memberships_sorted_from_persisted_supports(technical_case):
    root = technical_case
    engine = open_database(root / "database/evidence.db")
    with Session(engine) as s:
        original = s.scalars(
            select(CorrelationCandidate).where(CorrelationCandidate.candidate_kind == "device")
        ).first()
        extra = clone(s, original, rule_version="synthetic-other-rule")
        s.flush()
        for support in list(
            s.scalars(
                select(CorrelationSupport).where(CorrelationSupport.candidate_id == original.id)
            )
        ):
            clone(s, support, candidate_id=extra.id)
        s.commit()
    engine.dispose()
    result = query_device(root, namespace=NS, value=VALUE)
    assert all(len(i["candidate_ids"]) == 2 for i in result["items"])
    assert_memberships(root, result["items"], "device")


def test_sql_error_does_not_echo_search_arguments(case_root, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    import evidence_engine.cli.query as cli_query

    def fail_query(*args, **kwargs):
        raise SQLAlchemyError(VALUE + " 203.0.113.10")

    monkeypatch.setattr(cli_query, "query_device", fail_query)
    monkeypatch.setattr(cli_query, "query_network", fail_query)
    for args in VALID_COMMANDS[:2]:
        result = command(case_root, *args)
        assert result.exit_code == 2
        assert VALUE not in result.output and "203.0.113.10" not in result.output
