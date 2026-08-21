import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

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
from app.core.auth import expires_at_iso, hash_token, normalize_email
from app.core.config import Settings, get_settings
from app.core.errors import (
    AuthenticationError,
    PasswordResetTokenError,
    RateLimitError,
    UserAlreadyExistsError,
)
from app.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    get_settings.cache_clear()
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
    get_settings.cache_clear()


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

    revoked_session_response = client.get("/api/auth/me", headers=auth_header)
    assert revoked_session_response.status_code == 401

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


def test_password_reset_token_is_consumed_atomically_under_concurrency(
    tmp_path: Path,
) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    service = AuthService(
        repository=repository,
        session_ttl_hours=24,
        password_reset_ttl_minutes=30,
        password_hash_iterations=1_000,
    )
    service.initialize()
    original_auth = service.register("concurrent-reset@example.com", "old-pass-123")
    request = service.request_password_reset("concurrent-reset@example.com")
    assert request.reset_token is not None

    barrier = Barrier(2)

    def reset(password: str) -> tuple[str, str]:
        barrier.wait()
        try:
            service.reset_password(request.reset_token or "", password)
        except PasswordResetTokenError:
            return "rejected", password
        return "success", password

    passwords = ["new-pass-456", "new-pass-789"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(reset, passwords))

    assert [status for status, _password in outcomes].count("success") == 1
    assert [status for status, _password in outcomes].count("rejected") == 1
    winning_password = next(
        password for status, password in outcomes if status == "success"
    )
    assert service.login("concurrent-reset@example.com", winning_password).user.email == (
        "concurrent-reset@example.com"
    )
    with pytest.raises(AuthenticationError, match="session expired"):
        service.get_user_for_token(original_auth.access_token)


def test_member_registration_is_atomic_under_concurrency(tmp_path: Path) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)
    service = AuthService(
        repository=repository,
        session_ttl_hours=24,
        password_reset_ttl_minutes=30,
        password_hash_iterations=1_000,
    )
    service.initialize()
    contender_count = 12
    barrier = Barrier(contender_count)

    def register(contender: int) -> tuple[str, str | None]:
        barrier.wait()
        try:
            result = service.register(
                "  Concurrent.Member@Example.COM  ",
                f"member-pass-{contender:03d}",
            )
        except UserAlreadyExistsError:
            return "conflict", None
        return "created", result.access_token

    with ThreadPoolExecutor(max_workers=contender_count) as executor:
        outcomes = list(executor.map(register, range(contender_count)))

    assert [status for status, _token in outcomes].count("created") == 1
    assert [status for status, _token in outcomes].count("conflict") == contender_count - 1
    winning_token = next(token for status, token in outcomes if status == "created")
    assert winning_token is not None
    assert service.get_user_for_token(winning_token).email == (
        "concurrent.member@example.com"
    )

    with sqlite3.connect(database_path) as connection:
        user_row = connection.execute(
            "SELECT user_id FROM user_accounts WHERE email = ?",
            ("concurrent.member@example.com",),
        ).fetchone()
        assert user_row is not None
        user_count = connection.execute(
            "SELECT COUNT(*) FROM user_accounts WHERE email = ?",
            ("concurrent.member@example.com",),
        ).fetchone()[0]
        session_count = connection.execute(
            "SELECT COUNT(*) FROM auth_sessions WHERE user_id = ?",
            (user_row[0],),
        ).fetchone()[0]
    assert user_count == 1
    assert session_count == 1


def test_registration_rolls_back_user_when_initial_session_insert_fails(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)
    service = AuthService(
        repository=repository,
        session_ttl_hours=24,
        password_reset_ttl_minutes=30,
        password_hash_iterations=1_000,
    )
    service.initialize()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_initial_auth_session
            BEFORE INSERT ON auth_sessions
            BEGIN
              SELECT RAISE(ABORT, 'injected session insert failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected session insert failure"):
        service.register("rollback-register@example.com", "member-pass-123")

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM user_accounts WHERE email = ?",
            ("rollback-register@example.com",),
        ).fetchone()[0] == 0


