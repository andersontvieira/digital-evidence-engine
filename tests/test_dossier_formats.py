"""Bounded captured formats only, without factual/visual interpretation."""

import struct
import warnings
import zlib
from io import BytesIO

import pytest
from PIL import Image

from evidence_engine.dossier import selection as s
from evidence_engine.dossier import validation as v
from evidence_engine.errors import EvidenceError
from evidence_engine.media.signatures import Signature
from tests.test_dossier_packaging import finish, image_bytes, setup_inputs
from tests.test_dossier_selection import item, minimal


def validate(content, role="structured_support"):
    return v.validate_captured_formats((v.CapturedFormatInput("synthetic", role, content),))


@pytest.mark.parametrize(
    "root", [b"{}", b"[]", b'"opaque"', b"12", b"1.5", b"true", b"false", b"null"]
)
def test_any_json_root(root):
    assert validate(root)[0].image_format is None


@pytest.mark.parametrize(
    "content",
    [
        b'{"x":1,"x":2}',
        b'{"a":{"x":1,"x":2}}',
        b"NaN",
        b"Infinity",
        b"-Infinity",
        b"\xff",
        b"\xef\xbb\xbf{}",
        b"{",
        b"[1,]",
    ],
)
@pytest.mark.parametrize(
    "role,code",
    [("structured_support", "UNSUPPORTED_FORMAT"), ("report_snapshot", "CANONICAL_SET_INVALID")],
)
def test_strict_json_error_mapping(content, role, code):
    with pytest.raises(EvidenceError, match=f"^DOSSIER_{code}$"):
        validate(content, role)


@pytest.mark.parametrize("content", [b"1" * 129, b"1e999", b"[" * 65 + b"0" + b"]" * 65])
def test_json_resource_errors(content):
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        validate(content)


def test_exact_json_lexical_depth_nodes_and_aggregate_limits(monkeypatch):
    assert validate(b"1" * 128)
    assert validate(b"[" * 64 + b"null" + b"]" * 64)
    monkeypatch.setattr(s, "MAX_JSON_NODES_PER_FILE", 3)
    assert validate(b'{"x":null}')
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        validate(b'{"x":[null]}')
    inputs = (
        v.CapturedFormatInput("snapshot", "report_snapshot", b'{"x":null}'),
        v.CapturedFormatInput("support", "structured_support", b'{"x":true}'),
    )
    monkeypatch.setattr(v, "MAX_TOTAL_JSON_NODES", 6)
    assert len(v.validate_captured_formats(inputs)) == 2
    monkeypatch.setattr(v, "MAX_TOTAL_JSON_NODES", 5)
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        v.validate_captured_formats(inputs)


