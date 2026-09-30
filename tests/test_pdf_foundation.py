"""Canonical-only synthetic PDF qualification. No golden PDF/PNG files."""

import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from evidence_engine.dossier import pdf_environment as environment
from evidence_engine.dossier import pdf_limits as limits
from evidence_engine.dossier import pdf_reportlab_adapter as adapter
from evidence_engine.dossier.pdf_probe import probe_expectation, qualification_pdf
from evidence_engine.dossier.pdf_validation import validate_pdf_bytes
from evidence_engine.errors import EvidenceError

CANONICAL = Path("/opt/digital-evidence-engine/render-environment.json").is_file()
PDF_SHA256 = "06fadb2a60e76c78a836ec1e118e3986941a17e803e0e81d727a0b47b59102d8"
PIXEL_SHA256 = (
    "55f00567696521e8343129534163d19cd02b9bc6d30e9291da7a8f172cc9fcde",
    "11c346f985bc3ba2d23792accdeec9ab5a0c33648850ff479a6a30518c898e86",
)
pytestmark = pytest.mark.skipif(
    not CANONICAL, reason="Requires qualified Dockerfile.pdf Linux/amd64 environment"
)


@pytest.fixture(scope="module")
def pdf():
    return qualification_pdf()


def test_metadata_fonts_navigation_and_text(pdf):
    result = validate_pdf_bytes(pdf, probe_expectation())
    assert result.page_count == 2
    reader = PdfReader(BytesIO(pdf), strict=True)
    assert set(reader.metadata) == {"/Title", "/Subject", "/Creator", "/Producer"}
    assert "/ID" not in reader.trailer
    assert len(reader.pages[0]["/Resources"]["/Font"]) == 6
    assert result.extracted_text == probe_expectation().page_text


def test_public_baseline_still_emits_forbidden_metadata():
    output = BytesIO()
    canvas = Canvas(output, invariant=1, pdfVersion=(1, 4), lang="pt-BR")
    canvas.drawString(30, 30, "synthetic")
    canvas.save()
    reader = PdfReader(output, strict=True)
    assert {"/Author", "/Keywords", "/CreationDate", "/ModDate"} <= set(reader.metadata)
    assert "/ID" in reader.trailer


@pytest.mark.parametrize(
    "text", ["missing \U0010ffff", "combining a\u0301", "control\x00", "bidi\u202e"]
)
def test_font_loss_fails_closed(text):
    with pytest.raises(EvidenceError, match="^DOSSIER_PDF_FONT_UNSUPPORTED$"):
        qualification_pdf(text=text)


def test_canvas_lifecycle_and_no_vendor_mutation(pdf):
    before = inspect.getsource(adapter.PDFDocument) + inspect.getsource(adapter.Canvas)
    canvas = adapter.ControlledCanvas(limits.BoundedPdfBuffer(), "Synthetic")
    with pytest.raises(EvidenceError, match="ENVIRONMENT_UNSUPPORTED"):
        canvas._doc = adapter.PDFDocument()
    other = object.__new__(adapter.ControlledCanvas)
    other._contract_document = None
    other._contract_title = "Synthetic"
    with pytest.raises(EvidenceError, match="ENVIRONMENT_UNSUPPORTED"):
        other._doc = object()
    assert adapter.ContractDocument.format is adapter.PDFDocument.format
    assert before == inspect.getsource(adapter.PDFDocument) + inspect.getsource(adapter.Canvas)
    assert "MethodType" not in inspect.getsource(adapter)


def test_adapter_version_guard(monkeypatch):
    monkeypatch.setattr(adapter, "version", lambda _: "5.0.2")
    with pytest.raises(EvidenceError, match="ENVIRONMENT_UNSUPPORTED"):
        adapter.verify_adapter_shape()


def test_adapter_shape_guard(monkeypatch):
    monkeypatch.setattr(adapter, "_SHAPES", ("different",))
    with pytest.raises(EvidenceError, match="ENVIRONMENT_UNSUPPORTED"):
        adapter.verify_adapter_shape()


def test_environment_and_font_guards(monkeypatch):
    monkeypatch.setenv("TZ", "different")
    with pytest.raises(EvidenceError, match="ENVIRONMENT_UNSUPPORTED"):
        environment.verify_environment()


