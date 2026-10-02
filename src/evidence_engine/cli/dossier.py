"""Explicit dossier assembly CLI; no case option, discovery or diagnostic payload."""

from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from typer.core import TyperCommand

from evidence_engine.dossier.pdf_worker import safe_error_code as pdf_error_code
from evidence_engine.dossier.service import assemble_dossier, safe_error_code
from evidence_engine.errors import EvidenceError

app = typer.Typer(
    help="Assemble an explicitly selected dossier into a new directory.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


def _explicit_path(value: str) -> Path:
    # Check the spelling before Path discards dot/empty components. Native
    # Windows separators are permitted for CLI host paths, never input_reference.
    text = value.replace("\\", "/")
    parts = text.split("/")
    if text.startswith("/"):
        parts = parts[1:]
    if not value or any(part in ("", ".", "..") for part in parts):
        raise EvidenceError("DOSSIER_INVALID_PATH")
    return Path(value)


@app.command("assemble")
def assemble(
    selection: Annotated[str, typer.Option("--selection", help="Explicit local selection JSON.")],
    output_dir: Annotated[
        str, typer.Option("--output-dir", help="New directory under an existing parent.")
    ],
) -> None:
    try:
        assemble_dossier(
            selection_path=_explicit_path(selection), output_dir=_explicit_path(output_dir)
        )
    except Exception as error:
        # Bytes preserve the contracted LF even on native Windows text streams.
        typer.echo(("ERROR: " + safe_error_code(error) + "\n").encode("ascii"), err=True, nl=False)
        raise typer.Exit(2) from None
    typer.echo(b"DOSSIER_ASSEMBLY_OK\n", nl=False)


def _pdf_failure(error: BaseException) -> NoReturn:
    typer.echo(("ERROR: " + pdf_error_code(error) + "\n").encode("ascii"), err=True, nl=False)
    raise typer.Exit(2) from None


class _PdfCommand(TyperCommand):
    """Closed syntax/diagnostics for PDF only; assemble retains its existing CLI."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        if args == ["--help"]:
            return super().parse_args(ctx, args)
        seen: set[str] = set()
        index = 0
        while index < len(args):
            token = args[index]
            option, separator, value = token.partition("=")
            if option not in ("--input-package", "--output-dir") or option in seen:
                _pdf_failure(EvidenceError("DOSSIER_PDF_INVALID_PACKAGE"))
            seen.add(option)
            if not separator:
                index += 1
                if index == len(args):
                    _pdf_failure(EvidenceError("DOSSIER_PDF_INVALID_PACKAGE"))
                value = args[index]
            if not value or value.startswith("-"):
                _pdf_failure(EvidenceError("DOSSIER_PDF_INVALID_PACKAGE"))
            index += 1
        if seen != {"--input-package", "--output-dir"}:
            _pdf_failure(EvidenceError("DOSSIER_PDF_INVALID_PACKAGE"))
        try:
            return super().parse_args(ctx, args)
        except Exception:
            _pdf_failure(EvidenceError("DOSSIER_PDF_INVALID_PACKAGE"))

    def invoke(self, ctx: Any) -> Any:
        try:
            return super().invoke(ctx)
        except Exception as error:
            _pdf_failure(error)


@app.command("pdf", cls=_PdfCommand)
def pdf(
    input_package: Annotated[
        str, typer.Option("--input-package", help="Explicit read-only directory-v1 package.")
    ],
    output_dir: Annotated[
        str, typer.Option("--output-dir", help="New PDF directory under an existing parent.")
    ],
) -> None:
    from evidence_engine.dossier.pdf_service import export_dossier_pdf

    try:
        source = _explicit_path(input_package)
        destination = _explicit_path(output_dir)
    except EvidenceError:
        raise EvidenceError("DOSSIER_PDF_INVALID_PACKAGE") from None
    export_dossier_pdf(input_package=source, output_dir=destination)
    typer.echo(b"DOSSIER_PDF_OK\n", nl=False)
