import hashlib
import json
import sqlite3
import zipfile

import pytest
from sqlalchemy import Engine, event
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.media.inventory import inventory_media
from evidence_engine.media.signatures import PREFIX_LIMIT, identify
from tests.test_correlation_schema import v4_catalog
from tests.test_technical_queries import read_rows
from tests.test_timeline import database_bytes

JPEG = b"\xff\xd8\xff" + b"SYNTHETIC-IMAGE"
PNG = b"\x89PNG\r\n\x1a\n" + b"SYNTHETIC-PNG"
WEBP = b"RIFF" + (4).to_bytes(4, "little") + b"WEBP"


def ftyp(major, compatible=(), extended=False):
    payload = major + b"\0" * 4 + b"".join(compatible)
    if extended:
        return (1).to_bytes(4, "big") + b"ftyp" + (16 + len(payload)).to_bytes(8, "big") + payload
    return (8 + len(payload)).to_bytes(4, "big") + b"ftyp" + payload


@pytest.mark.parametrize(
    "data,kind,fmt",
    [
        (JPEG, "image", "jpeg"),
        (PNG, "image", "png"),
        (b"GIF87a", "image", "gif"),
        (b"GIF89a", "image", "gif"),
        (WEBP, "image", "webp"),
        (ftyp(b"heic"), "image", "heic"),
        (ftyp(b"heix"), "image", "heic"),
        (ftyp(b"hevc"), "image", "heic"),
        (ftyp(b"hevx"), "image", "heic"),
        (ftyp(b"avif"), "image", "avif"),
        (ftyp(b"avis"), "image", "avif"),
        (ftyp(b"mif1"), "image", "heif"),
        (ftyp(b"msf1"), "image", "heif"),
        (ftyp(b"mif1", (b"heic",)), "image", "heic"),
        (ftyp(b"mif1", (b"avif",)), "image", "avif"),
        (ftyp(b"avif", extended=True), "image", "avif"),
        ((8).to_bytes(4, "big") + b"free" + ftyp(b"heic"), "image", "heic"),
        (ftyp(b"isom"), None, "iso-bmff"),
        (ftyp(b"mp42"), None, "iso-bmff"),
        (ftyp(b"qt  "), None, "iso-bmff"),
        (ftyp(b"M4A "), None, "iso-bmff"),
        (ftyp(b"????"), None, "iso-bmff"),
        (ftyp(b"heic", (b"avif",)), None, "iso-bmff"),
        (ftyp(b"mp42", (b"avif",)), None, "iso-bmff"),
    ],
)
def test_restricted_signatures(data, kind, fmt):
    result = identify(data)
    assert (result.media_kind, result.media_format) == (kind, fmt)


@pytest.mark.parametrize(
    "signature",
    [
        b"\xff\xd8\xff",
        b"\x89PNG\r\n\x1a\n",
        b"GIF87a",
        WEBP,
        ftyp(b"avif"),
        ftyp(b"heic", extended=True),
    ],
)
def test_every_truncated_signature_is_unknown(signature):
    for length in range(len(signature)):
        assert identify(signature[:length]).media_kind is None


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not media",
        b"GIF88a",
        b"RIFF" + (4).to_bytes(4, "little") + b"WAVE",
        b"RIFF" + (3).to_bytes(4, "little") + b"WEBP",
        b"\0\0\0\0ftypavif\0\0\0\0",
        b"\0\0\0\x0fftypavif\0\0\0",
        (17).to_bytes(4, "big") + b"ftypavif" + b"\0" * 5,
        (PREFIX_LIMIT + 4).to_bytes(4, "big") + b"ftypavif" + b"\0" * PREFIX_LIMIT,
        b"junk" + ftyp(b"avif"),
        (8).to_bytes(4, "big") + b"mdat" + ftyp(b"avif"),
    ],
)
def test_malformed_or_unrecognized_prefix(data):
    assert identify(data).media_format == "unknown"


def test_signature_input_is_bounded():
    padding = (PREFIX_LIMIT).to_bytes(4, "big") + b"free" + b"\0" * (PREFIX_LIMIT - 8)
    assert identify(padding + ftyp(b"heic")).media_format == "unknown"
    assert identify(b"\xff\xd8\xff" + b"x" * (PREFIX_LIMIT * 2)).media_format == "jpeg"


def media_cli(root):
    return CliRunner().invoke(app, ["media", "inventory", "--case-root", str(root)])


