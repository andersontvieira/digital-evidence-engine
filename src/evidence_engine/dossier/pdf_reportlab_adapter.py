"""Narrow ReportLab 5.0.1 coupling authorized by ADR 0039; no case semantics."""

import hashlib
import inspect
from importlib.metadata import version
from typing import Any

from reportlab.pdfbase.pdfdoc import (  # type: ignore[import-untyped]
    PDFDictionary,
    PDFDocument,
    PDFInfo,
    PDFString,
    PDFTrailer,
)
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]

from evidence_engine.dossier.pdf_limits import BoundedPdfBuffer, fail

SUBJECT = "Apresentação técnica de artefato aprovado; sem nova análise."
PRODUCER = "Digital Evidence Engine dossier.pdf_export/1.0.0"
A4 = (595.276, 841.890)
_SHAPES = (
    "8bfca25dcd6a794d7d8590354a3ef0b7aa37490f7e702dc20d12db9aa754ce39",
    "cd323144e687e270b21e3ecb59e068bf4806637cdffb15f662be629a78129cf6",
    "8d46bfc4b003dc8a92e584324e47486601baed2a3d30de8ec5c35eca5d8cee26",
    "b9e9b1f18b53ac93eaff803aefe103e53e732fa3430dc37b9c4c497ac8f2c74a",
    "536ea7a675493430f5438f2eda50eb2ac959284cb4bbae99a86008ec615dcb22",
    "af98dae6de3c830b9bdc332e458eb722af644e734d7e8d764b1798e468fa3702",
)


def verify_adapter_shape() -> None:
    """Source hashes pin the reviewed signatures, lifecycle and None omission."""
    try:
        methods = (
            Canvas.__init__,
            PDFDocument.__init__,
            PDFInfo.format,
            PDFDocument.ID,
            PDFDocument.format,
            PDFTrailer.__init__,
        )
        actual = tuple(
            hashlib.sha256(inspect.getsource(m).encode("utf-8")).hexdigest() for m in methods
        )
        if version("reportlab") != "5.0.1" or actual != _SHAPES:
            fail("ENVIRONMENT_UNSUPPORTED")
        if (
            str(inspect.signature(PDFDictionary)) != "(dict=None)"
            or str(inspect.signature(PDFString)) != "(s, escape=1, enc='auto')"
        ):
            fail("ENVIRONMENT_UNSUPPORTED")
    except (AttributeError, OSError, TypeError, ValueError):
        fail("ENVIRONMENT_UNSUPPORTED")


class ContractInfo(PDFInfo):  # type: ignore[misc]
    def __init__(self, title: str) -> None:
        self.contract_title = title

    def format(self, document: Any) -> bytes:
        values = {
            "Title": self.contract_title,
            "Subject": SUBJECT,
            "Creator": PRODUCER,
            "Producer": PRODUCER,
        }
        result: bytes = PDFDictionary({k: PDFString(v) for k, v in values.items()}).format(document)
        return result


class ContractDocument(PDFDocument):  # type: ignore[misc]
    def __init__(self, title: str) -> None:
        super().__init__(compression=0, invariant=1, pdfVersion=(1, 4), lang="pt-BR")
        self.info = ContractInfo(title)

    def ID(self) -> None:
        return None


class ControlledCanvas(Canvas):  # type: ignore[misc]
    """The original initializer runs; only its first _doc assignment is intercepted."""

    def __init__(self, output: BoundedPdfBuffer, title: str) -> None:
        verify_adapter_shape()
        self._contract_document: ContractDocument | None = None
        self._contract_title = title
        super().__init__(
            output,
            pagesize=A4,
            invariant=1,
            pdfVersion=(1, 4),
            lang="pt-BR",
            encrypt=None,
            pageCompression=0,
            initialFontName="DejaVuSans",
            initialFontSize=10.5,
            initialLeading=14,
        )
        if self._contract_document is None:
            fail("ENVIRONMENT_UNSUPPORTED")

    @property
    def _doc(self) -> ContractDocument:
        if self._contract_document is None:
            fail("ENVIRONMENT_UNSUPPORTED")
        return self._contract_document

    @_doc.setter
    def _doc(self, value: Any) -> None:
        if (
            self._contract_document is not None
            or type(value) is not PDFDocument
            or type(value.info) is not PDFInfo
        ):
            fail("ENVIRONMENT_UNSUPPORTED")
        self._contract_document = ContractDocument(self._contract_title)
