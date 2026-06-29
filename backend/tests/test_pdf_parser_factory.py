from app.adapters.pdf.factory import get_pdf_parser_status
from app.core.config import Settings


def test_fake_pdf_parser_status_is_available() -> None:
    status = get_pdf_parser_status(Settings(pdf_parser_backend="fake"))

    assert status.backend == "fake"
    assert status.available is True
    assert status.command is None
    assert "Fake PDF parser" in status.detail


def test_missing_mineru_command_reports_unavailable() -> None:
    status = get_pdf_parser_status(
        Settings(
            pdf_parser_backend="mineru",
            mineru_command="definitely_missing_mineru_for_tests_000000",
        )
    )

    assert status.backend == "mineru"
    assert status.available is False
    assert status.command == "definitely_missing_mineru_for_tests_000000"
    assert "not found" in status.detail


def test_unknown_pdf_parser_backend_reports_unavailable() -> None:
    status = get_pdf_parser_status(Settings(pdf_parser_backend="remote"))

    assert status.backend == "remote"
    assert status.available is False
    assert "Unsupported PDF parser backend" in status.detail
