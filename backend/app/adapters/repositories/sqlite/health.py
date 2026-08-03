import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.adapters.repositories.sqlite.migrations import (
    SQLiteMigrationRunner,
    SQLiteSchemaInspection,
)


@dataclass(frozen=True)
class SQLiteRuntimeInspection:
    database_available: bool
    schema: SQLiteSchemaInspection | None
    error_code: str | None = None


class SQLiteRuntimeHealthProbe:
    """Read-only SQLite connectivity and schema inspection."""

    def __init__(
        self,
        database_path: Path,
        migration_runner: SQLiteMigrationRunner,
        *,
        busy_timeout_ms: int,
    ) -> None:
        self._database_path = database_path
        self._migration_runner = migration_runner
        self._busy_timeout_ms = busy_timeout_ms

    def inspect(self) -> SQLiteRuntimeInspection:
        if not self._database_path.is_file():
            return SQLiteRuntimeInspection(
                database_available=False,
                schema=None,
                error_code="database_missing",
            )
        try:
            database_uri = f"{self._database_path.resolve().as_uri()}?mode=ro"
            connection = sqlite3.connect(database_uri, uri=True, timeout=1.0)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
                connection.execute("SELECT 1").fetchone()
                schema = self._migration_runner.inspect_schema(connection)
            finally:
                connection.close()
        except sqlite3.Error:
            return SQLiteRuntimeInspection(
                database_available=False,
                schema=None,
                error_code="database_unavailable",
            )
        return SQLiteRuntimeInspection(
            database_available=True,
            schema=schema,
        )
