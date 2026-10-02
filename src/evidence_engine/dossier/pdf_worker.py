"""Closed operation-worker protocol; PDF/source payloads never cross its pipes."""

import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NoReturn, cast

from evidence_engine.dossier.pdf_limits import Phase, PhaseEvent
from evidence_engine.errors import EvidenceError

MESSAGE_BYTES = 4096
CHANNEL_BYTES = 64 * 1024
OUTPUT_PATHS = (
    "human/consolidated-report.pdf",
    "human/dossier.pdf",
    "integrity/SHA256SUMS.txt",
    "integrity/pdf-export-manifest.json",
)
SAFE_CODES = frozenset(
    "DOSSIER_PDF_" + name
    for name in (
        "INVALID_PACKAGE",
        "INTEGRITY_MISMATCH",
        "INPUT_CHANGED",
        "RESOURCE_LIMIT",
        "INTERNAL_ERROR",
        "ENVIRONMENT_UNSUPPORTED",
        "FONT_UNSUPPORTED",
        "UNSUPPORTED_MARKDOWN",
        "UNSUPPORTED_LAYOUT",
        "RENDER_FAILURE",
        "PDF_VALIDATION_FAILURE",
        "STAGING_FAILURE",
        "OUTPUT_EXISTS",
        "PUBLICATION_FAILURE",
    )
)
TIMED_PHASES = frozenset(
    ("RENDER_CONSOLIDATED", "VALIDATE_CONSOLIDATED", "RENDER_DOSSIER", "VALIDATE_DOSSIER")
)


def fail(code: str) -> NoReturn:
    full = "DOSSIER_PDF_" + code
    raise EvidenceError(full if full in SAFE_CODES else "DOSSIER_PDF_INTERNAL_ERROR")


def safe_error_code(error: BaseException) -> str:
    if isinstance(error, (MemoryError, RecursionError)):
        return "DOSSIER_PDF_RESOURCE_LIMIT"
    if isinstance(error, EvidenceError) and str(error) in SAFE_CODES:
        return str(error)
    return "DOSSIER_PDF_INTERNAL_ERROR"


@dataclass(frozen=True, slots=True)
class OutputRecord:
    package_path: str
    byte_size: int
    sha256: str


def _records(value: object) -> tuple[OutputRecord, ...]:
    if type(value) is not list or len(value) != 4:
        fail("INTERNAL_ERROR")
    result = []
    for expected, row in zip(OUTPUT_PATHS, value, strict=True):
        if type(row) is not dict or set(row) != {"package_path", "byte_size", "sha256"}:
            fail("INTERNAL_ERROR")
        if (
            row["package_path"] != expected
            or type(row["byte_size"]) is not int
            or not 0 < row["byte_size"] <= (64 * 1024**2 if expected.endswith(".pdf") else 1024**2)
            or type(row["sha256"]) is not str
            or re.fullmatch("[0-9a-f]{64}", row["sha256"]) is None
        ):
            fail("INTERNAL_ERROR")
        result.append(OutputRecord(**row))
    return tuple(result)


def encode(message: dict[str, object]) -> bytes:
    data = (
        json.dumps(
            message, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        )
        + "\n"
    ).encode("ascii")
    if len(data) > MESSAGE_BYTES:
        fail("RESOURCE_LIMIT")
    return data


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            fail("INTERNAL_ERROR")
        result[name] = value
    return result


def decode(data: bytes, *, ack: bool = False) -> dict[str, object]:
    if len(data) > MESSAGE_BYTES:
        fail("RESOURCE_LIMIT")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_object)
        if type(value) is not dict or encode(value) != data:
            fail("INTERNAL_ERROR")
        if type(value.get("v")) is not int or value["v"] != 1:
            fail("INTERNAL_ERROR")
        if type(value.get("seq")) is not int or not 1 <= value["seq"] <= 1024:
            fail("INTERNAL_ERROR")
        event = value.get("event")
        keys = {"v", "seq", "event"}
        if ack:
            if event != "ACK" or set(value) != keys:
                fail("INTERNAL_ERROR")
        elif event in ("ENTER", "EXIT"):
            if set(value) != keys | {"phase"} or value["phase"] not in PHASES:
                fail("INTERNAL_ERROR")
        elif event == "READY":
            if set(value) != keys | {"records"}:
                fail("INTERNAL_ERROR")
            _records(value["records"])
        elif event == "FAIL":
            if set(value) != keys | {"code"} or value["code"] not in SAFE_CODES:
                fail("INTERNAL_ERROR")
        else:
            fail("INTERNAL_ERROR")
        return cast(dict[str, object], value)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        fail("INTERNAL_ERROR")


PHASES: tuple[Phase, ...] = (
    "PREFLIGHT",
    "CAPTURE",
    "RENDER_CONSOLIDATED",
    "VALIDATE_CONSOLIDATED",
    "RENDER_DOSSIER",
    "VALIDATE_DOSSIER",
    "BIND",
    "WRITE_STAGING",
    "DROP_SCRATCH",
    "VERIFY_STAGING",
    "FINAL_RECHECK",
    "READY_TO_PUBLISH",
)


def _sequence() -> tuple[tuple[str, str], ...]:
    result = []
    for phase in PHASES:
        result.append(("ENTER", phase))
        if phase in ("BIND", "VERIFY_STAGING"):
            for nested in ("VALIDATE_CONSOLIDATED", "VALIDATE_DOSSIER"):
                result.extend((("ENTER", nested), ("EXIT", nested)))
        result.append(("EXIT", phase))
    return tuple(result)


