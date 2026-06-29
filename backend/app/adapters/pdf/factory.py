from app.adapters.pdf.fake_parser import FakePdfParser
from app.adapters.pdf.mineru_parser import MinerUPdfParser, check_mineru_runtime
from app.core.config import Settings
from app.ports.pdf_parser import PdfParser, PdfParserRuntimeStatus


def create_pdf_parser(settings: Settings) -> PdfParser:
    backend = settings.pdf_parser_backend.strip().lower()
    if backend == "mineru":
        return MinerUPdfParser(
            command=settings.mineru_command,
            timeout_seconds=settings.mineru_timeout_seconds,
        )
    return FakePdfParser()


def get_pdf_parser_status(settings: Settings) -> PdfParserRuntimeStatus:
    backend = settings.pdf_parser_backend.strip().lower()
    if backend == "mineru":
        return check_mineru_runtime(command=settings.mineru_command)
    if backend == "fake":
        return PdfParserRuntimeStatus(
            backend="fake",
            available=True,
            detail="Fake PDF parser is active for local development and tests.",
        )
    return PdfParserRuntimeStatus(
        backend=backend or "unknown",
        available=False,
        detail=f"Unsupported PDF parser backend '{settings.pdf_parser_backend}'.",
    )
