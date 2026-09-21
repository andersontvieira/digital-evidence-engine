"""Synthetic contract and composition tests; no real case artifacts."""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from unittest.mock import Mock

import pytest
from sqlalchemy import Engine, event
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.correlation.overlap import temporal_exact_overlap
from evidence_engine.correlation.temporal import temporal_candidates
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.media.contents import media_contents
from evidence_engine.media.inventory import inventory_media
from evidence_engine.media.perceptual import perceptual_hashes
from evidence_engine.query.catalog import read_catalog
from evidence_engine.query.incident import query_incident_window
from evidence_engine.query.incident_candidates import query_incident_candidates
from evidence_engine.query.provenance import record_origin
from evidence_engine.reports import snapshot
from tests.test_media_inventory import JPEG, tree_state
from tests.test_perceptual_hash import image_case as image_case
from tests.test_temporal_overlap import END, START, execute, group
from tests.test_temporal_overlap import catalog as catalog
from tests.test_timeline import timeline_case as timeline_case

WINDOW = {"start": START, "end": END, "max_delta_seconds": 10}


def cli(root, **kwargs):
    args = ["report", "snapshot", "--case-root", str(root)]
    for key, value in kwargs.items():
        args.extend(("--" + key.replace("_", "-"), str(value)))
    return CliRunner().invoke(app, args)


def data(root, **kwargs):
    return asdict(snapshot.report_snapshot(root, **kwargs))


def test_no_window_policy_structure_and_no_temporal_execution(catalog, monkeypatch):
    forbidden = Mock(side_effect=AssertionError("unexpected window call"))
    for name in (
        "incident_window_in_snapshot",
        "incident_candidates_in_snapshot",
        "temporal_candidates_in_snapshot",
        "overlap_in_snapshot",
    ):
        monkeypatch.setattr(snapshot, name, forbidden)
    result = data(catalog.root)
    assert result["analysis_window"] is None
    assert set(result) == {
        "snapshot",
        "consistency",
        "scope",
        "policies",
        "inventory",
        "coverage",
        "current_events",
        "exact_candidates",
        "media",
        "analysis_window",
        "finding_candidates",
        "gap_inputs",
        "provenance_index",
    }
    assert result["snapshot"]["snapshot_id"] == "report.data_snapshot"
    assert result["snapshot"]["snapshot_version"] == "1.0.0"
    assert result["snapshot"]["evidence_schema_version"] == 5
    assert result["snapshot"]["feature_class"] == "DERIVED"
    assert "temporal_proximity" not in result["scope"]["executed_components"]
    policies = result["policies"]
    assert policies["current_event_policy"]["policy_version"] == "1.0.0"
    assert policies["eligible_normalizers"] == [
        {"normalizer_id": "meta.event_normalizer", "normalizer_version": "1.0.0"},
        {"normalizer_id": "google.event_normalizer", "normalizer_version": "1.1.0"},
        {"normalizer_id": "apple.event_normalizer", "normalizer_version": "1.0.0"},
    ]
    for key in ("temporal_proximity", "temporal_exact_overlap"):
        assert policies[key]["policy_version"] == "1.0.0"
        assert "max_delta_seconds" not in policies[key]
    assert policies["perceptual_hash"]["algorithm_version"] == "1.0.0"
    assert policies["exact_correlator"]["correlator_version"] == "1.0.0"
    assert all(r["rule_version"] == "1.0.0" for r in policies["exact_rules"])
    assert all(r["observer_version"] == "1.0.0" for r in policies["observers"])
    assert result["scope"]["underlying_classifications"] == {
        "parsed_records": "OBSERVED",
        "normalized_events": "DERIVED",
    }
    forbidden.assert_not_called()


@pytest.mark.parametrize("window", [False, True])
def test_cli_determinism_ascii_lf_and_zero_write(catalog, window):
    before = tree_state(catalog.root)
    kwargs = WINDOW if window else {}
    first, second = cli(catalog.root, **kwargs), cli(catalog.root, **kwargs)
    assert first.exit_code == second.exit_code == 0, first.output
    assert first.stdout_bytes == second.stdout_bytes
    assert first.stdout_bytes.endswith(b"\n") and b"\r" not in first.stdout_bytes
    first.stdout_bytes.decode("ascii")
    result = json.loads(first.stdout)
    assert first.stdout_bytes == (
        json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("ascii")
    assert tree_state(catalog.root) == before


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start": START},
        {"end": END},
        {"max_delta_seconds": 1},
        {"start": START, "end": END},
        {"start": START, "max_delta_seconds": 1},
        {"end": END, "max_delta_seconds": 1},
        {"platform": "meta"},
        {"event_kind": "content.activity"},
        WINDOW | {"max_delta_seconds": 0},
        WINDOW | {"max_delta_seconds": 86401},
        WINDOW | {"start": "2026-01-01T00:00:00"},
        WINDOW | {"start": "2026-01-01T00:00:00+00:00"},
        WINDOW | {"end": START},
    ],
)
def test_invalid_scope_exits_two_before_reads(case_root, kwargs, monkeypatch):
    opener = Mock(side_effect=AssertionError("invalid input must not open catalog"))
    monkeypatch.setattr(snapshot, "read_catalog", opener)
    assert cli(case_root, **kwargs).exit_code == 2
    opener.assert_not_called()


