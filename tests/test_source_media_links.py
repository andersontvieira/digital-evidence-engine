"""Entirely synthetic catalog, source references and media signatures."""

import hashlib
import json
import sqlite3
import warnings
import zipfile
from dataclasses import replace
from unittest.mock import Mock

import pytest
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.ingest.parsing.service import parse_instagram
from evidence_engine.media import source_links as links
from evidence_engine.media.contents import media_contents
from evidence_engine.models.entities import NormalizedEvent, ParsedRecord
from evidence_engine.normalization.service import normalize_events
from evidence_engine.storage.database import open_database
from tests.test_media_inventory import JPEG, ftyp, tree_state
from tests.test_technical_queries import clone

START = "2024-01-01T00:00:00Z"
END = "2024-01-01T00:01:00Z"
BASE = 1704067200


def payload(refs, timestamp=BASE, label="Mídia"):
    return {
        "timestamp": timestamp,
        "media": [],
        "label_values": [{"label": label, "media": [{"uri": r} for r in refs]}],
    }


def source(data=None, **changes):
    return replace(
        links.ParsedMediaSource(
            "synthetic-record",
            "meta.recently_deleted_content",
            "1.1.0",
            "recently_deleted_content",
            "$/0",
            json.dumps(payload(["media/a.jpg"]) if data is None else data),
        ),
        **changes,
    )


@pytest.fixture
def link_case(tmp_path):
    root = tmp_path / "synthetic-case"
    (root / "originals").mkdir(parents=True)
    records = [
        payload(refs, BASE + i)
        for i, refs in enumerate(
            [
                ["media/a.jpg"],
                ["media/b.jpg"],
                ["media/video.mp4"],
                [],
                ["media/missing.jpg"],
                ["media/a.jpg", "media/b.jpg"],
            ]
        )
    ]
    with zipfile.ZipFile(root / "originals/synthetic-export.zip", "w") as z:
        z.writestr("recently_deleted_content.json", json.dumps(records))
        z.writestr("media/a.jpg", JPEG)
        z.writestr("media/copy.jpg", JPEG)
        z.writestr("media/b.jpg", JPEG + b"-SECOND-SYNTHETIC")
        z.writestr("media/video.mp4", ftyp(b"mp42"))
        z.writestr(
            "messages/inbox/synthetic-thread/message_1.json",
            json.dumps(
                {
                    "participants": [{"name": "Synthetic participant"}],
                    "messages": [
                        {
                            "timestamp_ms": (BASE + 6) * 1000,
                            "content": "Synthetic attachment marker",
                            "photos": [{"uri": "media/a.jpg"}],
                        }
                    ],
                }
            ),
        )
    with zipfile.ZipFile(root / "originals/synthetic-other.zip", "w") as z:
        z.writestr("media/missing.jpg", JPEG)
    ingest(root)
    parse_instagram(root)
    normalize_events(root)
    return root


def query(root, **kwargs):
    return links.query_source_links(root, **({"start": START, "end": END} | kwargs))


def edit_record(root, **changes):
    engine = open_database(root / "database/evidence.db")
    with Session(engine) as s:
        r = s.scalars(
            select(ParsedRecord).where(
                ParsedRecord.record_type == "recently_deleted_content",
                ParsedRecord.source_locator == "$/0",
            )
        ).one()
        for k, v in changes.items():
            setattr(r, k, v)
        s.commit()
    engine.dispose()


def rewrite_zip(root, entries):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(root / "originals/synthetic-export.zip", "w") as z:
            for name, data in entries:
                z.writestr(name, data)


