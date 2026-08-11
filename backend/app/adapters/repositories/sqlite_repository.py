import sqlite3
from pathlib import Path

from app.adapters.repositories.sqlite.auth import SQLiteAuthRepository
from app.adapters.repositories.sqlite.database import SQLiteDatabase
from app.adapters.repositories.sqlite.excel_upload_tasks import (
    SQLiteExcelUploadTaskRepository,
)
from app.adapters.repositories.sqlite.health import (
    SQLiteRuntimeHealthProbe,
    SQLiteRuntimeInspection,
)
from app.adapters.repositories.sqlite.llm_preferences import (
    SQLiteLlmPreferenceRepository,
)
from app.adapters.repositories.sqlite.migrations import SQLiteMigrationRunner
from app.adapters.repositories.sqlite.policies import (
    AUTH_SESSION_RETENTION_DAYS,
    LOGIN_ATTEMPT_RETENTION_DAYS,
    PASSWORD_RESET_TOKEN_RETENTION_DAYS,
    SQLITE_BUSY_TIMEOUT_MS,
    SQLITE_CONNECTION_TIMEOUT_SECONDS,
    SQLITE_MAINTENANCE_INTERVAL_SECONDS,
    SQLITE_WAL_AUTOCHECKPOINT_PAGES,
    SQLiteConnectionPolicy,
    SQLiteMaintenancePolicy,
)
from app.adapters.repositories.sqlite.row_search import SQLiteRowSearchIndex
from app.adapters.repositories.sqlite.schema import SCHEMA_MIGRATIONS, SchemaMigration
from app.adapters.repositories.sqlite.serialization import (
    dump_json,
    load_json_object,
    load_object_list,
    load_scope_map,
    load_string_list,
    row_str,
    row_value,
    safe_int,
)
from app.core.content_fingerprint import ordered_content_fingerprint
from app.core.errors import (
    ChatIdempotencyConflict,
    ChatRequestInProgress,
    ChatSessionRevisionConflict,
)
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    AttachedDocument,
    AuthSession,
    ChatAnswerBlock,
    ChatSession,
    ChatTurn,
    ChatWorkspace,
    DocumentSummary,
    ExcelArtifact,
    ExcelArtifactType,
    ExcelCitation,
    ExcelFile,
    ExcelFileStatus,
    ExcelFileVersion,
    ExcelFileVisibility,
    ExcelRowMapping,
    ExcelRowSearchEntry,
    ExcelRowSearchMatch,
    ExcelSheet,
    ExcelUploadTask,
    ExcelVersionStatus,
    LlmPreference,
    PasswordResetToken,
    PdfAttachedDocument,
    PdfDocumentChunk,
    PdfDocumentDetail,
    PdfDocumentSummary,
    PdfFile,
    PdfFileCleanupJob,
    PdfFileKind,
    PdfFileStatus,
    PdfFileVisibility,
    PdfModelSetting,
    PdfParseArtifact,
    PdfParsePage,
    PdfParsePageStatus,
    PdfParseQualityStatus,
    PdfParseReport,
    PdfPreviewBlock,
    PdfProcessingStatus,
    PdfSchemaItem,
    PdfSummaryTask,
    PdfSummaryTaskStatus,
    PdfUploadBatch,
    PdfUploadBatchStatus,
    PdfUploadTask,
    PdfUploadTaskStage,
    PdfUploadTaskStatus,
    SelectedDocument,
    SheetSummary,
    UserAccount,
)

__all__ = [
    "AUTH_SESSION_RETENTION_DAYS",
    "PASSWORD_RESET_TOKEN_RETENTION_DAYS",
    "LOGIN_ATTEMPT_RETENTION_DAYS",
    "SCHEMA_MIGRATIONS",
    "SQLITE_BUSY_TIMEOUT_MS",
    "SQLITE_CONNECTION_TIMEOUT_SECONDS",
    "SQLITE_MAINTENANCE_INTERVAL_SECONDS",
    "SQLITE_WAL_AUTOCHECKPOINT_PAGES",
    "SQLiteExcelAssetRepository",
    "SchemaMigration",
]

PDF_FILE_WITH_PARSE_REPORT_SELECT = """
SELECT
  f.file_id,
  f.user_id,
  f.parent_id,
  f.display_name,
  f.original_filename,
  f.kind,
  f.size_bytes,
  f.storage_path,
  f.status,
  f.visibility,
  f.processing_status,
  f.progress,
  f.status_detail,
  f.error_message,
  f.page_count,
  f.chunk_count,
  f.created_at,
  f.updated_at,
  f.deleted_at,
  f.content_fingerprint,
  r.quality_status AS parse_quality_status,
  r.coverage_ratio AS parse_coverage_ratio,
  r.warning_count AS parse_warning_count,
  r.failed_pages AS parse_failed_page_count,
  r.parser_backend AS parse_parser_backend
FROM pdf_files f
LEFT JOIN pdf_parse_reports r ON r.file_id = f.file_id
"""