@pytest.mark.parametrize("filters", [{}, {"platform": "meta"}, {"event_kind": "absent"}])
def test_window_components_equal_public_apis(catalog, filters):
    group(catalog, "device", [0, 1, 2], "device")
    group(catalog, "network", [1, 2, 3], "network")
    args = WINDOW | filters
    result = data(catalog.root, **args)
    window = result["analysis_window"]
    incident_args = {k: v for k, v in args.items() if k != "max_delta_seconds"}
    expected = query_incident_window(catalog.root, **incident_args)
    for item in expected["items"]:
        origin = item.pop("provenance")
        actual = result["provenance_index"]["parsed_records"][item["parsed_record_id"]]
        assert {
            k: v for k, v in origin.items() if k not in {"evidence_relative_path", "member_path"}
        } == {k: v for k, v in actual.items() if k != "classification"}
    assert window["incident_window"] == expected
    assert window["incident_candidates"] == query_incident_candidates(catalog.root, **incident_args)
    assert window["temporal_proximity"] == asdict(temporal_candidates(catalog.root, **args))
    assert window["temporal_exact_overlap"] == asdict(temporal_exact_overlap(catalog.root, **args))
    assert result["exact_candidates"] == {
        "unit": "eligible_persisted_candidates",
        "total": 2,
        "device": 1,
        "network": 1,
        "supports": {"unit": "persisted_support_rows", "total": 6},
        "eligibility": "exact_policy_versions_with_matching_completed_run",
    }


def test_current_counts_separate_from_physical_and_historical_coverage(timeline_case):
    root, expected = timeline_case
    result = data(root)
    current = result["current_events"]
    assert current["total"] == len(expected)
    assert current["undated"] == 2
    assert current["dated"] == len(expected) - 2
    assert sum(g["total"] for g in current["by_platform_event_kind"]) == len(expected)
    assert result["inventory"]["tables"]["normalized_events"] > current["total"]
    assert result["inventory"]["unit"] == "physical_rows"
    groups = result["coverage"]["normalized_events"]["items"]
    assert {g["normalizer_version"] for g in groups if g["platform"] == "google"} == {
        "1.0.0",
        "1.1.0",
        "1.2.0",
    }
    assert result["gap_inputs"]["undated_current_events"]["count"] == 2
    with sqlite3.connect(root / "database/evidence.db") as connection:
        for name, total in result["inventory"]["tables"].items():
            assert total == connection.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]


def test_coverage_failed_unsupported_and_version_dimensions(catalog):
    execute(catalog, "UPDATE parser_runs SET status='FAILED', parser_version='0.0.1'")
    execute(
        catalog,
        "INSERT INTO parser_runs SELECT 'synthetic-unsupported', source_record_id, "
        "parser_id, '0.0.2', 'UNSUPPORTED', 0, '[]', NULL, created_at, NULL "
        "FROM parser_runs LIMIT 1",
    )
    group(catalog, "device", [0, 1], "historical")
    execute(catalog, "UPDATE correlation_candidates SET rule_version='0.0.1'")
    result = data(catalog.root)
    assert result["gap_inputs"]["parser_runs"]["FAILED"] > 0
    assert result["gap_inputs"]["parser_runs"]["UNSUPPORTED"] == 1
    assert {r["parser_version"] for r in result["coverage"]["parser_runs"]["items"]} == {
        "0.0.1",
        "0.0.2",
    }
    assert result["exact_candidates"]["total"] == 0
    assert result["coverage"]["correlation_candidates"]["items"][0]["rule_version"] == "0.0.1"
    assert {r["observer_id"] for r in result["coverage"]["observation_runs"]["items"]} == {
        "device.observer",
        "network.observer",
    }