@pytest.fixture
def media_case(case_root):
    (case_root / "originals/synthetic-image.jpg").write_bytes(JPEG)
    (case_root / "originals/synthetic-mismatch.jpg").write_bytes(PNG)
    (case_root / "originals/synthetic-invalid.jpg").write_bytes(b"not an image")
    for name in ("synthetic-a.zip", "synthetic-b.zip"):
        with zipfile.ZipFile(case_root / "originals" / name, "w") as z:
            z.writestr("synthetic-copy.bin", JPEG)
    ingest(case_root)
    return case_root


def tree_state(root):
    return {
        p.relative_to(root).as_posix(): (
            p.read_bytes(),
            p.stat().st_size,
            p.stat().st_mtime_ns,
            p.stat().st_mode,
        )
        for p in root.rglob("*")
        if p.is_file()
    }


def test_inventory_all_sources_signature_first_duplicates_and_determinism(media_case):
    root = media_case
    before = tree_state(root)
    a = media_cli(root)
    b = media_cli(root)
    assert a.exit_code == b.exit_code == 0, a.output
    assert a.stdout_bytes == b.stdout_bytes
    result = json.loads(a.stdout)
    assert result["scanned_occurrences"] == 7
    assert result["recognized_media"] == result["verified_media"] == 4
    assert result["unrecognized_occurrences"] == 3
    assert result["format_counts"] == {"jpeg": 3, "png": 1} and result["kind_counts"] == {
        "image": 4
    }
    assert result["exact_duplicate_groups"] == 1 and result["exact_duplicate_occurrences"] == 3
    group = result["duplicate_groups"][0]
    assert group["sha256"] == hashlib.sha256(JPEG).hexdigest() and group["occurrence_count"] == 3
    assert len(group["occurrences"]) == 3
    assert {i["source_kind"] for i in group["occurrences"]} == {"evidence_file", "archive_member"}
    assert len({(i["evidence_file_id"], i["archive_member_id"]) for i in group["occurrences"]}) == 3
    png = next(i for i in result["items"] if i["media_format"] == "png")
    assert png["extension_hint"] == ".jpg"
    assert any(
        i["extension_hint"] == ".bin" and i["media_format"] == "jpeg" for i in result["items"]
    )
    assert all("synthetic-invalid.jpg" != i["evidence_relative_path"] for i in result["items"])
    fields = {
        "source_kind",
        "evidence_file_id",
        "archive_member_id",
        "evidence_relative_path",
        "member_path",
        "size_bytes",
        "cataloged_sha256",
        "media_kind",
        "media_format",
        "extension_hint",
    }
    assert all(set(i) == fields for i in result["items"])
    for i in result["items"]:
        table = "archive_members" if i["archive_member_id"] else "evidence_files"
        ident = i["archive_member_id"] or i["evidence_file_id"]
        row = next(r for r in read_rows(root, table) if r["id"] == ident)
        assert i["cataloged_sha256"] == row["sha256"] and i["size_bytes"] == row["size_bytes"]
    assert str(root) not in a.stdout and "working_relative_path" not in a.stdout
    assert tree_state(root) == before


@pytest.mark.parametrize("count", [1, 2, 3])
def test_exact_duplicates_preserve_occurrences(case_root, count):
    for i in range(count):
        (case_root / "originals" / f"synthetic-{i}.bin").write_bytes(JPEG)
    ingest(case_root)
    result = inventory_media(case_root)
    assert len(result.items) == count
    assert result.exact_duplicate_groups == (1 if count >= 2 else 0)
    assert result.exact_duplicate_occurrences == (count if count >= 2 else 0)


def test_different_content_same_filename_and_group_order(case_root):
    for directory, data in [("a", JPEG), ("b", PNG), ("c", JPEG), ("d", PNG), ("e", PNG)]:
        (case_root / "originals" / directory).mkdir()
        (case_root / "originals" / directory / "synthetic-image.jpg").write_bytes(data)
    ingest(case_root)
    result = inventory_media(case_root)
    assert [g.occurrence_count for g in result.duplicate_groups] == [3, 2]
    assert len(result.items) == 5
    for group in result.duplicate_groups:
        assert list(group.occurrences) == sorted(
            group.occurrences,
            key=lambda i: (i.source_kind, i.evidence_relative_path, i.member_path or ""),
        )


@pytest.mark.parametrize("target", ["original", "member"])
@pytest.mark.parametrize("mutation", ["hash", "size", "missing", "signature_removed"])
def test_integrity_failure_no_baseline_rewrite(media_case, target, mutation):
    root = media_case
    if target == "original":
        path = root / "originals/synthetic-image.jpg"
    else:
        path = root / "working" / read_rows(root, "archive_members")[0]["working_relative_path"]
    original = path.read_bytes()
    if mutation == "hash":
        path.write_bytes(original[:-1] + b"!")
    elif mutation == "size":
        path.write_bytes(original + b"extra")
    elif mutation == "signature_removed":
        path.write_bytes(b"X" * len(original))
    else:
        path.unlink()
    before = database_bytes(root)
    result = media_cli(root)
    assert result.exit_code == 2 and not result.stdout
    assert "MISSING" in result.output or "MISMATCH" in result.output
    assert str(path) not in result.output and "Traceback" not in result.output
    assert database_bytes(root) == before
    if mutation == "missing":
        assert not path.exists()