SEQUENCE = _sequence()


class History:
    """One closed schedule. A repeated/late event cannot reset a deadline."""

    def __init__(self, global_deadline: float, phase_seconds: float = 120) -> None:
        self.global_deadline = global_deadline
        self.phase_seconds = phase_seconds
        self.phase_deadline = global_deadline
        self.count = 0
        self.records: tuple[OutputRecord, ...] | None = None

    def check_time(self, now: float) -> None:
        if now >= min(self.global_deadline, self.phase_deadline):
            fail("RESOURCE_LIMIT")

    def accept(self, message: dict[str, object], now: float) -> None:
        self.check_time(now)
        if message["seq"] != self.count + 1 or self.records is not None:
            fail("INTERNAL_ERROR")
        if message["event"] == "FAIL":
            raise EvidenceError(cast(str, message["code"]))
        if self.count == len(SEQUENCE):
            if message["event"] != "READY":
                fail("INTERNAL_ERROR")
            self.records = _records(message["records"])
        else:
            event, phase = SEQUENCE[self.count]
            if (message["event"], message.get("phase")) != (event, phase):
                fail("INTERNAL_ERROR")
            if phase in TIMED_PHASES:
                self.phase_deadline = (
                    now + self.phase_seconds if event == "ENTER" else self.global_deadline
                )
        self.count += 1


class Peer:
    def __init__(self, events_fd: int, ack_fd: int) -> None:
        self.events_fd = events_fd
        self.ack_fd = ack_fd
        self.sequence = 0
        self.sent = 0
        self.received = 0
        self.failed = False

    def send(self, event: str, **fields: object) -> None:
        self.sequence += 1
        data = encode({"v": 1, "seq": self.sequence, "event": event, **fields})
        self.sent += len(data)
        if self.sent > CHANNEL_BYTES:
            fail("RESOURCE_LIMIT")
        if os.write(self.events_fd, data) != len(data):
            fail("INTERNAL_ERROR")
        content = bytearray()
        while not content.endswith(b"\n"):
            chunk = os.read(self.ack_fd, MESSAGE_BYTES + 1 - len(content))
            if not chunk:
                fail("INTERNAL_ERROR")
            content.extend(chunk)
            self.received += len(chunk)
            if len(content) > MESSAGE_BYTES or self.received > CHANNEL_BYTES:
                fail("RESOURCE_LIMIT")
        ack = decode(bytes(content), ack=True)
        if ack["seq"] != self.sequence:
            fail("INTERNAL_ERROR")

    def failure(self, error: BaseException) -> None:
        if not self.failed:
            self.failed = True
            self.send("FAIL", code=safe_error_code(error))

    def observe(self, event: PhaseEvent, phase: Phase) -> None:
        error = sys.exception()
        if event == "EXIT" and error is not None:
            self.failure(error)
        elif not self.failed:
            self.send(event, phase=phase)


def operation(input_package: Path, staging_path: Path, peer: Peer) -> None:
    # Heavy libraries are imported after the operation address-space limit.
    from evidence_engine.dossier import packaging, pdf_package, pdf_renderer
    from evidence_engine.dossier.pdf_limits import phase_boundary, supervised_phases
    from evidence_engine.dossier.pdf_service import read_staged, write_staged

    root = packaging._inspect(staging_path, directory=True)
    with supervised_phases(peer.observe):
        with phase_boundary("PREFLIGHT"):
            packaging._parents(root, include_self=True)
        with phase_boundary("CAPTURE"):
            source = pdf_package.capture_source_package(input_package)
        consolidated = pdf_renderer.render_consolidated_report_pdf(
            source.source_bytes("technical/canonical/consolidated-report.md")
        )
        dossier = pdf_renderer.render_dossier_pdf(source.source_bytes("human/dossier.md"))
        with phase_boundary("BIND"):
            bound = pdf_package.bind_pdf_export(
                source, dossier_pdf=dossier, consolidated_report_pdf=consolidated
            )
        with phase_boundary("WRITE_STAGING"):
            write_staged(root, bound.files)
        # No handles or cwd remain in scratch before the removal handshake.
        os.chdir(root.path)
        with phase_boundary("DROP_SCRATCH"):
            pass
        with phase_boundary("VERIFY_STAGING"):
            files = read_staged(root)
            pdf_package.verify_pdf_export(source, files)
        with phase_boundary("FINAL_RECHECK"):
            pdf_package.recheck_source_package(source)
        with phase_boundary("READY_TO_PUBLISH"):
            records = [
                asdict(OutputRecord(path, len(data), hashlib.sha256(data).hexdigest()))
                for path, data in sorted(files.items())
            ]
        peer.send("READY", records=records)


def main() -> int:
    peer = None
    try:
        from evidence_engine.dossier.pdf_limits import impose_operation_worker_limits

        if len(sys.argv) != 5:
            fail("INTERNAL_ERROR")
        events_fd, ack_fd = int(sys.argv[3]), int(sys.argv[4])
        if min(events_fd, ack_fd) < 3 or events_fd == ack_fd:
            fail("INTERNAL_ERROR")
        peer = Peer(events_fd, ack_fd)
        impose_operation_worker_limits()
        operation(Path(sys.argv[1]), Path(sys.argv[2]), peer)
        return 0
    except BaseException as error:
        if peer is not None:
            try:
                peer.failure(error)
            except BaseException:
                pass
        return 2


if __name__ == "__main__":
    sys.exit(main())
