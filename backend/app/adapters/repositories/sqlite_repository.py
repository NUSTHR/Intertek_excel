import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock

from app.adapters.repositories.sqlite.maintenance import SQLiteOperationalMaintenance
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
from app.core.time import utc_now_iso
from app.domain.models import (
    AttachedDocument,
    AuthSession,
    ChatAnswerBlock,
    ChatSession,
    ChatTurn,
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
    ExcelUploadTaskStatus,
    ExcelVersionStatus,
    LlmPreference,
    PasswordResetToken,
    PdfDocumentChunk,
    PdfDocumentDetail,
    PdfDocumentSummary,
    PdfFile,
    PdfFileKind,
    PdfFileStatus,
    PdfFileVisibility,
    PdfModelSetting,
    PdfPreviewBlock,
    PdfProcessingStatus,
    PdfSchemaItem,
    PdfUploadTask,
    PdfUploadTaskStage,
    PdfUploadTaskStatus,
    SelectedDocument,
    SheetSummary,
    UserAccount,
    UserRole,
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
        self._last_maintenance_at = 0.0
        self._maintenance_lock = Lock()
        self._connection_policy = connection_policy or SQLiteConnectionPolicy(
            maintenance_interval_seconds=maintenance_interval_seconds,
        )
        self._maintenance_policy = maintenance_policy or SQLiteMaintenancePolicy(
            auth_session_retention_days=auth_session_retention_days,
            password_reset_token_retention_days=password_reset_token_retention_days,
        )
        self._maintenance = SQLiteOperationalMaintenance(self._maintenance_policy)
        self._migration_runner = SQLiteMigrationRunner(SCHEMA_MIGRATIONS)
        self._row_search_index = SQLiteRowSearchIndex(
            connect=self._connect,
            dump_json=dump_json,
        )

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect(run_maintenance=False) as connection:
            self._migration_runner.initialize_schema(connection)
        self.run_operational_maintenance()

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
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO excel_upload_tasks
                  (
                    task_id, user_id, original_filename, staging_path,
                    replace_existing, status, error_message, result_json,
                    created_at, updated_at, started_at, finished_at, worker_id
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._upload_task_values(task),
            )

    def get_upload_task(self, task_id: str) -> ExcelUploadTask | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM excel_upload_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._to_upload_task(row)

    def claim_next_upload_task(
        self,
        *,
        worker_id: str,
        started_at: str,
    ) -> ExcelUploadTask | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE excel_upload_tasks
                SET status = ?,
                    worker_id = ?,
                    started_at = ?,
                    updated_at = ?,
                    error_message = NULL
                WHERE task_id = (
                  SELECT task_id
                  FROM excel_upload_tasks
                  WHERE status = ?
                  ORDER BY created_at ASC
                  LIMIT 1
                )
                """,
                (
                    ExcelUploadTaskStatus.PROCESSING.value,
                    worker_id,
                    started_at,
                    started_at,
                    ExcelUploadTaskStatus.QUEUED.value,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT * FROM excel_upload_tasks
                WHERE worker_id = ?
                  AND status = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (worker_id, ExcelUploadTaskStatus.PROCESSING.value),
            ).fetchone()
        return self._to_upload_task(row)

    def complete_upload_task(
        self,
        *,
        task_id: str,
        result: dict[str, object],
        finished_at: str,
    ) -> ExcelUploadTask | None:
        return self._finish_upload_task(
            task_id=task_id,
            status=ExcelUploadTaskStatus.READY,
            error_message=None,
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
        return self._finish_upload_task(
            task_id=task_id,
            status=ExcelUploadTaskStatus.FAILED,
            error_message=error_message,
            result={},
            finished_at=finished_at,
        )

    def fail_stale_processing_upload_tasks(
        self,
        *,
        cutoff_started_at: str,
        failed_at: str,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE excel_upload_tasks
                SET status = ?,
                    error_message = ?,
                    updated_at = ?,
                    finished_at = ?
                WHERE status = ?
                  AND started_at IS NOT NULL
                  AND started_at < ?
                """,
                (
                    ExcelUploadTaskStatus.FAILED.value,
                    "Upload processing was interrupted. Please upload the workbook again.",
                    failed_at,
                    failed_at,
                    ExcelUploadTaskStatus.PROCESSING.value,
                    cutoff_started_at,
                ),
            )
        return max(0, cursor.rowcount)

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
                """
                SELECT * FROM pdf_files
                WHERE file_id = ? AND status = ?
                """,
                (file_id, PdfFileStatus.ACTIVE.value),
            ).fetchone()
        return self._to_pdf_file(row)

    def list_pdf_files(self) -> list[PdfFile]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pdf_files
                WHERE status = ?
                ORDER BY updated_at DESC, display_name ASC
                """,
                (PdfFileStatus.ACTIVE.value,),
            ).fetchall()
        return [file for row in rows if (file := self._to_pdf_file(row)) is not None]

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

    def create_pdf_upload_task(self, task: PdfUploadTask) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pdf_upload_tasks
                  (
                    task_id, user_id, file_id, original_filename, staging_path,
                    status, progress, detail, error_message, result_json,
                    created_at, updated_at, started_at, finished_at, worker_id,
                    stage, parser_backend, error_code, retry_count, last_retry_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    "Ready for PDF-grounded chat.",
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

    def save_pdf_document_detail(self, detail: PdfDocumentDetail) -> None:
        with self._connect() as connection:
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
        )

    def save_pdf_document_summary(self, summary: PdfDocumentSummary) -> None:
        with self._connect() as connection:
            self._save_pdf_summary(connection, summary)

    def replace_pdf_document_chunks(
        self,
        file_id: str,
        chunks: list[PdfDocumentChunk],
    ) -> None:
        created_at = utc_now_iso()
        with self._connect() as connection:
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

    def _finish_upload_task(
        self,
        *,
        task_id: str,
        status: ExcelUploadTaskStatus,
        error_message: str | None,
        result: dict[str, object],
        finished_at: str,
    ) -> ExcelUploadTask | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE excel_upload_tasks
                SET status = ?,
                    error_message = ?,
                    result_json = ?,
                    updated_at = ?,
                    finished_at = ?
                WHERE task_id = ?
                  AND status = ?
                """,
                (
                    status.value,
                    error_message,
                    dump_json(result),
                    finished_at,
                    finished_at,
                    task_id,
                    ExcelUploadTaskStatus.PROCESSING.value,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM excel_upload_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._to_upload_task(row)

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
                  (session_id, user_id, created_at, updated_at, title, pinned_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.user_id,
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
                    follow_up_suggestions_json, warnings_json
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    dump_json(
                        self._attached_documents_payload(turn.attached_documents)
                    ),
                    dump_json(self._citations_payload(turn.citations)),
                    1 if turn.insufficient_evidence else 0,
                    dump_json(turn.follow_up_suggestions),
                    dump_json(turn.warnings),
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

    def create_user(self, user: UserAccount) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_accounts
                  (
                    user_id, email, password_hash, role, is_active,
                    created_at, updated_at, last_login_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.user_id,
                    user.email,
                    user.password_hash,
                    user.role.value,
                    1 if user.is_active else 0,
                    user.created_at,
                    user.updated_at,
                    user.last_login_at,
                ),
            )

    def get_user(self, user_id: str) -> UserAccount | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM user_accounts WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return self._to_user(row)

    def get_user_by_email(self, email: str) -> UserAccount | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM user_accounts WHERE email = ?",
                (email,),
            ).fetchone()
        return self._to_user(row)

    def update_user_password(
        self,
        user_id: str,
        password_hash: str,
        updated_at: str,
    ) -> UserAccount | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE user_accounts
                SET password_hash = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (password_hash, updated_at, user_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM user_accounts WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return self._to_user(row)

    def record_user_login(self, user_id: str, last_login_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE user_accounts
                SET last_login_at = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (last_login_at, last_login_at, user_id),
            )

    def create_auth_session(self, session: AuthSession) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO auth_sessions
                  (
                    session_id, user_id, session_token_hash,
                    created_at, expires_at, revoked_at
                  )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.user_id,
                    session.session_token_hash,
                    session.created_at,
                    session.expires_at,
                    session.revoked_at,
                ),
            )

    def get_auth_session_by_token_hash(
        self,
        token_hash: str,
    ) -> tuple[AuthSession, UserAccount] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                  auth_sessions.session_id AS auth_session_id,
                  auth_sessions.user_id AS auth_user_id,
                  auth_sessions.session_token_hash,
                  auth_sessions.created_at AS auth_created_at,
                  auth_sessions.expires_at,
                  auth_sessions.revoked_at,
                  user_accounts.user_id,
                  user_accounts.email,
                  user_accounts.password_hash,
                  user_accounts.role,
                  user_accounts.is_active,
                  user_accounts.created_at AS user_created_at,
                  user_accounts.updated_at AS user_updated_at,
                  user_accounts.last_login_at
                FROM auth_sessions
                JOIN user_accounts ON user_accounts.user_id = auth_sessions.user_id
                WHERE auth_sessions.session_token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return self._to_auth_session(row), self._to_joined_user(row)

    def revoke_auth_session(self, token_hash: str, revoked_at: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE session_token_hash = ? AND revoked_at IS NULL
                """,
                (revoked_at, token_hash),
            )
        return cursor.rowcount > 0

    def create_password_reset_token(self, token: PasswordResetToken) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO password_reset_tokens
                  (reset_token_id, user_id, token_hash, created_at, expires_at, used_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    token.reset_token_id,
                    token.user_id,
                    token.token_hash,
                    token.created_at,
                    token.expires_at,
                    token.used_at,
                ),
            )

    def get_password_reset_token_by_hash(
        self,
        token_hash: str,
    ) -> tuple[PasswordResetToken, UserAccount] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                  password_reset_tokens.reset_token_id,
                  password_reset_tokens.user_id AS reset_user_id,
                  password_reset_tokens.token_hash,
                  password_reset_tokens.created_at AS reset_created_at,
                  password_reset_tokens.expires_at,
                  password_reset_tokens.used_at,
                  user_accounts.user_id,
                  user_accounts.email,
                  user_accounts.password_hash,
                  user_accounts.role,
                  user_accounts.is_active,
                  user_accounts.created_at AS user_created_at,
                  user_accounts.updated_at AS user_updated_at,
                  user_accounts.last_login_at
                FROM password_reset_tokens
                JOIN user_accounts ON user_accounts.user_id = password_reset_tokens.user_id
                WHERE password_reset_tokens.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return self._to_password_reset_token(row), self._to_joined_user(row)

    def mark_password_reset_token_used(
        self,
        reset_token_id: str,
        used_at: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE password_reset_tokens
                SET used_at = ?
                WHERE reset_token_id = ?
                """,
                (used_at, reset_token_id),
            )

    def get_login_rate_limit_retry_after(
        self,
        email: str,
        now: str,
    ) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT blocked_until
                FROM auth_login_attempts
                WHERE email = ?
                """,
                (email,),
            ).fetchone()
        if row is None:
            return None
        return _retry_after_seconds(row["blocked_until"], now)

    def record_login_rate_limit_failure(
        self,
        email: str,
        *,
        now: str,
        max_failed_attempts: int,
        window_seconds: int,
    ) -> int | None:
        bounded_max_attempts = max(1, max_failed_attempts)
        bounded_window_seconds = max(1, window_seconds)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT failures, first_failure_at, blocked_until
                FROM auth_login_attempts
                WHERE email = ?
                """,
                (email,),
            ).fetchone()

            if row is None or _iso_seconds_between(row["first_failure_at"], now) > (
                bounded_window_seconds
            ):
                failures = 1
                first_failure_at = now
                blocked_until = now
            else:
                failures = int(row["failures"]) + 1
                first_failure_at = str(row["first_failure_at"])
                blocked_until = str(row["blocked_until"])

            if failures >= bounded_max_attempts:
                blocked_until = _add_seconds(first_failure_at, bounded_window_seconds)

            connection.execute(
                """
                INSERT INTO auth_login_attempts
                  (email, failures, first_failure_at, blocked_until)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                  failures = excluded.failures,
                  first_failure_at = excluded.first_failure_at,
                  blocked_until = excluded.blocked_until
                """,
                (email, failures, first_failure_at, blocked_until),
            )
        return _retry_after_seconds(blocked_until, now)

    def clear_login_rate_limit(self, email: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM auth_login_attempts
                WHERE email = ?
                """,
                (email,),
            )

    def run_operational_maintenance(self, now_iso: str | None = None) -> dict[str, int]:
        with self._connect(run_maintenance=False) as connection:
            result = self._run_connection_maintenance(connection, now_iso=now_iso)
            self._last_maintenance_at = time.monotonic()
        return result

    def _connect(self, *, run_maintenance: bool = True) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._database_path,
            timeout=self._connection_policy.timeout_seconds,
            isolation_level="IMMEDIATE",
        )
        connection.row_factory = sqlite3.Row
        self._configure_connection(connection)
        if run_maintenance:
            self._maybe_run_connection_maintenance(connection)
        return connection

    def _configure_connection(self, connection: sqlite3.Connection) -> None:
        connection.execute(f"PRAGMA busy_timeout = {self._connection_policy.busy_timeout_ms}")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute(
            f"PRAGMA wal_autocheckpoint = {self._connection_policy.wal_autocheckpoint_pages}"
        )

    def _maybe_run_connection_maintenance(self, connection: sqlite3.Connection) -> None:
        now = time.monotonic()
        if (
            self._connection_policy.maintenance_interval_seconds > 0
            and now - self._last_maintenance_at
            < self._connection_policy.maintenance_interval_seconds
        ):
            return
        if not self._maintenance_lock.acquire(blocking=False):
            return
        try:
            now = time.monotonic()
            if (
                self._connection_policy.maintenance_interval_seconds > 0
                and now - self._last_maintenance_at
                < self._connection_policy.maintenance_interval_seconds
            ):
                return
            self._run_connection_maintenance(connection)
            self._last_maintenance_at = now
        finally:
            self._maintenance_lock.release()

    def _run_connection_maintenance(
        self,
        connection: sqlite3.Connection,
        *,
        now_iso: str | None = None,
    ) -> dict[str, int]:
        connection.execute("PRAGMA optimize")
        connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
        return self._cleanup_expired_operational_records(
            connection,
            now_iso=now_iso or utc_now_iso(),
        )

    def _cleanup_expired_operational_records(
        self,
        connection: sqlite3.Connection,
        *,
        now_iso: str,
    ) -> dict[str, int]:
        return self._maintenance.cleanup_expired_operational_records(
            connection,
            now_iso=now_iso,
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

    def _upload_task_values(self, task: ExcelUploadTask) -> tuple[object, ...]:
        return (
            task.task_id,
            task.user_id,
            task.original_filename,
            task.staging_path,
            1 if task.replace_existing else 0,
            task.status.value,
            task.error_message,
            dump_json(task.result),
            task.created_at,
            task.updated_at,
            task.started_at,
            task.finished_at,
            task.worker_id,
        )

    def _to_upload_task(self, row: sqlite3.Row | None) -> ExcelUploadTask | None:
        if row is None:
            return None
        return ExcelUploadTask(
            task_id=str(row["task_id"]),
            user_id=str(row["user_id"]),
            original_filename=str(row["original_filename"]),
            staging_path=str(row["staging_path"]),
            replace_existing=bool(int(row["replace_existing"])),
            status=ExcelUploadTaskStatus(str(row["status"])),
            error_message=row["error_message"],
            result=load_json_object(row_value(row, "result_json", "{}")),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            worker_id=row["worker_id"],
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
        )

    def _save_pdf_summary(
        self,
        connection: sqlite3.Connection,
        summary: PdfDocumentSummary,
    ) -> None:
        connection.execute(
            """
            INSERT INTO pdf_document_summaries
              (file_id, status, content, updated_at, error_message)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
              status = excluded.status,
              content = excluded.content,
              updated_at = excluded.updated_at,
              error_message = excluded.error_message
            """,
            (
                summary.file_id,
                summary.status,
                summary.content,
                summary.updated_at,
                summary.error_message,
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
        )

    def _to_user(self, row: sqlite3.Row | None) -> UserAccount | None:
        if row is None:
            return None
        return UserAccount(
            user_id=str(row["user_id"]),
            email=str(row["email"]),
            password_hash=str(row["password_hash"]),
            role=UserRole(str(row["role"])),
            is_active=bool(int(row["is_active"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            last_login_at=row["last_login_at"],
        )

    def _to_joined_user(self, row: sqlite3.Row) -> UserAccount:
        return UserAccount(
            user_id=str(row["user_id"]),
            email=str(row["email"]),
            password_hash=str(row["password_hash"]),
            role=UserRole(str(row["role"])),
            is_active=bool(int(row["is_active"])),
            created_at=str(row["user_created_at"]),
            updated_at=str(row["user_updated_at"]),
            last_login_at=row["last_login_at"],
        )

    def _to_auth_session(self, row: sqlite3.Row) -> AuthSession:
        return AuthSession(
            session_id=str(row["auth_session_id"]),
            user_id=str(row["auth_user_id"]),
            session_token_hash=str(row["session_token_hash"]),
            created_at=str(row["auth_created_at"]),
            expires_at=str(row["expires_at"]),
            revoked_at=row["revoked_at"],
        )

    def _to_password_reset_token(self, row: sqlite3.Row) -> PasswordResetToken:
        return PasswordResetToken(
            reset_token_id=str(row["reset_token_id"]),
            user_id=str(row["reset_user_id"]),
            token_hash=str(row["token_hash"]),
            created_at=str(row["reset_created_at"]),
            expires_at=str(row["expires_at"]),
            used_at=row["used_at"],
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


def _retry_after_seconds(blocked_until: str, now: str) -> int | None:
    remaining_seconds = _iso_seconds_between(now, blocked_until)
    if remaining_seconds <= 0:
        return None
    return max(1, int(remaining_seconds))


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso_seconds_between(start: str, end: str) -> float:
    return (_parse_iso_datetime(end) - _parse_iso_datetime(start)).total_seconds()


def _add_seconds(value: str, seconds: int) -> str:
    return (_parse_iso_datetime(value) + timedelta(seconds=seconds)).isoformat(
        timespec="seconds"
    )


def _parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
