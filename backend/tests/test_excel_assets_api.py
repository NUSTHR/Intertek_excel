from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.adapters.storage.filesystem_storage import FilesystemExcelArtifactStorage
from app.adapters.workbook.openpyxl_reader import OpenpyxlWorkbookReader
from app.api.dependencies import (
    get_current_user,
    get_excel_asset_service,
    get_upload_task_service,
    get_upload_task_worker,
    require_admin_user,
)
from app.api.routes import excel_assets
from app.application.excel_assets.service import ExcelAssetService
from app.application.excel_assets.upload_tasks import UploadTaskService, UploadTaskWorker
from app.domain.models import AuthenticatedUser, UserRole
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
    upload_tasks = UploadTaskService(
        repository=repository,
        storage_root=tmp_path / "storage",
    )
    upload_worker = UploadTaskWorker(
        repository=repository,
        excel_assets=service,
        storage_root=tmp_path / "storage",
        poll_interval_seconds=0.1,
    )
    app.dependency_overrides[get_excel_asset_service] = lambda: service
    app.dependency_overrides[get_upload_task_service] = lambda: upload_tasks
    app.dependency_overrides[get_upload_task_worker] = lambda: upload_worker
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


def test_api_upload_reader_uses_configured_size_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeUpload:
        filename = "guarded.xlsx"
        requested_size = 0

        async def read(self, size: int = -1) -> bytes:
            self.requested_size = size
            return b"content"

    monkeypatch.setattr(
        excel_assets,
        "get_settings",
        lambda: SimpleNamespace(excel_max_upload_bytes=4),
    )
    upload = FakeUpload()

    content = _run_async(excel_assets._read_upload_content(upload))  # noqa: SLF001

    assert content == b"content"
    assert upload.requested_size == 5


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


def test_api_upload_task_creates_background_parse_result(
    client: TestClient,
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "standards.xlsx"
    _write_xlsx_fixture(workbook_path)

    with workbook_path.open("rb") as workbook_file:
        create_response = client.post(
            "/api/excel/files/upload-tasks",
            files={
                "file": (
                    "standards.xlsx",
                    workbook_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]
    queued_response = client.get(f"/api/excel/files/upload-tasks/{task_id}")
    assert queued_response.status_code == 200
    assert queued_response.json()["status"] == "queued"

    worker = app.dependency_overrides[get_upload_task_worker]()
    assert worker.run_once() is True

    ready_response = client.get(f"/api/excel/files/upload-tasks/{task_id}")
    assert ready_response.status_code == 200
    ready = ready_response.json()
    assert ready["status"] == "ready"
    assert ready["result"]["file"]["display_name"] == "standards.xlsx"
    assert ready["result"]["sheets"][0]["sheet_name"] == "Standards"


def test_api_upload_task_preserves_duplicate_confirmation(
    client: TestClient,
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "standards.xlsx"
    _write_xlsx_fixture(workbook_path)
    with workbook_path.open("rb") as workbook_file:
        assert client.post(
            "/api/excel/files",
            files={
                "file": (
                    "standards.xlsx",
                    workbook_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        ).status_code == 200

    with workbook_path.open("rb") as workbook_file:
        duplicate_response = client.post(
            "/api/excel/files/upload-tasks",
            files={
                "file": (
                    "standards.xlsx",
                    workbook_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["requires_confirmation"] is True


def test_api_upload_task_records_failure_and_cleans_staging(client: TestClient) -> None:
    create_response = client.post(
        "/api/excel/files/upload-tasks",
        files={
            "file": (
                "broken.xlsx",
                b"not a real workbook",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]
    task = app.dependency_overrides[get_upload_task_service]().get_task(
        task_id,
        user_id=admin_user().user_id,
    )
    staging_path = Path(task.staging_path)
    assert staging_path.exists()

    worker = app.dependency_overrides[get_upload_task_worker]()
    assert worker.run_once() is True

    failed_response = client.get(f"/api/excel/files/upload-tasks/{task_id}")
    assert failed_response.status_code == 200
    failed = failed_response.json()
    assert failed["status"] == "failed"
    assert failed["error_message"]
    assert not staging_path.exists()
    assert not staging_path.parent.exists()


def test_api_upload_task_worker_rejects_tampered_staging_path(
    client: TestClient,
    tmp_path: Path,
) -> None:
    external_file = tmp_path / "outside.xlsx"
    external_file.write_bytes(b"do not touch")
    create_response = client.post(
        "/api/excel/files/upload-tasks",
        files={
            "file": (
                "broken.xlsx",
                b"not a real workbook",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    repository = app.dependency_overrides[get_upload_task_service]()._repository
    with repository._connect() as connection:
        connection.execute(
            """
            UPDATE excel_upload_tasks
            SET staging_path = ?
            WHERE task_id = ?
            """,
            (str(external_file), task_id),
        )

    worker = app.dependency_overrides[get_upload_task_worker]()
    assert worker.run_once() is True

    failed_response = client.get(f"/api/excel/files/upload-tasks/{task_id}")
    assert failed_response.status_code == 200
    failed = failed_response.json()
    assert failed["status"] == "failed"
    assert "staging path is invalid" in failed["error_message"]
    assert external_file.read_bytes() == b"do not touch"


def test_api_upload_task_requires_owner(client: TestClient, tmp_path: Path) -> None:
    workbook_path = tmp_path / "standards.xlsx"
    _write_xlsx_fixture(workbook_path)

    with workbook_path.open("rb") as workbook_file:
        create_response = client.post(
            "/api/excel/files/upload-tasks",
            files={
                "file": (
                    "standards.xlsx",
                    workbook_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    app.dependency_overrides[require_admin_user] = lambda: AuthenticatedUser(
        user_id="other_admin_test",
        email="other-admin@example.com",
        role=UserRole.ADMIN,
        created_at="2026-01-01T00:00:00+00:00",
    )
    try:
        forbidden_response = client.get(f"/api/excel/files/upload-tasks/{task_id}")
    finally:
        app.dependency_overrides[require_admin_user] = admin_user

    assert forbidden_response.status_code == 404


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


def _run_async(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as exc:
        return exc.value
    raise AssertionError("coroutine did not finish synchronously")
