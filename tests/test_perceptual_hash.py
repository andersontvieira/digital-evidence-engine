import hashlib
import json
import re
import zipfile
from dataclasses import asdict, replace
from importlib.metadata import version
from io import BytesIO
from unittest.mock import Mock

import pytest
from PIL import Image, ImageFile, ImageOps
from typer._click.utils import strip_ansi
from typer.testing import CliRunner

from evidence_engine.cli import app
from evidence_engine.errors import EvidenceError
from evidence_engine.ingest.generic.service import ingest
from evidence_engine.media.contents import media_contents
from evidence_engine.media.perceptual import (
    PerceptualPolicy,
    decode_hash,
    normalize_rgb,
    perceptual_hashes,
)
from tests.perceptual_samples import encoded, pattern, samples
from tests.test_media_inventory import tree_state


@pytest.fixture
def image_case(case_root):
    png = encoded(pattern())
    (case_root / "originals/synthetic-image.png").write_bytes(png)
    (case_root / "originals/synthetic-image.jpg").write_bytes(encoded(pattern(), "JPEG"))
    container = BytesIO()
    with zipfile.ZipFile(container, "w") as archive:
        archive.writestr("synthetic-copy.bin", png)
    (case_root / "originals/synthetic-export.zip").write_bytes(container.getvalue())
    ingest(case_root)
    return case_root


def cli(root):
    return CliRunner().invoke(app, ["media", "perceptual-hash", "--case-root", str(root)])


@pytest.mark.parametrize("name", list(samples()))
def test_synthetic_transformations_are_valid_and_deterministic(name):
    data, fmt = samples()[name]
    a = decode_hash(BytesIO(data), fmt)
    assert a == decode_hash(BytesIO(data), fmt)
    assert a.status == "SUCCESS" and a.error_code is None
    assert re.fullmatch("[0-9a-f]{16}", a.phash_hex)
    assert a.width > 0 and a.height > 0


def test_policy_versions_and_explicit_parameters(monkeypatch):
    import evidence_engine.media.perceptual as module

    policy = asdict(PerceptualPolicy())
    assert policy["algorithm_id"] == "image.phash" and policy["algorithm_version"] == "1.0.0"
    assert (policy["hash_size"], policy["highfreq_factor"], policy["hash_bits"]) == (8, 4, 64)
    assert policy["supported_formats"] == ("jpeg", "png")
    assert policy["alpha_background_rgb"] == (255, 255, 255)
    assert policy["exif_orientation"] and policy["icc_transform"] == "none"
    for key, package in [
        ("pillow", "Pillow"),
        ("imagehash", "ImageHash"),
        ("numpy", "numpy"),
        ("scipy", "scipy"),
    ]:
        assert policy[key + "_version"] == version(package)
    mocked = Mock(return_value="0000000000000001")
    monkeypatch.setattr(module.imagehash, "phash", mocked)
    result = decode_hash(BytesIO(encoded(pattern())), "png")
    assert result.phash_hex == "0000000000000001"
    assert mocked.call_args.kwargs == {"hash_size": 8, "highfreq_factor": 4}


@pytest.mark.parametrize("digest", ["ABCDEF0123456789", "123", "0" * 17, "z" * 16])
def test_invalid_hash_serialization_is_global_error(monkeypatch, digest):
    import evidence_engine.media.perceptual as module

    monkeypatch.setattr(module.imagehash, "phash", Mock(return_value=digest))
    with pytest.raises(EvidenceError, match="INVALID_PHASH_REPRESENTATION"):
        decode_hash(BytesIO(encoded(pattern())), "png")


@pytest.mark.parametrize("orientation", range(1, 9))
def test_exif_orientation_matches_physical_pixels(orientation):
    exif = Image.Exif()
    exif[274] = orientation
    jpeg = encoded(pattern(), "JPEG", exif=exif)
    result = decode_hash(BytesIO(jpeg), "jpeg")
    with Image.open(BytesIO(jpeg)) as image:
        image.load()
        with ImageOps.exif_transpose(image) as oriented:
            physical = decode_hash(BytesIO(encoded(oriented)), "png")
            assert (result.width, result.height) == oriented.size
    assert result.phash_hex == physical.phash_hex


@pytest.mark.parametrize("orientation", [0, 9])
def test_invalid_orientation(orientation):
    exif = Image.Exif()
    exif[274] = orientation
    result = decode_hash(BytesIO(encoded(pattern(), "JPEG", exif=exif)), "jpeg")
    assert result.status == "FAILED" and result.error_code == "INVALID_EXIF_ORIENTATION"
    assert result.phash_hex is None


