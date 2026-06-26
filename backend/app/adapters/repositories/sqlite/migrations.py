import hashlib
import sqlite3

from app.adapters.repositories.sqlite.schema import SchemaMigration
from app.core.time import utc_now_iso


class SQLiteMigrationRunner:
    def __init__(self, migrations: list[SchemaMigration]) -> None:
        self._migrations = migrations

    def initialize_schema(self, connection: sqlite3.Connection) -> None:
        self._ensure_migration_table(connection)
        self._apply_migrations(connection)

    def _ensure_migration_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version INTEGER PRIMARY KEY,
              name TEXT NOT NULL,
              checksum TEXT NOT NULL,
              applied_at TEXT NOT NULL
            )
            """
        )

    def _apply_migrations(self, connection: sqlite3.Connection) -> None:
        applied = self._applied_migrations(connection)
        known_versions = {migration.version for migration in self._migrations}
        unknown_versions = sorted(set(applied) - known_versions)
        if unknown_versions:
            raise RuntimeError(
                "database contains unknown schema migration version(s): "
                f"{unknown_versions}"
            )
        for migration in sorted(self._migrations, key=lambda item: item.version):
            checksum = self._migration_checksum(migration)
            applied_checksum = applied.get(migration.version)
            if applied_checksum is not None:
                if applied_checksum != checksum:
                    raise RuntimeError(
                        "schema migration checksum mismatch "
                        f"for version {migration.version}"
                    )
                continue

            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                """
                INSERT INTO schema_migrations
                  (version, name, checksum, applied_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    migration.version,
                    migration.name,
                    checksum,
                    utc_now_iso(),
                ),
            )

    def _applied_migrations(self, connection: sqlite3.Connection) -> dict[int, str]:
        rows = connection.execute(
            "SELECT version, checksum FROM schema_migrations ORDER BY version ASC"
        ).fetchall()
        return {int(row["version"]): str(row["checksum"]) for row in rows}

    def _migration_checksum(self, migration: SchemaMigration) -> str:
        payload = "\n".join(
            [
                str(migration.version),
                migration.name,
                *[statement.strip() for statement in migration.statements],
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