def test_media_projection_statuses_duplicates_and_provenance(image_case):
    (image_case / "originals/synthetic-broken.jpg").write_bytes(JPEG)
    (image_case / "originals/synthetic-unsupported.gif").write_bytes(b"GIF89a")
    (image_case / "originals/synthetic-unknown.txt").write_bytes(b"synthetic unknown")
    ingest(image_case)
    result = data(image_case)
    inventory, contents, perceptual = (
        inventory_media(image_case),
        media_contents(image_case),
        perceptual_hashes(image_case),
    )
    media = result["media"]
    for name, value in media["inventory"].items():
        if name != "unit":
            assert value == getattr(inventory, name)
    for name in ("exact_content_count", "singleton_content_count", "duplicate_content_count"):
        assert media["contents"][name] == getattr(contents, name)
    for name in ("success_count", "failed_count", "unsupported_count"):
        assert media["perceptual"][name] == getattr(perceptual, name)
        assert media["perceptual"][name] > 0
    duplicate = media["contents"]["duplicates"]["items"][0]
    assert duplicate["occurrence_count"] == 2
    assert any(o["archive_member_id"] for o in duplicate["occurrences"])
    assert all(
        o["evidence_file_id"] in result["provenance_index"]["evidence_files"]
        for o in duplicate["occurrences"]
    )
    findings = result["finding_candidates"]["exact_media_duplicate"]
    assert findings["total"] == findings["returned"] == 1 and not findings["truncated"]
    assert findings["items"][0]["references"]["occurrences"] == duplicate["occurrences"]
    assert result["gap_inputs"]["unrecognized_media"]["count"] > 0
    assert result["gap_inputs"]["perceptual_status_counts"] == {
        "unit": "exact_contents",
        "failed": 1,
        "unsupported": 1,
    }


def test_window_findings_are_projections_without_selection(catalog):
    group(catalog, "device", [0, 1], "shared")
    result = data(catalog.root, **WINDOW)
    findings, window = result["finding_candidates"], result["analysis_window"]
    assert (
        findings["window_exact_candidate"]["items"][0]["references"]["candidate_id"]
        == (window["incident_candidates"]["items"][0]["candidate_id"])
    )
    for component, kind in (
        ("temporal_proximity", "temporal_pair_candidate"),
        ("temporal_exact_overlap", "temporal_exact_overlap_candidate"),
    ):
        assert findings[kind]["returned"] == window[component]["returned_pairs"]
        for finding, pair in zip(findings[kind]["items"], window[component]["items"], strict=True):
            assert finding["classification"] == "DERIVED"
            assert finding["references"]["event_a_id"] == pair["event_a"]["event_id"]
            assert finding["references"]["delta_microseconds"] == pair["delta_microseconds"]
            if "shared_exact_candidates" in pair:
                assert (
                    finding["references"]["shared_exact_candidates"]
                    == pair["shared_exact_candidates"]
                )
    assert not result["gap_inputs"]["media_event_link_available"]
    assert not result["gap_inputs"]["whatsapp_parser_available"]


def test_independent_component_limits_and_complete_provenance(catalog, monkeypatch):
    group(catalog, "device", [0, 1, 2], "one")
    group(catalog, "network", [2, 3, 4], "two")
    monkeypatch.setattr(snapshot, "INCIDENT_LIMIT", 1)
    monkeypatch.setattr(snapshot, "MATRIX_LIMIT", 1)
    monkeypatch.setattr(snapshot, "PAIR_LIMIT", 2)
    result = data(catalog.root, **WINDOW)
    assert result["gap_inputs"]["truncated_components"] == [
        "incident_candidates",
        "incident_window",
        "temporal_exact_overlap",
        "temporal_proximity",
    ]
    assert result["analysis_window"]["incident_window"]["returned"] == 1
    assert result["finding_candidates"]["temporal_pair_candidate"]["returned"] == 2
    assert result["finding_candidates"]["window_exact_candidate"]["truncated"]
    refs = result["provenance_index"]["parsed_records"]
    assert len(refs) > 1  # Beyond the independently limited incident prefix.
    assert list(refs) == sorted(refs)
    with read_catalog(catalog.root) as connection:
        for key, value in refs.items():
            expected = record_origin(connection, key)
            for field in (
                "source_record_id",
                "source_locator",
                "evidence_file_id",
                "evidence_sha256",
            ):
                assert value[field] == expected[field]


