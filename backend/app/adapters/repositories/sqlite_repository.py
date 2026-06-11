import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.time import utc_now_iso
from app.domain.models import (
    AttachedDocument,
    ChatAnswerBlock,
    ChatSession,
    ChatStageTiming,
    ChatTurn,
    DocumentSummary,
    ExcelArtifact,
    ExcelArtifactType,
    ExcelCitation,
    ExcelFile,
    ExcelFileVersion,
    ExcelRowMapping,
    ExcelSheet,
    ExcelVersionStatus,
    LlmPreference,
    SelectedDocument,
    SheetSummary,
)


@dataclass(frozen=True)
class SchemaMigration:
    version: int
    name: str
    statements: tuple[str, ...]


SCHEMA_MIGRATIONS: tuple[SchemaMigration, ...] = (
    SchemaMigration(
        version=1,
        name="initial_excel_workspace_schema",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS excel_files (
              file_id TEXT PRIMARY KEY,
              display_name TEXT NOT NULL UNIQUE,
              active_version_id TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS excel_file_versions (
              version_id TEXT PRIMARY KEY,
              file_id TEXT NOT NULL,
              original_filename TEXT NOT NULL,
              file_hash TEXT NOT NULL,
              status TEXT NOT NULL,
              error_message TEXT,
              created_at TEXT NOT NULL,
              activated_at TEXT,
              FOREIGN KEY(file_id) REFERENCES excel_files(file_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS excel_sheets (
              sheet_id TEXT PRIMARY KEY,
              version_id TEXT NOT NULL,
              sheet_index INTEGER NOT NULL,
              sheet_code TEXT NOT NULL,
              sheet_name TEXT NOT NULL,
              row_count INTEGER NOT NULL,
              column_count INTEGER NOT NULL,
              raw_csv_path TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(version_id) REFERENCES excel_file_versions(version_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS excel_artifacts (
              artifact_id TEXT PRIMARY KEY,
              version_id TEXT NOT NULL,
              artifact_type TEXT NOT NULL,
              path TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(version_id) REFERENCES excel_file_versions(version_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS excel_row_mappings (
              mapping_id TEXT PRIMARY KEY,
              version_id TEXT NOT NULL,
              sheet_id TEXT NOT NULL,
              row_id TEXT NOT NULL,
              original_row_number INTEGER NOT NULL,
              raw_csv_row_number INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(version_id) REFERENCES excel_file_versions(version_id),
              FOREIGN KEY(sheet_id) REFERENCES excel_sheets(sheet_id),
              UNIQUE(sheet_id, row_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS document_summaries (
              summary_id TEXT PRIMARY KEY,
              file_id TEXT NOT NULL,
              version_id TEXT NOT NULL UNIQUE,
              summary_text TEXT NOT NULL,
              business_domain TEXT NOT NULL,
              key_topics_json TEXT NOT NULL,
              suitable_questions_json TEXT NOT NULL,
              unsuitable_questions_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(version_id) REFERENCES excel_file_versions(version_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS document_sheet_summaries (
              summary_id TEXT NOT NULL,
              sheet_id TEXT NOT NULL,
              sheet_name TEXT NOT NULL,
              summary TEXT NOT NULL,
              important_columns_json TEXT NOT NULL,
              likely_question_types_json TEXT NOT NULL,
              PRIMARY KEY(summary_id, sheet_id),
              FOREIGN KEY(summary_id) REFERENCES document_summaries(summary_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
              session_id TEXT PRIMARY KEY,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              status TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_session_documents (
              session_id TEXT NOT NULL,
              file_id TEXT NOT NULL,
              version_id TEXT NOT NULL,
              attached_at TEXT NOT NULL,
              row_count INTEGER NOT NULL,
              context_hash TEXT NOT NULL,
              status TEXT NOT NULL,
              PRIMARY KEY(session_id, version_id),
              FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id),
              FOREIGN KEY(version_id) REFERENCES excel_file_versions(version_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_turns (
              turn_id TEXT PRIMARY KEY,
              session_id TEXT NOT NULL,
              question TEXT NOT NULL,
              answer_text TEXT NOT NULL,
              citation_ids_json TEXT NOT NULL,
              selected_documents_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_versions_file_id
              ON excel_file_versions(file_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sheets_version_id
              ON excel_sheets(version_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_mappings_sheet_row
              ON excel_row_mappings(sheet_id, row_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sheet_summaries_summary_id
              ON document_sheet_summaries(summary_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_chat_turns_session_id
              ON chat_turns(session_id, created_at)
            """,
        ),
    ),
    SchemaMigration(
        version=2,
        name="add_chat_session_metadata",
        statements=(
            """
            ALTER TABLE chat_sessions
            ADD COLUMN title TEXT NOT NULL DEFAULT 'New chat'
            """,
            """
            ALTER TABLE chat_sessions
            ADD COLUMN pinned_at TEXT
            """,
        ),
    ),
    SchemaMigration(
        version=3,
        name="add_document_routing_summary_fields",
        statements=(
            """
            ALTER TABLE document_summaries
            ADD COLUMN document_title TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE document_summaries
            ADD COLUMN document_type TEXT NOT NULL DEFAULT 'unknown'
            """,
            """
            ALTER TABLE document_summaries
            ADD COLUMN coverage_scope_json TEXT NOT NULL DEFAULT '{}'
            """,
            """
            ALTER TABLE document_summaries
            ADD COLUMN positive_routing_terms_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE document_summaries
            ADD COLUMN negative_routing_terms_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE document_summaries
            ADD COLUMN exact_identifiers_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE document_summaries
            ADD COLUMN routing_notes TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE document_sheet_summaries
            ADD COLUMN header_terms_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE document_sheet_summaries
            ADD COLUMN sampled_identifiers_json TEXT NOT NULL DEFAULT '[]'
            """,
        ),
    ),
    SchemaMigration(
        version=4,
        name="persist_chat_turn_snapshots_and_llm_preferences",
        statements=(
            """
            ALTER TABLE chat_turns
            ADD COLUMN answer_blocks_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE chat_turns
            ADD COLUMN newly_attached_documents_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE chat_turns
            ADD COLUMN attached_documents_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE chat_turns
            ADD COLUMN citations_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE chat_turns
            ADD COLUMN insufficient_evidence INTEGER NOT NULL DEFAULT 0
            """,
            """
            ALTER TABLE chat_turns
            ADD COLUMN follow_up_suggestions_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE chat_turns
            ADD COLUMN warnings_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE chat_turns
            ADD COLUMN timings_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            CREATE TABLE IF NOT EXISTS llm_preferences (
              scope TEXT PRIMARY KEY,
              summary_provider TEXT NOT NULL,
              summary_model TEXT NOT NULL,
              router_provider TEXT NOT NULL,
              router_model TEXT NOT NULL,
              answer_provider TEXT NOT NULL,
              answer_model TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
        ),
    ),
)


SQLITE_CONNECTION_TIMEOUT_SECONDS = 30.0
SQLITE_BUSY_TIMEOUT_MS = 30000
SQLITE_WAL_AUTOCHECKPOINT_PAGES = 1000
SQLITE_MAINTENANCE_INTERVAL_SECONDS = 300.0


class SQLiteExcelAssetRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._last_maintenance_at = 0.0

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
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
        known_versions = {migration.version for migration in SCHEMA_MIGRATIONS}
        unknown_versions = sorted(set(applied) - known_versions)
        if unknown_versions:
            raise RuntimeError(
                "database contains unknown schema migration version(s): "
                f"{unknown_versions}"
            )
        for migration in sorted(SCHEMA_MIGRATIONS, key=lambda item: item.version):
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

    def create_file(self, file: ExcelFile) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO excel_files
                  (file_id, display_name, active_version_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    file.file_id,
                    file.display_name,
                    file.active_version_id,
                    file.created_at,
                    file.updated_at,
                ),
            )

    def get_file(self, file_id: str) -> ExcelFile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM excel_files WHERE file_id = ?",
                (file_id,),
            ).fetchone()
        return self._to_file(row)

    def find_file_by_display_name(self, display_name: str) -> ExcelFile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM excel_files WHERE display_name = ?",
                (display_name,),
            ).fetchone()
        return self._to_file(row)

    def list_files(self) -> list[ExcelFile]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM excel_files ORDER BY updated_at DESC, display_name ASC"
            ).fetchall()
        return [file for row in rows if (file := self._to_file(row)) is not None]

    def update_file_display_name(
        self,
        file_id: str,
        display_name: str,
        updated_at: str,
    ) -> ExcelFile | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE excel_files
                SET display_name = ?, updated_at = ?
                WHERE file_id = ?
                """,
                (display_name, updated_at, file_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM excel_files WHERE file_id = ?",
                (file_id,),
            ).fetchone()
        return self._to_file(row)

    def delete_file(self, file_id: str) -> dict[str, int]:
        with self._connect() as connection:
            version_rows = connection.execute(
                """
                SELECT version_id FROM excel_file_versions
                WHERE file_id = ?
                """,
                (file_id,),
            ).fetchall()
            version_ids = [str(row["version_id"]) for row in version_rows]

            deleted_chat_session_documents = 0
            deleted_summaries = 0
            deleted_row_mappings = 0
            deleted_artifacts = 0
            deleted_sheets = 0
            deleted_versions = 0

            if version_ids:
                placeholders = ",".join("?" for _ in version_ids)

                deleted_chat_session_documents = connection.execute(
                    f"""
                    DELETE FROM chat_session_documents
                    WHERE version_id IN ({placeholders})
                    """,
                    version_ids,
                ).rowcount

                summary_ids = connection.execute(
                    f"""
                    SELECT summary_id FROM document_summaries
                    WHERE version_id IN ({placeholders})
                    """,
                    version_ids,
                ).fetchall()
                if summary_ids:
                    summary_id_values = [str(row["summary_id"]) for row in summary_ids]
                    summary_placeholders = ",".join("?" for _ in summary_id_values)
                    connection.execute(
                        f"""
                        DELETE FROM document_sheet_summaries
                        WHERE summary_id IN ({summary_placeholders})
                        """,
                        summary_id_values,
                    )
                deleted_summaries = connection.execute(
                    f"""
                    DELETE FROM document_summaries
                    WHERE version_id IN ({placeholders})
                    """,
                    version_ids,
                ).rowcount

                sheet_rows = connection.execute(
                    f"""
                    SELECT sheet_id FROM excel_sheets
                    WHERE version_id IN ({placeholders})
                    """,
                    version_ids,
                ).fetchall()
                sheet_ids = [str(row["sheet_id"]) for row in sheet_rows]
                if sheet_ids:
                    sheet_placeholders = ",".join("?" for _ in sheet_ids)
                    deleted_row_mappings = connection.execute(
                        f"""
                        DELETE FROM excel_row_mappings
                        WHERE sheet_id IN ({sheet_placeholders})
                        """,
                        sheet_ids,
                    ).rowcount

                deleted_artifacts = connection.execute(
                    f"""
                    DELETE FROM excel_artifacts
                    WHERE version_id IN ({placeholders})
                    """,
                    version_ids,
                ).rowcount
                deleted_sheets = connection.execute(
                    f"""
                    DELETE FROM excel_sheets
                    WHERE version_id IN ({placeholders})
                    """,
                    version_ids,
                ).rowcount
                deleted_versions = connection.execute(
                    """
                    DELETE FROM excel_file_versions
                    WHERE file_id = ?
                    """,
                    (file_id,),
                ).rowcount

            connection.execute(
                """
                UPDATE excel_files
                SET active_version_id = NULL
                WHERE file_id = ?
                """,
                (file_id,),
            )
            connection.execute(
                """
                DELETE FROM excel_files
                WHERE file_id = ?
                """,
                (file_id,),
            )

        return {
            "deleted_versions": deleted_versions,
            "deleted_sheets": deleted_sheets,
            "deleted_artifacts": deleted_artifacts,
            "deleted_row_mappings": deleted_row_mappings,
            "deleted_summaries": deleted_summaries,
            "deleted_chat_session_documents": deleted_chat_session_documents,
        }

    def create_version(self, version: ExcelFileVersion) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO excel_file_versions
                  (
                    version_id, file_id, original_filename, file_hash, status,
                    error_message, created_at, activated_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version.version_id,
                    version.file_id,
                    version.original_filename,
                    version.file_hash,
                    version.status.value,
                    version.error_message,
                    version.created_at,
                    version.activated_at,
                ),
            )

    def get_version(self, version_id: str) -> ExcelFileVersion | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM excel_file_versions WHERE version_id = ?",
                (version_id,),
            ).fetchone()
        return self._to_version(row)

    def list_versions(self, file_id: str) -> list[ExcelFileVersion]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM excel_file_versions
                WHERE file_id = ?
                ORDER BY created_at DESC
                """,
                (file_id,),
            ).fetchall()
        return [version for row in rows if (version := self._to_version(row)) is not None]

    def update_version_status(
        self,
        version_id: str,
        status: ExcelVersionStatus,
        error_message: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE excel_file_versions
                SET status = ?, error_message = ?
                WHERE version_id = ?
                """,
                (status.value, error_message, version_id),
            )

    def activate_version(self, file_id: str, version_id: str, activated_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE excel_files
                SET active_version_id = ?, updated_at = ?
                WHERE file_id = ?
                """,
                (version_id, activated_at, file_id),
            )
            connection.execute(
                """
                UPDATE excel_file_versions
                SET status = ?, activated_at = ?
                WHERE version_id = ?
                """,
                (ExcelVersionStatus.READY.value, activated_at, version_id),
            )

    def create_sheet(self, sheet: ExcelSheet) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO excel_sheets
                  (
                    sheet_id, version_id, sheet_index, sheet_code, sheet_name,
                    row_count, column_count, raw_csv_path, created_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sheet.sheet_id,
                    sheet.version_id,
                    sheet.sheet_index,
                    sheet.sheet_code,
                    sheet.sheet_name,
                    sheet.row_count,
                    sheet.column_count,
                    sheet.raw_csv_path,
                    sheet.created_at,
                ),
            )

    def get_sheet(self, sheet_id: str) -> ExcelSheet | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM excel_sheets WHERE sheet_id = ?",
                (sheet_id,),
            ).fetchone()
        return self._to_sheet(row)

    def list_sheets(self, version_id: str) -> list[ExcelSheet]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM excel_sheets
                WHERE version_id = ?
                ORDER BY sheet_index ASC
                """,
                (version_id,),
            ).fetchall()
        return [sheet for row in rows if (sheet := self._to_sheet(row)) is not None]

    def create_artifact(self, artifact: ExcelArtifact) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO excel_artifacts
                  (artifact_id, version_id, artifact_type, path, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    artifact.artifact_id,
                    artifact.version_id,
                    artifact.artifact_type.value,
                    artifact.path,
                    artifact.created_at,
                ),
            )

    def list_artifacts(self, version_id: str) -> list[ExcelArtifact]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM excel_artifacts
                WHERE version_id = ?
                ORDER BY created_at ASC
                """,
                (version_id,),
            ).fetchall()
        return [artifact for row in rows if (artifact := self._to_artifact(row)) is not None]

    def create_row_mappings(self, mappings: list[ExcelRowMapping]) -> None:
        if not mappings:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO excel_row_mappings
                  (
                    mapping_id, version_id, sheet_id, row_id,
                    original_row_number, raw_csv_row_number, created_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        mapping.mapping_id,
                        mapping.version_id,
                        mapping.sheet_id,
                        mapping.row_id,
                        mapping.original_row_number,
                        mapping.raw_csv_row_number,
                        mapping.created_at,
                    )
                    for mapping in mappings
                ],
            )

    def get_row_mapping(
        self,
        sheet_id: str,
        row_id: str,
    ) -> ExcelRowMapping | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM excel_row_mappings
                WHERE sheet_id = ? AND row_id = ?
                """,
                (sheet_id, row_id),
            ).fetchone()
        return self._to_mapping(row)

    def list_row_mappings_for_sheet(self, sheet_id: str) -> list[ExcelRowMapping]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM excel_row_mappings
                WHERE sheet_id = ?
                ORDER BY raw_csv_row_number ASC
                """,
                (sheet_id,),
            ).fetchall()
        return [mapping for row in rows if (mapping := self._to_mapping(row)) is not None]

    def save_summary(self, summary: DocumentSummary) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM document_sheet_summaries
                WHERE summary_id IN (
                  SELECT summary_id FROM document_summaries WHERE version_id = ?
                )
                """,
                (summary.version_id,),
            )
            connection.execute(
                "DELETE FROM document_summaries WHERE version_id = ?",
                (summary.version_id,),
            )
            connection.execute(
                """
                INSERT INTO document_summaries
                  (
                    summary_id, file_id, version_id, document_title, document_type,
                    summary_text, business_domain, coverage_scope_json,
                    key_topics_json, positive_routing_terms_json,
                    negative_routing_terms_json, exact_identifiers_json,
                    suitable_questions_json, unsuitable_questions_json,
                    routing_notes, created_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.summary_id,
                    summary.file_id,
                    summary.version_id,
                    summary.document_title,
                    summary.document_type,
                    summary.summary_text,
                    summary.business_domain,
                    self._dump_json(summary.coverage_scope),
                    self._dump_json(summary.key_topics),
                    self._dump_json(summary.positive_routing_terms),
                    self._dump_json(summary.negative_routing_terms),
                    self._dump_json(summary.exact_identifiers),
                    self._dump_json(summary.suitable_questions),
                    self._dump_json(summary.unsuitable_questions),
                    summary.routing_notes,
                    summary.created_at,
                ),
            )
            connection.executemany(
                """
                INSERT INTO document_sheet_summaries
                  (
                    summary_id, sheet_id, sheet_name, summary,
                    important_columns_json, likely_question_types_json,
                    header_terms_json, sampled_identifiers_json
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        summary.summary_id,
                        sheet.sheet_id,
                        sheet.sheet_name,
                        sheet.summary,
                        self._dump_json(sheet.important_columns),
                        self._dump_json(sheet.likely_question_types),
                        self._dump_json(sheet.header_terms),
                        self._dump_json(sheet.sampled_identifiers),
                    )
                    for sheet in summary.sheet_summaries
                ],
            )

    def get_summary(self, version_id: str) -> DocumentSummary | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM document_summaries WHERE version_id = ?",
                (version_id,),
            ).fetchone()
            if row is None:
                return None
            sheet_rows = connection.execute(
                """
                SELECT * FROM document_sheet_summaries
                WHERE summary_id = ?
                ORDER BY rowid ASC
                """,
                (row["summary_id"],),
            ).fetchall()
        return self._to_summary(row, sheet_rows)

    def list_summaries(self) -> list[DocumentSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM document_summaries ORDER BY created_at DESC"
            ).fetchall()
            sheet_rows_by_summary_id = {
                str(row["summary_id"]): connection.execute(
                    """
                    SELECT * FROM document_sheet_summaries
                    WHERE summary_id = ?
                    ORDER BY rowid ASC
                    """,
                    (row["summary_id"],),
                ).fetchall()
                for row in rows
            }
        return [
            summary
            for row in rows
            if (
                summary := self._to_summary(
                    row,
                    sheet_rows_by_summary_id.get(str(row["summary_id"]), []),
                )
            )
            is not None
        ]

    def create_session(self, session: ChatSession) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO chat_sessions
                  (session_id, created_at, updated_at, title, pinned_at, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.created_at,
                    session.updated_at,
                    session.title,
                    session.pinned_at,
                    session.status,
                ),
            )

    def list_sessions(self) -> list[ChatSession]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM chat_sessions
                WHERE status = 'active'
                ORDER BY
                  CASE WHEN pinned_at IS NULL THEN 1 ELSE 0 END ASC,
                  pinned_at DESC,
                  updated_at DESC
                """,
            ).fetchall()
        return [session for row in rows if (session := self._to_session(row)) is not None]

    def get_session(self, session_id: str) -> ChatSession | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return self._to_session(row)

    def touch_session(self, session_id: str, updated_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE chat_sessions
                SET updated_at = ?
                WHERE session_id = ?
                """,
                (updated_at, session_id),
            )

    def rename_session(
        self,
        session_id: str,
        title: str,
        updated_at: str,
    ) -> ChatSession | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE chat_sessions
                SET title = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (title, updated_at, session_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return self._to_session(row)

    def set_session_pinned(
        self,
        session_id: str,
        pinned_at: str | None,
        updated_at: str,
    ) -> ChatSession | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE chat_sessions
                SET pinned_at = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (pinned_at, updated_at, session_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return self._to_session(row)

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM chat_turns WHERE session_id = ?",
                (session_id,),
            )
            connection.execute(
                "DELETE FROM chat_session_documents WHERE session_id = ?",
                (session_id,),
            )
            cursor = connection.execute(
                "DELETE FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            )
        return cursor.rowcount > 0

    def attach_document(self, document: AttachedDocument) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO chat_session_documents
                  (
                    session_id, file_id, version_id, attached_at,
                    row_count, context_hash, status
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.session_id,
                    document.file_id,
                    document.version_id,
                    document.attached_at,
                    document.row_count,
                    document.context_hash,
                    document.status,
                ),
            )

    def list_attached_documents(self, session_id: str) -> list[AttachedDocument]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM chat_session_documents
                WHERE session_id = ?
                ORDER BY attached_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [doc for row in rows if (doc := self._to_attached_document(row)) is not None]

    def create_turn(self, turn: ChatTurn) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_turns
                  (
                    turn_id, session_id, question, answer_text,
                    citation_ids_json, selected_documents_json, created_at,
                    answer_blocks_json, newly_attached_documents_json,
                    attached_documents_json, citations_json, insufficient_evidence,
                    follow_up_suggestions_json, warnings_json, timings_json
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn.turn_id,
                    turn.session_id,
                    turn.question,
                    turn.answer_text,
                    self._dump_json(turn.citation_ids),
                    self._dump_json(self._selected_documents_payload(turn.selected_documents)),
                    turn.created_at,
                    self._dump_json(self._answer_blocks_payload(turn.answer_blocks)),
                    self._dump_json(
                        self._selected_documents_payload(turn.newly_attached_documents)
                    ),
                    self._dump_json(
                        self._attached_documents_payload(turn.attached_documents)
                    ),
                    self._dump_json(self._citations_payload(turn.citations)),
                    1 if turn.insufficient_evidence else 0,
                    self._dump_json(turn.follow_up_suggestions),
                    self._dump_json(turn.warnings),
                    self._dump_json(self._timings_payload(turn.timings)),
                ),
            )

    def list_turns(self, session_id: str) -> list[ChatTurn]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM chat_turns
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [turn for row in rows if (turn := self._to_turn(row)) is not None]

    def get_llm_preference(self, scope: str) -> LlmPreference | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM llm_preferences WHERE scope = ?",
                (scope,),
            ).fetchone()
        return self._to_llm_preference(row)

    def save_llm_preference(self, preference: LlmPreference) -> LlmPreference:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO llm_preferences
                  (
                    scope, summary_provider, summary_model, router_provider,
                    router_model, answer_provider, answer_model, created_at, updated_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope) DO UPDATE SET
                  summary_provider = excluded.summary_provider,
                  summary_model = excluded.summary_model,
                  router_provider = excluded.router_provider,
                  router_model = excluded.router_model,
                  answer_provider = excluded.answer_provider,
                  answer_model = excluded.answer_model,
                  updated_at = excluded.updated_at
                """,
                (
                    preference.scope,
                    preference.summary_provider,
                    preference.summary_model,
                    preference.router_provider,
                    preference.router_model,
                    preference.answer_provider,
                    preference.answer_model,
                    preference.created_at,
                    preference.updated_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM llm_preferences WHERE scope = ?",
                (preference.scope,),
            ).fetchone()
        saved = self._to_llm_preference(row)
        if saved is None:
            raise RuntimeError("failed to persist llm preference")
        return saved

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._database_path,
            timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS,
        )
        connection.row_factory = sqlite3.Row
        self._configure_connection(connection)
        self._maybe_run_connection_maintenance(connection)
        return connection

    def _configure_connection(self, connection: sqlite3.Connection) -> None:
        connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute(
            f"PRAGMA wal_autocheckpoint = {SQLITE_WAL_AUTOCHECKPOINT_PAGES}"
        )

    def _maybe_run_connection_maintenance(self, connection: sqlite3.Connection) -> None:
        now = time.monotonic()
        if now - self._last_maintenance_at < SQLITE_MAINTENANCE_INTERVAL_SECONDS:
            return
        self._run_connection_maintenance(connection)
        self._last_maintenance_at = now

    def _run_connection_maintenance(self, connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA optimize")
        connection.execute("PRAGMA wal_checkpoint(PASSIVE)")

    def _to_file(self, row: sqlite3.Row | None) -> ExcelFile | None:
        if row is None:
            return None
        return ExcelFile(
            file_id=str(row["file_id"]),
            display_name=str(row["display_name"]),
            active_version_id=row["active_version_id"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _to_version(self, row: sqlite3.Row | None) -> ExcelFileVersion | None:
        if row is None:
            return None
        return ExcelFileVersion(
            version_id=str(row["version_id"]),
            file_id=str(row["file_id"]),
            original_filename=str(row["original_filename"]),
            file_hash=str(row["file_hash"]),
            status=ExcelVersionStatus(str(row["status"])),
            error_message=row["error_message"],
            created_at=str(row["created_at"]),
            activated_at=row["activated_at"],
        )

    def _to_sheet(self, row: sqlite3.Row | None) -> ExcelSheet | None:
        if row is None:
            return None
        return ExcelSheet(
            sheet_id=str(row["sheet_id"]),
            version_id=str(row["version_id"]),
            sheet_index=int(row["sheet_index"]),
            sheet_code=str(row["sheet_code"]),
            sheet_name=str(row["sheet_name"]),
            row_count=int(row["row_count"]),
            column_count=int(row["column_count"]),
            raw_csv_path=str(row["raw_csv_path"]),
            created_at=str(row["created_at"]),
        )

    def _to_artifact(self, row: sqlite3.Row | None) -> ExcelArtifact | None:
        if row is None:
            return None
        return ExcelArtifact(
            artifact_id=str(row["artifact_id"]),
            version_id=str(row["version_id"]),
            artifact_type=ExcelArtifactType(str(row["artifact_type"])),
            path=str(row["path"]),
            created_at=str(row["created_at"]),
        )

    def _to_mapping(self, row: sqlite3.Row | None) -> ExcelRowMapping | None:
        if row is None:
            return None
        return ExcelRowMapping(
            mapping_id=str(row["mapping_id"]),
            version_id=str(row["version_id"]),
            sheet_id=str(row["sheet_id"]),
            row_id=str(row["row_id"]),
            original_row_number=int(row["original_row_number"]),
            raw_csv_row_number=int(row["raw_csv_row_number"]),
            created_at=str(row["created_at"]),
        )

    def _to_summary(
        self,
        row: sqlite3.Row | None,
        sheet_rows: list[sqlite3.Row],
    ) -> DocumentSummary | None:
        if row is None:
            return None
        return DocumentSummary(
            summary_id=str(row["summary_id"]),
            file_id=str(row["file_id"]),
            version_id=str(row["version_id"]),
            document_title=self._row_str(row, "document_title"),
            document_type=self._row_str(row, "document_type", "unknown") or "unknown",
            summary_text=str(row["summary_text"]),
            business_domain=str(row["business_domain"]),
            coverage_scope=self._load_scope_map(self._row_value(row, "coverage_scope_json", "{}")),
            key_topics=self._load_string_list(row["key_topics_json"]),
            positive_routing_terms=self._load_string_list(
                self._row_value(row, "positive_routing_terms_json", "[]")
            ),
            negative_routing_terms=self._load_string_list(
                self._row_value(row, "negative_routing_terms_json", "[]")
            ),
            exact_identifiers=self._load_string_list(
                self._row_value(row, "exact_identifiers_json", "[]")
            ),
            suitable_questions=self._load_string_list(row["suitable_questions_json"]),
            unsuitable_questions=self._load_string_list(
                row["unsuitable_questions_json"]
            ),
            sheet_summaries=[
                SheetSummary(
                    sheet_id=str(sheet_row["sheet_id"]),
                    sheet_name=str(sheet_row["sheet_name"]),
                    summary=str(sheet_row["summary"]),
                    important_columns=self._load_string_list(
                        sheet_row["important_columns_json"]
                    ),
                    likely_question_types=self._load_string_list(
                        sheet_row["likely_question_types_json"]
                    ),
                    header_terms=self._load_string_list(
                        self._row_value(sheet_row, "header_terms_json", "[]")
                    ),
                    sampled_identifiers=self._load_string_list(
                        self._row_value(sheet_row, "sampled_identifiers_json", "[]")
                    ),
                )
                for sheet_row in sheet_rows
            ],
            routing_notes=self._row_str(row, "routing_notes"),
            created_at=str(row["created_at"]),
        )

    def _to_session(self, row: sqlite3.Row | None) -> ChatSession | None:
        if row is None:
            return None
        columns = set(row.keys())
        return ChatSession(
            session_id=str(row["session_id"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            title=str(row["title"]) if "title" in columns else "New chat",
            pinned_at=row["pinned_at"] if "pinned_at" in columns else None,
            status=str(row["status"]),
        )

    def _to_attached_document(
        self,
        row: sqlite3.Row | None,
    ) -> AttachedDocument | None:
        if row is None:
            return None
        return AttachedDocument(
            session_id=str(row["session_id"]),
            file_id=str(row["file_id"]),
            version_id=str(row["version_id"]),
            attached_at=str(row["attached_at"]),
            row_count=int(row["row_count"]),
            context_hash=str(row["context_hash"]),
            status=str(row["status"]),
        )

    def _to_turn(self, row: sqlite3.Row | None) -> ChatTurn | None:
        if row is None:
            return None
        citation_ids = self._load_string_list(row["citation_ids_json"])
        selected_documents = self._selected_documents_from_payload(
            self._load_object_list(row["selected_documents_json"])
        )
        answer_blocks = self._answer_blocks_from_payload(
            self._load_object_list(self._row_value(row, "answer_blocks_json", "[]"))
        )
        if not answer_blocks and str(row["answer_text"]):
            answer_blocks = [
                ChatAnswerBlock(
                    text=str(row["answer_text"]),
                    citation_ids=citation_ids,
                )
            ]
        return ChatTurn(
            turn_id=str(row["turn_id"]),
            session_id=str(row["session_id"]),
            question=str(row["question"]),
            answer_text=str(row["answer_text"]),
            citation_ids=citation_ids,
            selected_documents=selected_documents,
            created_at=str(row["created_at"]),
            answer_blocks=answer_blocks,
            newly_attached_documents=self._selected_documents_from_payload(
                self._load_object_list(
                    self._row_value(row, "newly_attached_documents_json", "[]")
                )
            ),
            attached_documents=self._attached_documents_from_payload(
                self._load_object_list(
                    self._row_value(row, "attached_documents_json", "[]")
                )
            ),
            citations=self._citations_from_payload(
                self._load_object_list(self._row_value(row, "citations_json", "[]"))
            ),
            insufficient_evidence=bool(
                int(self._row_value(row, "insufficient_evidence", 0) or 0)
            ),
            follow_up_suggestions=self._load_string_list(
                self._row_value(row, "follow_up_suggestions_json", "[]")
            ),
            warnings=self._load_string_list(self._row_value(row, "warnings_json", "[]")),
            timings=self._timings_from_payload(
                self._load_object_list(self._row_value(row, "timings_json", "[]"))
            ),
        )

    def _to_llm_preference(self, row: sqlite3.Row | None) -> LlmPreference | None:
        if row is None:
            return None
        return LlmPreference(
            scope=str(row["scope"]),
            summary_provider=str(row["summary_provider"]),
            summary_model=str(row["summary_model"]),
            router_provider=str(row["router_provider"]),
            router_model=str(row["router_model"]),
            answer_provider=str(row["answer_provider"]),
            answer_model=str(row["answer_model"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _answer_blocks_payload(self, blocks: list[ChatAnswerBlock]) -> list[dict[str, object]]:
        return [
            {
                "text": block.text,
                "citation_ids": block.citation_ids,
                "reasoning": block.reasoning,
            }
            for block in blocks
        ]

    def _answer_blocks_from_payload(
        self,
        payload: list[dict],
    ) -> list[ChatAnswerBlock]:
        return [
            ChatAnswerBlock(
                text=str(block.get("text", "")),
                citation_ids=[
                    str(item)
                    for item in block.get("citation_ids", [])
                    if str(item).strip()
                ]
                if isinstance(block.get("citation_ids", []), list)
                else [],
                reasoning=str(block.get("reasoning", "") or ""),
            )
            for block in payload
            if str(block.get("text", "")).strip()
        ]

    def _selected_documents_payload(
        self,
        documents: list[SelectedDocument],
    ) -> list[dict[str, object]]:
        return [
            {
                "file_id": document.file_id,
                "version_id": document.version_id,
                "reason": document.reason,
                "confidence": document.confidence,
            }
            for document in documents
        ]

    def _selected_documents_from_payload(
        self,
        payload: list[dict],
    ) -> list[SelectedDocument]:
        documents: list[SelectedDocument] = []
        for document in payload:
            file_id = str(document.get("file_id", ""))
            version_id = str(document.get("version_id", ""))
            if not file_id or not version_id:
                continue
            confidence = document.get("confidence")
            documents.append(
                SelectedDocument(
                    file_id=file_id,
                    version_id=version_id,
                    reason=str(document.get("reason", "")),
                    confidence=float(confidence) if isinstance(confidence, int | float) else None,
                )
            )
        return documents

    def _attached_documents_payload(
        self,
        documents: list[AttachedDocument],
    ) -> list[dict[str, object]]:
        return [
            {
                "session_id": document.session_id,
                "file_id": document.file_id,
                "version_id": document.version_id,
                "attached_at": document.attached_at,
                "row_count": document.row_count,
                "context_hash": document.context_hash,
                "status": document.status,
            }
            for document in documents
        ]

    def _attached_documents_from_payload(
        self,
        payload: list[dict],
    ) -> list[AttachedDocument]:
        documents: list[AttachedDocument] = []
        for document in payload:
            file_id = str(document.get("file_id", ""))
            version_id = str(document.get("version_id", ""))
            if not file_id or not version_id:
                continue
            documents.append(
                AttachedDocument(
                    session_id=str(document.get("session_id", "")),
                    file_id=file_id,
                    version_id=version_id,
                    attached_at=str(document.get("attached_at", "")),
                    row_count=self._safe_int(document.get("row_count"), 0),
                    context_hash=str(document.get("context_hash", "")),
                    status=str(document.get("status", "attached")),
                )
            )
        return documents

    def _citations_payload(self, citations: list[ExcelCitation]) -> list[dict[str, object]]:
        return [
            {
                "citation_id": citation.citation_id,
                "evidence_id": citation.evidence_id,
                "file_id": citation.file_id,
                "version_id": citation.version_id,
                "sheet_id": citation.sheet_id,
                "sheet_name": citation.sheet_name,
                "row_id": citation.row_id,
                "row": citation.row,
                "quote": citation.quote,
            }
            for citation in citations
        ]

    def _citations_from_payload(self, payload: list[dict]) -> list[ExcelCitation]:
        citations: list[ExcelCitation] = []
        for citation in payload:
            citation_id = str(citation.get("citation_id", ""))
            evidence_id = str(citation.get("evidence_id", ""))
            if not citation_id or not evidence_id:
                continue
            row_payload = citation.get("row", [])
            row_values = (
                [str(item) for item in row_payload]
                if isinstance(row_payload, list)
                else []
            )
            citations.append(
                ExcelCitation(
                    citation_id=citation_id,
                    evidence_id=evidence_id,
                    file_id=str(citation.get("file_id", "")),
                    version_id=str(citation.get("version_id", "")),
                    sheet_id=str(citation.get("sheet_id", "")),
                    sheet_name=str(citation.get("sheet_name", "")),
                    row_id=str(citation.get("row_id", "")),
                    row=row_values,
                    quote=str(citation.get("quote", "")),
                )
            )
        return citations

    def _timings_payload(self, timings: list[ChatStageTiming]) -> list[dict[str, object]]:
        return [
            {
                "stage": timing.stage,
                "duration_seconds": timing.duration_seconds,
            }
            for timing in timings
        ]

    def _timings_from_payload(self, payload: list[dict]) -> list[ChatStageTiming]:
        timings: list[ChatStageTiming] = []
        for timing in payload:
            stage = str(timing.get("stage", ""))
            if not stage:
                continue
            duration = timing.get("duration_seconds", 0.0)
            timings.append(
                ChatStageTiming(
                    stage=stage,
                    duration_seconds=float(duration) if isinstance(duration, int | float) else 0.0,
                )
            )
        return timings

    def _dump_json(self, value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _load_string_list(self, value: object) -> list[str]:
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed if str(item).strip()]

    def _load_scope_map(self, value: object) -> dict[str, list[str]]:
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {
            str(key): [
                str(item)
                for item in items
                if str(item).strip()
            ]
            for key, items in parsed.items()
            if isinstance(items, list)
        }

    def _load_object_list(self, value: object) -> list[dict]:
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, dict)]

    def _row_value(
        self,
        row: sqlite3.Row,
        column: str,
        default: object = None,
    ) -> object:
        return row[column] if column in row.keys() else default

    def _row_str(
        self,
        row: sqlite3.Row,
        column: str,
        default: str = "",
    ) -> str:
        value = self._row_value(row, column, default)
        return str(value) if value is not None else default

    def _safe_int(self, value: object, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
