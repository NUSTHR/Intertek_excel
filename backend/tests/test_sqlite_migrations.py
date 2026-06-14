import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.adapters.repositories import sqlite_repository
from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.core.config import Settings
from app.domain.models import ExcelUploadTask, ExcelUploadTaskStatus


def test_repository_initialization_records_schema_migration(tmp_path: Path) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)

    repository.initialize()
    repository.initialize()

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT version, name, checksum
            FROM schema_migrations
            ORDER BY version ASC
            """
        ).fetchall()

    assert [int(row["version"]) for row in rows] == list(range(1, 13))
    assert [row["name"] for row in rows] == [
        "initial_excel_workspace_schema",
        "add_chat_session_metadata",
        "add_document_routing_summary_fields",
        "persist_chat_turn_snapshots_and_llm_preferences",
        "add_authentication_and_session_ownership",
        "add_operational_maintenance_indexes",
        "remove_chat_turn_performance_timings",
        "soft_delete_excel_files",
        "add_excel_file_visibility",
        "add_row_mapping_raw_order_index",
        "add_upload_tasks_and_shared_chat_cancellations",
        "add_shared_auth_login_attempts",
    ]
    assert all(row["checksum"] for row in rows)


def test_repository_configures_connections_for_long_running_use(tmp_path: Path) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)

    repository.initialize()

    with repository._connect() as connection:
        isolation_level = connection.isolation_level
        busy_timeout_ms = int(connection.execute("PRAGMA busy_timeout").fetchone()[0])
        foreign_keys_enabled = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
        wal_autocheckpoint = int(
            connection.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
        )

    assert isolation_level == "IMMEDIATE"
    assert busy_timeout_ms == sqlite_repository.SQLITE_BUSY_TIMEOUT_MS
    assert foreign_keys_enabled == 1
    assert journal_mode.lower() == "wal"
    assert wal_autocheckpoint == sqlite_repository.SQLITE_WAL_AUTOCHECKPOINT_PAGES


def test_repository_concurrent_upload_task_claims_are_unique(tmp_path: Path) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)
    repository.initialize()

    created_at = "2026-06-14T00:00:00+00:00"
    for index in range(8):
        repository.create_upload_task(
            ExcelUploadTask(
                task_id=f"task_{index}",
                user_id="user_admin",
                original_filename=f"workbook_{index}.xlsx",
                staging_path=f"staging/{index}.xlsx",
                replace_existing=False,
                status=ExcelUploadTaskStatus.QUEUED,
                error_message=None,
                result={},
                created_at=created_at,
                updated_at=created_at,
            )
        )

    def claim(worker_index: int) -> str | None:
        task = repository.claim_next_upload_task(
            worker_id=f"worker_{worker_index}",
            started_at=f"2026-06-14T00:00:{worker_index:02d}+00:00",
        )
        return task.task_id if task is not None else None

    with ThreadPoolExecutor(max_workers=8) as executor:
        claimed_task_ids = [
            task_id
            for task_id in executor.map(claim, range(8))
            if task_id is not None
        ]

    assert len(claimed_task_ids) == 8
    assert len(set(claimed_task_ids)) == 8
    assert repository.claim_next_upload_task(
        worker_id="worker_extra",
        started_at="2026-06-14T00:01:00+00:00",
    ) is None


def test_repository_creates_raw_row_mapping_pagination_index(tmp_path: Path) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)

    repository.initialize()

    with sqlite3.connect(database_path) as connection:
        indexes = {
            row[1]
            for row in connection.execute(
                "PRAGMA index_list('excel_row_mappings')"
            ).fetchall()
        }

    assert "idx_mappings_sheet_raw_csv_row" in indexes


def test_repository_throttles_periodic_sqlite_maintenance(tmp_path: Path) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)
    calls = 0

    def record_maintenance(_connection: sqlite3.Connection) -> None:
        nonlocal calls
        calls += 1

    repository._run_connection_maintenance = record_maintenance  # type: ignore[method-assign]

    with repository._connect():
        pass
    with repository._connect():
        pass

    repository._last_maintenance_at -= (
        sqlite_repository.SQLITE_MAINTENANCE_INTERVAL_SECONDS + 1
    )
    with repository._connect():
        pass

    assert calls == 2


def test_repository_operational_maintenance_removes_expired_runtime_records(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(
        database_path,
        auth_session_retention_days=30,
        password_reset_token_retention_days=7,
    )
    repository.initialize()

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO user_accounts
              (user_id, email, password_hash, role, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "user_cleanup",
                "cleanup@example.com",
                "hash",
                "member",
                1,
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.executemany(
            """
            INSERT INTO auth_sessions
              (session_id, user_id, session_token_hash, created_at, expires_at, revoked_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "auth_old_expired",
                    "user_cleanup",
                    "token_old_expired",
                    "2026-01-01T00:00:00+00:00",
                    "2026-04-01T00:00:00+00:00",
                    None,
                ),
                (
                    "auth_recent_expired",
                    "user_cleanup",
                    "token_recent_expired",
                    "2026-05-20T00:00:00+00:00",
                    "2026-06-01T00:00:00+00:00",
                    None,
                ),
                (
                    "auth_old_revoked",
                    "user_cleanup",
                    "token_old_revoked",
                    "2026-05-01T00:00:00+00:00",
                    "2026-07-01T00:00:00+00:00",
                    "2026-04-01T00:00:00+00:00",
                ),
                (
                    "auth_active",
                    "user_cleanup",
                    "token_active",
                    "2026-06-01T00:00:00+00:00",
                    "2026-07-01T00:00:00+00:00",
                    None,
                ),
            ],
        )
        connection.executemany(
            """
            INSERT INTO password_reset_tokens
              (reset_token_id, user_id, token_hash, created_at, expires_at, used_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "reset_old_expired",
                    "user_cleanup",
                    "reset_token_old_expired",
                    "2026-05-01T00:00:00+00:00",
                    "2026-05-01T01:00:00+00:00",
                    None,
                ),
                (
                    "reset_recent_expired",
                    "user_cleanup",
                    "reset_token_recent_expired",
                    "2026-06-08T00:00:00+00:00",
                    "2026-06-08T01:00:00+00:00",
                    None,
                ),
                (
                    "reset_old_used",
                    "user_cleanup",
                    "reset_token_old_used",
                    "2026-06-01T00:00:00+00:00",
                    "2026-07-01T00:00:00+00:00",
                    "2026-05-01T00:00:00+00:00",
                ),
                (
                    "reset_active",
                    "user_cleanup",
                    "reset_token_active",
                    "2026-06-10T00:00:00+00:00",
                    "2026-07-01T00:00:00+00:00",
                    None,
                ),
            ],
        )

    deleted = repository.run_operational_maintenance(
        now_iso="2026-06-11T00:00:00+00:00"
    )

    with sqlite3.connect(database_path) as connection:
        auth_session_ids = {
            row[0]
            for row in connection.execute(
                "SELECT session_id FROM auth_sessions ORDER BY session_id"
            )
        }
        reset_token_ids = {
            row[0]
            for row in connection.execute(
                "SELECT reset_token_id FROM password_reset_tokens ORDER BY reset_token_id"
            )
        }

    assert deleted == {
        "auth_sessions": 2,
        "password_reset_tokens": 2,
        "chat_request_cancellations": 0,
        "auth_login_attempts": 0,
    }
    assert auth_session_ids == {"auth_active", "auth_recent_expired"}
    assert reset_token_ids == {"reset_active", "reset_recent_expired"}


def test_repository_initialization_detects_changed_applied_migration(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)
    repository.initialize()

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE schema_migrations
            SET checksum = ?
            WHERE version = ?
            """,
            ("stale-checksum", 1),
        )

    with pytest.raises(RuntimeError, match="schema migration checksum mismatch"):
        repository.initialize()


