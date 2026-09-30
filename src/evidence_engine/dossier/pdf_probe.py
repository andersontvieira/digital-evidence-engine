"""Synthetic two-page qualification only. Not a dossier/report renderer or CLI."""

import hashlib
import json
import unicodedata
from io import BytesIO

from pypdf import PdfReader
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]

from evidence_engine.dossier.pdf_environment import (
    FONT_NAMES,
    register_fonts,
    verify_environment,
)
from evidence_engine.dossier.pdf_limits import BoundedPdfBuffer, fail, impose_worker_limits
from evidence_engine.dossier.pdf_reportlab_adapter import ControlledCanvas
from evidence_engine.dossier.pdf_validation import PdfExpectation, validate_pdf_bytes
from evidence_engine.errors import EvidenceError

TITLE = "Qualificação PDF sintética"
TEXT = "Usuário sintético — seção → ç Ç ã õ á é í ó ú â ê ô _ .,:;!? MODEL-SYNTH-A"
SECOND = "Destino interno sintético"


def probe_expectation(title: str = TITLE, text: str = TEXT) -> PdfExpectation:
    return PdfExpectation(
        title,
        (title + "\n" + "\n".join([text] * 6) + "\nPágina 1\n", SECOND + "\nPágina 2\n"),
        ((title, 0, 0), (SECOND, 1, 1)),
        ((0, 1),),
    )


def qualification_pdf(title: str = TITLE, text: str = TEXT) -> bytes:
    """Sequential, in-memory synthetic capability probe; no source-package input."""
    verify_environment()
    register_fonts()
    # Unqualified shaping is refused, never normalized or substituted.
    if any(
        unicodedata.combining(c) or unicodedata.category(c) in ("Cc", "Cf", "Cs")
        for c in title + text
    ):
        fail("FONT_UNSUPPORTED")
    try:
        output = BoundedPdfBuffer()
        canvas = ControlledCanvas(output, title)
        canvas.bookmarkPage("heading-0")
        canvas.addOutlineEntry(title, "heading-0", level=0)
        canvas.setFont("DejaVuSans-Bold", 18)
        canvas.drawString(56.693, 760, title)
        for i, name in enumerate(FONT_NAMES):
            if pdfmetrics.stringWidth(text, name, 9) > 481.89:
                fail("RENDER_FAILURE")
            canvas.setFont(name, 9)
            canvas.drawString(56.693, 710 - 30 * i, text)
        canvas.linkRect("", "heading-1", (56.693, 500, 180, 520), relative=0)
        canvas.setFont("DejaVuSans", 9)
        canvas.drawString(56.693, 34.016, "Página 1")
        canvas.showPage()
        canvas.bookmarkPage("heading-1")
        canvas.addOutlineEntry(SECOND, "heading-1", level=1)
        canvas.setFont("DejaVuSans-Bold", 13)
        canvas.drawString(56.693, 760, SECOND)
        canvas.setFont("DejaVuSans", 9)
        canvas.drawString(56.693, 34.016, "Página 2")
        canvas.showPage()
        canvas.save()
        data = output.getvalue()
        # Detect .notdef/Unicode loss independently, including glyphs unsupported by DejaVu.
        extracted = tuple(
            page.extract_text() for page in PdfReader(BytesIO(data), strict=True).pages
        )
        expected = probe_expectation(title, text)
        if extracted != expected.page_text:
            fail("FONT_UNSUPPORTED")
        validate_pdf_bytes(data, expected)
        return data
    except EvidenceError:
        raise
    except MemoryError:
        fail("RESOURCE_LIMIT")
    except Exception:
        fail("RENDER_FAILURE")


def qualification_fingerprint() -> dict[str, object]:
    data = qualification_pdf()
    return {
        "bytes": len(data),
        "pdf_sha256": hashlib.sha256(data).hexdigest(),
        "render_environment_id": verify_environment(),
    }


if __name__ == "__main__":
    impose_worker_limits()
    try:
        print(json.dumps(qualification_fingerprint(), sort_keys=True))
    except EvidenceError as exc:
        print(str(exc))
        raise SystemExit(1) from None
