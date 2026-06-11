import sqlite3
from pathlib import Path

import pytest

from app.adapters.repositories import sqlite_repository
from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.core.config import Settings


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

    assert [int(row["version"]) for row in rows] == [1, 2, 3, 4]
    assert rows[0]["name"] == "initial_excel_workspace_schema"
    assert rows[1]["name"] == "add_chat_session_metadata"
    assert rows[2]["name"] == "add_document_routing_summary_fields"
    assert rows[3]["name"] == "persist_chat_turn_snapshots_and_llm_preferences"
    assert rows[0]["checksum"]
    assert rows[1]["checksum"]
    assert rows[2]["checksum"]
    assert rows[3]["checksum"]


def test_repository_configures_connections_for_long_running_use(tmp_path: Path) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)

    repository.initialize()

    with repository._connect() as connection:
        busy_timeout_ms = int(connection.execute("PRAGMA busy_timeout").fetchone()[0])
        foreign_keys_enabled = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
        wal_autocheckpoint = int(
            connection.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
        )

    assert busy_timeout_ms == sqlite_repository.SQLITE_BUSY_TIMEOUT_MS
    assert foreign_keys_enabled == 1
    assert journal_mode.lower() == "wal"
    assert wal_autocheckpoint == sqlite_repository.SQLITE_WAL_AUTOCHECKPOINT_PAGES


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