def test_repository_initialization_rejects_unknown_future_migration(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)
    repository.initialize()

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO schema_migrations
              (version, name, checksum, applied_at)
            VALUES (?, ?, ?, ?)
            """,
            (999, "future_schema", "checksum", "2026-01-01T00:00:00+00:00"),
        )

    with pytest.raises(RuntimeError, match="unknown schema migration"):
        repository.initialize()


def test_all_repository_schema_migrations_have_unique_versions() -> None:
    versions = [migration.version for migration in sqlite_repository.SCHEMA_MIGRATIONS]

    assert versions == sorted(versions)
    assert len(versions) == len(set(versions))


def test_removed_legacy_chat_rows_setting_is_ignored() -> None:
    settings = Settings(_env_file=None, llm_chat_rows_per_sheet=999)

    assert not hasattr(settings, "llm_chat_rows_per_sheet")


def test_production_settings_reject_unsafe_defaults() -> None:
    settings = Settings(_env_file=None, app_env="production")

    with pytest.raises(RuntimeError, match="unsafe production configuration"):
        settings.validate_runtime_safety()


def test_production_settings_accept_explicit_safe_runtime_values() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        app_cors_origins="https://excel.example.com",
        auth_admin_password="safe-admin-password",
        auth_expose_reset_token=False,
        auth_cookie_secure=True,
        llm_api_key="siliconflow-key",
        deepseek_api_key="deepseek-key",
    )

    settings.validate_runtime_safety()
