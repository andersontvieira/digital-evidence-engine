"""Build-time downloads/qualification only. Never imported by product code."""

import hashlib
import importlib.metadata as metadata
import json
import pathlib
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from email.parser import BytesParser

ROOT = pathlib.Path("/opt/digital-evidence-engine")
INPUTS = pathlib.Path("/app/tools/pdf-qualified-inputs.json")
# These package initializers execute before the PDF modules; errors.py supplies
# their shared failure type. No other project module participates in this foundation.
IMPLEMENTATION_SUPPORT = (
    "src/evidence_engine/__init__.py",
    "src/evidence_engine/dossier/__init__.py",
    "src/evidence_engine/errors.py",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_bytes(
        (
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            )
            + "\n"
        ).encode()
    )


def preserve_payload(licenses, mappings, name, source):
    relative = pathlib.PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
        raise RuntimeError("Invalid license destination")
    data = source.read_bytes()
    target = licenses / relative
    if target.exists():
        if not target.is_file() or target.read_bytes() != data:
            raise RuntimeError("License destination collision")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    mappings[relative.as_posix()] = digest(data)


def preserve_distribution_licenses(dist, licenses, mappings):
    name = dist.metadata["Name"].lower()
    declared = dist.metadata.get_all("License-File") or []
    if name == "pypdfium2" and (len(declared) != 19 or len(set(declared)) != 19):
        raise RuntimeError("PDFium license inventory divergence")
    entries = tuple(dist.files or ())
    if declared:
        metadata_files = [
            pathlib.PurePosixPath(str(entry))
            for entry in entries
            if entry.name == "METADATA" and entry.parent.name.endswith(".dist-info")
        ]
        if len(metadata_files) != 1:
            raise RuntimeError("Ambiguous license metadata location")
        base = metadata_files[0].parent
        # Metadata 2.4+ uses the dist-info/licenses tree; older wheel metadata
        # places declared payloads directly in dist-info. Never guess by basename.
        version = tuple(int(part) for part in dist.metadata["Metadata-Version"].split("."))
        if version >= (2, 4):
            base /= "licenses"
        for member in sorted(declared):
            relative = pathlib.PurePosixPath(member)
            if (
                not member
                or relative.is_absolute()
                or ".." in relative.parts
                or "\\" in member
                or ":" in member
            ):
                raise RuntimeError("Invalid declared license path")
            entry = base / relative
            source = pathlib.Path(dist.locate_file(entry))
            if not source.is_file():
                raise RuntimeError("Declared license payload missing")
            preserve_payload(licenses, mappings, f"python/{name}/{entry}", source)
    # Additional coverage, including distributions without License-File metadata.
    for entry in sorted(entries, key=str):
        if any(
            word in str(entry).lower() for word in ("license", "copying", "copyright", "notice")
        ):
            source = pathlib.Path(dist.locate_file(entry))
            if source.is_file() and source.suffix != ".pyc":
                relative = str(entry).replace("../", "")
                preserve_payload(licenses, mappings, f"python/{name}/{relative}", source)


def implementation_inventory(project_root):
    paths = set(project_root / name for name in IMPLEMENTATION_SUPPORT)
    paths.update((project_root / "src/evidence_engine/dossier").glob("pdf_*.py"))
    return {
        path.relative_to(project_root).as_posix(): digest(path.read_bytes())
        for path in sorted(paths)
    }


def download_wheel(item):
    info = json.load(
        urllib.request.urlopen(
            f"https://pypi.org/pypi/{item['name']}/{item['version']}/json", timeout=60
        )
    )
    artifact = next(a for a in info["urls"] if a["filename"] == item["file"])
    data = urllib.request.urlopen(artifact["url"], timeout=60).read()
    if digest(data) != item["sha256"]:
        raise RuntimeError("Unqualified wheel artifact")
    path = pathlib.Path("/tmp") / item["file"]
    path.write_bytes(data)
    return path


def bootstrap():
    inputs = json.loads(INPUTS.read_bytes())
    path = download_wheel(next(p for p in inputs["wheels"] if p["name"] == "uv"))
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-index", "--no-deps", str(path)], check=True
    )
    path.unlink()