def test_single_direct_database_snapshot_and_consistency_metadata(catalog, monkeypatch):
    connections = []
    captured = []

    @contextmanager
    def opener(root):
        with read_catalog(root) as connection:
            assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 1
            assert connection.in_transaction()
            connections.append(connection)
            yield connection

    monkeypatch.setattr(snapshot, "read_catalog", opener)
    # Direct DB composition must never fall back to a public wrapper's own opener.
    for module in (
        "evidence_engine.query.incident",
        "evidence_engine.query.incident_candidates",
        "evidence_engine.correlation.temporal",
        "evidence_engine.correlation.overlap",
    ):
        monkeypatch.setattr(
            module + ".read_catalog", Mock(side_effect=AssertionError("extra opener"))
        )
    for name in ("_coverage", "_current_events", "_exact_summary", "_window"):
        original = getattr(snapshot, name)

        def wrapper(connection, *args, _original=original, **kwargs):
            captured.append(connection)
            return _original(connection, *args, **kwargs)

        monkeypatch.setattr(snapshot, name, wrapper)
    result = data(catalog.root, **WINDOW)
    assert len(connections) == 1
    assert len(captured) == 4 and all(c is connections[0] for c in captured)
    assert result["consistency"] == {
        "database_consistency": "single_read_snapshot",
        "database_scope": "direct_db_components_and_provenance_index",
        "media_consistency": "verified_read_only_components",
        "media_catalogs": "separate_read_snapshots",
        "atomic_database_filesystem": False,
    }


def test_single_snapshot_blocks_writer_commit_until_read_finishes(catalog, monkeypatch):
    db = catalog.root / "database/evidence.db"
    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        kind = connection.execute("SELECT event_kind FROM normalized_events LIMIT 1").fetchone()[0]
    original = snapshot._current_events

    def concurrent_change(connection):
        result = original(connection)
        with sqlite3.connect(db, timeout=0) as writer:
            writer.execute("UPDATE normalized_events SET event_kind='synthetic.concurrent.change'")
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                writer.commit()
            writer.rollback()
        return result

    monkeypatch.setattr(snapshot, "_current_events", concurrent_change)
    result = data(catalog.root, **WINDOW, event_kind=kind)
    assert result["analysis_window"]["incident_window"]["returned"] == len(catalog.events)
    assert all(
        e["event_kind"] == kind for e in result["analysis_window"]["incident_window"]["items"]
    )
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE normalized_events SET event_kind='synthetic.concurrent.change'")
        connection.commit()
        assert (
            connection.execute(
                "SELECT count(*) FROM normalized_events WHERE event_kind=?", (kind,)
            ).fetchone()[0]
            == 0
        )


def test_privacy_explicit_columns_no_payload_or_interpretation(catalog):
    secret = "SYNTHETIC_SECRET_PERSONAL_CONTENT"
    execute(
        catalog,
        "UPDATE normalized_events SET action_raw=?, ip_raw=?, device_model_raw=?",
        (secret, "203.0.113.23", secret),
    )
    execute(
        catalog, "UPDATE parsed_records SET payload_json=?, annotations_json=?", (secret, secret)
    )
    execute(catalog, "UPDATE device_observations SET value_raw=?", (secret,))
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(Engine, "before_cursor_execute", capture)
    try:
        result = cli(catalog.root, **WINDOW)
    finally:
        event.remove(Engine, "before_cursor_execute", capture)
    assert result.exit_code == 0, result.output
    for forbidden in (
        secret,
        str(catalog.root),
        "203.0.113.23",
        "payload_json",
        "annotations_json",
        '"pair_id"',
        '"finding_id"',
        '"score"',
        '"confidence"',
        '"conclusion"',
        '"generated_at"',
        '"key_digest"',
        '"phash_hex"',
        '"base64"',
        '"REPORTED"',
        '"HYPOTHESIS"',
    ):
        assert forbidden not in result.stdout
    for statement in statements:
        if statement.lstrip().startswith("select"):
            assert "payload_json" not in statement and "annotations_json" not in statement


def test_media_integrity_failure_does_not_emit_partial_json(image_case):
    (image_case / "originals/synthetic-image.png").write_bytes(b"changed synthetic original")
    result = cli(image_case)
    assert result.exit_code == 2
    assert result.stdout == ""


def test_media_components_disagreement_is_explicit(image_case, monkeypatch):
    from dataclasses import replace

    result = perceptual_hashes(image_case)
    monkeypatch.setattr(snapshot, "perceptual_hashes", lambda root: replace(result, items=()))
    with pytest.raises(EvidenceError, match="REPORT_MEDIA_COMPONENTS_CHANGED"):
        data(image_case)


def test_schema_v5_is_required(catalog):
    execute(catalog, "PRAGMA user_version=4")
    result = cli(catalog.root)
    assert result.exit_code == 2 and "schema" in result.output


@pytest.mark.parametrize("args", [["report", "--help"], ["report", "snapshot", "--help"]])
def test_cli_helps(args):
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0
    assert "snapshot" in result.stdout


def test_required_case_root():
    assert CliRunner().invoke(app, ["report", "snapshot"]).exit_code == 2