@pytest.mark.parametrize("error", [MemoryError, RecursionError])
def test_decode_exhaustion_sanitized(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error("private synthetic payload")

    monkeypatch.setattr(v.json, "loads", fail)
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        validate(b"{}")


@pytest.mark.parametrize("role", ["technical_review", "validation_report"])
@pytest.mark.parametrize(
    "content", [b"# opaque\r\nhttps://example.invalid\r\n", "sintético\n".encode()]
)
def test_markdown_is_opaque_utf8(role, content):
    assert validate(content, role)


@pytest.mark.parametrize("content", [b"\xff", b"\xef\xbb\xbftext", b"text\0more"])
def test_bad_markdown(content):
    with pytest.raises(EvidenceError, match="^DOSSIER_UNSUPPORTED_FORMAT$"):
        validate(content, "technical_review")


@pytest.mark.parametrize(
    "fmt,filename,suffix",
    [
        ("JPEG", "image.png", ".jpg"),
        ("PNG", "image.jpg", ".png"),
        ("PNG", "image.arbitrary", ".png"),
    ],
)
def test_image_destination_from_validated_captured_bytes(tmp_path, fmt, filename, suffix):
    document = minimal()
    document["visual_exhibits"] = [item("contextual_visual", "visual", filename)]
    original = image_bytes(fmt)
    config = setup_inputs(tmp_path, document=document, payloads={"visual": original})
    batch, entries, _ = finish(config)
    image = next(i for i in batch.inputs if i.role == "contextual_visual")
    assert image.package_path == "exhibits/visual/visual" + suffix
    assert image.captured_path.read_bytes() == original
    entry = next(e for e in entries if e.role == "contextual_visual")
    assert entry.package_path == image.package_path
    assert entry.display_caption == document["visual_exhibits"][0]["display_caption"]


@pytest.mark.parametrize(
    "content", [b"random", b"%PDF-1.7\nsynthetic", b"\xff\xd8\xffbad", b"\x89PNG\r\n\x1a\nbad"]
)
def test_spoofed_signatures(content):
    with pytest.raises(EvidenceError, match="^DOSSIER_UNSUPPORTED_FORMAT$"):
        validate(content, "contextual_visual")


@pytest.mark.parametrize("fmt", ["PNG", "JPEG"])
def test_truncated_image(fmt):
    with pytest.raises(EvidenceError, match="^DOSSIER_UNSUPPORTED_FORMAT$"):
        validate(image_bytes(fmt)[:40], "contextual_visual")


def test_signature_and_decoder_must_agree(monkeypatch):
    monkeypatch.setattr(v, "identify", lambda data: Signature("image", "jpeg"))
    with pytest.raises(EvidenceError, match="^DOSSIER_UNSUPPORTED_FORMAT$"):
        validate(image_bytes("PNG"), "contextual_visual")


@pytest.mark.parametrize("single_frame", [False, True])
def test_apng_rejected(single_frame):
    buffer = BytesIO()
    first = Image.new("RGB", (2, 2), "red")
    second = Image.new("RGB", (2, 2), "blue")
    first.save(buffer, format="PNG", save_all=True, append_images=[second], duration=20, loop=0)
    content = buffer.getvalue()
    if single_frame:
        # Retain one animated frame with a valid acTL/CRC. Pillow's writer turns
        # single-frame save_all into ordinary PNG, so build this synthetic case.
        result = bytearray(content[:8])
        offset, frames = 8, 0
        while offset < len(content):
            size = int.from_bytes(content[offset : offset + 4], "big")
            kind = content[offset + 4 : offset + 8]
            data = content[offset + 8 : offset + 8 + size]
            offset += size + 12
            if kind == b"acTL":
                data = struct.pack(">II", 1, 0)
            if kind == b"fcTL":
                frames += 1
            if frames > 1 and kind != b"IEND":
                continue
            result.extend(
                struct.pack(">I", len(data))
                + kind
                + data
                + struct.pack(">I", zlib.crc32(kind + data))
            )
        content = bytes(result)
        with Image.open(BytesIO(content)) as image:
            assert image.n_frames == 1 and image.get_format_mimetype() == "image/apng"
    with pytest.raises(EvidenceError, match="^DOSSIER_UNSUPPORTED_FORMAT$"):
        validate(content, "contextual_visual")


def test_bomb_warning_is_promoted_to_resource_error(monkeypatch):
    content = image_bytes()

    def warning(*args, **kwargs):
        warnings.warn("synthetic", Image.DecompressionBombWarning, stacklevel=2)

    monkeypatch.setattr(v.Image, "open", warning)
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        validate(content, "contextual_visual")


@pytest.mark.parametrize("budget", ["MAX_IMAGE_DIMENSION", "MAX_IMAGE_PIXELS", "MAX_VISUAL_BYTES"])
def test_image_limits_before_decode_or_full_load(monkeypatch, budget):
    content = image_bytes(size=(3, 2))
    limit = {"MAX_IMAGE_DIMENSION": 3, "MAX_IMAGE_PIXELS": 6, "MAX_VISUAL_BYTES": len(content)}[
        budget
    ]
    monkeypatch.setattr(v, budget, limit)
    assert validate(content, "contextual_visual")
    monkeypatch.setattr(v, budget, limit - 1)
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        validate(content, "contextual_visual")


@pytest.mark.parametrize("error", [Image.DecompressionBombWarning, Image.DecompressionBombError])
def test_bomb_errors(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error("synthetic private path")

    monkeypatch.setattr(v.Image, "open", fail)
    with pytest.raises(EvidenceError, match="^DOSSIER_RESOURCE_LIMIT$"):
        validate(image_bytes(), "contextual_visual")


def test_verify_reopen_load_without_transformations(monkeypatch):
    original_open = v.Image.open
    phases = []

    class Wrapper:
        def __init__(self, image):
            self.image = image

        def __getattr__(self, name):
            return getattr(self.image, name)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.image.close()

        def verify(self):
            phases.append("verify")
            self.image.verify()

        def load(self):
            phases.append("load")
            self.image.load()

    def opened(*args, **kwargs):
        phases.append("open")
        return Wrapper(original_open(*args, **kwargs))

    content = image_bytes()
    monkeypatch.setattr(v.Image, "open", opened)
    assert validate(content, "contextual_visual")
    assert phases == ["open", "verify", "open", "load"]
