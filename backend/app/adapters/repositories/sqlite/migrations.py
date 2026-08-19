import hashlib
import sqlite3
from dataclasses import dataclass

from app.adapters.repositories.sqlite.schema import SchemaMigration
from app.core.time import utc_now_iso


@dataclass(frozen=True)
class SQLiteSchemaInspection:
    migration_table_exists: bool
    expected_version: int
    applied_version: int
    missing_versions: tuple[int, ...]
    unknown_versions: tuple[int, ...]
    checksum_mismatches: tuple[int, ...]

    @property
    def is_ready(self) -> bool:
        return (
            self.migration_table_exists
            and not self.missing_versions
            and not self.unknown_versions
            and not self.checksum_mismatches
            and self.applied_version == self.expected_version
        )


class SQLiteMigrationRunner:
    def __init__(self, migrations: list[SchemaMigration]) -> None:
        self._migrations = migrations

    def initialize_schema(self, connection: sqlite3.Connection) -> None:
        savepoint = "schema_migration"
        connection.execute(f"SAVEPOINT {savepoint}")
        try:
            self._ensure_migration_table(connection)
            self._apply_migrations(connection)
        except Exception:
            connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise
        connection.execute(f"RELEASE SAVEPOINT {savepoint}")

    def inspect_schema(self, connection: sqlite3.Connection) -> SQLiteSchemaInspection:
        expected_checksums = {
            migration.version: self._migration_checksum(migration)
            for migration in self._migrations
        }
        expected_versions = set(expected_checksums)
        table_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'schema_migrations'
            """
        ).fetchone() is not None
        if not table_exists:
            return SQLiteSchemaInspection(
                migration_table_exists=False,
                expected_version=max(expected_versions, default=0),
                applied_version=0,
                missing_versions=tuple(sorted(expected_versions)),
                unknown_versions=(),
                checksum_mismatches=(),
            )

        applied = self._applied_migrations(connection)
        applied_versions = set(applied)
        return SQLiteSchemaInspection(
            migration_table_exists=True,
            expected_version=max(expected_versions, default=0),
            applied_version=max(applied_versions, default=0),
            missing_versions=tuple(sorted(expected_versions - applied_versions)),
            unknown_versions=tuple(sorted(applied_versions - expected_versions)),
            checksum_mismatches=tuple(
                sorted(
                    version
                    for version in expected_versions & applied_versions
                    if applied[version] != expected_checksums[version]
                )
            ),
        )

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