def test_unknown_cataloged_content_is_verified_too(media_case):
    path = media_case / "originals/synthetic-invalid.jpg"
    path.write_bytes(b"changed non-media")
    with pytest.raises(EvidenceError, match="MISMATCH"):
        inventory_media(media_case)


@pytest.mark.parametrize(
    "stored", ["../outside", "/outside", "C:/outside", "a\\b", "a//b", "a:stream", ""]
)
def test_unsafe_materialization_path_rejected(media_case, stored):
    with sqlite3.connect(media_case / "database/evidence.db") as c:
        ident = c.execute("SELECT id FROM archive_members LIMIT 1").fetchone()[0]
        c.execute("UPDATE archive_members SET working_relative_path=? WHERE id=?", (stored, ident))
    before = database_bytes(media_case)
    with pytest.raises(EvidenceError, match="UNSAFE"):
        inventory_media(media_case)
    assert database_bytes(media_case) == before


def test_stream_hash_reused_with_read_stability(media_case, monkeypatch):
    import evidence_engine.media.inventory as module

    real_hash = module.sha256_stream
    calls = []

    # File descriptor streams use integer .name; only the existing hasher is wrapped.
    def tracked(stream):
        calls.append(True)
        return real_hash(stream)

    monkeypatch.setattr(module, "sha256_stream", tracked)
    assert inventory_media(media_case).verified_media == 4 and len(calls) == 7


def test_concurrent_mutation_rejected(media_case, monkeypatch):
    import evidence_engine.media.inventory as module

    real_hash = module.sha256_stream
    target = media_case / "originals/synthetic-image.jpg"

    def changed(stream):
        result = real_hash(stream)
        # Mutate the same opened inode through its pathname in this synthetic adversarial test.
        if result[0] == hashlib.sha256(JPEG).hexdigest() and target.read_bytes() == JPEG:
            target.write_bytes(JPEG + b"mutated")
        return result

    monkeypatch.setattr(module, "sha256_stream", changed)
    before = database_bytes(media_case)
    with pytest.raises(EvidenceError, match="changed during reading|MISMATCH"):
        inventory_media(media_case)
    assert database_bytes(media_case) == before


def test_only_foundation_tables_single_read_snapshot_and_no_writes(media_case):
    before = tree_state(media_case)
    connections = set()

    def inspect(connection, cursor, statement, parameters, context, executemany):
        if statement.lower().startswith("select") and "sqlite_master" not in statement:
            assert not any(
                t in statement
                for t in (
                    "parsed_records",
                    "normalized_events",
                    "device_observations",
                    "network_observations",
                    "correlation_candidates",
                    "source_records",
                )
            )
            assert cursor.connection.execute("PRAGMA query_only").fetchone()[0] == 1
            assert cursor.connection.in_transaction
            connections.add(id(cursor.connection))

    event.listen(Engine, "before_cursor_execute", inspect)
    try:
        inventory_media(media_case)
    finally:
        event.remove(Engine, "before_cursor_execute", inspect)
    assert len(connections) == 1 and tree_state(media_case) == before


def test_uncataloged_external_image_not_included(media_case):
    (media_case / "originals/uncataloged-synthetic.png").write_bytes(PNG)
    result = inventory_media(media_case)
    assert result.scanned_occurrences == 7 and result.recognized_media == 4


def test_empty_catalog(case_root):
    ingest(case_root)
    result = inventory_media(case_root)
    assert result.scanned_occurrences == result.recognized_media == 0
    assert result.items == result.duplicate_groups == ()


@pytest.mark.parametrize("mode", ["missing", "v4", "wal"])
def test_media_catalog_defenses(case_root, mode):
    if mode == "v4":
        v4_catalog(case_root)
    if mode == "wal":
        ingest(case_root)
        with sqlite3.connect(case_root / "database/evidence.db") as c:
            c.execute("PRAGMA journal_mode=WAL")
    before = database_bytes(case_root) if mode != "missing" else set(case_root.rglob("*"))
    result = media_cli(case_root)
    assert result.exit_code == 2
    assert (database_bytes(case_root) if mode != "missing" else set(case_root.rglob("*"))) == before
