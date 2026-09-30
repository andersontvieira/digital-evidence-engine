"""Verify the fixed build inventory and register only the six qualified fonts."""

import hashlib
import json
import os
import platform
from importlib import metadata
from pathlib import Path
from typing import Any

from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]

from evidence_engine.dossier.pdf_limits import fail

ROOT = Path("/opt/digital-evidence-engine")
FONT_NAMES = (
    "DejaVuSans",
    "DejaVuSans-Bold",
    "DejaVuSans-Oblique",
    "DejaVuSans-BoldOblique",
    "DejaVuSansMono",
    "DejaVuSansMono-Bold",
)


def canonical_inventory_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def verify_environment() -> str:
    """Read build assets only; this API accepts no caller filesystem paths."""
    try:
        data = (ROOT / "render-environment.json").read_bytes()
        if len(data) > 16 * 1024 * 1024:
            fail("ENVIRONMENT_UNSUPPORTED")
        inventory = json.loads(data)
        if canonical_inventory_bytes(inventory) != data:
            fail("ENVIRONMENT_UNSUPPORTED")
        if (platform.system(), platform.machine(), platform.python_version()) != (
            "Linux",
            "x86_64",
            "3.12.14",
        ):
            fail("ENVIRONMENT_UNSUPPORTED")
        if os.getuid() == 0 or any(os.environ.get(k) != v for k, v in inventory["env"].items()):
            fail("ENVIRONMENT_UNSUPPORTED")
        status = dict(
            line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines()
        )
        if int(status["CapEff"].strip(), 16) or status["NoNewPrivs"].strip() != "1":
            fail("ENVIRONMENT_UNSUPPORTED")
        if not os.statvfs("/").f_flag & os.ST_RDONLY:
            fail("ENVIRONMENT_UNSUPPORTED")
        # Docker --network none exposes loopback only. No sockets or probes are opened.
        interfaces = Path("/proc/net/dev").read_text().splitlines()[2:]
        if any(line.split(":", 1)[0].strip() != "lo" for line in interfaces):
            fail("ENVIRONMENT_UNSUPPORTED")
        if Path("/etc/os-release").read_text() != inventory["os_release"]:
            fail("ENVIRONMENT_UNSUPPORTED")
        for name, expected in inventory["packages"].items():
            if name in ("uv", "pip"):
                dist = next(
                    d
                    for d in metadata.distributions(
                        path=["/usr/local/lib/python3.12/site-packages"]
                    )
                    if d.metadata["Name"].lower() == name
                )
                actual = dist.version
            else:
                actual = metadata.version(name)
            if actual != expected:
                fail("ENVIRONMENT_UNSUPPORTED")
        for path, expected in inventory["package_files"].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
                fail("ENVIRONMENT_UNSUPPORTED")
        for name, expected in inventory["licenses"].items():
            if hashlib.sha256((ROOT / "licenses" / name).read_bytes()).hexdigest() != expected:
                fail("ENVIRONMENT_UNSUPPORTED")
        for name, expected in inventory["implementation_files"].items():
            if hashlib.sha256((Path("/app") / name).read_bytes()).hexdigest() != expected:
                fail("ENVIRONMENT_UNSUPPORTED")
        if tuple(f["file"] for f in inventory["fonts"]) != tuple(n + ".ttf" for n in FONT_NAMES):
            fail("ENVIRONMENT_UNSUPPORTED")
        for font in inventory["fonts"]:
            payload = (ROOT / "fonts" / font["file"]).read_bytes()
            if (
                len(payload) != font["size"]
                or hashlib.sha256(payload).hexdigest() != font["sha256"]
            ):
                fail("FONT_UNSUPPORTED")
        return hashlib.sha256(data).hexdigest()
    except (OSError, ValueError, KeyError, TypeError, StopIteration, metadata.PackageNotFoundError):
        fail("ENVIRONMENT_UNSUPPORTED")


def register_fonts() -> None:
    """Public font registration; sequential worker use only, without host discovery."""
    try:
        for name in FONT_NAMES:
            pdfmetrics.registerFont(TTFont(name, str(ROOT / "fonts" / (name + ".ttf"))))
    except Exception:
        fail("FONT_UNSUPPORTED")