class SQLiteExcelAssetRepository:
    def __init__(
        self,
        database_path: Path,
        *,
        maintenance_interval_seconds: float = SQLITE_MAINTENANCE_INTERVAL_SECONDS,
        auth_session_retention_days: int = AUTH_SESSION_RETENTION_DAYS,
        password_reset_token_retention_days: int = PASSWORD_RESET_TOKEN_RETENTION_DAYS,
        connection_policy: SQLiteConnectionPolicy | None = None,
        maintenance_policy: SQLiteMaintenancePolicy | None = None,
    ) -> None:
        self._database_path = database_path
        self._connection_policy = connection_policy or SQLiteConnectionPolicy(
            maintenance_interval_seconds=maintenance_interval_seconds,
        )
        self._maintenance_policy = maintenance_policy or SQLiteMaintenancePolicy(
            auth_session_retention_days=auth_session_retention_days,
            password_reset_token_retention_days=password_reset_token_retention_days,
        )
        self._database = SQLiteDatabase(
            self._database_path,
            connection_policy=self._connection_policy,
            maintenance_policy=self._maintenance_policy,
        )
        self._migration_runner = SQLiteMigrationRunner(SCHEMA_MIGRATIONS)
        self._runtime_health = SQLiteRuntimeHealthProbe(
            self._database_path,
            self._migration_runner,
            busy_timeout_ms=self._connection_policy.busy_timeout_ms,
        )
        self._row_search_index = SQLiteRowSearchIndex(
            connect=self._connect,
            dump_json=dump_json,
        )
        self._auth = SQLiteAuthRepository(self._connect)
        self._excel_upload_tasks = SQLiteExcelUploadTaskRepository(self._connect)
        self._llm_preferences = SQLiteLlmPreferenceRepository(self._connect)

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect(run_maintenance=False) as connection:
            self._migration_runner.initialize_schema(connection)
            self._backfill_pdf_content_fingerprints(connection)
        self.run_operational_maintenance()

    def inspect_runtime(self) -> SQLiteRuntimeInspection:
        return self._runtime_health.inspect()

    def _backfill_pdf_content_fingerprints(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        rows = connection.execute(
            """
            SELECT chunk.file_id, chunk.content_hash
            FROM pdf_document_chunks AS chunk
            JOIN pdf_files AS file ON file.file_id = chunk.file_id
            WHERE file.kind = ?
              AND file.content_fingerprint = ''
            ORDER BY chunk.file_id ASC, chunk.chunk_index ASC
            """,
            (PdfFileKind.PDF.value,),
        ).fetchall()
        hashes_by_file_id: dict[str, list[str]] = {}
        for row in rows:
            hashes_by_file_id.setdefault(str(row["file_id"]), []).append(
                str(row["content_hash"])
            )
        connection.executemany(
            """
            UPDATE pdf_files
            SET content_fingerprint = ?
            WHERE file_id = ?
            """,
            [
                (ordered_content_fingerprint(content_hashes), file_id)
                for file_id, content_hashes in hashes_by_file_id.items()
            ],
        )
        connection.execute(
            """
            UPDATE pdf_document_summaries
            SET source_fingerprint = (
                  SELECT content_fingerprint
                  FROM pdf_files
                  WHERE pdf_files.file_id = pdf_document_summaries.file_id
                ),
                source_updated_at = COALESCE(
                  source_updated_at,
                  (SELECT updated_at
                   FROM pdf_files
                   WHERE pdf_files.file_id = pdf_document_summaries.file_id)
                )
            WHERE source_fingerprint = ''
              AND EXISTS (
                SELECT 1
                FROM pdf_files
                WHERE pdf_files.file_id = pdf_document_summaries.file_id
                  AND pdf_files.content_fingerprint <> ''
              )
            """
        )

    def create_file(self, file: ExcelFile) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO excel_files
                  (
                    file_id, display_name, active_version_id, created_at,
                    updated_at, status, deleted_at, visibility
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file.file_id,
                    file.display_name,
                    file.active_version_id,
                    file.created_at,
                    file.updated_at,
                    file.status.value,
                    file.deleted_at,
                    file.visibility.value,
                ),
            )

    def get_file(self, file_id: str) -> ExcelFile | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM excel_files
                WHERE file_id = ? AND status = ?
                """,
                (file_id, ExcelFileStatus.ACTIVE.value),
            ).fetchone()
        return self._to_file(row)

    def get_file_including_deleted(self, file_id: str) -> ExcelFile | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM excel_files
                WHERE file_id = ?
                """,
                (file_id,),
            ).fetchone()
        return self._to_file(row)

    def find_file_by_display_name(self, display_name: str) -> ExcelFile | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM excel_files
                WHERE display_name = ? AND status = ?
                """,
                (display_name, ExcelFileStatus.ACTIVE.value),
            ).fetchone()
        return self._to_file(row)

    def list_files(self) -> list[ExcelFile]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM excel_files
                WHERE status = ?
                ORDER BY updated_at DESC, display_name ASC
                """,
                (ExcelFileStatus.ACTIVE.value,),
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
                WHERE file_id = ? AND status = ?
                """,
                (display_name, updated_at, file_id, ExcelFileStatus.ACTIVE.value),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT * FROM excel_files
                WHERE file_id = ? AND status = ?
                """,
                (file_id, ExcelFileStatus.ACTIVE.value),
            ).fetchone()
        return self._to_file(row)

    def update_file_visibility(
        self,
        file_id: str,
        visibility: ExcelFileVisibility,
        updated_at: str,
    ) -> ExcelFile | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE excel_files
                SET visibility = ?, updated_at = ?
                WHERE file_id = ? AND status = ?
                """,
                (
                    visibility.value,
                    updated_at,
                    file_id,
                    ExcelFileStatus.ACTIVE.value,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT * FROM excel_files
                WHERE file_id = ? AND status = ?
                """,
                (file_id, ExcelFileStatus.ACTIVE.value),
            ).fetchone()
        return self._to_file(row)

    def delete_file(self, file_id: str) -> dict[str, int]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT display_name FROM excel_files
                WHERE file_id = ? AND status = ?
                """,
                (file_id, ExcelFileStatus.ACTIVE.value),
            ).fetchone()
            if row is None:
                return {
                    "deleted_versions": 0,
                    "deleted_sheets": 0,
                    "deleted_artifacts": 0,
                    "deleted_row_mappings": 0,
                    "deleted_summaries": 0,
                    "deleted_chat_session_documents": 0,
                }

            deleted_at = utc_now_iso()
            archived_display_name = self._deleted_file_display_name(
                file_id=file_id,
                display_name=str(row["display_name"]),
            )
            connection.execute(
                """
                UPDATE excel_files
                SET
                  display_name = ?,
                  active_version_id = NULL,
                  status = ?,
                  deleted_at = ?,
                  updated_at = ?
                WHERE file_id = ? AND status = ?
                """,
                (
                    archived_display_name,
                    ExcelFileStatus.DELETED.value,
                    deleted_at,
                    deleted_at,
                    file_id,
                    ExcelFileStatus.ACTIVE.value,
                ),
            )

        return {
            "deleted_versions": 0,
            "deleted_sheets": 0,
            "deleted_artifacts": 0,
            "deleted_row_mappings": 0,
            "deleted_summaries": 0,
            "deleted_chat_session_documents": 0,
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

    def list_row_mappings_for_sheet_page(
        self,
        sheet_id: str,
        offset: int,
        limit: int,
    ) -> list[ExcelRowMapping]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM excel_row_mappings
                WHERE sheet_id = ?
                ORDER BY raw_csv_row_number ASC
                LIMIT ? OFFSET ?
                """,
                (sheet_id, max(1, limit), max(0, offset)),
            ).fetchall()
        return [mapping for row in rows if (mapping := self._to_mapping(row)) is not None]

    def replace_row_search_entries(
        self,
        version_id: str,
        entries: list[ExcelRowSearchEntry],
    ) -> None:
        self._row_search_index.replace_entries(version_id, entries)

    def has_row_search_entries(self, version_id: str) -> bool:
        return self._row_search_index.has_entries(version_id)

    def search_row_index(
        self,
        *,
        version_id: str,
        query: str,
        sheet_id: str | None = None,
        limit: int | None = None,
    ) -> list[ExcelRowSearchMatch]:
        return self._row_search_index.search(
            version_id=version_id,
            query=query,
            sheet_id=sheet_id,
            limit=limit,
        )

    def create_upload_task(self, task: ExcelUploadTask) -> None:
        self._excel_upload_tasks.create(task)

    def get_upload_task(self, task_id: str) -> ExcelUploadTask | None:
        return self._excel_upload_tasks.get(task_id)

    def claim_next_upload_task(
        self,
        *,
        worker_id: str,
        started_at: str,
    ) -> ExcelUploadTask | None:
        return self._excel_upload_tasks.claim_next(
            worker_id=worker_id,
            started_at=started_at,
        )

    def complete_upload_task(
        self,
        *,
        task_id: str,
        result: dict[str, object],
        finished_at: str,
    ) -> ExcelUploadTask | None:
        return self._excel_upload_tasks.complete(
            task_id=task_id,
            result=result,
            finished_at=finished_at,
        )

    def fail_upload_task(
        self,
        *,
        task_id: str,
        error_message: str,
        finished_at: str,
    ) -> ExcelUploadTask | None:
        return self._excel_upload_tasks.fail(
            task_id=task_id,
            error_message=error_message,
            finished_at=finished_at,
        )

    def fail_stale_processing_upload_tasks(
        self,
        *,
        cutoff_started_at: str,
        failed_at: str,
    ) -> int:
        return self._excel_upload_tasks.fail_stale_processing(
            cutoff_started_at=cutoff_started_at,
            failed_at=failed_at,
        )

    def create_pdf_file(self, file: PdfFile) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pdf_files
                  (
                    file_id, user_id, parent_id, display_name, original_filename,
                    kind, size_bytes, storage_path, status, visibility,
                    processing_status, progress, status_detail, error_message,
                    page_count, chunk_count, created_at, updated_at, deleted_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._pdf_file_values(file),
            )

    def get_pdf_file(self, file_id: str) -> PdfFile | None:
        with self._connect() as connection:
            row = connection.execute(
                f"""
                {PDF_FILE_WITH_PARSE_REPORT_SELECT}
                WHERE f.file_id = ? AND f.status = ?
                """,
                (file_id, PdfFileStatus.ACTIVE.value),
            ).fetchone()
        return self._to_pdf_file(row)

    def get_pdf_file_including_deleted(self, file_id: str) -> PdfFile | None:
        with self._connect() as connection:
            row = connection.execute(
                f"""
                {PDF_FILE_WITH_PARSE_REPORT_SELECT}
                WHERE f.file_id = ?
                """,
                (file_id,),
            ).fetchone()
        return self._to_pdf_file(row)

    def find_pdf_file_by_parent_and_name(
        self,
        *,
        user_id: str,
        parent_id: str | None,
        display_name: str,
        status: PdfFileStatus = PdfFileStatus.ACTIVE,
    ) -> PdfFile | None:
        with self._connect() as connection:
            row = connection.execute(
                f"""
                {PDF_FILE_WITH_PARSE_REPORT_SELECT}
                WHERE f.user_id = ?
                  AND f.display_name = ?
                  AND f.status = ?
                  AND (
                    (? IS NULL AND f.parent_id IS NULL)
                    OR f.parent_id = ?
                  )
                ORDER BY f.updated_at DESC, f.file_id ASC
                LIMIT 1
                """,
                (
                    user_id,
                    display_name,
                    status.value,
                    parent_id,
                    parent_id,
                ),
            ).fetchone()
        return self._to_pdf_file(row)

    def get_pdf_folder_by_parent_and_name(
        self,
        *,
        user_id: str,
        parent_id: str | None,
        display_name: str,
    ) -> PdfFile | None:
        with self._connect() as connection:
            return self._get_pdf_folder_by_parent_and_name(
                connection,
                user_id=user_id,
                parent_id=parent_id,
                display_name=display_name,
            )

    def get_or_create_pdf_folder(
        self,
        *,
        user_id: str,
        parent_id: str | None,
        display_name: str,
        created_at: str,
    ) -> PdfFile:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            folder = self._get_pdf_folder_by_parent_and_name(
                connection,
                user_id=user_id,
                parent_id=parent_id,
                display_name=display_name,
            )
            if folder is not None:
                return folder
            folder = PdfFile(
                file_id=new_id("pdffolder"),
                user_id=user_id,
                parent_id=parent_id,
                display_name=display_name,
                original_filename=display_name,
                kind=PdfFileKind.FOLDER,
                size_bytes=0,
                storage_path=None,
                status=PdfFileStatus.ACTIVE,
                visibility=PdfFileVisibility.VISIBLE,
                processing_status=PdfProcessingStatus.READY,
                progress=100,
                status_detail="Folder indexed",
                error_message=None,
                page_count=None,
                chunk_count=None,
                created_at=created_at,
                updated_at=created_at,
            )
            connection.execute(
                """
                INSERT INTO pdf_files
                  (
                    file_id, user_id, parent_id, display_name, original_filename,
                    kind, size_bytes, storage_path, status, visibility,
                    processing_status, progress, status_detail, error_message,
                    page_count, chunk_count, created_at, updated_at, deleted_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._pdf_file_values(folder),
            )
            return folder

    def list_pdf_files(self) -> list[PdfFile]:
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                {PDF_FILE_WITH_PARSE_REPORT_SELECT}
                WHERE f.status = ?
                ORDER BY f.updated_at DESC, f.display_name ASC
                """,
                (PdfFileStatus.ACTIVE.value,),
            ).fetchall()
        return [file for row in rows if (file := self._to_pdf_file(row)) is not None]

    def list_pdf_files_by_ids(self, file_ids: list[str]) -> list[PdfFile]:
        normalized_ids = list(dict.fromkeys(file_id for file_id in file_ids if file_id))
        if not normalized_ids:
            return []
        placeholders = ",".join("?" for _file_id in normalized_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                {PDF_FILE_WITH_PARSE_REPORT_SELECT}
                WHERE f.file_id IN ({placeholders})
                  AND f.status = ?
                """,
                (*normalized_ids, PdfFileStatus.ACTIVE.value),
            ).fetchall()
        return [file for row in rows if (file := self._to_pdf_file(row)) is not None]

    def update_pdf_file_display_name(
        self,
        file_id: str,
        display_name: str,
        updated_at: str,
    ) -> PdfFile | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_files
                SET display_name = ?, updated_at = ?
                WHERE file_id = ? AND status = ?
                """,
                (display_name, updated_at, file_id, PdfFileStatus.ACTIVE.value),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                f"""
                {PDF_FILE_WITH_PARSE_REPORT_SELECT}
                WHERE f.file_id = ? AND f.status = ?
                """,
                (file_id, PdfFileStatus.ACTIVE.value),
            ).fetchone()
        return self._to_pdf_file(row)

    def update_pdf_file_processing(
        self,
        *,
        file_id: str,
        processing_status: PdfProcessingStatus,
        progress: int,
        status_detail: str,
        updated_at: str,
        error_message: str | None = None,
        page_count: int | None = None,
        chunk_count: int | None = None,
    ) -> PdfFile | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_files
                SET processing_status = ?,
                    progress = ?,
                    status_detail = ?,
                    error_message = ?,
                    page_count = COALESCE(?, page_count),
                    chunk_count = COALESCE(?, chunk_count),
                    updated_at = ?
                WHERE file_id = ? AND status = ?
                """,
                (
                    processing_status.value,
                    progress,
                    status_detail,
                    error_message,
                    page_count,
                    chunk_count,
                    updated_at,
                    file_id,
                    PdfFileStatus.ACTIVE.value,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT * FROM pdf_files
                WHERE file_id = ? AND status = ?
                """,
                (file_id, PdfFileStatus.ACTIVE.value),
            ).fetchone()
        return self._to_pdf_file(row)

    def update_pdf_file_visibility(
        self,
        file_id: str,
        visibility: PdfFileVisibility,
        updated_at: str,
    ) -> PdfFile | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_files
                SET visibility = ?, updated_at = ?
                WHERE file_id = ? AND status = ?
                """,
                (
                    visibility.value,
                    updated_at,
                    file_id,
                    PdfFileStatus.ACTIVE.value,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT * FROM pdf_files
                WHERE file_id = ? AND status = ?
                """,
                (file_id, PdfFileStatus.ACTIVE.value),
            ).fetchone()
        return self._to_pdf_file(row)

    def delete_pdf_file_tree(self, file_id: str) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                WITH RECURSIVE tree(file_id, display_name) AS (
                  SELECT file_id, display_name
                  FROM pdf_files
                  WHERE file_id = ? AND status = ?
                  UNION ALL
                  SELECT child.file_id, child.display_name
                  FROM pdf_files child
                  JOIN tree parent ON child.parent_id = parent.file_id
                  WHERE child.status = ?
                )
                SELECT file_id, display_name FROM tree
                """,
                (
                    file_id,
                    PdfFileStatus.ACTIVE.value,
                    PdfFileStatus.ACTIVE.value,
                ),
            ).fetchall()
            if not rows:
                return self._empty_pdf_delete_counts()

            deleted_at = utc_now_iso()
            file_ids = [str(row["file_id"]) for row in rows]
            cleanup_jobs = [
                (
                    new_id("pdfcleanup"),
                    current_file_id,
                    f"pdf-knowledge/files/{current_file_id}",
                    "pending",
                    0,
                    None,
                    deleted_at,
                    deleted_at,
                    None,
                )
                for current_file_id in file_ids
                if connection.execute(
                    """
                    SELECT 1 FROM pdf_files
                    WHERE file_id = ? AND storage_path IS NOT NULL
                    """,
                    (current_file_id,),
                ).fetchone()
                is not None
            ]
            connection.executemany(
                """
                INSERT OR IGNORE INTO pdf_file_cleanup_jobs
                  (
                    job_id, file_id, relative_path, status, attempt_count,
                    error_message, created_at, updated_at, completed_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                cleanup_jobs,
            )

            deleted_counts: dict[str, int] = {}
            content_tables = (
                ("pdf_chat_session_documents", "deleted_chat_attachments"),
                ("pdf_document_chunks", "deleted_chunks"),
                ("pdf_preview_blocks", "deleted_preview_blocks"),
                ("pdf_schema_items", "deleted_schema_items"),
                ("pdf_document_tags", "deleted_tags"),
                ("pdf_parse_pages", "deleted_parse_pages"),
                ("pdf_parse_artifacts", "deleted_parse_artifacts"),
                ("pdf_parse_reports", "deleted_parse_reports"),
                ("pdf_document_summaries", "deleted_summaries"),
            )
            for table_name, count_name in content_tables:
                deleted_counts[count_name] = sum(
                    max(
                        0,
                        connection.execute(
                            f"DELETE FROM {table_name} WHERE file_id = ?",
                            (current_file_id,),
                        ).rowcount,
                    )
                    for current_file_id in file_ids
                )
            connection.executemany(
                """
                UPDATE pdf_summary_tasks
                SET status = ?,
                    progress = 100,
                    detail = ?,
                    error_message = NULL,
                    updated_at = ?,
                    finished_at = ?,
                    state_revision = state_revision + 1
                WHERE file_id = ? AND status IN (?, ?)
                """,
                [
                    (
                        PdfSummaryTaskStatus.CANCELLED.value,
                        "Cancelled because the PDF source was deleted.",
                        deleted_at,
                        deleted_at,
                        current_file_id,
                        PdfSummaryTaskStatus.QUEUED.value,
                        PdfSummaryTaskStatus.RUNNING.value,
                    )
                    for current_file_id in file_ids
                ],
            )
            connection.executemany(
                """
                UPDATE pdf_upload_tasks
                SET status = ?,
                    stage = ?,
                    progress = 100,
                    detail = ?,
                    updated_at = ?,
                    finished_at = ?
                WHERE file_id = ? AND status IN (?, ?)
                """,
                [
                    (
                        PdfUploadTaskStatus.CANCELLED.value,
                        PdfUploadTaskStage.CANCELLED.value,
                        "Cancelled because the PDF source was deleted.",
                        deleted_at,
                        deleted_at,
                        current_file_id,
                        PdfUploadTaskStatus.QUEUED.value,
                        PdfUploadTaskStatus.PROCESSING.value,
                    )
                    for current_file_id in file_ids
                ],
            )
            archived_names = [
                (
                    self._deleted_file_display_name(
                        file_id=str(row["file_id"]),
                        display_name=str(row["display_name"]),
                    ),
                    PdfFileStatus.DELETED.value,
                    PdfProcessingStatus.CANCELLED.value,
                    "Deleted from PDF knowledge directory.",
                    deleted_at,
                    deleted_at,
                    str(row["file_id"]),
                )
                for row in rows
            ]
            connection.executemany(
                """
                UPDATE pdf_files
                SET
                  display_name = ?,
                  status = ?,
                  processing_status = ?,
                  status_detail = ?,
                  deleted_at = ?,
                  updated_at = ?
                WHERE file_id = ? AND status = 'active'
                """,
                archived_names,
            )

        return {
            **self._empty_pdf_delete_counts(),
            **deleted_counts,
            "deleted_files": len(file_ids),
            "cleanup_jobs": len(cleanup_jobs),
        }

    def list_pending_pdf_file_cleanup_jobs(self) -> list[PdfFileCleanupJob]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pdf_file_cleanup_jobs
                WHERE status IN ('pending', 'failed')
                  AND attempt_count < 10
                ORDER BY created_at ASC
                LIMIT 100
                """
            ).fetchall()
        return [self._to_pdf_file_cleanup_job(row) for row in rows]

    def complete_pdf_file_cleanup_job(
        self,
        *,
        job_id: str,
        completed_at: str,
    ) -> PdfFileCleanupJob | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_file_cleanup_jobs
                SET status = 'completed',
                    attempt_count = attempt_count + 1,
                    error_message = NULL,
                    updated_at = ?,
                    completed_at = ?
                WHERE job_id = ? AND status IN ('pending', 'failed')
                """,
                (completed_at, completed_at, job_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM pdf_file_cleanup_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._to_pdf_file_cleanup_job(row)

    def fail_pdf_file_cleanup_job(
        self,
        *,
        job_id: str,
        error_message: str,
        failed_at: str,
    ) -> PdfFileCleanupJob | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_file_cleanup_jobs
                SET status = 'failed',
                    attempt_count = attempt_count + 1,
                    error_message = ?,
                    updated_at = ?
                WHERE job_id = ? AND status IN ('pending', 'failed')
                """,
                (error_message[:500], failed_at, job_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM pdf_file_cleanup_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._to_pdf_file_cleanup_job(row)

    def _empty_pdf_delete_counts(self) -> dict[str, int]:
        return {
            "deleted_files": 0,
            "deleted_chunks": 0,
            "deleted_summaries": 0,
            "deleted_preview_blocks": 0,
            "deleted_schema_items": 0,
            "deleted_parse_reports": 0,
            "deleted_parse_pages": 0,
            "deleted_parse_artifacts": 0,
        }

    def create_pdf_upload_batch(self, batch: PdfUploadBatch) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pdf_upload_batches
                  (
                    batch_id, user_id, source_name, status, total_files,
                    accepted_files, skipped_files, total_bytes, progress, detail,
                    error_message, parser_backend, result_json, created_at, updated_at,
                    completed_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._pdf_upload_batch_values(batch),
            )

    def get_pdf_upload_batch(self, batch_id: str) -> PdfUploadBatch | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pdf_upload_batches WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
        return self._to_pdf_upload_batch(row)

    def list_pdf_upload_batches(self, user_id: str) -> list[PdfUploadBatch]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pdf_upload_batches
                WHERE user_id = ?
                ORDER BY updated_at DESC
                LIMIT 20
                """,
                (user_id,),
            ).fetchall()
        return [batch for row in rows if (batch := self._to_pdf_upload_batch(row)) is not None]

    def update_pdf_upload_batch_status(
        self,
        *,
        batch_id: str,
        status: PdfUploadBatchStatus,
        progress: int,
        detail: str,
        updated_at: str,
        completed_at: str | None = None,
        error_message: str | None = None,
        result: dict[str, object] | None = None,
    ) -> PdfUploadBatch | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_upload_batches
                SET status = ?,
                    progress = ?,
                    detail = ?,
                    error_message = ?,
                    result_json = COALESCE(?, result_json),
                    updated_at = ?,
                    completed_at = COALESCE(?, completed_at)
                WHERE batch_id = ?
                """,
                (
                    status.value,
                    progress,
                    detail,
                    error_message,
                    dump_json(result) if result is not None else None,
                    updated_at,
                    completed_at,
                    batch_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM pdf_upload_batches WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
        return self._to_pdf_upload_batch(row)

    def create_pdf_upload_task(self, task: PdfUploadTask) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pdf_upload_tasks
                  (
                    task_id, user_id, file_id, original_filename, staging_path,
                    status, progress, detail, error_message, result_json,
                    created_at, updated_at, started_at, finished_at, worker_id,
                    stage, parser_backend, error_code, retry_count, last_retry_at,
                    batch_id
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._pdf_upload_task_values(task),
            )

    def get_pdf_upload_task(self, task_id: str) -> PdfUploadTask | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pdf_upload_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._to_pdf_upload_task(row)

    def list_pdf_upload_tasks(self, user_id: str) -> list[PdfUploadTask]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pdf_upload_tasks
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (user_id,),
            ).fetchall()
        return [task for row in rows if (task := self._to_pdf_upload_task(row)) is not None]

    def list_pdf_upload_tasks_by_batch(self, batch_id: str) -> list[PdfUploadTask]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pdf_upload_tasks
                WHERE batch_id = ?
                ORDER BY created_at ASC
                """,
                (batch_id,),
            ).fetchall()
        return [task for row in rows if (task := self._to_pdf_upload_task(row)) is not None]

    def claim_next_pdf_upload_task(
        self,
        *,
        worker_id: str,
        started_at: str,
    ) -> PdfUploadTask | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_upload_tasks
                SET status = ?,
                    worker_id = ?,
                    started_at = ?,
                    updated_at = ?,
                    error_message = NULL,
                    error_code = NULL,
                    stage = ?,
                    detail = ?,
                    progress = ?
                WHERE task_id = (
                  SELECT task_id
                  FROM pdf_upload_tasks
                  WHERE status = ?
                  ORDER BY created_at ASC
                  LIMIT 1
                )
                """,
                (
                    PdfUploadTaskStatus.PROCESSING.value,
                    worker_id,
                    started_at,
                    started_at,
                    PdfUploadTaskStage.CLAIMED.value,
                    "MinerU parsing started.",
                    20,
                    PdfUploadTaskStatus.QUEUED.value,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT * FROM pdf_upload_tasks
                WHERE worker_id = ?
                  AND status = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (worker_id, PdfUploadTaskStatus.PROCESSING.value),
            ).fetchone()
        return self._to_pdf_upload_task(row)

    def update_pdf_upload_task_progress(
        self,
        *,
        task_id: str,
        progress: int,
        detail: str,
        updated_at: str,
        stage: PdfUploadTaskStage | None = None,
    ) -> PdfUploadTask | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_upload_tasks
                SET progress = ?,
                    detail = ?,
                    stage = COALESCE(?, stage),
                    updated_at = ?
                WHERE task_id = ?
                  AND status = ?
                """,
                (
                    progress,
                    detail,
                    stage.value if stage is not None else None,
                    updated_at,
                    task_id,
                    PdfUploadTaskStatus.PROCESSING.value,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM pdf_upload_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._to_pdf_upload_task(row)

    def complete_pdf_upload_task(
        self,
        *,
        task_id: str,
        result: dict[str, object],
        detail: str,
        finished_at: str,
    ) -> PdfUploadTask | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_upload_tasks
                SET status = ?,
                    progress = ?,
                    stage = ?,
                    detail = ?,
                    result_json = ?,
                    updated_at = ?,
                    finished_at = ?
                WHERE task_id = ?
                """,
                (
                    PdfUploadTaskStatus.READY.value,
                    100,
                    PdfUploadTaskStage.READY.value,
                    detail,
                    dump_json(result),
                    finished_at,
                    finished_at,
                    task_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM pdf_upload_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._to_pdf_upload_task(row)

    def fail_pdf_upload_task(
        self,
        *,
        task_id: str,
        error_message: str,
        failed_at: str,
        error_code: str | None = None,
    ) -> PdfUploadTask | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_upload_tasks
                SET status = ?,
                    progress = ?,
                    stage = ?,
                    detail = ?,
                    error_message = ?,
                    error_code = ?,
                    updated_at = ?,
                    finished_at = ?
                WHERE task_id = ?
                """,
                (
                    PdfUploadTaskStatus.FAILED.value,
                    100,
                    PdfUploadTaskStage.FAILED.value,
                    "PDF parsing failed.",
                    error_message,
                    error_code,
                    failed_at,
                    failed_at,
                    task_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM pdf_upload_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._to_pdf_upload_task(row)

    def cancel_pdf_upload_task(
        self,
        *,
        task_id: str,
        cancelled_at: str,
        detail: str,
    ) -> PdfUploadTask | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_upload_tasks
                SET status = ?,
                    progress = ?,
                    stage = ?,
                    detail = ?,
                    error_message = NULL,
                    error_code = NULL,
                    updated_at = ?,
                    finished_at = ?
                WHERE task_id = ?
                  AND status = ?
                """,
                (
                    PdfUploadTaskStatus.CANCELLED.value,
                    100,
                    PdfUploadTaskStage.CANCELLED.value,
                    detail,
                    cancelled_at,
                    cancelled_at,
                    task_id,
                    PdfUploadTaskStatus.QUEUED.value,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM pdf_upload_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._to_pdf_upload_task(row)

    def list_stale_processing_pdf_upload_tasks(
        self,
        *,
        cutoff_started_at: str,
    ) -> list[PdfUploadTask]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pdf_upload_tasks
                WHERE status = ?
                  AND started_at IS NOT NULL
                  AND started_at < ?
                ORDER BY started_at ASC
                """,
                (
                    PdfUploadTaskStatus.PROCESSING.value,
                    cutoff_started_at,
                ),
            ).fetchall()
        return [task for row in rows if (task := self._to_pdf_upload_task(row)) is not None]

    def fail_stale_processing_pdf_upload_tasks(
        self,
        *,
        cutoff_started_at: str,
        failed_at: str,
    ) -> int:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE pdf_files
                SET processing_status = ?,
                    progress = ?,
                    status_detail = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE file_id IN (
                  SELECT file_id
                  FROM pdf_upload_tasks
                  WHERE status = ?
                    AND started_at IS NOT NULL
                    AND started_at < ?
                    AND file_id IS NOT NULL
                )
                """,
                (
                    PdfProcessingStatus.FAILED.value,
                    100,
                    "PDF processing was interrupted.",
                    "PDF processing was interrupted. Please upload the document again.",
                    failed_at,
                    PdfUploadTaskStatus.PROCESSING.value,
                    cutoff_started_at,
                ),
            )
            cursor = connection.execute(
                """
                UPDATE pdf_upload_tasks
                SET status = ?,
                    error_message = ?,
                    error_code = ?,
                    detail = ?,
                    stage = ?,
                    progress = ?,
                    updated_at = ?,
                    finished_at = ?
                WHERE status = ?
                  AND started_at IS NOT NULL
                  AND started_at < ?
                """,
                (
                    PdfUploadTaskStatus.FAILED.value,
                    "PDF processing was interrupted. Please upload the document again.",
                    "stale_processing_task",
                    "PDF processing was interrupted.",
                    PdfUploadTaskStage.FAILED.value,
                    100,
                    failed_at,
                    failed_at,
                    PdfUploadTaskStatus.PROCESSING.value,
                    cutoff_started_at,
                ),
            )
        return max(0, cursor.rowcount)

    def create_pdf_summary_task(self, task: PdfSummaryTask) -> PdfSummaryTask:
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO pdf_summary_tasks
                      (
                        task_id, user_id, file_id, status, progress, detail,
                        error_message, result_json, created_at, updated_at,
                        started_at, finished_at, worker_id, retry_count, last_retry_at,
                        source_fingerprint, state_revision, claim_token, claimed_at,
                        attempt, parent_task_id
                      )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._pdf_summary_task_values(task),
                )
            except sqlite3.IntegrityError:
                row = connection.execute(
                    """
                    SELECT * FROM pdf_summary_tasks
                    WHERE file_id = ? AND status IN (?, ?)
                    ORDER BY created_at ASC, task_id ASC
                    LIMIT 1
                    """,
                    (
                        task.file_id,
                        PdfSummaryTaskStatus.QUEUED.value,
                        PdfSummaryTaskStatus.RUNNING.value,
                    ),
                ).fetchone()
                existing = self._to_pdf_summary_task(row)
                if existing is None:
                    raise
                return existing
        return task

    def get_pdf_summary_task(self, task_id: str) -> PdfSummaryTask | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pdf_summary_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._to_pdf_summary_task(row)

    def find_active_pdf_summary_task(self, file_id: str) -> PdfSummaryTask | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM pdf_summary_tasks
                WHERE file_id = ?
                  AND status IN (?, ?)
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (
                    file_id,
                    PdfSummaryTaskStatus.QUEUED.value,
                    PdfSummaryTaskStatus.RUNNING.value,
                ),
            ).fetchone()
        return self._to_pdf_summary_task(row)

    def list_pdf_summary_tasks(self, user_id: str) -> list[PdfSummaryTask]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pdf_summary_tasks
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 50
                """
            ).fetchall()
        return [
            task
            for row in rows
            if (task := self._to_pdf_summary_task(row)) is not None
        ]

    def claim_next_pdf_summary_task(
        self,
        *,
        worker_id: str,
        started_at: str,
    ) -> PdfSummaryTask | None:
        claim_token = new_id("pdfsummaryclaim")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_summary_tasks
                SET status = ?,
                    worker_id = ?,
                    claim_token = ?,
                    claimed_at = ?,
                    started_at = ?,
                    updated_at = ?,
                    error_message = NULL,
                    detail = ?,
                    progress = ?,
                    state_revision = state_revision + 1
                WHERE task_id = (
                  SELECT task_id
                  FROM pdf_summary_tasks
                  WHERE status = ?
                  ORDER BY created_at ASC
                  LIMIT 1
                )
                """,
                (
                    PdfSummaryTaskStatus.RUNNING.value,
                    worker_id,
                    claim_token,
                    started_at,
                    started_at,
                    started_at,
                    "PDF summary generation started.",
                    25,
                    PdfSummaryTaskStatus.QUEUED.value,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT * FROM pdf_summary_tasks
                WHERE worker_id = ?
                  AND claim_token = ?
                  AND status = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (worker_id, claim_token, PdfSummaryTaskStatus.RUNNING.value),
            ).fetchone()
        return self._to_pdf_summary_task(row)

    def complete_pdf_summary_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        result: dict[str, object],
        detail: str,
        finished_at: str,
    ) -> PdfSummaryTask | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_summary_tasks
                SET status = ?,
                    progress = ?,
                    detail = ?,
                    error_message = NULL,
                    result_json = ?,
                    updated_at = ?,
                    finished_at = ?,
                    state_revision = state_revision + 1
                WHERE task_id = ?
                  AND status = ?
                  AND worker_id = ?
                  AND claim_token = ?
                """,
                (
                    PdfSummaryTaskStatus.READY.value,
                    100,
                    detail,
                    dump_json(result),
                    finished_at,
                    finished_at,
                    task_id,
                    PdfSummaryTaskStatus.RUNNING.value,
                    worker_id,
                    claim_token,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM pdf_summary_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._to_pdf_summary_task(row)

    def fail_pdf_summary_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        error_message: str,
        failed_at: str,
    ) -> PdfSummaryTask | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_summary_tasks
                SET status = ?,
                    progress = ?,
                    detail = ?,
                    error_message = ?,
                    updated_at = ?,
                    finished_at = ?,
                    state_revision = state_revision + 1
                WHERE task_id = ?
                  AND status = ?
                  AND worker_id = ?
                  AND claim_token = ?
                """,
                (
                    PdfSummaryTaskStatus.FAILED.value,
                    100,
                    "PDF summary generation failed.",
                    error_message,
                    failed_at,
                    failed_at,
                    task_id,
                    PdfSummaryTaskStatus.RUNNING.value,
                    worker_id,
                    claim_token,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM pdf_summary_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._to_pdf_summary_task(row)

    def skip_pdf_summary_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        detail: str,
        result: dict[str, object],
        skipped_at: str,
    ) -> PdfSummaryTask | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_summary_tasks
                SET status = ?,
                    progress = ?,
                    detail = ?,
                    error_message = NULL,
                    result_json = ?,
                    updated_at = ?,
                    finished_at = ?,
                    state_revision = state_revision + 1
                WHERE task_id = ?
                  AND status = ?
                  AND worker_id = ?
                  AND claim_token = ?
                """,
                (
                    PdfSummaryTaskStatus.SKIPPED.value,
                    100,
                    detail,
                    dump_json(result),
                    skipped_at,
                    skipped_at,
                    task_id,
                    PdfSummaryTaskStatus.RUNNING.value,
                    worker_id,
                    claim_token,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM pdf_summary_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._to_pdf_summary_task(row)

    def cancel_pdf_summary_task(
        self,
        *,
        task_id: str,
        cancelled_at: str,
        detail: str,
    ) -> PdfSummaryTask | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_summary_tasks
                SET status = ?,
                    progress = ?,
                    detail = ?,
                    error_message = NULL,
                    updated_at = ?,
                    finished_at = ?
                WHERE task_id = ?
                  AND status = ?
                """,
                (
                    PdfSummaryTaskStatus.CANCELLED.value,
                    100,
                    detail,
                    cancelled_at,
                    cancelled_at,
                    task_id,
                    PdfSummaryTaskStatus.QUEUED.value,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM pdf_summary_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._to_pdf_summary_task(row)

    def retry_pdf_summary_task(
        self,
        *,
        task_id: str,
        retried_at: str,
    ) -> PdfSummaryTask | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_summary_tasks
                SET status = ?,
                    progress = ?,
                    detail = ?,
                    error_message = NULL,
                    result_json = ?,
                    updated_at = ?,
                    started_at = NULL,
                    finished_at = NULL,
                    worker_id = NULL,
                    claim_token = NULL,
                    claimed_at = NULL,
                    source_fingerprint = COALESCE(
                      (SELECT content_fingerprint
                       FROM pdf_files
                       WHERE pdf_files.file_id = pdf_summary_tasks.file_id),
                      ''
                    ),
                    retry_count = retry_count + 1,
                    attempt = attempt + 1,
                    state_revision = state_revision + 1,
                    last_retry_at = ?
                WHERE task_id = ?
                  AND status IN (?, ?, ?)
                """,
                (
                    PdfSummaryTaskStatus.QUEUED.value,
                    5,
                    "Queued for PDF summary retry.",
                    dump_json({}),
                    retried_at,
                    retried_at,
                    task_id,
                    PdfSummaryTaskStatus.FAILED.value,
                    PdfSummaryTaskStatus.SKIPPED.value,
                    PdfSummaryTaskStatus.CANCELLED.value,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM pdf_summary_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._to_pdf_summary_task(row)

    def fail_stale_running_pdf_summary_tasks(
        self,
        *,
        cutoff_started_at: str,
        failed_at: str,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_summary_tasks
                SET status = ?,
                    progress = ?,
                    detail = ?,
                    error_message = ?,
                    updated_at = ?,
                    finished_at = ?
                    , state_revision = state_revision + 1
                WHERE status = ?
                  AND started_at IS NOT NULL
                  AND started_at < ?
                """,
                (
                    PdfSummaryTaskStatus.FAILED.value,
                    100,
                    "PDF summary generation was interrupted.",
                    "PDF summary generation was interrupted. Please retry the task.",
                    failed_at,
                    failed_at,
                    PdfSummaryTaskStatus.RUNNING.value,
                    cutoff_started_at,
                ),
            )
        return max(0, cursor.rowcount)

    def save_pdf_document_detail(self, detail: PdfDocumentDetail) -> None:
        with self._connect() as connection:
            if not self._is_active_pdf_file(connection, detail.file_id):
                return
            connection.execute(
                "DELETE FROM pdf_preview_blocks WHERE file_id = ?",
                (detail.file_id,),
            )
            connection.execute(
                "DELETE FROM pdf_schema_items WHERE file_id = ?",
                (detail.file_id,),
            )
            connection.execute(
                "DELETE FROM pdf_document_tags WHERE file_id = ?",
                (detail.file_id,),
            )
            self._save_pdf_summary(connection, detail.summary)
            connection.executemany(
                """
                INSERT INTO pdf_preview_blocks
                  (block_id, file_id, page_label, title, content, block_index)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        block.block_id,
                        block.file_id,
                        block.page_label,
                        block.title,
                        block.content,
                        block.block_index,
                    )
                    for block in detail.preview_blocks
                ],
            )
            connection.executemany(
                """
                INSERT INTO pdf_schema_items
                  (item_id, file_id, label, value, item_index)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.item_id,
                        item.file_id,
                        item.label,
                        item.value,
                        item.item_index,
                    )
                    for item in detail.schema
                ],
            )
            connection.executemany(
                """
                INSERT INTO pdf_document_tags
                  (file_id, tag, tag_index)
                VALUES (?, ?, ?)
                """,
                [
                    (detail.file_id, tag, index)
                    for index, tag in enumerate(detail.tags)
                ],
            )

    def get_pdf_document_detail(self, file_id: str) -> PdfDocumentDetail | None:
        with self._connect() as connection:
            summary_row = connection.execute(
                "SELECT * FROM pdf_document_summaries WHERE file_id = ?",
                (file_id,),
            ).fetchone()
            block_rows = connection.execute(
                """
                SELECT * FROM pdf_preview_blocks
                WHERE file_id = ?
                ORDER BY block_index ASC
                """,
                (file_id,),
            ).fetchall()
            schema_rows = connection.execute(
                """
                SELECT * FROM pdf_schema_items
                WHERE file_id = ?
                ORDER BY item_index ASC
                """,
                (file_id,),
            ).fetchall()
            tag_rows = connection.execute(
                """
                SELECT tag FROM pdf_document_tags
                WHERE file_id = ?
                ORDER BY tag_index ASC
                """,
                (file_id,),
            ).fetchall()
        if summary_row is None and not block_rows and not schema_rows and not tag_rows:
            return None
        return PdfDocumentDetail(
            file_id=file_id,
            summary=self._to_pdf_summary(summary_row)
            or PdfDocumentSummary(
                file_id=file_id,
                status="empty",
                content="",
            ),
            preview_blocks=[self._to_pdf_preview_block(row) for row in block_rows],
            schema=[self._to_pdf_schema_item(row) for row in schema_rows],
            tags=[str(row["tag"]) for row in tag_rows],
            parse_report=self.get_pdf_parse_report(file_id),
        )

    def save_pdf_document_summary(self, summary: PdfDocumentSummary) -> bool:
        with self._connect() as connection:
            source = connection.execute(
                """
                SELECT content_fingerprint
                FROM pdf_files
                WHERE file_id = ? AND status = ?
                """,
                (summary.file_id, PdfFileStatus.ACTIVE.value),
            ).fetchone()
            if source is None or str(source["content_fingerprint"]) != summary.source_fingerprint:
                return False
            self._save_pdf_summary(connection, summary)
        return True

    def list_pdf_document_summaries(self) -> list[PdfDocumentSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pdf_document_summaries
                ORDER BY updated_at DESC, file_id ASC
                """
            ).fetchall()
        return [
            summary
            for row in rows
            if (summary := self._to_pdf_summary(row)) is not None
        ]

    def save_pdf_parse_report(self, report: PdfParseReport) -> None:
        with self._connect() as connection:
            if not self._is_active_pdf_file(connection, report.file_id):
                return
            connection.execute(
                """
                INSERT INTO pdf_parse_reports
                  (
                    file_id, parser_backend, parser_version, quality_status,
                    total_pages, parsed_pages, failed_pages, empty_pages,
                    text_block_count, table_block_count, image_block_count,
                    chunk_count, coverage_ratio, warning_count, error_count,
                    warnings_json, started_at, finished_at, created_at, updated_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                  parser_backend = excluded.parser_backend,
                  parser_version = excluded.parser_version,
                  quality_status = excluded.quality_status,
                  total_pages = excluded.total_pages,
                  parsed_pages = excluded.parsed_pages,
                  failed_pages = excluded.failed_pages,
                  empty_pages = excluded.empty_pages,
                  text_block_count = excluded.text_block_count,
                  table_block_count = excluded.table_block_count,
                  image_block_count = excluded.image_block_count,
                  chunk_count = excluded.chunk_count,
                  coverage_ratio = excluded.coverage_ratio,
                  warning_count = excluded.warning_count,
                  error_count = excluded.error_count,
                  warnings_json = excluded.warnings_json,
                  started_at = excluded.started_at,
                  finished_at = excluded.finished_at,
                  updated_at = excluded.updated_at
                """,
                (
                    report.file_id,
                    report.parser_backend,
                    report.parser_version,
                    report.quality_status.value,
                    report.total_pages,
                    report.parsed_pages,
                    report.failed_pages,
                    report.empty_pages,
                    report.text_block_count,
                    report.table_block_count,
                    report.image_block_count,
                    report.chunk_count,
                    report.coverage_ratio,
                    report.warning_count,
                    report.error_count,
                    dump_json(report.warnings),
                    report.started_at,
                    report.finished_at,
                    report.created_at,
                    report.updated_at,
                ),
            )

    def get_pdf_parse_report(self, file_id: str) -> PdfParseReport | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pdf_parse_reports WHERE file_id = ?",
                (file_id,),
            ).fetchone()
        report = self._to_pdf_parse_report(row)
        if report is None:
            return None
        return PdfParseReport(
            file_id=report.file_id,
            parser_backend=report.parser_backend,
            parser_version=report.parser_version,
            quality_status=report.quality_status,
            total_pages=report.total_pages,
            parsed_pages=report.parsed_pages,
            failed_pages=report.failed_pages,
            empty_pages=report.empty_pages,
            text_block_count=report.text_block_count,
            table_block_count=report.table_block_count,
            image_block_count=report.image_block_count,
            chunk_count=report.chunk_count,
            coverage_ratio=report.coverage_ratio,
            warning_count=report.warning_count,
            error_count=report.error_count,
            warnings=report.warnings,
            started_at=report.started_at,
            finished_at=report.finished_at,
            created_at=report.created_at,
            updated_at=report.updated_at,
            pages=self.list_pdf_parse_pages(file_id),
            artifacts=self.list_pdf_parse_artifacts(file_id),
        )

    def replace_pdf_parse_pages(
        self,
        file_id: str,
        pages: list[PdfParsePage],
    ) -> None:
        with self._connect() as connection:
            if not self._is_active_pdf_file(connection, file_id):
                return
            connection.execute(
                "DELETE FROM pdf_parse_pages WHERE file_id = ?",
                (file_id,),
            )
            connection.executemany(
                """
                INSERT INTO pdf_parse_pages
                  (
                    page_id, file_id, page_number, page_label, status,
                    text_block_count, table_block_count, image_block_count,
                    char_count, warning_message, error_message
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        page.page_id,
                        page.file_id,
                        page.page_number,
                        page.page_label,
                        page.status.value,
                        page.text_block_count,
                        page.table_block_count,
                        page.image_block_count,
                        page.char_count,
                        page.warning_message,
                        page.error_message,
                    )
                    for page in pages
                ],
            )

    def list_pdf_parse_pages(self, file_id: str) -> list[PdfParsePage]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pdf_parse_pages
                WHERE file_id = ?
                ORDER BY page_number ASC
                """,
                (file_id,),
            ).fetchall()
        return [self._to_pdf_parse_page(row) for row in rows]

    def replace_pdf_parse_artifacts(
        self,
        file_id: str,
        artifacts: list[PdfParseArtifact],
    ) -> None:
        with self._connect() as connection:
            if not self._is_active_pdf_file(connection, file_id):
                return
            connection.execute(
                "DELETE FROM pdf_parse_artifacts WHERE file_id = ?",
                (file_id,),
            )
            connection.executemany(
                """
                INSERT INTO pdf_parse_artifacts
                  (
                    artifact_id, file_id, artifact_type, name, path,
                    size_bytes, content_hash, created_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        artifact.artifact_id,
                        artifact.file_id,
                        artifact.artifact_type,
                        artifact.name,
                        artifact.path,
                        artifact.size_bytes,
                        artifact.content_hash,
                        artifact.created_at,
                    )
                    for artifact in artifacts
                ],
            )

    def list_pdf_parse_artifacts(self, file_id: str) -> list[PdfParseArtifact]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pdf_parse_artifacts
                WHERE file_id = ?
                ORDER BY artifact_type ASC, name ASC
                """,
                (file_id,),
            ).fetchall()
        return [self._to_pdf_parse_artifact(row) for row in rows]

    def replace_pdf_document_chunks(
        self,
        file_id: str,
        chunks: list[PdfDocumentChunk],
    ) -> None:
        created_at = utc_now_iso()
        with self._connect() as connection:
            if not self._is_active_pdf_file(connection, file_id):
                return
            connection.execute(
                "DELETE FROM pdf_document_chunks WHERE file_id = ?",
                (file_id,),
            )
            connection.executemany(
                """
                INSERT INTO pdf_document_chunks
                  (
                    chunk_id, file_id, chunk_index, text, page_label, title,
                    token_count, content_hash, metadata_json, created_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id,
                        chunk.file_id,
                        chunk.chunk_index,
                        chunk.text,
                        chunk.page_label,
                        chunk.title,
                        chunk.token_count,
                        chunk.content_hash,
                        dump_json(chunk.metadata),
                        created_at,
                    )
                    for chunk in chunks
                ],
            )
            connection.execute(
                """
                UPDATE pdf_files
                SET content_fingerprint = ?
                WHERE file_id = ?
                """,
                (
                    ordered_content_fingerprint(
                        [chunk.content_hash for chunk in chunks]
                    ),
                    file_id,
                ),
            )

    def list_pdf_document_chunks(self, file_id: str) -> list[PdfDocumentChunk]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pdf_document_chunks
                WHERE file_id = ?
                ORDER BY chunk_index ASC
                """,
                (file_id,),
            ).fetchall()
        return [self._to_pdf_chunk(row) for row in rows]

    def get_pdf_document_chunk(
        self,
        file_id: str,
        chunk_id: str,
    ) -> PdfDocumentChunk | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM pdf_document_chunks
                WHERE file_id = ? AND chunk_id = ?
                """,
                (file_id, chunk_id),
            ).fetchone()
        return self._to_pdf_chunk(row) if row is not None else None

    def list_pdf_document_chunks_by_file_ids(
        self,
        file_ids: list[str],
    ) -> dict[str, list[PdfDocumentChunk]]:
        normalized_ids = list(dict.fromkeys(file_id for file_id in file_ids if file_id))
        chunks_by_file_id = {file_id: [] for file_id in normalized_ids}
        if not normalized_ids:
            return chunks_by_file_id
        placeholders = ",".join("?" for _file_id in normalized_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM pdf_document_chunks
                WHERE file_id IN ({placeholders})
                ORDER BY file_id ASC, chunk_index ASC
                """,
                normalized_ids,
            ).fetchall()
        for row in rows:
            chunk = self._to_pdf_chunk(row)
            chunks_by_file_id.setdefault(chunk.file_id, []).append(chunk)
        return chunks_by_file_id

    def list_pdf_model_settings(self) -> list[PdfModelSetting]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pdf_model_settings
                ORDER BY setting_id ASC
                """
            ).fetchall()
        return [
            setting
            for row in rows
            if (setting := self._to_pdf_model_setting(row)) is not None
        ]

    def save_pdf_model_setting(self, setting: PdfModelSetting) -> PdfModelSetting:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pdf_model_settings
                  (
                    setting_id, label, providers_json, models_json,
                    selected_provider, selected_model, created_at, updated_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(setting_id) DO UPDATE SET
                  label = excluded.label,
                  providers_json = excluded.providers_json,
                  models_json = excluded.models_json,
                  selected_provider = excluded.selected_provider,
                  selected_model = excluded.selected_model,
                  updated_at = excluded.updated_at
                """,
                (
                    setting.setting_id,
                    setting.label,
                    dump_json(setting.providers),
                    dump_json(setting.models),
                    setting.selected_provider,
                    setting.selected_model,
                    setting.created_at,
                    setting.updated_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM pdf_model_settings WHERE setting_id = ?",
                (setting.setting_id,),
            ).fetchone()
        saved = self._to_pdf_model_setting(row)
        if saved is None:
            raise RuntimeError("failed to save PDF model setting")
        return saved

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
                    dump_json(summary.coverage_scope),
                    dump_json(summary.key_topics),
                    dump_json(summary.positive_routing_terms),
                    dump_json(summary.negative_routing_terms),
                    dump_json(summary.exact_identifiers),
                    dump_json(summary.suitable_questions),
                    dump_json(summary.unsuitable_questions),
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
                        dump_json(sheet.important_columns),
                        dump_json(sheet.likely_question_types),
                        dump_json(sheet.header_terms),
                        dump_json(sheet.sampled_identifiers),
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
                  (
                    session_id, user_id, created_at, updated_at,
                    title, pinned_at, status, workspace, context_file_ids_json,
                    revision, conversation_revision
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.user_id,
                    session.created_at,
                    session.updated_at,
                    session.title,
                    session.pinned_at,
                    session.status,
                    session.workspace.value,
                    dump_json(session.context_file_ids),
                    session.revision,
                    session.conversation_revision,
                ),
            )

    def list_sessions(self, *, workspace: str = ChatWorkspace.EXCEL.value) -> list[ChatSession]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM chat_sessions
                WHERE status = 'active' AND workspace = ?
                ORDER BY
                  CASE WHEN pinned_at IS NULL THEN 1 ELSE 0 END ASC,
                  pinned_at DESC,
                  updated_at DESC
                """,
                (workspace,),
            ).fetchall()
        return [session for row in rows if (session := self._to_session(row)) is not None]

    def get_session(
        self,
        session_id: str,
        *,
        workspace: str = ChatWorkspace.EXCEL.value,
    ) -> ChatSession | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_sessions WHERE session_id = ? AND workspace = ?",
                (session_id, workspace),
            ).fetchone()
        return self._to_session(row)

    def touch_session(self, session_id: str, updated_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE chat_sessions
                SET updated_at = ?, revision = revision + 1
                WHERE session_id = ?
                """,
                (updated_at, session_id),
            )

    def set_session_context_file_ids(
        self,
        session_id: str,
        file_ids: list[str],
        updated_at: str,
        *,
        workspace: str = ChatWorkspace.EXCEL.value,
    ) -> ChatSession | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE chat_sessions
                SET context_file_ids_json = ?, updated_at = ?, revision = revision + 1
                WHERE session_id = ? AND workspace = ?
                """,
                (dump_json(file_ids), updated_at, session_id, workspace),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM chat_sessions WHERE session_id = ? AND workspace = ?",
                (session_id, workspace),
            ).fetchone()
        return self._to_session(row)

    def rename_session(
        self,
        session_id: str,
        title: str,
        updated_at: str,
        *,
        workspace: str = ChatWorkspace.EXCEL.value,
        expected_revision: int | None = None,
    ) -> ChatSession | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE chat_sessions
                SET title = ?, updated_at = ?, revision = revision + 1
                WHERE session_id = ? AND workspace = ?
                  AND (? IS NULL OR revision = ?)
                """,
                (
                    title,
                    updated_at,
                    session_id,
                    workspace,
                    expected_revision,
                    expected_revision,
                ),
            )
            if cursor.rowcount == 0:
                existing = connection.execute(
                    """
                    SELECT revision FROM chat_sessions
                    WHERE session_id = ? AND workspace = ?
                    """,
                    (session_id, workspace),
                ).fetchone()
                if existing is not None and expected_revision is not None:
                    raise ChatSessionRevisionConflict(session_id)
                return None
            row = connection.execute(
                "SELECT * FROM chat_sessions WHERE session_id = ? AND workspace = ?",
                (session_id, workspace),
            ).fetchone()
        return self._to_session(row)

    def set_session_pinned(
        self,
        session_id: str,
        pinned_at: str | None,
        updated_at: str,
        *,
        workspace: str = ChatWorkspace.EXCEL.value,
        expected_revision: int | None = None,
    ) -> ChatSession | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE chat_sessions
                SET pinned_at = ?, updated_at = ?, revision = revision + 1
                WHERE session_id = ? AND workspace = ?
                  AND (? IS NULL OR revision = ?)
                """,
                (
                    pinned_at,
                    updated_at,
                    session_id,
                    workspace,
                    expected_revision,
                    expected_revision,
                ),
            )
            if cursor.rowcount == 0:
                existing = connection.execute(
                    """
                    SELECT revision FROM chat_sessions
                    WHERE session_id = ? AND workspace = ?
                    """,
                    (session_id, workspace),
                ).fetchone()
                if existing is not None and expected_revision is not None:
                    raise ChatSessionRevisionConflict(session_id)
                return None
            row = connection.execute(
                "SELECT * FROM chat_sessions WHERE session_id = ? AND workspace = ?",
                (session_id, workspace),
            ).fetchone()
        return self._to_session(row)

    def delete_session(
        self,
        session_id: str,
        *,
        workspace: str = ChatWorkspace.EXCEL.value,
        expected_revision: int | None = None,
    ) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT session_id, revision FROM chat_sessions
                WHERE session_id = ? AND workspace = ?
                """,
                (session_id, workspace),
            ).fetchone()
            if row is None:
                return False
            if (
                expected_revision is not None
                and int(row["revision"]) != expected_revision
            ):
                raise ChatSessionRevisionConflict(session_id)
            connection.execute(
                "DELETE FROM chat_request_executions WHERE session_id = ?",
                (session_id,),
            )
            connection.execute(
                "DELETE FROM chat_turns WHERE session_id = ?",
                (session_id,),
            )
            connection.execute(
                "DELETE FROM chat_session_documents WHERE session_id = ?",
                (session_id,),
            )
            connection.execute(
                "DELETE FROM pdf_chat_session_documents WHERE session_id = ?",
                (session_id,),
            )
            cursor = connection.execute(
                """
                DELETE FROM chat_sessions
                WHERE session_id = ?
                  AND workspace = ?
                  AND (? IS NULL OR revision = ?)
                """,
                (
                    session_id,
                    workspace,
                    expected_revision,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ChatSessionRevisionConflict(session_id)
        return cursor.rowcount > 0

    def batch_set_sessions_pinned(
        self,
        session_revisions: dict[str, int],
        pinned_at: str | None,
        updated_at: str,
        *,
        workspace: str = ChatWorkspace.EXCEL.value,
    ) -> list[ChatSession]:
        if not session_revisions:
            return []
        session_ids = sorted(session_revisions)
        placeholders = ",".join("?" for _session_id in session_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM chat_sessions
                WHERE workspace = ? AND session_id IN ({placeholders})
                """,
                (workspace, *session_ids),
            ).fetchall()
            rows_by_id = {str(row["session_id"]): row for row in rows}
            for session_id in session_ids:
                row = rows_by_id.get(session_id)
                if (
                    row is None
                    or int(row["revision"]) != session_revisions[session_id]
                ):
                    raise ChatSessionRevisionConflict(session_id)
            cursor = connection.executemany(
                """
                UPDATE chat_sessions
                SET pinned_at = ?, updated_at = ?, revision = revision + 1
                WHERE session_id = ? AND workspace = ? AND revision = ?
                """,
                [
                    (
                        pinned_at,
                        updated_at,
                        session_id,
                        workspace,
                        session_revisions[session_id],
                    )
                    for session_id in session_ids
                ],
            )
            if cursor.rowcount != len(session_ids):
                raise ChatSessionRevisionConflict(session_ids[0])
            updated_rows = connection.execute(
                f"""
                SELECT * FROM chat_sessions
                WHERE workspace = ? AND session_id IN ({placeholders})
                """,
                (workspace, *session_ids),
            ).fetchall()
        sessions = [
            session
            for row in updated_rows
            if (session := self._to_session(row)) is not None
        ]
        return sessions

    def batch_delete_sessions(
        self,
        session_revisions: dict[str, int],
        *,
        workspace: str = ChatWorkspace.EXCEL.value,
    ) -> list[str]:
        if not session_revisions:
            return []
        session_ids = sorted(session_revisions)
        placeholders = ",".join("?" for _session_id in session_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT session_id, revision FROM chat_sessions
                WHERE workspace = ? AND session_id IN ({placeholders})
                """,
                (workspace, *session_ids),
            ).fetchall()
            rows_by_id = {str(row["session_id"]): row for row in rows}
            for session_id in session_ids:
                row = rows_by_id.get(session_id)
                if (
                    row is None
                    or int(row["revision"]) != session_revisions[session_id]
                ):
                    raise ChatSessionRevisionConflict(session_id)
            for table_name in (
                "chat_request_executions",
                "chat_turns",
                "chat_session_documents",
                "pdf_chat_session_documents",
            ):
                connection.execute(
                    f"DELETE FROM {table_name} WHERE session_id IN ({placeholders})",
                    session_ids,
                )
            cursor = connection.executemany(
                """
                DELETE FROM chat_sessions
                WHERE workspace = ?
                  AND session_id = ?
                  AND revision = ?
                """,
                [
                    (workspace, session_id, session_revisions[session_id])
                    for session_id in session_ids
                ],
            )
            if cursor.rowcount != len(session_ids):
                raise ChatSessionRevisionConflict(session_ids[0])
        return session_ids

    def attach_document(self, document: AttachedDocument) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
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
        return cursor.rowcount > 0

    def detach_documents(self, session_id: str, version_ids: list[str]) -> None:
        if not version_ids:
            return
        placeholders = ",".join("?" for _version_id in version_ids)
        with self._connect() as connection:
            connection.execute(
                f"""
                DELETE FROM chat_session_documents
                WHERE session_id = ? AND version_id IN ({placeholders})
                """,
                (session_id, *version_ids),
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

    def attach_pdf_document(self, document: PdfAttachedDocument) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO pdf_chat_session_documents
                  (
                    session_id, file_id, attached_at,
                    chunk_count, context_hash, status
                  )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    document.session_id,
                    document.file_id,
                    document.attached_at,
                    document.chunk_count,
                    document.context_hash,
                    document.status,
                ),
            )
        return cursor.rowcount > 0

    def detach_pdf_documents(self, session_id: str, file_ids: list[str]) -> None:
        if not file_ids:
            return
        placeholders = ",".join("?" for _file_id in file_ids)
        with self._connect() as connection:
            connection.execute(
                f"""
                DELETE FROM pdf_chat_session_documents
                WHERE session_id = ? AND file_id IN ({placeholders})
                """,
                (session_id, *file_ids),
            )

    def list_pdf_attached_documents(self, session_id: str) -> list[PdfAttachedDocument]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pdf_chat_session_documents
                WHERE session_id = ?
                ORDER BY attached_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [
            document
            for row in rows
            if (document := self._to_pdf_attached_document(row)) is not None
        ]

    def commit_pdf_chat_turn(
        self,
        *,
        session_id: str,
        user_id: str,
        expected_conversation_revision: int,
        context_file_ids: list[str],
        attached_documents: list[PdfAttachedDocument],
        turn: ChatTurn,
        title_if_new: str | None,
        request_fingerprint: str | None,
    ) -> ChatTurn:
        with self._connect() as connection:
            existing_turn = self._get_turn_by_request_id_on_connection(
                connection,
                session_id=session_id,
                request_id=turn.request_id,
                workspace=ChatWorkspace.PDF.value,
            )
            if existing_turn is not None:
                return existing_turn
            cursor = connection.execute(
                """
                UPDATE chat_sessions
                SET
                  context_file_ids_json = ?,
                  updated_at = ?,
                  title = CASE
                    WHEN title = 'New chat' AND ? IS NOT NULL THEN ?
                    ELSE title
                  END,
                  conversation_revision = conversation_revision + 1
                WHERE session_id = ?
                  AND user_id = ?
                  AND workspace = ?
                  AND conversation_revision = ?
                """,
                (
                    dump_json(context_file_ids),
                    turn.created_at,
                    title_if_new,
                    title_if_new,
                    session_id,
                    user_id,
                    ChatWorkspace.PDF.value,
                    expected_conversation_revision,
                ),
            )
            if cursor.rowcount == 0:
                existing_turn = self._get_turn_by_request_id_on_connection(
                    connection,
                    session_id=session_id,
                    request_id=turn.request_id,
                    workspace=ChatWorkspace.PDF.value,
                )
                if existing_turn is not None:
                    return existing_turn
                raise ChatSessionRevisionConflict(session_id)
            for document in attached_documents:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO pdf_chat_session_documents
                      (
                        session_id, file_id, attached_at,
                        chunk_count, context_hash, status
                      )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document.session_id,
                        document.file_id,
                        document.attached_at,
                        document.chunk_count,
                        document.context_hash,
                        document.status,
                    ),
                )
            self._insert_turn_on_connection(connection, turn)
            self._complete_chat_request_on_connection(
                connection,
                workspace=ChatWorkspace.PDF.value,
                session_id=session_id,
                user_id=user_id,
                turn=turn,
                request_fingerprint=request_fingerprint,
            )
        return turn

    def create_turn(self, turn: ChatTurn) -> None:
        with self._connect() as connection:
            self._insert_turn_on_connection(connection, turn)

    def get_turn_by_request_id(
        self,
        session_id: str,
        request_id: str,
        *,
        workspace: str = ChatWorkspace.EXCEL.value,
    ) -> ChatTurn | None:
        with self._connect() as connection:
            return self._get_turn_by_request_id_on_connection(
                connection,
                session_id=session_id,
                request_id=request_id,
                workspace=workspace,
            )

    def claim_excel_chat_request(
        self,
        *,
        session_id: str,
        user_id: str,
        request_id: str,
        request_fingerprint: str,
        claimed_at: str,
        lease_expires_at: str,
    ) -> ChatTurn | None:
        return self._claim_chat_request(
            workspace=ChatWorkspace.EXCEL.value,
            session_id=session_id,
            user_id=user_id,
            request_id=request_id,
            request_fingerprint=request_fingerprint,
            claimed_at=claimed_at,
            lease_expires_at=lease_expires_at,
        )

    def claim_pdf_chat_request(
        self,
        *,
        session_id: str,
        user_id: str,
        request_id: str,
        request_fingerprint: str,
        claimed_at: str,
        lease_expires_at: str,
    ) -> ChatTurn | None:
        return self._claim_chat_request(
            workspace=ChatWorkspace.PDF.value,
            session_id=session_id,
            user_id=user_id,
            request_id=request_id,
            request_fingerprint=request_fingerprint,
            claimed_at=claimed_at,
            lease_expires_at=lease_expires_at,
        )

    def _claim_chat_request(
        self,
        *,
        workspace: str,
        session_id: str,
        user_id: str,
        request_id: str,
        request_fingerprint: str,
        claimed_at: str,
        lease_expires_at: str,
    ) -> ChatTurn | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM chat_request_executions
                WHERE workspace = ?
                  AND session_id = ?
                  AND request_id = ?
                """,
                (workspace, session_id, request_id),
            ).fetchone()
            if row is not None:
                if (
                    str(row["user_id"]) != user_id
                    or str(row["request_fingerprint"]) != request_fingerprint
                ):
                    raise ChatIdempotencyConflict(request_id)
                if str(row["status"]) == "completed":
                    turn = self._get_turn_by_request_id_on_connection(
                        connection,
                        session_id=session_id,
                        request_id=request_id,
                        workspace=workspace,
                    )
                    if turn is not None:
                        return turn
                if (
                    str(row["status"]) == "in_progress"
                    and str(row["lease_expires_at"]) >= claimed_at
                ):
                    raise ChatRequestInProgress(request_id)
                connection.execute(
                    """
                    UPDATE chat_request_executions
                    SET
                      status = 'in_progress',
                      lease_expires_at = ?,
                      turn_id = NULL,
                      updated_at = ?
                    WHERE workspace = ?
                      AND session_id = ?
                      AND request_id = ?
                    """,
                    (
                        lease_expires_at,
                        claimed_at,
                        workspace,
                        session_id,
                        request_id,
                    ),
                )
                return None
            connection.execute(
                """
                INSERT INTO chat_request_executions
                  (
                    workspace, session_id, request_id, user_id,
                    request_fingerprint, status, lease_expires_at,
                    turn_id, created_at, updated_at
                  )
                VALUES (?, ?, ?, ?, ?, 'in_progress', ?, NULL, ?, ?)
                """,
                (
                    workspace,
                    session_id,
                    request_id,
                    user_id,
                    request_fingerprint,
                    lease_expires_at,
                    claimed_at,
                    claimed_at,
                ),
            )
        return None

    def release_excel_chat_request(
        self,
        *,
        session_id: str,
        request_id: str,
        request_fingerprint: str,
    ) -> None:
        self._release_chat_request(
            workspace=ChatWorkspace.EXCEL.value,
            session_id=session_id,
            request_id=request_id,
            request_fingerprint=request_fingerprint,
        )

    def release_pdf_chat_request(
        self,
        *,
        session_id: str,
        request_id: str,
        request_fingerprint: str,
    ) -> None:
        self._release_chat_request(
            workspace=ChatWorkspace.PDF.value,
            session_id=session_id,
            request_id=request_id,
            request_fingerprint=request_fingerprint,
        )

    def _release_chat_request(
        self,
        *,
        workspace: str,
        session_id: str,
        request_id: str,
        request_fingerprint: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM chat_request_executions
                WHERE workspace = ?
                  AND session_id = ?
                  AND request_id = ?
                  AND request_fingerprint = ?
                  AND status = 'in_progress'
                """,
                (
                    workspace,
                    session_id,
                    request_id,
                    request_fingerprint,
                ),
            )

    def commit_excel_chat_turn(
        self,
        *,
        session_id: str,
        user_id: str,
        expected_conversation_revision: int,
        attached_documents: list[AttachedDocument],
        turn: ChatTurn,
        request_fingerprint: str | None,
    ) -> ChatTurn:
        with self._connect() as connection:
            existing_turn = self._get_turn_by_request_id_on_connection(
                connection,
                session_id=session_id,
                request_id=turn.request_id,
                workspace=ChatWorkspace.EXCEL.value,
            )
            if existing_turn is not None:
                return existing_turn
            cursor = connection.execute(
                """
                UPDATE chat_sessions
                SET
                  updated_at = ?,
                  conversation_revision = conversation_revision + 1
                WHERE session_id = ?
                  AND user_id = ?
                  AND workspace = ?
                  AND conversation_revision = ?
                """,
                (
                    turn.created_at,
                    session_id,
                    user_id,
                    ChatWorkspace.EXCEL.value,
                    expected_conversation_revision,
                ),
            )
            if cursor.rowcount == 0:
                existing_turn = self._get_turn_by_request_id_on_connection(
                    connection,
                    session_id=session_id,
                    request_id=turn.request_id,
                    workspace=ChatWorkspace.EXCEL.value,
                )
                if existing_turn is not None:
                    return existing_turn
                raise ChatSessionRevisionConflict(session_id)
            for document in attached_documents:
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
            self._insert_turn_on_connection(connection, turn)
            self._complete_chat_request_on_connection(
                connection,
                workspace=ChatWorkspace.EXCEL.value,
                session_id=session_id,
                user_id=user_id,
                turn=turn,
                request_fingerprint=request_fingerprint,
            )
        return turn

    def _complete_chat_request_on_connection(
        self,
        connection: sqlite3.Connection,
        *,
        workspace: str,
        session_id: str,
        user_id: str,
        turn: ChatTurn,
        request_fingerprint: str | None,
    ) -> None:
        if not turn.request_id or not request_fingerprint:
            return
        cursor = connection.execute(
            """
            UPDATE chat_request_executions
            SET
              status = 'completed',
              turn_id = ?,
              updated_at = ?
            WHERE workspace = ?
              AND session_id = ?
              AND request_id = ?
              AND user_id = ?
              AND request_fingerprint = ?
              AND status = 'in_progress'
            """,
            (
                turn.turn_id,
                turn.created_at,
                workspace,
                session_id,
                turn.request_id,
                user_id,
                request_fingerprint,
            ),
        )
        if cursor.rowcount == 0:
            raise ChatIdempotencyConflict(turn.request_id)

    def _get_turn_by_request_id_on_connection(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        request_id: str | None,
        workspace: str,
    ) -> ChatTurn | None:
        if not request_id:
            return None
        row = connection.execute(
            """
            SELECT turn.*
            FROM chat_turns AS turn
            JOIN chat_sessions AS session
              ON session.session_id = turn.session_id
            WHERE turn.session_id = ?
              AND turn.request_id = ?
              AND session.workspace = ?
            LIMIT 1
            """,
            (session_id, request_id, workspace),
        ).fetchone()
        return self._to_turn(row)

    def _insert_turn_on_connection(
        self,
        connection: sqlite3.Connection,
        turn: ChatTurn,
    ) -> None:
        connection.execute(
            """
            INSERT INTO chat_turns
              (
                turn_id, session_id, question, answer_text,
                citation_ids_json, selected_documents_json, created_at,
                answer_blocks_json, newly_attached_documents_json,
                attached_documents_json, citations_json, insufficient_evidence,
                follow_up_suggestions_json, warnings_json, request_id
              )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn.turn_id,
                turn.session_id,
                turn.question,
                turn.answer_text,
                dump_json(turn.citation_ids),
                dump_json(self._selected_documents_payload(turn.selected_documents)),
                turn.created_at,
                dump_json(self._answer_blocks_payload(turn.answer_blocks)),
                dump_json(
                    self._selected_documents_payload(turn.newly_attached_documents)
                ),
                dump_json(self._attached_documents_payload(turn.attached_documents)),
                dump_json(self._citations_payload(turn.citations)),
                1 if turn.insufficient_evidence else 0,
                dump_json(turn.follow_up_suggestions),
                dump_json(turn.warnings),
                turn.request_id,
            ),
        )

    def delete_turn(self, session_id: str, turn_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM chat_turns
                WHERE session_id = ? AND turn_id = ?
                """,
                (session_id, turn_id),
            )

    def record_chat_cancellation(
        self,
        *,
        request_id: str,
        cancelled_at: str,
        expires_at: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_request_cancellations
                  (request_id, cancelled_at, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                  cancelled_at = excluded.cancelled_at,
                  expires_at = excluded.expires_at
                """,
                (request_id, cancelled_at, expires_at),
            )

    def is_chat_request_cancelled(self, request_id: str, *, now_iso: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM chat_request_cancellations
                WHERE request_id = ?
                  AND expires_at >= ?
                """,
                (request_id, now_iso),
            ).fetchone()
        return row is not None

    def list_turns(
        self,
        session_id: str,
        *,
        workspace: str = ChatWorkspace.EXCEL.value,
    ) -> list[ChatTurn]:
        with self._connect() as connection:
            session_row = connection.execute(
                "SELECT session_id FROM chat_sessions WHERE session_id = ? AND workspace = ?",
                (session_id, workspace),
            ).fetchone()
            if session_row is None:
                return []
            rows = connection.execute(
                """
                SELECT * FROM chat_turns
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [turn for row in rows if (turn := self._to_turn(row)) is not None]

    def get_session_with_turns(
        self,
        session_id: str,
        *,
        workspace: str = ChatWorkspace.EXCEL.value,
        user_id: str | None = None,
    ) -> tuple[ChatSession, list[ChatTurn]] | None:
        with self._connect() as connection:
            if user_id is None:
                session_row = connection.execute(
                    "SELECT * FROM chat_sessions WHERE session_id = ? AND workspace = ?",
                    (session_id, workspace),
                ).fetchone()
            else:
                session_row = connection.execute(
                    """
                    SELECT * FROM chat_sessions
                    WHERE session_id = ? AND workspace = ? AND user_id = ?
                    """,
                    (session_id, workspace, user_id),
                ).fetchone()
            session = self._to_session(session_row)
            if session is None:
                return None
            turn_rows = connection.execute(
                """
                SELECT * FROM chat_turns
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return session, [
            turn for row in turn_rows if (turn := self._to_turn(row)) is not None
        ]

    def get_llm_preference(self, scope: str) -> LlmPreference | None:
        return self._llm_preferences.get(scope)

    def save_llm_preference(self, preference: LlmPreference) -> LlmPreference:
        return self._llm_preferences.save(preference)

    def create_user(self, user: UserAccount) -> None:
        self._auth.create_user(user)

    def get_user(self, user_id: str) -> UserAccount | None:
        return self._auth.get_user(user_id)

    def get_user_by_email(self, email: str) -> UserAccount | None:
        return self._auth.get_user_by_email(email)

    def update_user_password(
        self,
        user_id: str,
        password_hash: str,
        updated_at: str,
    ) -> UserAccount | None:
        return self._auth.update_user_password(user_id, password_hash, updated_at)

    def record_user_login(self, user_id: str, last_login_at: str) -> None:
        self._auth.record_user_login(user_id, last_login_at)

    def create_auth_session(self, session: AuthSession) -> None:
        self._auth.create_auth_session(session)

    def get_auth_session_by_token_hash(
        self,
        token_hash: str,
    ) -> tuple[AuthSession, UserAccount] | None:
        return self._auth.get_auth_session_by_token_hash(token_hash)

    def revoke_auth_session(self, token_hash: str, revoked_at: str) -> bool:
        return self._auth.revoke_auth_session(token_hash, revoked_at)

    def create_password_reset_token(self, token: PasswordResetToken) -> None:
        self._auth.create_password_reset_token(token)

    def get_password_reset_token_by_hash(
        self,
        token_hash: str,
    ) -> tuple[PasswordResetToken, UserAccount] | None:
        return self._auth.get_password_reset_token_by_hash(token_hash)

    def mark_password_reset_token_used(
        self,
        reset_token_id: str,
        used_at: str,
    ) -> None:
        self._auth.mark_password_reset_token_used(reset_token_id, used_at)

    def get_login_rate_limit_retry_after(
        self,
        email: str,
        now: str,
    ) -> int | None:
        return self._auth.get_login_rate_limit_retry_after(email, now)

    def record_login_rate_limit_failure(
        self,
        email: str,
        *,
        now: str,
        max_failed_attempts: int,
        window_seconds: int,
    ) -> int | None:
        return self._auth.record_login_rate_limit_failure(
            email,
            now=now,
            max_failed_attempts=max_failed_attempts,
            window_seconds=window_seconds,
        )

    def clear_login_rate_limit(self, email: str) -> None:
        self._auth.clear_login_rate_limit(email)

    def run_operational_maintenance(self, now_iso: str | None = None) -> dict[str, int]:
        return self._database.run_operational_maintenance(now_iso=now_iso)

    @property
    def _last_maintenance_at(self) -> float:
        """Compatibility seam for operational tests and diagnostics."""
        return self._database._last_maintenance_at

    @_last_maintenance_at.setter
    def _last_maintenance_at(self, value: float) -> None:
        self._database._last_maintenance_at = value

    def _run_connection_maintenance(
        self,
        connection: sqlite3.Connection,
    ) -> dict[str, int]:
        """Delegate the legacy maintenance hook to the database owner."""
        return self._database._run_connection_maintenance(connection)

    def _connect(self, *, run_maintenance: bool = True) -> sqlite3.Connection:
        return self._database.connect(
            run_maintenance=run_maintenance,
            maintenance_runner=self._run_connection_maintenance,
        )

    def _to_file(self, row: sqlite3.Row | None) -> ExcelFile | None:
        if row is None:
            return None
        return ExcelFile(
            file_id=str(row["file_id"]),
            display_name=str(row["display_name"]),
            active_version_id=row["active_version_id"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            status=ExcelFileStatus(
                row_str(row, "status", ExcelFileStatus.ACTIVE.value)
            ),
            deleted_at=row_value(row, "deleted_at"),
            visibility=ExcelFileVisibility(
                row_str(row, "visibility", ExcelFileVisibility.VISIBLE.value)
            ),
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

    def _pdf_file_values(self, file: PdfFile) -> tuple[object, ...]:
        return (
            file.file_id,
            file.user_id,
            file.parent_id,
            file.display_name,
            file.original_filename,
            file.kind.value,
            file.size_bytes,
            file.storage_path,
            file.status.value,
            file.visibility.value,
            file.processing_status.value,
            file.progress,
            file.status_detail,
            file.error_message,
            file.page_count,
            file.chunk_count,
            file.created_at,
            file.updated_at,
            file.deleted_at,
        )

    def _get_pdf_folder_by_parent_and_name(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: str,
        parent_id: str | None,
        display_name: str,
    ) -> PdfFile | None:
        row = connection.execute(
            f"""
            {PDF_FILE_WITH_PARSE_REPORT_SELECT}
            WHERE f.user_id = ?
              AND f.kind = ?
              AND f.display_name = ?
              AND f.status = ?
              AND (
                (? IS NULL AND f.parent_id IS NULL)
                OR f.parent_id = ?
              )
            ORDER BY f.updated_at DESC, f.file_id ASC
            LIMIT 1
            """,
            (
                user_id,
                PdfFileKind.FOLDER.value,
                display_name,
                PdfFileStatus.ACTIVE.value,
                parent_id,
                parent_id,
            ),
        ).fetchone()
        return self._to_pdf_file(row)

    def _to_pdf_file(self, row: sqlite3.Row | None) -> PdfFile | None:
        if row is None:
            return None
        return PdfFile(
            file_id=str(row["file_id"]),
            user_id=str(row["user_id"]),
            parent_id=row["parent_id"],
            display_name=str(row["display_name"]),
            original_filename=str(row["original_filename"]),
            kind=PdfFileKind(str(row["kind"])),
            size_bytes=int(row["size_bytes"]),
            storage_path=row["storage_path"],
            status=PdfFileStatus(str(row["status"])),
            visibility=PdfFileVisibility(str(row["visibility"])),
            processing_status=PdfProcessingStatus(str(row["processing_status"])),
            progress=int(row["progress"]),
            status_detail=str(row["status_detail"]),
            error_message=row["error_message"],
            page_count=_optional_int(row["page_count"]),
            chunk_count=_optional_int(row["chunk_count"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            deleted_at=row["deleted_at"],
            quality_status=_optional_pdf_parse_quality_status(
                row_value(row, "parse_quality_status")
            ),
            coverage_ratio=_optional_float(row_value(row, "parse_coverage_ratio")),
            warning_count=_optional_int(row_value(row, "parse_warning_count")),
            failed_page_count=_optional_int(row_value(row, "parse_failed_page_count")),
            parser_backend=row_value(row, "parse_parser_backend"),
            content_fingerprint=str(row_value(row, "content_fingerprint", "")),
        )

    def _pdf_upload_batch_values(self, batch: PdfUploadBatch) -> tuple[object, ...]:
        return (
            batch.batch_id,
            batch.user_id,
            batch.source_name,
            batch.status.value,
            batch.total_files,
            batch.accepted_files,
            batch.skipped_files,
            batch.total_bytes,
            batch.progress,
            batch.detail,
            batch.error_message,
            batch.parser_backend,
            dump_json(batch.result),
            batch.created_at,
            batch.updated_at,
            batch.completed_at,
        )

    def _to_pdf_upload_batch(self, row: sqlite3.Row | None) -> PdfUploadBatch | None:
        if row is None:
            return None
        return PdfUploadBatch(
            batch_id=str(row["batch_id"]),
            user_id=str(row["user_id"]),
            source_name=str(row["source_name"]),
            status=PdfUploadBatchStatus(str(row["status"])),
            total_files=int(row["total_files"]),
            accepted_files=int(row["accepted_files"]),
            skipped_files=int(row["skipped_files"]),
            total_bytes=int(row["total_bytes"]),
            progress=int(row["progress"]),
            detail=str(row["detail"]),
            parser_backend=str(row["parser_backend"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            completed_at=row["completed_at"],
            error_message=row["error_message"],
            result=load_json_object(row_value(row, "result_json", "{}")),
        )

    def _pdf_upload_task_values(self, task: PdfUploadTask) -> tuple[object, ...]:
        return (
            task.task_id,
            task.user_id,
            task.file_id,
            task.original_filename,
            task.staging_path,
            task.status.value,
            task.progress,
            task.detail,
            task.error_message,
            dump_json(task.result),
            task.created_at,
            task.updated_at,
            task.started_at,
            task.finished_at,
            task.worker_id,
            task.stage.value,
            task.parser_backend,
            task.error_code,
            task.retry_count,
            task.last_retry_at,
            task.batch_id,
        )

    def _to_pdf_upload_task(self, row: sqlite3.Row | None) -> PdfUploadTask | None:
        if row is None:
            return None
        return PdfUploadTask(
            task_id=str(row["task_id"]),
            user_id=str(row["user_id"]),
            file_id=row["file_id"],
            original_filename=str(row["original_filename"]),
            staging_path=str(row["staging_path"]),
            status=PdfUploadTaskStatus(str(row["status"])),
            progress=int(row["progress"]),
            detail=str(row["detail"]),
            error_message=row["error_message"],
            result=load_json_object(row_value(row, "result_json", "{}")),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            worker_id=row["worker_id"],
            stage=PdfUploadTaskStage(
                str(row_value(row, "stage", PdfUploadTaskStage.QUEUED.value))
            ),
            parser_backend=row_str(row, "parser_backend", "unknown"),
            error_code=row_value(row, "error_code"),
            retry_count=safe_int(row_value(row, "retry_count", 0), 0),
            last_retry_at=row_value(row, "last_retry_at"),
            batch_id=row_value(row, "batch_id"),
        )

    def _pdf_summary_task_values(self, task: PdfSummaryTask) -> tuple[object, ...]:
        return (
            task.task_id,
            task.user_id,
            task.file_id,
            task.status.value,
            task.progress,
            task.detail,
            task.error_message,
            dump_json(task.result),
            task.created_at,
            task.updated_at,
            task.started_at,
            task.finished_at,
            task.worker_id,
            task.retry_count,
            task.last_retry_at,
            task.source_fingerprint,
            task.state_revision,
            task.claim_token,
            task.claimed_at,
            task.attempt,
            task.parent_task_id,
        )

    def _to_pdf_summary_task(self, row: sqlite3.Row | None) -> PdfSummaryTask | None:
        if row is None:
            return None
        return PdfSummaryTask(
            task_id=str(row["task_id"]),
            user_id=str(row["user_id"]),
            file_id=str(row["file_id"]),
            status=PdfSummaryTaskStatus(str(row["status"])),
            progress=int(row["progress"]),
            detail=str(row["detail"]),
            error_message=row["error_message"],
            result=load_json_object(row_value(row, "result_json", "{}")),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            worker_id=row["worker_id"],
            retry_count=safe_int(row_value(row, "retry_count", 0), 0),
            last_retry_at=row_value(row, "last_retry_at"),
            source_fingerprint=row_str(row, "source_fingerprint"),
            state_revision=safe_int(row_value(row, "state_revision", 0), 0),
            claim_token=row_value(row, "claim_token"),
            claimed_at=row_value(row, "claimed_at"),
            attempt=safe_int(row_value(row, "attempt", 1), 1),
            parent_task_id=row_value(row, "parent_task_id"),
        )

    def _to_pdf_file_cleanup_job(self, row: sqlite3.Row) -> PdfFileCleanupJob:
        return PdfFileCleanupJob(
            job_id=str(row["job_id"]),
            file_id=str(row["file_id"]),
            relative_path=str(row["relative_path"]),
            status=str(row["status"]),
            attempt_count=int(row["attempt_count"]),
            error_message=row["error_message"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            completed_at=row["completed_at"],
        )

    def _is_active_pdf_file(
        self,
        connection: sqlite3.Connection,
        file_id: str,
    ) -> bool:
        return connection.execute(
            "SELECT 1 FROM pdf_files WHERE file_id = ? AND status = ?",
            (file_id, PdfFileStatus.ACTIVE.value),
        ).fetchone() is not None

    def _save_pdf_summary(
        self,
        connection: sqlite3.Connection,
        summary: PdfDocumentSummary,
    ) -> None:
        connection.execute(
            """
            INSERT INTO pdf_document_summaries
              (
                file_id, status, content, updated_at, error_message,
                document_title, document_type, business_domain,
                key_topics_json, positive_routing_terms_json,
                negative_routing_terms_json, exact_identifiers_json,
                suitable_questions_json, unsuitable_questions_json, routing_notes
                , source_fingerprint, source_updated_at, provider, model,
                prompt_version, generation_task_id, generated_by_user_id,
                revision, created_at
              )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
              status = excluded.status,
              content = excluded.content,
              updated_at = excluded.updated_at,
              error_message = excluded.error_message,
              document_title = excluded.document_title,
              document_type = excluded.document_type,
              business_domain = excluded.business_domain,
              key_topics_json = excluded.key_topics_json,
              positive_routing_terms_json = excluded.positive_routing_terms_json,
              negative_routing_terms_json = excluded.negative_routing_terms_json,
              exact_identifiers_json = excluded.exact_identifiers_json,
              suitable_questions_json = excluded.suitable_questions_json,
              unsuitable_questions_json = excluded.unsuitable_questions_json,
              routing_notes = excluded.routing_notes,
              source_fingerprint = excluded.source_fingerprint,
              source_updated_at = excluded.source_updated_at,
              provider = excluded.provider,
              model = excluded.model,
              prompt_version = excluded.prompt_version,
              generation_task_id = excluded.generation_task_id,
              generated_by_user_id = excluded.generated_by_user_id,
              revision = pdf_document_summaries.revision + 1,
              created_at = COALESCE(pdf_document_summaries.created_at, excluded.created_at)
            """,
            (
                summary.file_id,
                summary.status,
                summary.content,
                summary.updated_at,
                summary.error_message,
                summary.document_title,
                summary.document_type,
                summary.business_domain,
                dump_json(summary.key_topics),
                dump_json(summary.positive_routing_terms),
                dump_json(summary.negative_routing_terms),
                dump_json(summary.exact_identifiers),
                dump_json(summary.suitable_questions),
                dump_json(summary.unsuitable_questions),
                summary.routing_notes,
                summary.source_fingerprint,
                summary.source_updated_at,
                summary.provider,
                summary.model,
                summary.prompt_version,
                summary.generation_task_id,
                summary.generated_by_user_id,
                summary.revision,
                summary.created_at or summary.updated_at,
            ),
        )

    def _to_pdf_summary(self, row: sqlite3.Row | None) -> PdfDocumentSummary | None:
        if row is None:
            return None
        return PdfDocumentSummary(
            file_id=str(row["file_id"]),
            status=str(row["status"]),
            content=str(row["content"]),
            updated_at=row["updated_at"],
            error_message=row["error_message"],
            document_title=row_str(row, "document_title"),
            document_type=row_str(row, "document_type", "pdf_document"),
            business_domain=row_str(row, "business_domain", "pdf knowledge"),
            key_topics=load_string_list(row_value(row, "key_topics_json", "[]")),
            positive_routing_terms=load_string_list(
                row_value(row, "positive_routing_terms_json", "[]")
            ),
            negative_routing_terms=load_string_list(
                row_value(row, "negative_routing_terms_json", "[]")
            ),
            exact_identifiers=load_string_list(
                row_value(row, "exact_identifiers_json", "[]")
            ),
            suitable_questions=load_string_list(
                row_value(row, "suitable_questions_json", "[]")
            ),
            unsuitable_questions=load_string_list(
                row_value(row, "unsuitable_questions_json", "[]")
            ),
            routing_notes=row_str(row, "routing_notes"),
            source_fingerprint=row_str(row, "source_fingerprint"),
            source_updated_at=row_value(row, "source_updated_at"),
            provider=row_str(row, "provider"),
            model=row_str(row, "model"),
            prompt_version=row_str(row, "prompt_version", "pdf-summary-v1"),
            generation_task_id=row_value(row, "generation_task_id"),
            generated_by_user_id=row_value(row, "generated_by_user_id"),
            revision=safe_int(row_value(row, "revision", 0), 0),
            created_at=row_value(row, "created_at"),
        )

    def _to_pdf_attached_document(
        self,
        row: sqlite3.Row | None,
    ) -> PdfAttachedDocument | None:
        if row is None:
            return None
        return PdfAttachedDocument(
            session_id=str(row["session_id"]),
            file_id=str(row["file_id"]),
            attached_at=str(row["attached_at"]),
            chunk_count=int(row["chunk_count"]),
            context_hash=str(row["context_hash"]),
            status=str(row["status"]),
        )

    def _to_pdf_preview_block(self, row: sqlite3.Row) -> PdfPreviewBlock:
        return PdfPreviewBlock(
            block_id=str(row["block_id"]),
            file_id=str(row["file_id"]),
            page_label=str(row["page_label"]),
            title=str(row["title"]),
            content=str(row["content"]),
            block_index=int(row["block_index"]),
        )

    def _to_pdf_schema_item(self, row: sqlite3.Row) -> PdfSchemaItem:
        return PdfSchemaItem(
            item_id=str(row["item_id"]),
            file_id=str(row["file_id"]),
            label=str(row["label"]),
            value=str(row["value"]),
            item_index=int(row["item_index"]),
        )

    def _to_pdf_chunk(self, row: sqlite3.Row) -> PdfDocumentChunk:
        metadata = load_json_object(row_value(row, "metadata_json", "{}"))
        return PdfDocumentChunk(
            chunk_id=str(row["chunk_id"]),
            file_id=str(row["file_id"]),
            chunk_index=int(row["chunk_index"]),
            text=str(row["text"]),
            page_label=row["page_label"],
            title=str(row["title"]),
            token_count=int(row["token_count"]),
            content_hash=str(row["content_hash"]),
            metadata={
                str(key): str(value)
                for key, value in metadata.items()
                if str(key).strip()
            },
        )

    def _to_pdf_parse_report(self, row: sqlite3.Row | None) -> PdfParseReport | None:
        if row is None:
            return None
        total_pages = max(0, safe_int(row_value(row, "total_pages", 0), 0))
        parsed_pages = max(0, safe_int(row_value(row, "parsed_pages", 0), 0))
        failed_pages = max(0, safe_int(row_value(row, "failed_pages", 0), 0))
        empty_pages = max(0, safe_int(row_value(row, "empty_pages", 0), 0))
        return PdfParseReport(
            file_id=str(row["file_id"]),
            parser_backend=str(row["parser_backend"]),
            parser_version=row_value(row, "parser_version"),
            quality_status=PdfParseQualityStatus(str(row["quality_status"])),
            total_pages=total_pages,
            parsed_pages=parsed_pages,
            failed_pages=failed_pages,
            empty_pages=empty_pages,
            text_block_count=max(0, safe_int(row_value(row, "text_block_count", 0), 0)),
            table_block_count=max(0, safe_int(row_value(row, "table_block_count", 0), 0)),
            image_block_count=max(0, safe_int(row_value(row, "image_block_count", 0), 0)),
            chunk_count=max(0, safe_int(row_value(row, "chunk_count", 0), 0)),
            coverage_ratio=_safe_float(row_value(row, "coverage_ratio", 0.0), 0.0),
            warning_count=max(0, safe_int(row_value(row, "warning_count", 0), 0)),
            error_count=max(0, safe_int(row_value(row, "error_count", 0), 0)),
            warnings=[
                str(item)
                for item in load_string_list(row_value(row, "warnings_json", "[]"))
            ],
            started_at=row_value(row, "started_at"),
            finished_at=row_value(row, "finished_at"),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _to_pdf_parse_page(self, row: sqlite3.Row) -> PdfParsePage:
        return PdfParsePage(
            page_id=str(row["page_id"]),
            file_id=str(row["file_id"]),
            page_number=max(1, safe_int(row_value(row, "page_number", 1), 1)),
            page_label=str(row["page_label"]),
            status=PdfParsePageStatus(str(row["status"])),
            text_block_count=max(0, safe_int(row_value(row, "text_block_count", 0), 0)),
            table_block_count=max(0, safe_int(row_value(row, "table_block_count", 0), 0)),
            image_block_count=max(0, safe_int(row_value(row, "image_block_count", 0), 0)),
            char_count=max(0, safe_int(row_value(row, "char_count", 0), 0)),
            warning_message=row_value(row, "warning_message"),
            error_message=row_value(row, "error_message"),
        )

    def _to_pdf_parse_artifact(self, row: sqlite3.Row) -> PdfParseArtifact:
        return PdfParseArtifact(
            artifact_id=str(row["artifact_id"]),
            file_id=str(row["file_id"]),
            artifact_type=str(row["artifact_type"]),
            name=str(row["name"]),
            path=row_value(row, "path"),
            size_bytes=max(0, safe_int(row_value(row, "size_bytes", 0), 0)),
            content_hash=row_value(row, "content_hash"),
            created_at=str(row["created_at"]),
        )

    def _to_pdf_model_setting(self, row: sqlite3.Row | None) -> PdfModelSetting | None:
        if row is None:
            return None
        return PdfModelSetting(
            setting_id=str(row["setting_id"]),
            label=str(row["label"]),
            providers=load_string_list(row["providers_json"]),
            models=load_string_list(row["models_json"]),
            selected_provider=str(row["selected_provider"]),
            selected_model=str(row["selected_model"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
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
            document_title=row_str(row, "document_title"),
            document_type=row_str(row, "document_type", "unknown") or "unknown",
            summary_text=str(row["summary_text"]),
            business_domain=str(row["business_domain"]),
            coverage_scope=load_scope_map(row_value(row, "coverage_scope_json", "{}")),
            key_topics=load_string_list(row["key_topics_json"]),
            positive_routing_terms=load_string_list(
                row_value(row, "positive_routing_terms_json", "[]")
            ),
            negative_routing_terms=load_string_list(
                row_value(row, "negative_routing_terms_json", "[]")
            ),
            exact_identifiers=load_string_list(
                row_value(row, "exact_identifiers_json", "[]")
            ),
            suitable_questions=load_string_list(row["suitable_questions_json"]),
            unsuitable_questions=load_string_list(
                row["unsuitable_questions_json"]
            ),
            sheet_summaries=[
                SheetSummary(
                    sheet_id=str(sheet_row["sheet_id"]),
                    sheet_name=str(sheet_row["sheet_name"]),
                    summary=str(sheet_row["summary"]),
                    important_columns=load_string_list(
                        sheet_row["important_columns_json"]
                    ),
                    likely_question_types=load_string_list(
                        sheet_row["likely_question_types_json"]
                    ),
                    header_terms=load_string_list(
                        row_value(sheet_row, "header_terms_json", "[]")
                    ),
                    sampled_identifiers=load_string_list(
                        row_value(sheet_row, "sampled_identifiers_json", "[]")
                    ),
                )
                for sheet_row in sheet_rows
            ],
            routing_notes=row_str(row, "routing_notes"),
            created_at=str(row["created_at"]),
        )

    def _to_session(self, row: sqlite3.Row | None) -> ChatSession | None:
        if row is None:
            return None
        columns = set(row.keys())
        user_id = str(row["user_id"]) if "user_id" in columns else "legacy"
        return ChatSession(
            session_id=str(row["session_id"]),
            user_id=user_id or "legacy",
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            title=str(row["title"]) if "title" in columns else "New chat",
            pinned_at=row["pinned_at"] if "pinned_at" in columns else None,
            status=str(row["status"]),
            workspace=ChatWorkspace(
                row_str(row, "workspace", ChatWorkspace.EXCEL.value)
            ),
            context_file_ids=load_string_list(
                row_value(row, "context_file_ids_json", "[]")
            ),
            revision=int(row_value(row, "revision", 0) or 0),
            conversation_revision=int(
                row_value(row, "conversation_revision", 0) or 0
            ),
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
        citation_ids = load_string_list(row["citation_ids_json"])
        selected_documents = self._selected_documents_from_payload(
            load_object_list(row["selected_documents_json"])
        )
        answer_blocks = self._answer_blocks_from_payload(
            load_object_list(row_value(row, "answer_blocks_json", "[]"))
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
                load_object_list(
                    row_value(row, "newly_attached_documents_json", "[]")
                )
            ),
            attached_documents=self._attached_documents_from_payload(
                load_object_list(
                    row_value(row, "attached_documents_json", "[]")
                )
            ),
            citations=self._citations_from_payload(
                load_object_list(row_value(row, "citations_json", "[]"))
            ),
            insufficient_evidence=bool(
                int(row_value(row, "insufficient_evidence", 0) or 0)
            ),
            follow_up_suggestions=load_string_list(
                row_value(row, "follow_up_suggestions_json", "[]")
            ),
            warnings=load_string_list(row_value(row, "warnings_json", "[]")),
            request_id=row_value(row, "request_id", None),
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
                    row_count=safe_int(document.get("row_count"), 0),
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

    def _deleted_file_display_name(self, *, file_id: str, display_name: str) -> str:
        return f"deleted:{file_id}:{display_name}"


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_pdf_parse_quality_status(value: object) -> PdfParseQualityStatus | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return PdfParseQualityStatus(value)
    except ValueError:
        return None


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
