"""One synthetic directory-v1 fixture, exercised independently on both native OSes."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from evidence_engine.dossier import packaging, rendering
from tests.test_dossier_service import inputs, package_bytes, run

SYNTHETIC_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000030000000208020000001216f14d"
    "0000001449444154789c63e451b26000032608c5c0c00000073c006abc96cea5"
    "0000000049454e44ae426082"
)


# Agreed after independent native Windows/Linux runs; package-relative synthetic data only.
EXPECTED_FINGERPRINT = dict(
    [
        (
            "exhibits/visual/visual.png",
            "3c83eb774de6103fbdf7fb76277cbee26bde8c932c85d4730e028c016270318e",
        ),
        (
            "human/annex-index.md",
            "2f36473d1611b13793403e79032877005557cd1552308ba6f00c9b2f3d84d506",
        ),
        ("human/dossier.md", "7b9566ab0c4729ed7620532fc68da367fb157c7363c7e1d0955e4b8c333e7fc7"),
        (
            "integrity/SHA256SUMS.txt",
            "3424122544312ade41f58713d65cac98d34141c8c42bdfe554e015df1467df89",
        ),
        (
            "integrity/manifest.json",
            "fe3887621c459764fd21a209b95113de8a0e595dc5dd311c8fa42a3c5375272e",
        ),
        (
            "technical/canonical/consolidated-report.md",
            "b2dab15c25ff2c39f6b7242324df7a00b07a52b6947493f93056d197b0e7ea13",
        ),
        (
            "technical/canonical/snapshots/anchor.json",
            "e0cd6af944ce6fe08ce4178b42cf22dad9102896c1650adb20fe20584c0e74ef",
        ),
        (
            "technical/canonical/snapshots/window-1.json",
            "6a7b7e017c3253281a75ef89fb8e1faa91b6fb6344619454f00bb0fedcd6c704",
        ),
        (
            "technical/canonical/snapshots/window-10.json",
            "21018cadb4b048f257e72382b2d455afaa1b67fd98b7eebfb07e64589ede8411",
        ),
        (
            "technical/canonical/snapshots/window-11.json",
            "14d986afcfa304d646ae7683d7c9ed5115e59dee861b823a2d97b5e9d03d078d",
        ),
        (
            "technical/canonical/snapshots/window-12.json",
            "8f4cf5b938f79af348d4176244c66df30b859f8fb1d6bdcd023e82d07f2f5e87",
        ),
        (
            "technical/canonical/snapshots/window-13.json",
            "c0e92abd9bb0dd084c46b66e4c941e1891e65ddf5a522b3f3cfedd977af2de9e",
        ),
        (
            "technical/canonical/snapshots/window-14.json",
            "e9066832e654dc0874b9cb2554f60ee6b04c40d39a1d901334cec32ec253229f",
        ),
        (
            "technical/canonical/snapshots/window-15.json",
            "7b54588fbbef2b7a1f68c82fec77770df06bd502e9da85149d6e08dcc9264a35",
        ),
        (
            "technical/canonical/snapshots/window-16.json",
            "75d3281132521e30a840343c9323cbeee2cfd720ab71ac09e1906f4c5a915f3d",
        ),
        (
            "technical/canonical/snapshots/window-17.json",
            "d4cdf25f344e61babaaf2710d1ba689920823829376c1dfa6dd1bede0ef30d6d",
        ),
        (
            "technical/canonical/snapshots/window-18.json",
            "f5a080ef2964a0b26f1b12d3a4a8c6d1824cf0cc083400b334c03f8031ecb69e",
        ),
        (
            "technical/canonical/snapshots/window-19.json",
            "72cd08b305b0d43ee84e6ee26bb35edef27877fc768a1fdae6485bfe33376208",
        ),
        (
            "technical/canonical/snapshots/window-2.json",
            "69752915cf1eddc51971bf2afa94449222867518fd170c8b938dc85f263f4e56",
        ),
        (
            "technical/canonical/snapshots/window-20.json",
            "302c9eea37bdceea5d2149e7c97549bf8a5189e44d147cff611a7fcaaaafd476",
        ),
        (
            "technical/canonical/snapshots/window-3.json",
            "26fb08e27eb4fca95f76655e8c775b91cef305cbfbbd53a94293a238a78ae48b",
        ),
        (
            "technical/canonical/snapshots/window-4.json",
            "a0241e749a6b8275072ae8bb4845b23b6d06d3f32e025af6542ead3a826d919f",
        ),
        (
            "technical/canonical/snapshots/window-5.json",
            "63e346358c5b763205952229693ab264dac99e5314a9c13803d4fc18103cab78",
        ),
        (
            "technical/canonical/snapshots/window-6.json",
            "972323313745d1712a7a81850ca152ff953f4b7a3a175db4644de94488d2e39a",
        ),
        (
            "technical/canonical/snapshots/window-7.json",
            "7d535d1f54f09ed179a503bf01eaee9c71ebbc5ff377971b079c19fc035cfc0b",
        ),
        (
            "technical/canonical/snapshots/window-8.json",
            "7883992e7d3f2ae0ed35b14c07d698a467f5f655a8e856ad2ad93241860e3b1d",
        ),
        (
            "technical/canonical/snapshots/window-9.json",
            "f492f895bfffe156edba401a7cb12c277f8ef5a04703d0100344aef24f3a3ba0",
        ),
        (
            "technical/selection-metadata.json",
            "bd1fa5b561f5f986a4b5539f21e01f2696bba4fffb0b0317f0d94eb88c516fa7",
        ),
        (
            "technical/structured/support.json",
            "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        ),
        (
            "technical/supplemental/review.md",
            "95be08a3da285ab9e7e0ab8bc48593852443dc554e30d65d3e9e2bf3c38b3482",
        ),
        (
            "technical/validation/validation.md",
            "18c4f85a180cf29ddc1f8e3a3143ff54d643d1c306dbe610f4f70482632071d4",
        ),
    ]
)


def fixture(root):
    # A fixed selection: anchor + 20 windows, all optional roles, explicit date/token,
    # reversed lists and opaque CRLF Markdown. Sources are written as bytes.
    config = inputs(root, full=True, windows=True, reverse=True)
    # Fixed 3x2 RGB synthetic pixels: encoder/zlib differences are not source
    # differences the assembler should normalize. Feed exactly the same bytes.
    config[3]["visual"] = SYNTHETIC_PNG
    visual = config[2]["visual_exhibits"][0]
    (config[0].parent / visual["input_reference"]).write_bytes(SYNTHETIC_PNG)
    return config


def fingerprint(payloads):
    return {path: hashlib.sha256(data).hexdigest() for path, data in sorted(payloads.items())}


def fingerprint_bytes(payloads):
    return (
        json.dumps(fingerprint(payloads), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def check_package(config):
    payloads = package_bytes(config[1])
    assert len(payloads) == 31
    assert len([p for p in payloads if p.startswith("technical/canonical/snapshots/")]) == 21
    manifest = json.loads(payloads["integrity/manifest.json"])
    entries = manifest["entries"]
    assert [e["package_path"] for e in entries] == sorted(e["package_path"] for e in entries)
    selected = {
        entry["local_label"]: entry
        for group in (
            "canonical_inputs",
            "supplemental_inputs",
            "validation_artifacts",
            "visual_exhibits",
        )
        for entry in config[2][group]
    }
    for entry in entries:
        data = payloads[entry["package_path"]]
        assert len(data) == entry["byte_size"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        if "local_label" in entry:
            source = selected[entry["local_label"]]
            assert data == (config[0].parent / source["input_reference"]).read_bytes()
            assert data == config[3][entry["local_label"]]
            assert entry["role"] == source["role"]
            assert entry["source_class"] == source["source_class"]
    assert payloads["technical/supplemental/review.md"] == b"# Synthetic claim: opaque\r\n"
    for path in payloads:
        assert "\\" not in path and not path.startswith("/")
    for path in packaging.GENERATED_PATHS:
        data = payloads[path]
        assert data.endswith(b"\n") and b"\r" not in data and not data.startswith(b"\xef\xbb\xbf")
        for forbidden in (
            str(config[0].parent).encode(),
            str(config[1]).encode(),
            b".dee-dossier-staging-",
            b"source-image.jpg",
            b"selection-private.json",
            b"C:\\",
            b"/tmp/",
            b"/Users/",
        ):
            assert forbidden not in data
    dossier = payloads["human/dossier.md"].decode()
    assert dossier.splitlines()[0] == "# " + rendering.TITLE
    assert [line for line in dossier.splitlines() if line.startswith("## ")] == [
        f"## {i}. {title}" for i, title in enumerate(rendering.SECTIONS, 1)
    ]
    sums = payloads["integrity/SHA256SUMS.txt"]
    assert sums == b"".join(
        f"{digest}  {path}\n".encode()
        for path, digest in fingerprint(payloads).items()
        if path != "integrity/SHA256SUMS.txt"
    )
    assert fingerprint(payloads) == EXPECTED_FINGERPRINT
    return payloads


def test_complete_synthetic_package(tmp_path):
    config = fixture(tmp_path)
    run(config)
    check_package(config)


def test_installed_cli_cross_platform(tmp_path):
    config = fixture(tmp_path)

    def invoke(*args):
        return subprocess.run(
            [sys.executable, "-m", "evidence_engine", "dossier", *args],
            capture_output=True,
            check=False,
            timeout=60,
        )

    for args in (("--help",), ("assemble", "--help")):
        result = invoke(*args)
        assert result.returncode == 0 and b"assemble" in result.stdout
    args = ("assemble", "--selection", str(config[0]), "--output-dir", str(config[1]))
    result = invoke(*args)
    assert result.returncode == 0 and result.stdout == b"DOSSIER_ASSEMBLY_OK\n"
    assert result.stderr == b""
    check_package(config)
    result = invoke(*args)
    assert result.returncode == 2 and result.stdout == b""
    assert result.stderr == b"ERROR: DOSSIER_OUTPUT_EXISTS\n"
    config[0].write_bytes(b"invalid synthetic selection")
    result = invoke(*args)
    assert result.returncode == 2 and result.stdout == b""
    assert result.stderr == b"ERROR: DOSSIER_INVALID_SELECTION\n"


if __name__ == "__main__":
    # Explicit TEST OUTPUT, outside the package; no host fields in the mapping.
    with TemporaryDirectory(prefix="dee-synthetic-parity-") as directory:
        config = fixture(Path(directory))
        run(config)
        Path(sys.argv[1]).write_bytes(fingerprint_bytes(check_package(config)))