@pytest.mark.parametrize("name", ["rgba", "palette", "la"])
def test_alpha_matches_explicit_white_composite(name):
    data, _ = samples()[name]
    with Image.open(BytesIO(data)) as source:
        rgba = source.convert("RGBA")
        white = Image.new("RGBA", rgba.size, "white")
        equivalent = Image.alpha_composite(white, rgba).convert("RGB")
        normalized = normalize_rgb(source)
        assert normalized.mode == "RGB" and normalized.tobytes() == equivalent.tobytes()
        assert (
            decode_hash(BytesIO(data), "png").phash_hex
            == decode_hash(BytesIO(encoded(equivalent)), "png").phash_hex
        )


def test_rgb_unchanged_and_no_metadata_in_output(image_case):
    image = pattern()
    image.info["icc_profile"] = b"SYNTHETIC-ICC"
    assert normalize_rgb(image).tobytes() == image.tobytes()
    exif = Image.Exif()
    exif[315] = "SYNTHETIC-PRIVATE-AUTHOR"
    payload = encoded(image, exif=exif, icc_profile=b"SYNTHETIC-ICC")
    assert (
        decode_hash(BytesIO(payload), "png").phash_hex
        == decode_hash(BytesIO(encoded(pattern())), "png").phash_hex
    )
    result = cli(image_case)
    for forbidden in [
        str(image_case),
        "SYNTHETIC-PRIVATE-AUTHOR",
        "SYNTHETIC-ICC",
        "Traceback",
        "base64",
        "threshold",
        "confidence",
        "score",
        "cluster",
    ]:
        assert forbidden not in result.output


@pytest.mark.parametrize(
    "data,fmt",
    [
        (b"\xff\xd8\xffbroken", "jpeg"),
        (b"\x89PNG\r\n\x1a\nbroken", "png"),
        (samples()["jpeg"][0][:-30], "jpeg"),
    ],
)
def test_corrupt_truncated_no_hash(data, fmt):
    assert ImageFile.LOAD_TRUNCATED_IMAGES is False
    result = decode_hash(BytesIO(data), fmt)
    assert result.status == "FAILED" and result.error_code == "DECODE_ERROR"
    assert result.phash_hex is None


def test_apng_rejected():
    first = pattern()
    second = Image.new("RGB", first.size, "red")
    payload = encoded(first, save_all=True, append_images=[second], duration=100, loop=0)
    result = decode_hash(BytesIO(payload), "png")
    assert result.status == "UNSUPPORTED" and result.error_code == "ANIMATED_IMAGE_UNSUPPORTED"
    assert result.phash_hex is None


@pytest.mark.parametrize("limit", [1500, 1000])
def test_bomb_warning_and_error_fail_without_hash(monkeypatch, limit):
    payload = encoded(pattern())
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", limit)
    result = decode_hash(BytesIO(payload), "png")
    assert result.error_code == "DECOMPRESSION_BOMB" and result.status == "FAILED"
    assert result.phash_hex is None and Image.MAX_IMAGE_PIXELS == limit


def test_decoder_format_mismatch():
    result = decode_hash(BytesIO(encoded(pattern())), "jpeg")
    assert result.error_code == "FORMAT_MISMATCH" and result.status == "FAILED"


def test_unsupported_without_decode(monkeypatch):
    mocked = Mock(side_effect=AssertionError("must not decode"))
    monkeypatch.setattr(Image, "open", mocked)
    assert decode_hash(BytesIO(b"unused"), "gif").error_code == "UNSUPPORTED_FORMAT"
    mocked.assert_not_called()


def test_once_per_representative_and_round_trip(image_case, monkeypatch):
    import evidence_engine.media.perceptual as module

    baseline = media_contents(image_case)
    opened = []
    real_decode = module.decode_hash

    def tracked(stream, fmt):
        stream.seek(0)
        opened.append(hashlib.sha256(stream.read()).hexdigest())
        stream.seek(0)
        return real_decode(stream, fmt)

    monkeypatch.setattr(module, "decode_hash", tracked)
    result = perceptual_hashes(image_case)
    assert len(opened) == len(set(opened)) == result.exact_content_count == 2
    assert result.projected_occurrences == 3 and result.success_count == 2
    for expected, actual in zip(baseline.contents, result.items, strict=True):
        assert actual.representative == expected.representative
        assert actual.occurrences == expected.occurrences
        assert actual.feature_class == "DERIVED"


def test_cli_determinism_and_zero_write(image_case):
    before = tree_state(image_case)
    a, b = cli(image_case), cli(image_case)
    assert a.exit_code == b.exit_code == 0 and a.stdout_bytes == b.stdout_bytes
    assert json.loads(a.stdout)["projected_occurrences"] == 3
    assert tree_state(image_case) == before


