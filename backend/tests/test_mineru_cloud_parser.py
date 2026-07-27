import io
import json
from pathlib import Path
from zipfile import ZipFile

from app.adapters.pdf.mineru_cloud_parser import MinerUCloudPdfParser, check_mineru_cloud_runtime


def test_mineru_cloud_runtime_requires_api_token() -> None:
    status = check_mineru_cloud_runtime(
        api_base_url="https://mineru.net/api/v4",
        api_token="",
        model_version="vlm",
    )

    assert status.backend == "mineru-cloud"
    assert status.available is False
    assert "API token is not configured" in status.detail


def test_mineru_cloud_parser_uploads_polls_and_reads_result_zip(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    zip_payload = _zip_bytes(
        {
            "full.md": "# Cloud PDF\n\nTraceable evidence.",
            "full_middle.json": '{"total_pages": 1}',
        }
    )

    def fake_urlopen(request, timeout):
        method = request.get_method()
        url = request.full_url
        calls.append((method, url))
        if method == "POST" and url.endswith("/file-urls/batch"):
            return FakeResponse(
                json.dumps(
                    {
                        "code": 0,
                        "data": {
                            "batch_id": "batch-1",
                            "file_urls": ["https://upload.example.test/file"],
                        },
                        "msg": "ok",
                    }
                ).encode("utf-8")
            )
        if method == "PUT" and url == "https://upload.example.test/file":
            assert request.data == b"%PDF-test"
            return FakeResponse(b"", status=200)
        if method == "GET" and url.endswith("/extract-results/batch/batch-1"):
            return FakeResponse(
                json.dumps(
                    {
                        "code": 0,
                        "data": {
                            "batch_id": "batch-1",
                            "extract_result": [
                                {
                                    "file_name": "cloud.pdf",
                                    "data_id": "pdf_cloud.pdf_123",
                                    "state": "done",
                                    "err_msg": "",
                                    "full_zip_url": "https://cdn.example.test/result.zip",
                                }
                            ],
                        },
                        "msg": "ok",
                    }
                ).encode("utf-8")
            )
        if method == "GET" and url == "https://cdn.example.test/result.zip":
            return FakeResponse(zip_payload)
        raise AssertionError(f"unexpected request {method} {url}")

    monkeypatch.setattr("app.adapters.pdf.mineru_cloud_parser.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "app.adapters.pdf.mineru_cloud_parser._data_id_for_filename",
        lambda filename: "pdf_cloud.pdf_123",
    )
    parser = MinerUCloudPdfParser(
        api_token="token-for-test",
        timeout_seconds=30,
        poll_interval_seconds=1,
    )

    parsed = parser.parse(filename="cloud.pdf", content=b"%PDF-test")

    assert parsed.parser_backend == "mineru-cloud"
    assert parsed.parser_version == "vlm"
    assert parsed.page_count == 1
    assert [chunk.text for chunk in parsed.chunks] == ["# Cloud PDF", "Traceable evidence."]
    assert parsed.artifact_root is not None
    assert (Path(parsed.artifact_root) / "full.md").is_file()
    assert [method for method, _ in calls] == ["POST", "PUT", "GET", "GET"]


class FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()
