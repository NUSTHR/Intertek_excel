import json
import shutil
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from app.adapters.pdf.mineru_parser import read_mineru_output
from app.ports.pdf_parser import ParsedPdfDocument, PdfParserRuntimeStatus

DEFAULT_MINERU_CLOUD_API_BASE_URL = "https://mineru.net/api/v4"
TERMINAL_STATES = {"done", "failed"}
IN_PROGRESS_STATES = {"waiting-file", "pending", "running", "converting"}


class MinerUCloudPdfParser:
    def __init__(
        self,
        *,
        api_base_url: str = DEFAULT_MINERU_CLOUD_API_BASE_URL,
        api_token: str = "",
        model_version: str = "vlm",
        timeout_seconds: float = 1_200.0,
        poll_interval_seconds: float = 5.0,
        language: str = "ch",
        enable_formula: bool = True,
        enable_table: bool = True,
        is_ocr: bool = False,
    ) -> None:
        self._api_base_url = api_base_url.rstrip("/") or DEFAULT_MINERU_CLOUD_API_BASE_URL
        self._api_token = api_token.strip()
        self._model_version = model_version.strip() or "vlm"
        self._timeout_seconds = max(30.0, timeout_seconds)
        self._poll_interval_seconds = max(1.0, poll_interval_seconds)
        self._language = language.strip() or "ch"
        self._enable_formula = enable_formula
        self._enable_table = enable_table
        self._is_ocr = is_ocr

    def parse(self, *, filename: str, content: bytes) -> ParsedPdfDocument:
        if not self._api_token:
            raise RuntimeError("MinerU cloud parsing is not configured with an API token.")
        with tempfile.TemporaryDirectory(prefix="mineru-cloud-") as temporary_dir:
            workspace = Path(temporary_dir)
            output_dir = workspace / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            data_id = _data_id_for_filename(filename)
            batch_id, upload_url = self._request_upload_url(filename=filename, data_id=data_id)
            self._upload_file(upload_url=upload_url, content=content)
            result = self._wait_for_result(
                batch_id=batch_id,
                filename=filename,
                data_id=data_id,
            )
            zip_url = str(result.get("full_zip_url") or "")
            if not zip_url:
                raise RuntimeError("MinerU cloud parsing completed without a result zip URL.")
            self._download_and_extract_zip(zip_url=zip_url, output_dir=output_dir)
            parsed = read_mineru_output(
                filename=filename,
                output_dir=output_dir,
                parser_name="MinerU Cloud",
                parser_backend="mineru-cloud",
                parser_version=self._model_version,
                extra_warnings=_warnings_from_cloud_result(result),
            )
            artifact_root = _copy_artifacts_to_handoff_dir(output_dir) if parsed.artifacts else None
            return replace(parsed, artifact_root=artifact_root)

    def runtime_status(self) -> PdfParserRuntimeStatus:
        return check_mineru_cloud_runtime(
            api_base_url=self._api_base_url,
            api_token=self._api_token,
            model_version=self._model_version,
        )

    def _request_upload_url(self, *, filename: str, data_id: str) -> tuple[str, str]:
        payload = {
            "files": [
                {
                    "name": Path(filename).name or "uploaded.pdf",
                    "data_id": data_id,
                    "is_ocr": self._is_ocr,
                }
            ],
            "model_version": self._model_version,
            "language": self._language,
            "enable_formula": self._enable_formula,
            "enable_table": self._enable_table,
        }
        response = self._request_json("POST", "/file-urls/batch", payload=payload)
        data = _expect_data_object(response)
        batch_id = str(data.get("batch_id") or "").strip()
        file_urls = data.get("file_urls")
        upload_url = ""
        if isinstance(file_urls, list) and file_urls:
            upload_url = str(file_urls[0] or "").strip()
        if not batch_id or not upload_url:
            raise RuntimeError("MinerU cloud did not return a batch id and upload URL.")
        return batch_id, upload_url

    def _upload_file(self, *, upload_url: str, content: bytes) -> None:
        request = Request(upload_url, data=content, method="PUT")
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                if response.status not in {200, 201, 204}:
                    raise RuntimeError(f"MinerU cloud upload failed with HTTP {response.status}.")
        except HTTPError as exc:
            raise RuntimeError(f"MinerU cloud upload failed with HTTP {exc.code}.") from exc
        except URLError as exc:
            raise RuntimeError(f"MinerU cloud upload failed: {exc.reason}") from exc

    def _wait_for_result(
        self,
        *,
        batch_id: str,
        filename: str,
        data_id: str,
    ) -> dict[str, object]:
        deadline = time.monotonic() + self._timeout_seconds
        last_state = "pending"
        last_error = ""
        while time.monotonic() < deadline:
            response = self._request_json("GET", f"/extract-results/batch/{batch_id}")
            data = _expect_data_object(response)
            result = _matching_extract_result(
                data.get("extract_result"),
                filename=filename,
                data_id=data_id,
            )
            if result is not None:
                last_state = str(result.get("state") or "").strip().lower()
                last_error = str(result.get("err_msg") or "").strip()
                if last_state == "done":
                    return result
                if last_state == "failed":
                    raise RuntimeError(
                        f"MinerU cloud parsing failed: {last_error or 'unknown error'}"
                    )
            time.sleep(self._poll_interval_seconds)
        raise RuntimeError(
            "MinerU cloud parsing timed out"
            f" after {int(self._timeout_seconds)} seconds; last state: {last_state}"
            + (f"; last error: {last_error}" if last_error else "")
        )

    def _download_and_extract_zip(self, *, zip_url: str, output_dir: Path) -> None:
        archive_path = output_dir.parent / "mineru-cloud-result.zip"
        request = Request(zip_url, method="GET", headers={"Accept": "application/zip,*/*"})
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"MinerU cloud result download failed with HTTP {response.status}."
                    )
                archive_path.write_bytes(response.read())
        except HTTPError as exc:
            raise RuntimeError(
                f"MinerU cloud result download failed with HTTP {exc.code}."
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"MinerU cloud result download failed: {exc.reason}") from exc
        try:
            with ZipFile(archive_path) as archive:
                _extract_zip_safely(archive, output_dir)
        except BadZipFile as exc:
            raise RuntimeError("MinerU cloud result was not a valid zip archive.") from exc

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self._api_base_url}{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._api_token}",
                **({"Content-Type": "application/json"} if payload is not None else {}),
            },
        )
        try:
            with urlopen(request, timeout=min(self._timeout_seconds, 120.0)) as response:
                body = response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")[:300]
            raise RuntimeError(
                f"MinerU cloud API request failed with HTTP {exc.code}: {body}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"MinerU cloud API request failed: {exc.reason}") from exc
        try:
            decoded = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("MinerU cloud API returned non-JSON response.") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("MinerU cloud API returned an unexpected response.")
        code = decoded.get("code")
        if code not in {0, "0", 200, "200"}:
            message = str(decoded.get("msg") or decoded.get("message") or "unknown error")
            raise RuntimeError(f"MinerU cloud API error {code}: {message}")
        return decoded


def check_mineru_cloud_runtime(
    *,
    api_base_url: str,
    api_token: str,
    model_version: str,
) -> PdfParserRuntimeStatus:
    if not api_token.strip():
        return PdfParserRuntimeStatus(
            backend="mineru-cloud",
            available=False,
            command=api_base_url.rstrip("/") or DEFAULT_MINERU_CLOUD_API_BASE_URL,
            version=model_version or None,
            detail=(
                "MinerU Cloud API token is not configured. Set MINERU_CLOUD_API_TOKEN "
                "or map your MinerU API token into that variable."
            ),
        )
    return PdfParserRuntimeStatus(
        backend="mineru-cloud",
        available=True,
        command=api_base_url.rstrip("/") or DEFAULT_MINERU_CLOUD_API_BASE_URL,
        version=model_version or None,
        detail=(
            "MinerU Cloud API is configured. The profile uses the official v4 "
            "file upload, batch polling, and result zip workflow."
        ),
    )


def _expect_data_object(response: dict[str, object]) -> dict[str, object]:
    data = response.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("MinerU cloud API response did not include a data object.")
    return data


def _matching_extract_result(
    value: object,
    *,
    filename: str,
    data_id: str,
) -> dict[str, object] | None:
    if not isinstance(value, list):
        return None
    fallback: dict[str, object] | None = None
    target_name = Path(filename).name
    for item in value:
        if not isinstance(item, dict):
            continue
        if fallback is None:
            fallback = item
        if str(item.get("data_id") or "") == data_id:
            return item
        if str(item.get("file_name") or "") == target_name:
            return item
    return fallback


def _warnings_from_cloud_result(result: dict[str, object]) -> list[str]:
    warnings: list[str] = []
    progress = result.get("extract_progress")
    if isinstance(progress, dict):
        total_pages = progress.get("total_pages")
        extracted_pages = progress.get("extracted_pages")
        if total_pages is not None and extracted_pages is not None:
            warnings.append(
                "MinerU Cloud progress reported "
                f"{extracted_pages}/{total_pages} pages before completion."
            )
    return warnings


def _extract_zip_safely(archive: ZipFile, output_dir: Path) -> None:
    output_root = output_dir.resolve()
    for member in archive.infolist():
        member_path = Path(member.filename)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise RuntimeError("MinerU cloud result zip contained an unsafe path.")
        destination = (output_root / member.filename).resolve()
        if not destination.is_relative_to(output_root):
            raise RuntimeError("MinerU cloud result zip contained an unsafe path.")
        if member.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, destination.open("wb") as target:
            shutil.copyfileobj(source, target)


def _copy_artifacts_to_handoff_dir(output_dir: Path) -> str:
    handoff_root = Path(tempfile.mkdtemp(prefix="mineru-cloud-artifacts-"))
    shutil.copytree(output_dir, handoff_root, dirs_exist_ok=True)
    return handoff_root.as_posix()


def _data_id_for_filename(filename: str) -> str:
    safe_name = "".join(
        char if char.isalnum() or char in {"_", "-", "."} else "_"
        for char in Path(filename).name
    )
    return f"pdf_{safe_name[:80]}_{int(time.time() * 1000)}"