def test_end_to_end_statuses_provenance_and_existing_contents(link_case):
    result = query(link_case)
    assert result["summary"] == {
        "unit": "event_source_reference_items",
        "eligible_events": 7,
        "source_references": 6,
        "undated_current_events": 0,
        "matched_total": 8,
        "returned": 8,
        "truncated": False,
        "status_counts_scope": "all_matched_items",
        "status_counts": {
            "LINK_EXACT_MEDIA_CONTENT": 4,
            "LINK_ARCHIVE_MEMBER_ONLY": 1,
            "NO_SOURCE_MEDIA_REFERENCE": 1,
            "NO_CATALOG_MEMBER_MATCH": 1,
            "UNSUPPORTED_SOURCE_REFERENCE_TYPE": 1,
        },
    }
    existing = {c.content_sha256: c for c in media_contents(link_case).contents}
    for item in result["items"]:
        assert item["provenance"]["parsed_record_id"] == item["event"]["parsed_record_id"]
        assert item["resolution"]["classification"] == "DERIVED"
        ref = item["source_reference"]
        if ref:
            assert ref["classification"] == "OBSERVED"
            assert ref["source_field_locator"].endswith("/uri")
        exact = item["resolution"].get("exact_media_content")
        if exact:
            assert exact["occurrence_count"] == existing[exact["content_sha256"]].occurrence_count
    a, b, video = [i["resolution"] for i in result["items"][:3]]
    assert a["exact_media_content"]["content_sha256"] == hashlib.sha256(JPEG).hexdigest()
    assert (
        b["exact_media_content"]["content_sha256"]
        == hashlib.sha256(JPEG + b"-SECOND-SYNTHETIC").hexdigest()
    )
    assert a["exact_media_content"]["occurrence_count"] == 3
    assert video["status"] == "LINK_ARCHIVE_MEMBER_ONLY" and video["bytes_verified"]
    assert video["exact_media_content"] is None


@pytest.mark.parametrize("label", ["Mídia", "M\u00c3\u00addia"])
def test_exact_labels_and_multiple_refs(label):
    refs = links.extract_meta_references(
        source(payload(["media/b.jpg", "media/a.jpg"], label=label))
    )
    assert [r.reference_value for r in refs] == ["media/b.jpg", "media/a.jpg"]
    assert [r.source_field_locator for r in refs] == [
        "$/0/label_values/0/media/0/uri",
        "$/0/label_values/0/media/1/uri",
    ]


@pytest.mark.parametrize(
    "changes",
    [
        {"parser_id": "meta.instagram_messages"},
        {"parser_version": "1.0.0"},
        {"parser_version": "1.2.0"},
        {"record_type": "instagram_message"},
    ],
)
def test_explicit_contract_allowlist(changes):
    assert links.extract_meta_references(source(**changes)) is None


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"uri": "media/a.jpg"},
        {"media": [{"uri": "media/a.jpg"}]},
        payload([], label="Mídia"),
        payload(["media/a.jpg"], label="mídia"),
        {"label_values": [{"label": "unknown", "dict": [{"uri": "media/a.jpg"}]}]},
        payload([None, ""]),
    ],
)
def test_no_recursive_discovery_or_fallback(data):
    assert links.extract_meta_references(source(data)) == ()


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"label_values": {}},
        {"label_values": [{"label": "Mídia", "media": {}}]},
        {"label_values": [{"label": "Mídia", "media": [False]}]},
        payload([False]),
        payload([12]),
    ],
)
def test_malformed_contracted_data_is_global_error(data):
    with pytest.raises(EvidenceError, match="INVALID_SOURCE_MEDIA"):
        links.extract_meta_references(source(data))


def test_duplicate_json_keys_rejected():
    with pytest.raises(EvidenceError, match="INVALID_SOURCE_MEDIA_PAYLOAD"):
        links.extract_meta_references(source(payload_json='{"label_values":[],"label_values":[]}'))


@pytest.mark.parametrize(
    "reference",
    [
        "a.jpg",
        "a",
        "prefix/media/a.jpg",
        "MEDIA/a.jpg",
        "media/A.jpg",
        "media\\a.jpg",
        "media/%61.jpg",
        "./media/a.jpg",
        "media//a.jpg",
        "../media/a.jpg",
        "/media/a.jpg",
        "C:/media/a.jpg",
        "media/a.jpg\x00ignored",
        "media/a.jpg ",
        "media/missing.jpg",
    ],
)
def test_literal_only_matching_and_untrusted_reference_never_opened(link_case, reference):
    edit_record(link_case, payload_json=json.dumps(payload([reference])))
    first = query(link_case)["items"][0]
    assert first["source_reference"]["reference_value"] == reference
    assert first["resolution"] == {"classification": "DERIVED", "status": "NO_CATALOG_MEMBER_MATCH"}


