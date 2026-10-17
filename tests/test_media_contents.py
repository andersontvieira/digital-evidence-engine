import hashlib
import json
from dataclasses import asdict, replace
from itertools import permutations
from unittest.mock import Mock

import pytest
from typer._click.utils import strip_ansi
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.errors import EvidenceError
from evidence_engine.media.contents import media_contents, project_contents
from evidence_engine.media.inventory import MediaItem, inventory_media
from tests.test_media_inventory import JPEG, PNG, tree_state
from tests.test_media_inventory import media_case as media_case


def item(index=0, data=JPEG, fmt="jpeg", **changes):
    return replace(
        MediaItem(
            "evidence_file",
            f"synthetic-id-{index}",
            None,
            f"synthetic-image-{index}.bin",
            None,
            len(data),
            hashlib.sha256(data).hexdigest(),
            "image",
            fmt,
            ".bin",
        ),
        **changes,
    )


@pytest.mark.parametrize("count", [1, 2, 3])
def test_one_content_preserves_every_occurrence(count):
    result = project_contents(tuple(item(i) for i in range(count)))
    assert result.exact_content_count == 1
    assert result.verified_media_occurrences == count
    assert result.singleton_content_count == (count == 1)
    assert result.duplicate_content_count == (count >= 2)
    assert result.occurrences_in_duplicate_contents == (count if count >= 2 else 0)
    content = result.contents[0]
    assert content.occurrence_count == len(content.occurrences) == count
    assert {o.evidence_file_id for o in content.occurrences} == {
        f"synthetic-id-{i}" for i in range(count)
    }
    assert content.representative == content.occurrences[0]


def test_distinct_hashes_and_counts_by_content():
    result = project_contents((item(0), item(1), item(2, JPEG + b"distinct"), item(3, PNG, "png")))
    assert result.exact_content_count == 3 and result.verified_media_occurrences == 4
    assert result.singleton_content_count == 2 and result.duplicate_content_count == 1
    assert result.occurrences_in_duplicate_contents == 2
    assert result.format_counts_by_content == {"jpeg": 2, "png": 1}
    assert result.kind_counts_by_content == {"image": 3}


def test_representative_and_output_independent_of_input_order():
    members = (
        item(2),
        item(0),
        item(
            1,
            source_kind="archive_member",
            archive_member_id="synthetic-member",
            member_path="synthetic-copy.bin",
        ),
    )
    expected = project_contents(members)
    assert expected.contents[0].representative.archive_member_id == "synthetic-member"
    for order in permutations(members):
        assert project_contents(order) == expected


def test_representative_uses_all_documented_tiebreakers():
    members = (
        item(
            2,
            source_kind="archive_member",
            evidence_relative_path="synthetic-export.zip",
            member_path="b",
            archive_member_id="a",
        ),
        item(
            1,
            source_kind="archive_member",
            evidence_relative_path="synthetic-export.zip",
            member_path="a",
            archive_member_id="b",
        ),
        item(
            1,
            source_kind="archive_member",
            evidence_relative_path="synthetic-export.zip",
            member_path="a",
            archive_member_id="a",
        ),
    )
    occurrences = project_contents(members).contents[0].occurrences
    assert [(o.evidence_file_id, o.archive_member_id) for o in occurrences] == [
        ("synthetic-id-1", "a"),
        ("synthetic-id-1", "b"),
        ("synthetic-id-2", "a"),
    ]


def test_same_content_between_evidence_file_and_archive_member():
    result = project_contents(
        (
            item(),
            item(
                1,
                source_kind="archive_member",
                archive_member_id="synthetic-member",
                member_path="synthetic-copy.bin",
            ),
        )
    )
    assert result.exact_content_count == 1 and result.contents[0].occurrence_count == 2
    assert {o.source_kind for o in result.contents[0].occurrences} == {
        "evidence_file",
        "archive_member",
    }


@pytest.mark.parametrize(
    "changes", [{"media_format": "png"}, {"media_kind": "video"}, {"size_bytes": 999}]
)
def test_inconsistent_metadata_fails(changes):
    with pytest.raises(EvidenceError, match="INCONSISTENT_EXACT_MEDIA_CONTENT"):
        project_contents((item(), item(1, **changes)))


def test_empty_projection():
    result = project_contents(())
    assert result.exact_content_count == result.verified_media_occurrences == 0
    assert result.singleton_content_count == result.duplicate_content_count == 0
    assert result.occurrences_in_duplicate_contents == 0
    assert (
        result.contents == ()
        and result.format_counts_by_content == result.kind_counts_by_content == {}
    )


def test_content_order_is_format_then_hash_not_occurrence_count():
    inputs = (item(0, PNG, "png"), item(1), item(2), item(3, JPEG + b"distinct"))
    result = project_contents(inputs)
    keys = [(c.media_kind, c.media_format, c.content_sha256) for c in result.contents]
    assert keys == sorted(keys)


def test_service_reuses_inventory_once(media_case, monkeypatch):
    import evidence_engine.media.contents as module

    inventory = inventory_media(media_case)
    reused = Mock(return_value=inventory)
    monkeypatch.setattr(module, "inventory_media", reused)
    assert media_contents(media_case) == project_contents(inventory.items)
    reused.assert_called_once_with(media_case)


def test_cli_round_trip_stable_json_and_zero_write(media_case):
    before = tree_state(media_case)
    inventory = inventory_media(media_case)
    args = ["media", "contents", "--case-root", str(media_case)]
    a = CliRunner().invoke(app, args)
    b = CliRunner().invoke(app, args)
    assert a.exit_code == b.exit_code == 0
    assert a.stdout_bytes == b.stdout_bytes
    result = json.loads(a.stdout)
    fields = {
        "source_kind",
        "evidence_file_id",
        "archive_member_id",
        "evidence_relative_path",
        "member_path",
    }
    expected = [{k: v for k, v in asdict(i).items() if k in fields} for i in inventory.items]
    actual = [o for c in result["contents"] for o in c["occurrences"]]
    assert sorted(map(lambda o: json.dumps(o, sort_keys=True), actual)) == sorted(
        map(lambda o: json.dumps(o, sort_keys=True), expected)
    )
    assert all(set(c["representative"]) == fields for c in result["contents"])
    assert result["duplicate_content_count"] == inventory.exact_duplicate_groups
    assert result["occurrences_in_duplicate_contents"] == inventory.exact_duplicate_occurrences
    assert tree_state(media_case) == before


def test_integrity_error_from_inventory_reaches_cli(media_case):
    (media_case / "originals/synthetic-image.jpg").write_bytes(JPEG + b"changed")
    before = tree_state(media_case)
    result = CliRunner().invoke(app, ["media", "contents", "--case-root", str(media_case)])
    assert result.exit_code == 2 and not result.stdout
    assert "MISMATCH" in result.output and str(media_case) not in result.output
    assert tree_state(media_case) == before


def test_contents_help():
    result = CliRunner().invoke(app, ["media", "contents", "--help"], color=False)
    assert result.exit_code == 0 and "--case-root" in strip_ansi(result.output)
