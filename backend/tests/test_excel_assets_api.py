from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.adapters.storage.filesystem_storage import FilesystemExcelArtifactStorage
from app.adapters.workbook.openpyxl_reader import OpenpyxlWorkbookReader
from app.api.dependencies import get_current_user, get_excel_asset_service, require_admin_user
from app.api.routes import excel_assets
from app.application.excel_assets.service import ExcelAssetService
from app.main import app
from tests.auth_helpers import admin_user


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    service = ExcelAssetService(
        repository=repository,
        storage=FilesystemExcelArtifactStorage(tmp_path / "storage"),
        workbook_reader=OpenpyxlWorkbookReader(),
    )
    service.initialize()
    app.dependency_overrides[get_excel_asset_service] = lambda: service
    app.dependency_overrides[get_current_user] = admin_user
    app.dependency_overrides[require_admin_user] = admin_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_api_rejects_unsupported_extension(client: TestClient) -> None:
    response = client.post(
        "/api/excel/files",
        files={
            "file": (
                "notes.txt",
                b"not a workbook",
                "text/plain",
            )
        },
    )

    assert response.status_code == 400
    assert "unsupported Excel file extension" in response.json()["detail"]


def test_api_rejects_oversized_upload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        excel_assets,
        "get_settings",
        lambda: SimpleNamespace(
            excel_max_upload_bytes=4,
            supported_excel_extensions=(".xls", ".xlsx", ".xlsm", ".xltx", ".xltm"),
        ),
    )

    response = client.post(
        "/api/excel/files",
        files={
            "file": (
                "standards.xlsx",
                b"too large",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 400
    assert "exceeds the 4 byte limit" in response.json()["detail"]


def test_api_upload_and_near_term_read_endpoints(client: TestClient, tmp_path: Path) -> None:
    workbook_path = tmp_path / "standards.xlsx"
    _write_xlsx_fixture(workbook_path)

    with workbook_path.open("rb") as workbook_file:
        upload_response = client.post(
            "/api/excel/files",
            files={
                "file": (
                    "standards.xlsx",
                    workbook_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert upload_response.status_code == 200
    upload = upload_response.json()
    file_id = upload["file"]["file_id"]
    version_id = upload["version"]["version_id"]
    sheet_id = upload["sheets"][0]["sheet_id"]

    active_response = client.get(f"/api/excel/files/{file_id}/active")
    profile_response = client.get(f"/api/excel/versions/{version_id}/profile")
    artifacts_response = client.get(f"/api/excel/versions/{version_id}/artifacts")
    rows_response = client.get(f"/api/excel/sheets/{sheet_id}/rows?offset=1&limit=1")
    search_response = client.get(
        f"/api/excel/sheets/{sheet_id}/search?query=60335&limit=5"
    )
    version_search_response = client.get(
        f"/api/excel/versions/{version_id}/search?query=narration&limit=5"
    )

    assert active_response.status_code == 200
    assert active_response.json()["version"]["version_id"] == version_id

    assert profile_response.status_code == 200
    assert profile_response.json()["sheets"][0]["candidate_header"] == [
        "Code",
        "日期",
    ]

    assert artifacts_response.status_code == 200
    assert {
        artifact["artifact_type"]
        for artifact in artifacts_response.json()["artifacts"]
    } == {"original", "raw_csv", "profile", "row_mapping"}

    assert rows_response.status_code == 200
    rows = rows_response.json()
    assert rows["total_rows"] == 2
    assert rows["rows"][0]["mapping"]["row_id"] == "S001_R2"
    assert rows["rows"][0]["row"] == ["S001_R2", "EN 60335-1:2023", "2024-01-01"]

    assert search_response.status_code == 200
    search = search_response.json()
    assert search["total_matches"] == 1
    assert search["matches"][0]["mapping"]["row_id"] == "S001_R2"
    assert search["matches"][0]["matched_columns"] == [1]

    assert version_search_response.status_code == 200
    version_search = version_search_response.json()
    assert version_search["total_matches"] == 1
    assert version_search["matches"][0]["sheet"]["sheet_name"] == "Script"
    assert version_search["matches"][0]["matched_columns"] == [2]


def test_api_failed_replacement_keeps_previous_active_version(
    client: TestClient,
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "standards.xlsx"
    _write_xlsx_fixture(workbook_path)

    with workbook_path.open("rb") as workbook_file:
        first_response = client.post(
            "/api/excel/files",
            files={
                "file": (
                    "standards.xlsx",
                    workbook_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert first_response.status_code == 200
    first = first_response.json()

    failed_response = client.post(
        "/api/excel/files",
        data={"replace_existing": "true"},
        files={
            "file": (
                "standards.xlsx",
                b"not a real workbook",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert failed_response.status_code == 400

    file_id = first["file"]["file_id"]
    active_response = client.get(f"/api/excel/files/{file_id}/active")
    versions_response = client.get(f"/api/excel/files/{file_id}/versions")

    assert active_response.json()["version"]["version_id"] == first["version"]["version_id"]
    assert sorted(version["status"] for version in versions_response.json()["versions"]) == [
        "failed",
        "ready",
    ]


def test_api_rename_file_updates_list_and_detail(
    client: TestClient,
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "standards.xlsx"
    _write_xlsx_fixture(workbook_path)

    with workbook_path.open("rb") as workbook_file:
        upload_response = client.post(
            "/api/excel/files",
            files={
                "file": (
                    "standards.xlsx",
                    workbook_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert upload_response.status_code == 200
    file_id = upload_response.json()["file"]["file_id"]

    rename_response = client.patch(
        f"/api/excel/files/{file_id}",
        json={"display_name": "standards-renamed.xlsx"},
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["display_name"] == "standards-renamed.xlsx"

    detail_response = client.get(f"/api/excel/files/{file_id}")
    list_response = client.get("/api/excel/files")

    assert detail_response.json()["display_name"] == "standards-renamed.xlsx"
    assert list_response.json()["files"][0]["display_name"] == "standards-renamed.xlsx"


def test_api_delete_file_requires_confirmation_and_soft_deletes_from_management(
    client: TestClient,
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "standards.xlsx"
    _write_xlsx_fixture(workbook_path)

    with workbook_path.open("rb") as workbook_file:
        upload_response = client.post(
            "/api/excel/files",
            files={
                "file": (
                    "standards.xlsx",
                    workbook_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert upload_response.status_code == 200
    file_id = upload_response.json()["file"]["file_id"]

    confirmation_response = client.delete(f"/api/excel/files/{file_id}")
    assert confirmation_response.status_code == 409
    assert confirmation_response.json()["requires_confirmation"] is True

    delete_response = client.delete(f"/api/excel/files/{file_id}?confirm_delete=true")
    assert delete_response.status_code == 200
    deleted = delete_response.json()
    assert deleted["file_id"] == file_id
    assert deleted["deleted_versions"] == 0
    assert deleted["deleted_sheets"] == 0
    assert deleted["deleted_artifacts"] == 0

    missing_response = client.get(f"/api/excel/files/{file_id}")
    assert missing_response.status_code == 404

    list_response = client.get("/api/excel/files")
    assert list_response.status_code == 200
    assert list_response.json()["files"] == []


def _write_xlsx_fixture(path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Standards"
    worksheet.append(["Code", "日期"])
    worksheet.append(["EN 60335-1:2023", "2024-01-01"])
    script_sheet = workbook.create_sheet("Script")
    script_sheet.append(["Scene", "Voiceover"])
    script_sheet.append(["Opening", "Narration line"])
    workbook.save(path)