def test_adapter_uses_persisted_representation_not_original_semantic_json(link_case):
    # Original still says media/a.jpg. The approved persisted projection now says b.
    edit_record(link_case, payload_json=json.dumps(payload(["media/b.jpg"])), annotations_json="[]")
    first = query(link_case)["items"][0]
    assert first["resolution"]["member_path"] == "media/b.jpg"


def test_defensive_multiple_catalog_members():
    connection = Mock()
    connection.execute.return_value.mappings.return_value.all.return_value = [{}, {}]
    with pytest.raises(EvidenceError, match="SOURCE_MEDIA_CATALOG_MEMBER_CARDINALITY"):
        links.resolve_member(connection, "synthetic-container", "media/a.jpg")


@pytest.mark.parametrize(
    "entries,code",
    [
        ([("other.jpg", JPEG)], "SOURCE_MEDIA_ZIP_MEMBER_CARDINALITY"),
        ([("media/a.jpg", JPEG), ("media/a.jpg", JPEG)], "SOURCE_MEDIA_ZIP_MEMBER_CARDINALITY"),
        ([("media/a.jpg", JPEG + b"size-change")], "CATALOG_MEMBER_INTEGRITY_MISMATCH"),
        ([("media/a.jpg", b"X" * len(JPEG))], "CATALOG_MEMBER_INTEGRITY_MISMATCH"),
    ],
)
def test_zip_integrity_failures_no_partial_success(link_case, entries, code):
    rewrite_zip(link_case, entries)
    with pytest.raises(EvidenceError, match=code):
        query(link_case, limit=1)
    result = CliRunner().invoke(
        app,
        ["media", "source-links", "--case-root", str(link_case), "--start", START, "--end", END],
    )
    assert result.exit_code == 2 and result.stdout == ""
    assert code in result.stderr and str(link_case) not in result.stderr


def test_failure_after_prefix_is_global(link_case):
    with zipfile.ZipFile(link_case / "originals/synthetic-export.zip") as z:
        entries = [(i.filename, z.read(i)) for i in z.infolist() if i.filename != "media/video.mp4"]
    rewrite_zip(link_case, entries)
    with pytest.raises(EvidenceError):
        query(link_case, limit=1)


def test_content_algorithm_reused_once(link_case, monkeypatch):
    original = links.project_contents
    called = Mock(wraps=original)
    monkeypatch.setattr(links, "project_contents", called)
    query(link_case)
    assert called.call_count == 1


