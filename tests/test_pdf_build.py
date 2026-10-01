"""Offline build-inventory regressions using only temporary synthetic payloads."""

import importlib.util
import json
from email.message import Message
from importlib.metadata import PackagePath
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "pdf_build", Path(__file__).parents[1] / "tools/pdf_build.py"
)
assert SPEC is not None and SPEC.loader is not None
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)

PDF_MODULES = (
    "pdf_environment.py",
    "pdf_limits.py",
    "pdf_model.py",
    "pdf_package.py",
    "pdf_probe.py",
    "pdf_renderer.py",
    "pdf_reportlab_adapter.py",
    "pdf_validation.py",
)
SUPPORT = (
    "src/evidence_engine/__init__.py",
    "src/evidence_engine/dossier/__init__.py",
    "src/evidence_engine/errors.py",
)


class SyntheticDistribution:
    def __init__(self, root, declared=(), name="synthetic", metadata_version="2.4"):
        self.root = root
        self.metadata = Message()
        self.metadata["Name"] = name
        self.metadata["Metadata-Version"] = metadata_version
        for member in declared:
            self.metadata["License-File"] = member
        self.base = f"{name}-1.0.dist-info"
        self.files = [PackagePath(self.base + "/METADATA")]
        self.license_base = self.base + ("/licenses" if metadata_version >= "2.4" else "")

    def locate_file(self, entry):
        return self.root / str(entry)

    def add(self, entry, data):
        path = self.locate_file(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.files.append(PackagePath(entry))
        return path


@pytest.mark.parametrize("metadata_version", ["2.1", "2.4", "2.5"])
def test_declared_payload_exact_bytes_and_heuristic_dedup(tmp_path, metadata_version):
    dist = SyntheticDistribution(
        tmp_path / "installed", ["AUTHORS", "LICENSE"], metadata_version=metadata_version
    )
    payload = b"synthetic\r\n\xff\x00\r\n"
    for member in ("AUTHORS", "LICENSE"):
        dist.add(dist.license_base + "/" + member, payload)
    mappings = {}
    destination = tmp_path / "preserved"
    build.preserve_distribution_licenses(dist, destination, mappings)
    assert len(mappings) == 2
    for name, fingerprint in mappings.items():
        assert (destination / name).read_bytes() == payload
        assert fingerprint == build.digest(payload)
    assert str(tmp_path) not in json.dumps(mappings)
    assert all(not Path(name).is_absolute() for name in mappings)


@pytest.mark.parametrize("metadata_version", ["2.1", "2.4"])
def test_missing_declared_payload_fails_without_basename_fallback(tmp_path, metadata_version):
    dist = SyntheticDistribution(tmp_path, ["AUTHORS"], metadata_version=metadata_version)
    dist.add("somewhere_else/AUTHORS", b"synthetic")
    with pytest.raises(RuntimeError, match="Declared license payload missing"):
        build.preserve_distribution_licenses(dist, tmp_path / "out", {})


def test_undeclared_heuristic_material_is_preserved(tmp_path):
    dist = SyntheticDistribution(tmp_path / "installed")
    for member in ("LICENSE", "NOTICE", "COPYING", "copyright"):
        dist.add("synthetic/" + member, b"synthetic " + member.encode())
    mappings = {}
    destination = tmp_path / "out"
    build.preserve_distribution_licenses(dist, destination, mappings)
    assert len(mappings) == 4
    for entry in dist.files[1:]:
        assert (destination / "python/synthetic" / str(entry)).read_bytes() == (
            dist.locate_file(entry).read_bytes()
        )


@pytest.mark.parametrize("count", [0, 18, 20])
def test_pdfium_declared_count_fails_closed(tmp_path, count):
    dist = SyntheticDistribution(tmp_path, [f"member-{i}" for i in range(count)], "pypdfium2")
    with pytest.raises(RuntimeError, match="PDFium license inventory divergence"):
        build.preserve_distribution_licenses(dist, tmp_path / "out", {})


def test_pdfium_duplicate_declarations_fail_closed(tmp_path):
    dist = SyntheticDistribution(tmp_path, ["same"] * 19, "pypdfium2")
    with pytest.raises(RuntimeError, match="PDFium license inventory divergence"):
        build.preserve_distribution_licenses(dist, tmp_path / "out", {})


@pytest.mark.parametrize("missing", [False, True])
def test_pdfium_all_nineteen_required_and_preserved(tmp_path, missing):
    members = [f"member-{i:02d}" for i in range(19)]
    dist = SyntheticDistribution(tmp_path / "installed", members, "pypdfium2")
    for member in members[:-1] if missing else members:
        dist.add(dist.license_base + "/" + member, member.encode() + b"\r\n")
    mappings = {}
    destination = tmp_path / "out"
    if missing:
        with pytest.raises(RuntimeError, match="Declared license payload missing"):
            build.preserve_distribution_licenses(dist, destination, mappings)
    else:
        build.preserve_distribution_licenses(dist, destination, mappings)
        assert len(mappings) == 19
        for member in members:
            assert (destination / "python/pypdfium2" / dist.license_base / member).read_bytes() == (
                member.encode() + b"\r\n"
            )


def test_order_independence_and_identical_repeated_preservation(tmp_path):
    inventories = []
    for index, members in enumerate((["AUTHORS", "LICENSE"], ["LICENSE", "AUTHORS"])):
        dist = SyntheticDistribution(tmp_path / str(index), members)
        for member in members:
            dist.add(dist.license_base + "/" + member, member.encode())
        mappings = {}
        destination = tmp_path / f"output-{index}"
        build.preserve_distribution_licenses(dist, destination, mappings)
        build.preserve_distribution_licenses(dist, destination, mappings)
        inventory = tmp_path / f"inventory-{index}.json"
        build.write_json(inventory, mappings)
        inventories.append(inventory.read_bytes())
    assert inventories[0] == inventories[1]
    assert str(tmp_path).encode() not in inventories[0]


def test_different_bytes_destination_collision_fails(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"first\r\n")
    destination = tmp_path / "out"
    mappings = {}
    build.preserve_payload(destination, mappings, "synthetic/NOTICE", source)
    source.write_bytes(b"different\n")
    with pytest.raises(RuntimeError, match="License destination collision"):
        build.preserve_payload(destination, mappings, "synthetic/NOTICE", source)
    assert (destination / "synthetic/NOTICE").read_bytes() == b"first\r\n"
    assert mappings == {"synthetic/NOTICE": build.digest(b"first\r\n")}


@pytest.mark.parametrize("member", ["../AUTHORS", "/AUTHORS", "C:/AUTHORS", "x\\AUTHORS"])
def test_declared_path_escape_fails(tmp_path, member):
    dist = SyntheticDistribution(tmp_path, [member])
    with pytest.raises(RuntimeError, match="Invalid declared license path"):
        build.preserve_distribution_licenses(dist, tmp_path / "out", {})


@pytest.fixture
def synthetic_project(tmp_path):
    for name in (*SUPPORT, *("src/evidence_engine/dossier/" + p for p in PDF_MODULES)):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# synthetic implementation\n")
    (tmp_path / "src/evidence_engine/unrelated.py").write_bytes(b"# unrelated\n")
    return tmp_path


def test_closed_implementation_inventory(synthetic_project):
    assert build.IMPLEMENTATION_SUPPORT == SUPPORT
    expected = {*SUPPORT, *("src/evidence_engine/dossier/" + p for p in PDF_MODULES)}
    inventory = build.implementation_inventory(synthetic_project)
    assert set(inventory) == expected
    # Read actual module names only; never mutate real project sources.
    assert {
        p.name for p in (Path(__file__).parents[1] / "src/evidence_engine/dossier").glob("pdf_*.py")
    } == set(PDF_MODULES)
    output = synthetic_project / "inventory.json"
    build.write_json(output, {"implementation_files": inventory})
    assert str(synthetic_project).encode() not in output.read_bytes()
    before = output.read_bytes()
    (synthetic_project / "src/evidence_engine/unrelated.py").write_bytes(b"# changed unrelated\n")
    build.write_json(
        output, {"implementation_files": build.implementation_inventory(synthetic_project)}
    )
    assert output.read_bytes() == before


@pytest.mark.parametrize(
    "name", (*SUPPORT, *("src/evidence_engine/dossier/" + p for p in PDF_MODULES))
)
def test_each_covered_source_changes_environment_id(synthetic_project, name):
    output = synthetic_project / "inventory.json"
    build.write_json(
        output, {"implementation_files": build.implementation_inventory(synthetic_project)}
    )
    before = build.digest(output.read_bytes())
    (synthetic_project / name).write_bytes(b"# changed synthetic implementation\n")
    build.write_json(
        output, {"implementation_files": build.implementation_inventory(synthetic_project)}
    )
    assert build.digest(output.read_bytes()) != before


def test_missing_explicit_support_module_fails(synthetic_project):
    (synthetic_project / SUPPORT[-1]).unlink()
    with pytest.raises(FileNotFoundError):
        build.implementation_inventory(synthetic_project)