def finalize():
    inputs = json.loads(INPUTS.read_bytes())
    ROOT.mkdir(parents=True, exist_ok=True)
    licenses = ROOT / "licenses"
    licenses.mkdir(exist_ok=True)
    mappings = {}

    def preserve(name, source):
        preserve_payload(licenses, mappings, name, source)

    # Preserve each declared payload, and other bundled copyright/license files.
    distributions = list(metadata.distributions())
    distributions += [
        d
        for d in metadata.distributions(path=["/usr/local/lib/python3.12/site-packages"])
        if d.metadata["Name"].lower() in ("pip", "uv")
    ]
    packages = {}
    package_files = {}
    for dist in distributions:
        name = dist.metadata["Name"].lower()
        packages[name] = dist.version
        preserve_distribution_licenses(dist, licenses, mappings)
        # Product metadata embeds README, which is not a rendering input. Product
        # foundation source is pinned independently below, without a docs/hash cycle.
        if name == "digital-evidence-engine":
            continue
        for entry in dist.files or ():
            path = pathlib.Path(dist.locate_file(entry))
            if not path.is_file() or path.suffix == ".pyc":
                continue
            # Exclude installer-generated location hints; inventory never includes host paths.
            if path.name in ("RECORD", "direct_url.json", "INSTALLER", "REQUESTED"):
                continue
            package_files[str(path)] = digest(path.read_bytes())

    # Verify installed payloads against the exact independently qualified wheels.
    for item in inputs["wheels"]:
        wheel = download_wheel(item)
        dist = next(d for d in distributions if d.metadata["Name"].lower() == item["name"].lower())
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.infolist():
                if member.is_dir() or member.filename.endswith("/RECORD"):
                    continue
                path = pathlib.Path(dist.locate_file(member.filename))
                # uv stores its executable through wheel .data; tools are pinned by wheel hash.
                if item["name"] == "uv" and ".data/" in member.filename:
                    continue
                if not path.is_file() or path.read_bytes() != archive.read(member):
                    raise RuntimeError("Installed wheel payload divergence")
        wheel.unlink()

    font_source = pathlib.Path("/tmp/dee-font-source")
    for name, expected in inputs["font_packages"].items():
        data = urllib.request.urlopen(
            "https://deb.debian.org/debian/pool/main/f/fonts-dejavu/" + name, timeout=60
        ).read()
        if digest(data) != expected:
            raise RuntimeError("Font source hash divergence")
        path = pathlib.Path("/tmp") / name
        path.write_bytes(data)
        subprocess.run(["dpkg-deb", "-x", str(path), str(font_source)], check=True)
        path.unlink()
    fonts = ROOT / "fonts"
    fonts.mkdir(exist_ok=True)
    for font in inputs["fonts"]:
        paths = list((font_source / "usr/share/fonts").rglob(font["file"]))
        if len(paths) != 1 or digest(paths[0].read_bytes()) != font["sha256"]:
            raise RuntimeError("Font payload divergence")
        shutil.copyfile(paths[0], fonts / font["file"])
    for path in (font_source / "usr/share/doc").rglob("copyright"):
        preserve("fonts/" + path.parent.name + "/copyright", path)
    shutil.rmtree(font_source)

    os_packages = []
    for chunk in pathlib.Path("/var/lib/dpkg/status").read_bytes().split(b"\n\n"):
        item = BytesParser().parsebytes(chunk)
        if item["Status"] != "install ok installed":
            continue
        path = pathlib.Path("/usr/share/doc") / item["Package"] / "copyright"
        preserve("os/" + item["Package"] + "/copyright", path)
        os_packages.append({"name": item["Package"], "version": item["Version"]})
    for path in pathlib.Path("/usr/share/common-licenses").iterdir():
        if path.is_file():
            preserve("os/common-licenses/" + path.name, path)
    preserve("python-runtime/LICENSE.txt", pathlib.Path("/usr/local/lib/python3.12/LICENSE.txt"))

    implementation = implementation_inventory(pathlib.Path("/app"))
    inventory = {
        "contract": "dossier.pdf_export/1.0.0",
        "implementation": "foundation/1.0.0",
        "style": "qualification-probe/1.0.0",
        "python": "3.12.14",
        "base_image": inputs["base_image"],
        "architecture": "x86_64",
        "system": "Linux",
        "os_release": pathlib.Path("/etc/os-release").read_text(),
        "os_packages": os_packages,
        "packages": packages,
        "package_files": package_files,
        "artifacts": inputs["wheels"],
        "font_sources": inputs["font_packages"],
        "fonts": inputs["fonts"],
        "licenses": mappings,
        "implementation_files": implementation,
        "pdfium": "153.0.7999.0",
        "env": {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    }
    write_json(ROOT / "render-environment.json", inventory)
    print("render_environment_id=" + digest((ROOT / "render-environment.json").read_bytes()))


if __name__ == "__main__":
    {"bootstrap": bootstrap, "finalize": finalize}[sys.argv[1]]()