def test_snapshot_consistency_and_no_writes(link_case):
    before = tree_state(link_case)
    database = (link_case / "database/evidence.db").read_bytes()
    connections = set()
    statements = []

    def watch(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
        if statement.startswith(
            (
                "SELECT normalized_events.",
                "SELECT parsed_records.",
                "SELECT archive_members.",
                "SELECT evidence_files.",
            )
        ):
            connections.add(id(conn))

    event.listen(Engine, "before_cursor_execute", watch)
    try:
        result = query(link_case)
    finally:
        event.remove(Engine, "before_cursor_execute", watch)
    assert len(connections) == 1
    assert "BEGIN" in statements
    assert not any(
        s.lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE ", "CREATE ", "DROP "))
        for s in statements
    )
    assert result["consistency"]["atomic_database_filesystem"] is False
    assert tree_state(link_case) == before
    assert (link_case / "database/evidence.db").read_bytes() == database


@pytest.mark.parametrize("limit", [1, 2, 5, 8, 20])
def test_order_determinism_and_limit_prefix(link_case, limit):
    all_items = query(link_case)
    result = query(link_case, limit=limit)
    assert result["items"] == all_items["items"][:limit]
    assert result["summary"]["matched_total"] == 8
    assert result["summary"]["returned"] == min(limit, 8)
    assert result["summary"]["truncated"] == (limit < 8)
    assert result == query(link_case, limit=limit)
    keys = [
        (
            i["event"]["occurred_at_utc"],
            i["event"]["platform"],
            i["event"]["event_kind"],
            i["event"]["event_id"],
            (i["source_reference"] or {}).get("source_field_locator", ""),
            (i["source_reference"] or {}).get("reference_value", ""),
        )
        for i in result["items"]
    ]
    assert keys == sorted(keys)


@pytest.mark.parametrize(
    "filters,count",
    [
        ({"platform": "meta"}, 8),
        ({"platform": "META"}, 0),
        ({"platform": "google"}, 0),
        ({"event_kind": "content.activity"}, 7),
        ({"event_kind": "communication.message"}, 1),
        ({"event_kind": "CONTENT.ACTIVITY"}, 0),
        ({"start": "2024-01-01T00:00:01Z", "end": "2024-01-01T00:00:02Z"}, 1),
    ],
)
def test_filters_and_half_open_bounds(link_case, filters, count):
    assert query(link_case, **filters)["summary"]["matched_total"] == count


@pytest.mark.parametrize(
    "bounds",
    [
        {"start": None},
        {"end": None},
        {"start": "2024-01-01"},
        {"end": START},
        {"start": END},
        {"end": "2024-01-01T00:01:00+00:00"},
        {"start": "2024-02-30T00:00:00Z"},
    ],
)
def test_invalid_bounds_before_case_access(tmp_path, bounds):
    with pytest.raises(EvidenceError):
        query(tmp_path / "absent", **bounds)


@pytest.mark.parametrize("limit", [0, -1, 5001, True, 1.5])
def test_invalid_limit_before_case_access(tmp_path, limit):
    with pytest.raises(EvidenceError):
        query(tmp_path / "absent", limit=limit)


def test_current_versions_and_undated_count(link_case):
    engine = open_database(link_case / "database/evidence.db")
    with Session(engine) as s:
        row = s.scalars(
            select(NormalizedEvent).where(NormalizedEvent.event_kind == "content.activity")
        ).first()
        clone(s, row, normalizer_version="0.9.0")
        clone(s, row, normalizer_version="9.0.0")
        clone(
            s,
            row,
            event_ordinal=99,
            occurred_at_utc=None,
            time_status="missing",
            time_basis="unknown",
        )
        s.commit()
    engine.dispose()
    result = query(link_case)
    assert result["summary"]["eligible_events"] == 7
    assert result["summary"]["undated_current_events"] == 1
    assert all(i["event"]["normalizer_version"] == "1.0.0" for i in result["items"])


def test_output_shape_and_cli_byte_determinism(link_case):
    args = ["media", "source-links", "--case-root", str(link_case), "--start", START, "--end", END]
    runner = CliRunner()
    a, b = runner.invoke(app, args), runner.invoke(app, args)
    assert a.exit_code == b.exit_code == 0 and a.stdout_bytes == b.stdout_bytes
    assert a.stdout_bytes.endswith(b"\n") and b"\r" not in a.stdout_bytes
    data = json.loads(a.stdout)
    assert set(data) == {"policy", "scope", "consistency", "summary", "items"}
    assert data["policy"]["policy_id"] == "source_media.provenance_link"
    assert data["policy"]["policy_version"] == "1.0.0"
    forbidden = {
        "generated_at",
        "score",
        "confidence",
        "person",
        "owner",
        "author",
        "sender",
        "session",
        "strength",
        "probability",
        "published",
        "uploaded",
        "sent",
        "deleted",
        "authored",
        "owned",
        "payload_json",
        "annotations_json",
    }

    def inspect(obj):
        if isinstance(obj, dict):
            assert not forbidden.intersection(obj)
            for value in obj.values():
                inspect(value)
        elif isinstance(obj, list):
            for value in obj:
                inspect(value)

    inspect(data)
    assert str(link_case) not in a.stdout
    for item in data["items"]:
        assert set(item) == {"event", "source_reference", "provenance", "resolution", "limitations"}
        assert set(item["event"]) == {
            "event_id",
            "parsed_record_id",
            "platform",
            "event_kind",
            "occurred_at_utc",
            "time_status",
            "time_basis",
            "normalizer_id",
            "normalizer_version",
        }
        assert item["limitations"] == list(links.LIMITATIONS)


@pytest.mark.parametrize("bounds", [[], ["--start", START], ["--end", END]])
def test_cli_requires_both_bounds(tmp_path, bounds):
    assert (
        CliRunner()
        .invoke(app, ["media", "source-links", "--case-root", str(tmp_path), *bounds])
        .exit_code
        == 2
    )


def test_help_and_missing_case(tmp_path):
    result = CliRunner().invoke(app, ["media", "source-links", "--help"])
    assert result.exit_code == 0
    for word in ("start", "end", "platform", "event-kind", "limit", "case-root"):
        assert word in result.stdout
    assert (
        CliRunner()
        .invoke(
            app,
            [
                "media",
                "source-links",
                "--case-root",
                str(tmp_path / "absent"),
                "--start",
                START,
                "--end",
                END,
            ],
        )
        .exit_code
        == 2
    )


def test_unsupported_message_reference_is_never_linked(link_case):
    item = query(link_case, event_kind="communication.message")["items"][0]
    assert item["source_reference"] is None
    assert item["resolution"]["status"] == "UNSUPPORTED_SOURCE_REFERENCE_TYPE"


def test_schema_older_version_rejected(link_case):
    with sqlite3.connect(link_case / "database/evidence.db") as c:
        c.execute("PRAGMA user_version=4")
    with pytest.raises(EvidenceError, match="schema"):
        query(link_case)


@pytest.mark.parametrize(
    "name", ["../a.jpg", "/a.jpg", "C:/a.jpg", "media\\a.jpg", "media/./a.jpg", "media/a.jpg\x00x"]
)
def test_even_cataloged_unsafe_member_is_rejected_before_open(tmp_path, name):
    member = links.CatalogMember("synthetic-member", "synthetic-container", name, 1, "0" * 64)
    parent = links.CatalogContainer("synthetic-container", "synthetic.zip", 1, "0" * 64, True)
    with pytest.raises(EvidenceError, match="UNSAFE_CATALOG_MEDIA_MEMBER_PATH"):
        links.verify_member(tmp_path / "does-not-exist", parent, member)


def test_changed_original_container_even_if_member_bytes_same(link_case):
    with zipfile.ZipFile(link_case / "originals/synthetic-export.zip", "a") as z:
        z.comment = b"synthetic change to container"
    with pytest.raises(EvidenceError, match="SOURCE_MEDIA_CONTAINER_INTEGRITY_MISMATCH"):
        query(link_case)


def test_catalog_member_hash_and_size_corruption(link_case):
    with sqlite3.connect(link_case / "database/evidence.db") as c:
        c.execute(
            "UPDATE archive_members SET sha256=? WHERE member_path=?", ("0" * 64, "media/a.jpg")
        )
    with pytest.raises(EvidenceError, match="CATALOG_MEMBER_INTEGRITY_MISMATCH"):
        query(link_case)


def test_wrong_content_projection_is_global_failure(link_case, monkeypatch):
    real = links.project_contents

    def changed(items):
        result = real(items)
        return replace(
            result, contents=tuple(replace(c, size_bytes=c.size_bytes + 1) for c in result.contents)
        )

    monkeypatch.setattr(links, "project_contents", changed)
    with pytest.raises(EvidenceError, match="SOURCE_MEDIA_CONTENT_INTEGRITY_MISMATCH"):
        query(link_case)


def test_unknown_query_never_runs_media_scan(link_case, monkeypatch):
    def denied(*args):
        raise AssertionError("unnecessary filesystem scan")

    monkeypatch.setattr(links, "inventory_in_snapshot", denied)
    result = query(link_case, event_kind="communication.message")
    assert result["consistency"]["exact_media_contents_consulted"] is False


def test_order_ties_and_duplicate_reference_occurrences(link_case):
    edit_record(link_case, payload_json=json.dumps(payload(["media/a.jpg"] * 12)))
    with sqlite3.connect(link_case / "database/evidence.db") as c:
        c.execute(
            "UPDATE normalized_events SET occurred_at_utc=?", ("2024-01-01T00:00:00.000000Z",)
        )
    result = query(link_case)
    keys = [
        (
            r["event"]["occurred_at_utc"],
            r["event"]["platform"],
            r["event"]["event_kind"],
            r["event"]["event_id"],
            (r["source_reference"] or {}).get("source_field_locator", ""),
            (r["source_reference"] or {}).get("reference_value", ""),
        )
        for r in result["items"]
    ]
    assert keys == sorted(keys)
    repeated = [
        r
        for r in result["items"]
        if (r["source_reference"] or {}).get("source_field_locator", "").startswith("$/0/")
    ]
    assert len(repeated) == 12
    assert len({r["source_reference"]["source_field_locator"] for r in repeated}) == 12


def test_no_unicode_normalization(link_case):
    edit_record(link_case, payload_json=json.dumps(payload(["media/\uff41.jpg"])))
    assert query(link_case)["items"][0]["resolution"]["status"] == "NO_CATALOG_MEMBER_MATCH"


def test_missing_original_does_not_fallback_to_working(link_case):
    (link_case / "originals/synthetic-export.zip").unlink()
    with pytest.raises(EvidenceError, match="MISSING_SOURCE_MEDIA_CONTAINER"):
        query(link_case)


def test_missing_working_keeps_existing_media_integrity_contract(link_case):
    with sqlite3.connect(link_case / "database/evidence.db") as c:
        stored = c.execute(
            "SELECT working_relative_path FROM archive_members WHERE member_path=?",
            ("media/a.jpg",),
        ).fetchone()[0]
    (link_case / "working" / stored).unlink()
    with pytest.raises(EvidenceError):
        query(link_case)


def test_missing_case_does_not_create_database(tmp_path):
    root = tmp_path / "synthetic-empty"
    (root / "originals").mkdir(parents=True)
    with pytest.raises(EvidenceError):
        query(root)
    assert not (root / "database").exists()


@pytest.mark.parametrize("name", ["logical:name.jpg", "media/logical:name.jpg"])
def test_foundation_safe_colon_links_without_physical_colon(tmp_path, name):
    root = tmp_path / "synthetic-colon-case"
    (root / "originals").mkdir(parents=True)
    with zipfile.ZipFile(root / "originals/synthetic-colon.zip", "w") as z:
        z.writestr("recently_deleted_content.json", json.dumps([payload([name])]))
        z.writestr(name, JPEG)
    ingest(root)
    parse_instagram(root)
    normalize_events(root)
    before = tree_state(root)
    item = query(root)["items"][0]
    assert item["resolution"]["status"] == "LINK_EXACT_MEDIA_CONTENT"
    assert item["resolution"]["member_path"] == item["source_reference"]["reference_value"] == name
    assert tree_state(root) == before
    with sqlite3.connect(root / "database/evidence.db") as c:
        stored = c.execute(
            "SELECT working_relative_path FROM archive_members WHERE member_path=?", (name,)
        ).fetchone()[0]
    assert ":" not in stored
    assert (root / "working" / stored).read_bytes() == JPEG


@pytest.mark.parametrize(
    "name",
    [
        "C:/media/a.jpg",
        "C:\\media\\a.jpg",
        "/media/a.jpg",
        "../media/a.jpg",
        "media\\a.jpg",
        "media/./a.jpg",
        "media/a.jpg\x00suffix",
        "media/CON.jpg",
        "media/noncanonical-e\u0301.jpg",
        "media/control\x1fname.jpg",
        "media/a.jpg.",
        "media/a?.jpg",
        "media/",
    ],
)
def test_logical_name_obeys_canonical_foundation_restrictions(tmp_path, name):
    parent = links.CatalogContainer("synthetic-container", "synthetic.zip", 1, "0" * 64, True)
    member = links.CatalogMember("synthetic-member", parent.id, name, 1, "0" * 64)
    with pytest.raises(EvidenceError, match="UNSAFE_CATALOG_MEDIA_MEMBER_PATH"):
        links.verify_member(tmp_path / "absent", parent, member)


def test_physical_materialized_path_still_rejects_colon(tmp_path):
    from evidence_engine.media.inventory import materialized_path

    with pytest.raises(EvidenceError, match="UNSAFE_CATALOG_MEDIA_PATH"):
        materialized_path(tmp_path, "logical:name.jpg")
