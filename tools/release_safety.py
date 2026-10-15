"""Deterministic public-release safety checks for tracked and generated artifacts."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import tarfile
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

DEMO_FILES = {
    "README.md",
    "SHA256SUMS.txt",
    "pipeline-summary.json",
    "technical-report.md",
    "technical-snapshot.json",
}
HIGH_RISK_SUFFIXES = {
    ".7z",
    ".avi",
    ".db",
    ".doc",
    ".docx",
    ".eml",
    ".gif",
    ".gz",
    ".heic",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".mbox",
    ".mov",
    ".mp3",
    ".mp4",
    ".ogg",
    ".parquet",
    ".pcap",
    ".pcapng",
    ".pdf",
    ".png",
    ".rar",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".tif",
    ".tiff",
    ".wav",
    ".webp",
    ".xls",
    ".xlsx",
    ".zip",
}
SENSITIVE_PATTERNS = {
    "AWS access key": re.compile(rb"\bAKIA[A-Z0-9]{16}\b"),
    "GitHub token": re.compile(rb"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Windows user path": re.compile(rb"(?i)\b[A-Z]:\\Users\\[A-Za-z0-9._-]+\\"),
    "POSIX user path": re.compile(rb"/(?:home|Users)/[A-Za-z0-9._-]+/"),
    "known case identifier": re.compile(rb"(?i)\b" + b"Nic" + b"olau" + rb"\b"),
}


def _fail(message: str) -> None:
    raise SystemExit(f"PUBLIC_SAFETY_FAILURE: {message}")


def _safe_member(name: str) -> None:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        _fail(f"unsafe archive member: {name}")


def _scan_bytes(label: str, data: bytes) -> None:
    for description, pattern in SENSITIVE_PATTERNS.items():
        if pattern.search(data):
            _fail(f"{description} in {label}")


def _allowed_high_risk_path(path: PurePosixPath) -> bool:
    normalized = path.as_posix()
    return normalized == "Dockerfile.pdf" or normalized.startswith("tests/fixtures/")


def scan_repository(root: Path) -> None:
    completed = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    names = [name.decode("utf-8") for name in completed.stdout.split(b"\0") if name]
    for name in names:
        relative = PurePosixPath(name)
        path = root / Path(*relative.parts)
        if not path.is_file():
            _fail(f"tracked path is not a regular file: {name}")
        if relative.suffix.lower() in HIGH_RISK_SUFFIXES and not _allowed_high_risk_path(relative):
            _fail(f"tracked high-risk artifact: {name}")
        if path.stat().st_size > 5 * 1024 * 1024:
            _fail(f"unexpected tracked file larger than 5 MiB: {name}")
        _scan_bytes(f"tracked file {name}", path.read_bytes())

    workflows = sorted((root / ".github" / "workflows").glob("*.yml"))
    if workflows:
        for workflow in workflows:
            text = workflow.read_text(encoding="utf-8")
            if "permissions:\n  contents: read" not in text:
                _fail(f"least-privilege permissions missing in {workflow.name}")
            for forbidden in (
                "pull_request_target:",
                "permissions: write-all",
                "contents: write",
                "id-token: write",
            ):
                if forbidden in text:
                    _fail(f"unsafe workflow permission/trigger in {workflow.name}: {forbidden}")
            for action in re.findall(r"uses:\s+([^\s]+)", text):
                reference = action.rsplit("@", 1)[-1]
                if not re.fullmatch(r"[0-9a-f]{40}", reference):
                    _fail(f"workflow action is not pinned by SHA: {action}")
    print(f"repository: PASS ({len(names)} tracked files, {len(workflows)} workflows)")


def _archive_entries(path: Path) -> Iterable[tuple[str, bytes]]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if not info.is_dir():
                    yield info.filename, archive.read(info)
        return
    with tarfile.open(path, mode="r:gz") as archive:
        for info in archive.getmembers():
            if info.isfile():
                stream = archive.extractfile(info)
                if stream is None:
                    _fail(f"cannot read archive member: {info.name}")
                yield info.name, stream.read()


def scan_distributions(directory: Path, expected_version: str) -> None:
    distributions = sorted((*directory.glob("*.whl"), *directory.glob("*.tar.gz")))
    if len(distributions) != 2 or not any(path.suffix == ".whl" for path in distributions):
        _fail("expected exactly one wheel and one source distribution")
    for distribution in distributions:
        version_seen = False
        for name, data in _archive_entries(distribution):
            _safe_member(name)
            relative = PurePosixPath(name)
            if relative.suffix.lower() in HIGH_RISK_SUFFIXES and not _allowed_high_risk_path(
                relative
            ):
                _fail(f"high-risk member in {distribution.name}: {name}")
            _scan_bytes(f"{distribution.name}:{name}", data)
            if name.endswith((".dist-info/METADATA", "/PKG-INFO")):
                version_seen = f"Version: {expected_version}\n".encode() in data.replace(
                    b"\r\n", b"\n"
                )
        if not version_seen:
            _fail(f"version {expected_version} absent from {distribution.name} metadata")
    print("distributions: PASS (wheel + sdist)")


def _demo_payload(directory: Path) -> dict[str, bytes]:
    names = {path.name for path in directory.iterdir() if path.is_file()}
    if names != DEMO_FILES or any(path.is_dir() for path in directory.iterdir()):
        _fail(f"demo output allowlist mismatch: {directory}")
    payload = {name: (directory / name).read_bytes() for name in sorted(names)}
    for name, data in payload.items():
        _scan_bytes(f"demo output {name}", data)
        if re.search(rb"\b[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-", data):
            _fail(f"operational UUID in demo output {name}")
        if b"evidence.db" in data or b"originals/" in data or b"working/" in data:
            _fail(f"operational case material reference in demo output {name}")
    expected = {}
    for line in payload["SHA256SUMS.txt"].decode("ascii").splitlines():
        digest, name = line.split("  ", 1)
        expected[name] = digest
    if set(expected) != DEMO_FILES - {"SHA256SUMS.txt"}:
        _fail("demo checksum allowlist mismatch")
    for name, digest in expected.items():
        if hashlib.sha256(payload[name]).hexdigest() != digest:
            _fail(f"demo checksum mismatch: {name}")
    return payload


def scan_demo(directories: list[Path]) -> None:
    payloads = [_demo_payload(directory) for directory in directories]
    if any(payload != payloads[0] for payload in payloads[1:]):
        _fail("independent demo outputs are not byte-identical")
    print(f"demo: PASS ({len(directories)} byte-identical run(s))")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    repository = subparsers.add_parser("repository")
    repository.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    distributions = subparsers.add_parser("distributions")
    distributions.add_argument("directory", type=Path)
    distributions.add_argument("--expected-version", required=True)
    demo = subparsers.add_parser("demo")
    demo.add_argument("directories", nargs="+", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "repository":
        scan_repository(arguments.root.resolve())
    elif arguments.command == "distributions":
        scan_distributions(arguments.directory.resolve(), arguments.expected_version)
    else:
        scan_demo([path.resolve() for path in arguments.directories])


if __name__ == "__main__":
    main()