def test_inventory_canonical_and_license_preservation():
    path = environment.ROOT / "render-environment.json"
    data = path.read_bytes()
    inventory = json.loads(data)
    assert environment.canonical_inventory_bytes(inventory) == data
    assert environment.verify_environment() == hashlib.sha256(data).hexdigest()
    assert data == (Path(__file__).parents[1] / "docs/pdf-render-environment.json").read_bytes()
    from importlib.metadata import distribution

    dist = distribution("pypdfium2")
    assert len(dist.metadata.get_all("License-File")) == 19
    for entry in dist.metadata.get_all("License-File"):
        name = f"pypdfium2-5.13.0.dist-info/licenses/{entry}"
        assert (environment.ROOT / "licenses/python/pypdfium2" / name).read_bytes() == Path(
            dist.locate_file(name)
        ).read_bytes()


def test_determinism_ten_processes_and_aba(pdf, tmp_path):
    expected = hashlib.sha256(pdf).hexdigest()
    assert expected == PDF_SHA256
    for number in range(10):
        scratch = tmp_path / str(number)
        scratch.mkdir()
        result = subprocess.run(
            [sys.executable, "-m", "evidence_engine.dossier.pdf_probe"],
            cwd=scratch,
            capture_output=True,
            timeout=120,
            check=True,
        )
        assert len(result.stdout) < 65536 and not result.stderr
        assert json.loads(result.stdout)["pdf_sha256"] == expected
    other = qualification_pdf(title="Título B sintético", text="Conteúdo B sintético")
    assert other != pdf
    assert qualification_pdf() == pdf


def test_pdfium_rasterization(pdf):
    import pypdfium2 as pdfium

    assert str(pdfium.PDFIUM_INFO) == "153.0.7999.0"
    fingerprints = []
    for _ in range(2):
        with pdfium.PdfDocument(pdf) as document:
            assert len(document) == 2
            current = []
            for page in document:
                bitmap = page.render(scale=2, fill_color=(255, 255, 255, 255), rev_byteorder=True)
                try:
                    image = bitmap.to_pil().convert("RGB")
                    assert image.size == (1191, 1684)
                    current.append(hashlib.sha256(image.tobytes()).hexdigest())
                finally:
                    bitmap.close()
                    page.close()
            fingerprints.append(current)
    assert fingerprints[0] == fingerprints[1]
    assert tuple(fingerprints[0]) == PIXEL_SHA256


def mutate_dictionary(pdf, dictionary, addition):
    """Test-only adversarial fixture: rebuild xref after inserting an invalid field."""
    reader = PdfReader(BytesIO(pdf), strict=True)
    target = reader.trailer.raw_get(dictionary).idnum
    offsets = [reader.xref[0][i] for i in range(1, reader.trailer["/Size"])]
    startxref = int(re.search(rb"startxref\s+(\d+)", pdf)[1])
    chunks = []
    for i, (a, b) in enumerate(zip(offsets, offsets[1:] + [startxref], strict=True), 1):
        chunk = pdf[a:b]
        if i == target:
            chunk = chunk.replace(b"<<", b"<< " + addition + b" ", 1)
        chunks.append(chunk)
    output = bytearray(pdf[: offsets[0]])
    new_offsets = []
    for chunk in chunks:
        new_offsets.append(len(output))
        output.extend(chunk)
    xref = len(output)
    output.extend(f"xref\n0 {len(chunks) + 1}\n0000000000 65535 f \n".encode())
    for offset in new_offsets:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    trailer = pdf[startxref:].split(b"trailer\n", 1)[1].split(b"startxref", 1)[0]
    output.extend(b"trailer\n" + trailer + f"startxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


@pytest.mark.parametrize(
    "dictionary,addition",
    [
        ("/Info", b"/Author (synthetic)"),
        ("/Info", b"/CreationDate (fixed)"),
        ("/Root", b"/Metadata << /Type /Metadata >>"),
        ("/Root", b"/OpenAction << /S /URI /URI (https://example.invalid) >>"),
        ("/Root", b"/Names << /EmbeddedFiles [] >>"),
        ("/Root", b"/AcroForm << >>"),
        ("/Root", b"/AF [<< /Type /Filespec >>]"),
    ],
)
def test_forbidden_pdf_content(pdf, dictionary, addition):
    with pytest.raises(EvidenceError, match="PDF_VALIDATION_FAILURE"):
        validate_pdf_bytes(mutate_dictionary(pdf, dictionary, addition), probe_expectation())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda b: b[:-12],
        lambda b: b + b"hidden",
        lambda b: b.replace(b"xref\n0 ", b"xxxx\n0 "),
        lambda b: b.replace(b"trailer\n<<", b"trailer\n<< /ID [] "),
    ],
)
def test_corrupt_pdf(pdf, mutation):
    with pytest.raises(EvidenceError, match="PDF_VALIDATION_FAILURE"):
        validate_pdf_bytes(mutation(pdf), probe_expectation())