def test_password_reset_transaction_rolls_back_token_when_password_update_fails(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)
    service = AuthService(
        repository=repository,
        session_ttl_hours=24,
        password_reset_ttl_minutes=30,
        password_hash_iterations=1_000,
    )
    service.initialize()
    service.register("rollback-reset@example.com", "old-pass-123")
    request = service.request_password_reset("rollback-reset@example.com")
    assert request.reset_token is not None

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_password_reset_update
            BEFORE UPDATE OF password_hash ON user_accounts
            BEGIN
              SELECT RAISE(ABORT, 'injected password update failure');
            END
            """
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected password update failure"):
        service.reset_password(request.reset_token, "new-pass-456")
    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP TRIGGER fail_password_reset_update")

    reset = service.reset_password(request.reset_token, "new-pass-456")
    assert reset.user.email == "rollback-reset@example.com"


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


def test_initialize_restores_fixed_admin_password_and_active_state(tmp_path: Path) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    initial_service = AuthService(
        repository=repository,
        session_ttl_hours=24,
        password_reset_ttl_minutes=30,
        password_hash_iterations=1_000,
    )
    initial_service.initialize()
    initial_auth = initial_service.login("admin@qq.com", "admin")

    with sqlite3.connect(tmp_path / "excel.sqlite3") as connection:
        connection.execute(
            """
            UPDATE user_accounts
            SET password_hash = 'invalid-hash', is_active = 0
            WHERE email = 'admin@qq.com'
            """
        )

    synchronized_service = AuthService(
        repository=repository,
        session_ttl_hours=24,
        password_reset_ttl_minutes=30,
        password_hash_iterations=1_000,
    )
    synchronized_service.initialize()

    assert synchronized_service.login("admin@qq.com", "admin").user.role.value == "admin"
    with pytest.raises(AuthenticationError, match="session expired"):
        synchronized_service.get_user_for_token(initial_auth.access_token)


def test_fixed_admin_initialization_is_idempotent_under_concurrency(
    tmp_path: Path,
) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    repository.initialize()
    barrier = Barrier(2)

    def initialize_admin() -> str:
        service = AuthService(
            repository=repository,
            session_ttl_hours=24,
            password_reset_ttl_minutes=30,
            password_hash_iterations=1_000,
        )
        barrier.wait()
        return service.ensure_admin_user().user_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        user_ids = list(executor.map(lambda _index: initialize_admin(), range(2)))

    assert len(set(user_ids)) == 1
    with sqlite3.connect(tmp_path / "excel.sqlite3") as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM user_accounts WHERE email = 'admin@qq.com'"
        ).fetchone()[0]
    assert count == 1


def test_fixed_admin_cannot_enter_password_reset_flow(client: TestClient) -> None:
    forgot_response = client.post(
        "/api/auth/password/forgot",
        json={"email": "admin@qq.com"},
    )

    assert forgot_response.status_code == 200
    assert forgot_response.json() == {
        "email": "admin@qq.com",
        "reset_token": None,
        "expires_at": None,
    }
    assert _login(client, "admin@qq.com", "admin")


def test_stale_fixed_admin_reset_token_cannot_change_password(tmp_path: Path) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)
    service = AuthService(
        repository=repository,
        session_ttl_hours=24,
        password_reset_ttl_minutes=30,
        password_hash_iterations=1_000,
    )
    service.initialize()
    admin = repository.get_user_by_email("admin@qq.com")
    assert admin is not None
    token = "stale-fixed-admin-reset-token"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO password_reset_tokens
              (reset_token_id, user_id, token_hash, created_at, expires_at, used_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (
                "reset_stale_admin",
                admin.user_id,
                hash_token(token),
                admin.created_at,
                expires_at_iso(minutes=30),
            ),
        )

    with pytest.raises(PasswordResetTokenError, match="invalid or expired"):
        service.reset_password(token, "new-admin-password")
    assert service.login("admin@qq.com", "admin").user.role.value == "admin"


def test_login_rate_limit_is_shared_through_repository(tmp_path: Path) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    first_service = AuthService(
        repository=repository,
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
