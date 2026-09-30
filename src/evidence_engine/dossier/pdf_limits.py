"""ADR 0038 presentation budgets; independent of case and package services."""

from collections.abc import Buffer
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
