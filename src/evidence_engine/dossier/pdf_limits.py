"""ADR 0038 presentation budgets; independent of case and package services."""

from collections.abc import Buffer, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from io import BytesIO
from typing import Literal, NoReturn

from evidence_engine.errors import EvidenceError

type PdfErrorCode = Literal[
    "ENVIRONMENT_UNSUPPORTED",
    "FONT_UNSUPPORTED",
    "UNSUPPORTED_MARKDOWN",
    "UNSUPPORTED_LAYOUT",
    "RESOURCE_LIMIT",
    "RENDER_FAILURE",
    "PDF_VALIDATION_FAILURE",
    "INTERNAL_ERROR",
]

MAX_MARKDOWN_BYTES = 64 * 1024 * 1024
MAX_BLOCKS = 200_000
MAX_COLUMNS = 16
MAX_ROWS = 100_000
MAX_CELLS = 1_000_000
MAX_PDF_BYTES = 64 * 1024 * 1024
MAX_PAGES = 1000
MAX_OBJECTS = 1_000_000
MAX_DEPTH = 64
WORKER_MEMORY = 1024**3
WORKER_SECONDS = 120

type Phase = Literal[
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
]
type PhaseEvent = Literal["ENTER", "EXIT"]
type PhaseObserver = Callable[[PhaseEvent, Phase], None]
_OBSERVER: ContextVar[PhaseObserver | None] = ContextVar("pdf_phase_observer", default=None)


@contextmanager
def supervised_phases(observer: PhaseObserver) -> Iterator[None]:
    """Install an execution-local observer; no clock, IPC or worker dependency."""
    token = _OBSERVER.set(observer)
    try:
        yield
    finally:
        _OBSERVER.reset(token)


@contextmanager
def phase_boundary(phase: Phase | None) -> Iterator[None]:
    observer = _OBSERVER.get()
    if observer is None:
        yield
        return
    if phase is None:
        fail("INTERNAL_ERROR")
    observer("ENTER", phase)
    try:
        yield
    finally:
        observer("EXIT", phase)


def fail(code: PdfErrorCode) -> NoReturn:
    raise EvidenceError("DOSSIER_PDF_" + code)


class BoundedPdfBuffer(BytesIO):
    """Reject a write before extending the output beyond its budget."""

    def write(self, data: Buffer, /) -> int:
        if self.tell() + memoryview(data).nbytes > MAX_PDF_BYTES:
            fail("RESOURCE_LIMIT")
        return super().write(data)


def impose_worker_limits() -> None:
    """Called only in a dedicated Linux worker, before processing content."""
    import sys

    if sys.platform != "linux":
        fail("ENVIRONMENT_UNSUPPORTED")
    import resource

    try:
        resource.setrlimit(resource.RLIMIT_AS, (WORKER_MEMORY, WORKER_MEMORY))
        resource.setrlimit(resource.RLIMIT_CPU, (WORKER_SECONDS, WORKER_SECONDS))
        if resource.getrlimit(resource.RLIMIT_AS) != (WORKER_MEMORY, WORKER_MEMORY):
            fail("ENVIRONMENT_UNSUPPORTED")
    except (OSError, ValueError):
        fail("ENVIRONMENT_UNSUPPORTED")


def impose_operation_worker_limits() -> None:
    """Limit address space only; external supervision owns operation/phase time."""
    import sys

    if sys.platform != "linux":
        fail("ENVIRONMENT_UNSUPPORTED")
    import resource

    try:
        resource.setrlimit(resource.RLIMIT_AS, (WORKER_MEMORY, WORKER_MEMORY))
        if resource.getrlimit(resource.RLIMIT_AS) != (WORKER_MEMORY, WORKER_MEMORY):
            fail("ENVIRONMENT_UNSUPPORTED")
    except (OSError, ValueError):
        fail("ENVIRONMENT_UNSUPPORTED")
