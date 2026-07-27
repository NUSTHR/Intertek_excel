from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.adapters.llm.fake_llm_client import FakeLlmClient
from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.adapters.storage.filesystem_storage import FilesystemExcelArtifactStorage
from app.adapters.workbook.openpyxl_reader import OpenpyxlWorkbookReader
from app.api.dependencies import (
    get_auth_service,
    get_chat_service,
    get_document_summary_service,
    get_excel_asset_service,
    get_llm_preference_service,
)
from app.application.auth.rate_limit import AuthenticationRateLimiter
from app.application.auth.service import AuthService
from app.application.chat.service import ChatService
from app.application.document_summaries.service import DocumentSummaryService
from app.application.excel_assets.service import ExcelAssetService
from app.application.llm_preferences import WorkspaceLlmPreferenceService
from app.core.auth import normalize_email
from app.core.config import Settings
from app.core.errors import AuthenticationError, RateLimitError
from app.main import app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    excel_assets = ExcelAssetService(
        repository=repository,
        storage=FilesystemExcelArtifactStorage(tmp_path / "storage"),
        workbook_reader=OpenpyxlWorkbookReader(),
    )
    excel_assets.initialize()
    llm_client = FakeLlmClient()
    llm_preferences = WorkspaceLlmPreferenceService(
        repository=repository,
        settings=Settings(_env_file=None),
    )
    summaries = DocumentSummaryService(
        excel_assets=excel_assets,
        llm_client=llm_client,
        repository=repository,
        llm_preferences=llm_preferences,
    )
    chat = ChatService(
        excel_assets=excel_assets,
        summaries=summaries,
        llm_client=llm_client,
        sessions=repository,
        llm_preferences=llm_preferences,
    )
    auth = AuthService(
        repository=repository,
        admin_email="admin@qq.com",
        admin_password="admin",
        session_ttl_hours=24,
        password_reset_ttl_minutes=30,
        password_hash_iterations=1_000,
        login_rate_limiter=AuthenticationRateLimiter(
            max_failed_attempts=3,
            window_seconds=60,
            repository=repository,
        ),
    )
    auth.initialize()
    app.dependency_overrides[get_excel_asset_service] = lambda: excel_assets
    app.dependency_overrides[get_document_summary_service] = lambda: summaries
    app.dependency_overrides[get_chat_service] = lambda: chat
    app.dependency_overrides[get_llm_preference_service] = lambda: llm_preferences
    app.dependency_overrides[get_auth_service] = lambda: auth
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_admin_can_login_and_member_cannot_manage_files(
    client: TestClient,
    tmp_path: Path,
) -> None:
    admin_auth = _login(client, "admin@qq.com", "admin")
    member_auth = _register(client, "analyst@example.com", "member-pass-123")

    workbook_path = tmp_path / "standards.xlsx"
    _write_xlsx_fixture(workbook_path)
    with workbook_path.open("rb") as workbook_file:
        upload_response = client.post(
            "/api/excel/files",
            headers=admin_auth,
            files={
                "file": (
                    "standards.xlsx",
                    workbook_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert upload_response.status_code == 200
    assert upload_response.json()["file"]["display_name"] == "standards.xlsx"

    member_upload_response = client.post(
        "/api/excel/files",
        headers=member_auth,
        files={
            "file": (
                "member.xlsx",
                b"not relevant",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert member_upload_response.status_code == 403

    shared_files_response = client.get("/api/excel/files", headers=member_auth)
    assert shared_files_response.status_code == 200
    assert shared_files_response.json()["files"][0]["display_name"] == "standards.xlsx"


def test_admin_can_hide_files_from_members(
    client: TestClient,
    tmp_path: Path,
) -> None:
    admin_auth = _login(client, "admin@qq.com", "admin")
    member_auth = _register(client, "visibility@example.com", "member-pass-123")

    workbook_path = tmp_path / "restricted.xlsx"
    _write_xlsx_fixture(workbook_path)
    with workbook_path.open("rb") as workbook_file:
        upload_response = client.post(
            "/api/excel/files",
            headers=admin_auth,
            files={
                "file": (
                    "restricted.xlsx",
                    workbook_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    assert upload_response.status_code == 200
    file_id = upload_response.json()["file"]["file_id"]
    assert upload_response.json()["file"]["visible_to_members"] is True

    hide_response = client.patch(
        f"/api/excel/files/{file_id}/visibility",
        headers=admin_auth,
        json={"visible_to_members": False},
    )
    assert hide_response.status_code == 200
    assert hide_response.json()["visible_to_members"] is False

    member_files_response = client.get("/api/excel/files", headers=member_auth)
    assert member_files_response.status_code == 200
    assert member_files_response.json()["files"] == []

    member_file_response = client.get(f"/api/excel/files/{file_id}", headers=member_auth)
    assert member_file_response.status_code == 404

    admin_files_response = client.get("/api/excel/files", headers=admin_auth)
    assert admin_files_response.status_code == 200
    assert admin_files_response.json()["files"][0]["file_id"] == file_id


def test_llm_preferences_are_global_and_admin_managed(client: TestClient) -> None:
    admin_auth = _login(client, "admin@qq.com", "admin")
    member_auth = _register(client, "model-user@example.com", "member-pass-123")

    save_response = client.patch(
        "/api/excel/llm/preferences",
        headers=admin_auth,
        json={
            "summary_provider": "siliconflow",
            "summary_model": "Qwen/Qwen3.6-27B",
            "router_provider": "deepseek",
            "router_model": "deepseek-v4-flash",
            "answer_provider": "siliconflow",
            "answer_model": "deepseek-ai/DeepSeek-V4-Pro",
        },
    )
    assert save_response.status_code == 200
    saved = save_response.json()

    member_read_response = client.get("/api/excel/llm/preferences", headers=member_auth)
    assert member_read_response.status_code == 200
    assert member_read_response.json() == saved

    member_options_response = client.get("/api/excel/llm/options", headers=member_auth)
    assert member_options_response.status_code == 200
    assert member_options_response.json()["defaults"]["router_model"] == "deepseek-v4-flash"

    member_save_response = client.patch(
        "/api/excel/llm/preferences",
        headers=member_auth,
        json={
            "summary_provider": "deepseek",
            "summary_model": "deepseek-v4-pro",
            "router_provider": "siliconflow",
            "router_model": "Qwen/Qwen3.6-35B-A3B",
            "answer_provider": "deepseek",
            "answer_model": "deepseek-v4-pro",
        },
    )
    assert member_save_response.status_code == 403


def test_register_login_me_logout_and_password_reset(client: TestClient) -> None:
    auth_header = _register(client, "reset@example.com", "old-pass-123")

    me_response = client.get("/api/auth/me", headers=auth_header)
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "reset@example.com"
    assert me_response.json()["role"] == "member"

    forgot_response = client.post(
        "/api/auth/password/forgot",
        json={"email": "reset@example.com"},
    )
    assert forgot_response.status_code == 200
    reset_token = forgot_response.json()["reset_token"]
    assert reset_token

    reset_response = client.post(
        "/api/auth/password/reset",
        json={"token": reset_token, "new_password": "new-pass-456"},
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["user"]["email"] == "reset@example.com"

    old_login_response = client.post(
        "/api/auth/login",
        json={"email": "reset@example.com", "password": "old-pass-123"},
    )
    assert old_login_response.status_code == 401

    new_auth_header = _login(client, "reset@example.com", "new-pass-456")
    logout_response = client.post("/api/auth/logout", headers=new_auth_header)
    assert logout_response.status_code == 204
    logged_out_me_response = client.get("/api/auth/me", headers=new_auth_header)
    assert logged_out_me_response.status_code == 401


def test_browser_session_uses_http_only_cookie_and_csrf(client: TestClient) -> None:
    login_response = client.post(
        "/api/auth/login",
        json={"email": "admin@qq.com", "password": "admin"},
    )
    assert login_response.status_code == 200

    session_cookie = client.cookies.get("excelai_session")
    csrf_cookie = client.cookies.get("excelai_csrf")
    assert session_cookie
    assert csrf_cookie
    assert "httponly" in ",".join(login_response.headers.get_list("set-cookie")).lower()

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "admin@qq.com"

    rejected_logout_response = client.post("/api/auth/logout")
    assert rejected_logout_response.status_code == 401
    assert rejected_logout_response.json()["detail"] == "csrf token is invalid or missing"

    logout_response = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": csrf_cookie},
    )
    assert logout_response.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_login_rate_limit_blocks_repeated_failures(client: TestClient) -> None:
    for attempt in range(2):
        response = client.post(
            "/api/auth/login",
            json={"email": "admin@qq.com", "password": f"wrong-pass-{attempt}"},
        )
        assert response.status_code == 401

    limited_response = client.post(
        "/api/auth/login",
        json={"email": "admin@qq.com", "password": "wrong-pass-final"},
    )
    assert limited_response.status_code == 429
    assert limited_response.json()["retry_after_seconds"] > 0

    still_limited_response = client.post(
        "/api/auth/login",
        json={"email": "admin@qq.com", "password": "admin"},
    )
    assert still_limited_response.status_code == 429


def test_login_success_resets_failed_attempt_counter(client: TestClient) -> None:
    for attempt in range(2):
        response = client.post(
            "/api/auth/login",
            json={"email": "admin@qq.com", "password": f"wrong-pass-{attempt}"},
        )
        assert response.status_code == 401

    successful_response = client.post(
        "/api/auth/login",
        json={"email": "admin@qq.com", "password": "admin"},
    )
    assert successful_response.status_code == 200


def test_initialize_synchronizes_configured_admin_password(tmp_path: Path) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    initial_service = AuthService(
        repository=repository,
        admin_email="admin@qq.com",
        admin_password="temporary-admin-password",
        session_ttl_hours=24,
        password_reset_ttl_minutes=30,
        password_hash_iterations=1_000,
    )
    initial_service.initialize()

    synchronized_service = AuthService(
        repository=repository,
        admin_email="admin@qq.com",
        admin_password="admin",
        session_ttl_hours=24,
        password_reset_ttl_minutes=30,
        password_hash_iterations=1_000,
    )
    synchronized_service.initialize()

    with pytest.raises(AuthenticationError, match="invalid email or password"):
        synchronized_service.login("admin@qq.com", "temporary-admin-password")
    assert synchronized_service.login("admin@qq.com", "admin").user.role.value == "admin"


def test_login_rate_limit_is_shared_through_repository(tmp_path: Path) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    first_service = AuthService(
        repository=repository,
        admin_email="admin@qq.com",
        admin_password="admin",
        session_ttl_hours=24,
        password_reset_ttl_minutes=30,
        password_hash_iterations=1_000,
        login_rate_limiter=AuthenticationRateLimiter(
            max_failed_attempts=2,
            window_seconds=60,
            repository=repository,
        ),
    )
    second_service = AuthService(
        repository=repository,
        admin_email="admin@qq.com",
        admin_password="admin",
        session_ttl_hours=24,
        password_reset_ttl_minutes=30,
        password_hash_iterations=1_000,
        login_rate_limiter=AuthenticationRateLimiter(
            max_failed_attempts=2,
            window_seconds=60,
            repository=repository,
        ),
    )
    first_service.initialize()
    second_service.initialize()

    with pytest.raises(AuthenticationError, match="invalid email or password"):
        first_service.login("admin@qq.com", "wrong-pass-1")
    with pytest.raises(RateLimitError, match="too many failed login attempts"):
        second_service.login("admin@qq.com", "wrong-pass-2")
    with pytest.raises(RateLimitError, match="too many failed login attempts"):
        first_service.login("admin@qq.com", "admin")

    repository.clear_login_rate_limit(normalize_email("admin@qq.com"))
    assert second_service.login("admin@qq.com", "admin").user.email == (
        "admin@qq.com"
    )


def test_chat_sessions_are_isolated_per_user(client: TestClient) -> None:
    first_auth = _register(client, "first@example.com", "member-pass-123")
    second_auth = _register(client, "second@example.com", "member-pass-123")

    first_session_response = client.post("/api/excel/chat/sessions", headers=first_auth)
    assert first_session_response.status_code == 200
    first_session_id = first_session_response.json()["session_id"]

    second_list_response = client.get("/api/excel/chat/sessions", headers=second_auth)
    assert second_list_response.status_code == 200
    assert second_list_response.json()["sessions"] == []

    second_access_response = client.get(
        f"/api/excel/chat/sessions/{first_session_id}",
        headers=second_auth,
    )
    assert second_access_response.status_code == 404

    second_message_response = client.post(
        f"/api/excel/chat/sessions/{first_session_id}/messages",
        headers=second_auth,
        json={"question": "Can I reuse this session?"},
    )
    assert second_message_response.status_code == 404


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _register(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _write_xlsx_fixture(path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Standards"
    worksheet.append(["Code", "Date"])
    worksheet.append(["EN 60335-1:2023", "2024-01-01"])
    workbook.save(path)