def test_text_loss_and_wrong_destination(pdf):
    expected = probe_expectation()
    for changed in (
        replace(expected, page_text=("lost", expected.page_text[1])),
        replace(expected, links=((0, 0),)),
    ):
        with pytest.raises(EvidenceError, match="PDF_VALIDATION_FAILURE"):
            validate_pdf_bytes(pdf, changed)


def test_bounded_writer_and_pdf_limits(pdf, monkeypatch):
    monkeypatch.setattr(limits, "MAX_PDF_BYTES", 3)
    writer = limits.BoundedPdfBuffer()
    assert writer.write(b"123") == 3
    with pytest.raises(EvidenceError, match="RESOURCE_LIMIT"):
        writer.write(b"4")
    assert writer.getvalue() == b"123"
    with pytest.raises(EvidenceError, match="RESOURCE_LIMIT"):
        validate_pdf_bytes(pdf, probe_expectation())


def test_worker_memory_limit():
    code = (
        "from evidence_engine.dossier.pdf_limits import impose_worker_limits; "
        "import resource; impose_worker_limits(); "
        "assert resource.getrlimit(resource.RLIMIT_AS) == (1024**3, 1024**3)"
    )
    subprocess.run([sys.executable, "-c", code], check=True, timeout=10, capture_output=True)
    assert os.getuid() != 0


@pytest.mark.parametrize("attribute", ["PDFInfo", "PDFDocument", "PDFTrailer", "Canvas"])
def test_missing_adapter_symbol(monkeypatch, attribute):
    monkeypatch.setattr(adapter, attribute, None)
    with pytest.raises(EvidenceError, match="ENVIRONMENT_UNSUPPORTED"):
        adapter.verify_adapter_shape()


def test_font_bytes_guard(monkeypatch):
    original = Path.read_bytes

    def altered(path):
        if path == environment.ROOT / "fonts/DejaVuSans.ttf":
            return b"synthetic corruption"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", altered)
    with pytest.raises(EvidenceError, match="FONT_UNSUPPORTED"):
        environment.verify_environment()


def test_installed_artifact_guard(monkeypatch):
    original = Path.read_bytes

    def altered(path):
        if str(path).endswith("reportlab/pdfbase/pdfdoc.py"):
            return original(path) + b"\n# synthetic divergence"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", altered)
    with pytest.raises(EvidenceError, match="ENVIRONMENT_UNSUPPORTED"):
        environment.verify_environment()


@pytest.mark.parametrize(
    "old,new",
    [(b"/ToUnicode", b"/NoUnicode"), (b"/FontFile2", b"/FontFile3"), (b"/StemV", b"/OOPSX")],
)
def test_font_structure_loss(pdf, old, new):
    with pytest.raises(EvidenceError, match="PDF_VALIDATION_FAILURE"):
        validate_pdf_bytes(pdf.replace(old, new), probe_expectation())


def test_page_budget_boundary(pdf, monkeypatch):
    monkeypatch.setattr(limits, "MAX_PAGES", 2)
    validate_pdf_bytes(pdf, probe_expectation())
    monkeypatch.setattr(limits, "MAX_PAGES", 1)
    with pytest.raises(EvidenceError, match="RESOURCE_LIMIT"):
        validate_pdf_bytes(pdf, probe_expectation())


def test_worker_oom_is_bounded():
    code = (
        "from evidence_engine.dossier.pdf_limits import impose_worker_limits\n"
        "impose_worker_limits()\n"
        "try: bytearray(2 * 1024**3)\n"
        "except MemoryError: print('RESOURCE_LIMIT')\n"
        "else: raise AssertionError('unbounded allocation')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, timeout=10, check=True
    )
    assert result.stdout == b"RESOURCE_LIMIT\n" and not result.stderr