def test_local_failures_emit_full_json_exit_one(case_root):
    (case_root / "originals/synthetic-broken.jpg").write_bytes(b"\xff\xd8\xffbroken")
    (case_root / "originals/synthetic.gif").write_bytes(encoded(pattern(), "GIF"))
    (case_root / "originals/synthetic-valid.png").write_bytes(encoded(pattern()))
    ingest(case_root)
    result = cli(case_root)
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["success_count"] == data["failed_count"] == data["unsupported_count"] == 1
    assert len(data["items"]) == data["projected_occurrences"] == 3


@pytest.mark.parametrize("mutation", ["bytes", "missing", "during_decode", "during_failed_decode"])
def test_revalidation_failure_global_no_fallback(image_case, monkeypatch, mutation):
    import evidence_engine.media.perceptual as module

    baseline = media_contents(image_case)
    member = next(c for c in baseline.contents if c.representative.archive_member_id)
    from evidence_engine.ingest.generic.paths import CasePaths
    from evidence_engine.query.catalog import read_catalog

    with read_catalog(image_case) as connection:
        path = module.representative_path(connection, CasePaths.load(image_case), member)
    original_decode = module.decode_hash
    calls = []

    def mutate():
        if mutation == "missing":
            path.unlink()
        else:
            path.write_bytes(b"changed")

    def baseline_then_mutate(root):
        if not mutation.startswith("during"):
            mutate()
        return baseline

    def decode(stream, fmt):
        calls.append(fmt)
        result = original_decode(stream, fmt)
        if mutation.startswith("during") and fmt == member.media_format:
            mutate()
            if mutation == "during_failed_decode":
                return module.DecodedHash("FAILED", error_code="DECODE_ERROR")
        return result

    monkeypatch.setattr(module, "media_contents", baseline_then_mutate)
    monkeypatch.setattr(module, "decode_hash", decode)
    before = (image_case / "database/evidence.db").read_bytes()
    result = cli(image_case)
    assert result.exit_code == 2 and not result.stdout
    assert "Traceback" not in result.output and str(image_case) not in result.output
    assert (image_case / "database/evidence.db").read_bytes() == before
    assert len(calls) <= 2


def test_failed_representative_no_fallback(image_case, monkeypatch):
    import evidence_engine.media.perceptual as module

    mocked = Mock(return_value=module.DecodedHash("FAILED", error_code="DECODE_ERROR"))
    monkeypatch.setattr(module, "decode_hash", mocked)
    result = perceptual_hashes(image_case)
    assert mocked.call_count == result.failed_count == 2
    assert result.projected_occurrences == 3


def test_catalog_mismatch_is_global(image_case, monkeypatch):
    import evidence_engine.media.perceptual as module

    baseline = media_contents(image_case)
    altered = replace(baseline.contents[0], size_bytes=999)
    monkeypatch.setattr(
        module, "media_contents", Mock(return_value=replace(baseline, contents=(altered,)))
    )
    with pytest.raises(EvidenceError, match="CATALOG_BASELINE_CHANGED"):
        perceptual_hashes(image_case)


def test_normalization_failure_local(monkeypatch):
    import evidence_engine.media.perceptual as module

    monkeypatch.setattr(module, "normalize_rgb", Mock(side_effect=ValueError("synthetic")))
    assert decode_hash(BytesIO(encoded(pattern())), "png").error_code == "NORMALIZATION_ERROR"


def test_help():
    result = CliRunner().invoke(app, ["media", "perceptual-hash", "--help"], color=False)
    assert result.exit_code == 0 and "--case-root" in strip_ansi(result.output)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("jpeg", "ab11d1f692ede00d"),
        ("png", "ab11d1f692ede00d"),
        ("rgba", "aaf0817e126ff00f"),
    ],
)
def test_synthetic_goldens_confirmed_windows_linux(name, expected):
    # Artificial samples only; identical values and normalized pixels verified on both OSes.
    data, fmt = samples()[name]
    assert decode_hash(BytesIO(data), fmt).phash_hex == expected


def test_operational_io_error_is_not_local_decode_failure(monkeypatch):
    monkeypatch.setattr(Image, "open", Mock(side_effect=PermissionError(13, "synthetic")))
    with pytest.raises(PermissionError):
        decode_hash(BytesIO(b"unused"), "png")


def test_empty_catalog(image_case, monkeypatch):
    import evidence_engine.media.perceptual as module

    baseline = media_contents(image_case)
    monkeypatch.setattr(module, "media_contents", Mock(return_value=replace(baseline, contents=())))
    result = cli(image_case)
    assert result.exit_code == 0
    assert json.loads(result.stdout)["items"] == []
