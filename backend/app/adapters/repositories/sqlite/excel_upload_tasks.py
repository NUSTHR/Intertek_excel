import sqlite3
from collections.abc import Callable

from app.adapters.repositories.sqlite.serialization import (
    dump_json,
    load_json_object,
    row_value,
)
from app.domain.models import ExcelUploadTask, ExcelUploadTaskStatus


class SQLiteExcelUploadTaskRepository:
    """Queue persistence for asynchronous Excel ingestion."""

    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect

    def create(self, task: ExcelUploadTask) -> None:
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
                _task_values(task),
            )

    def get(self, task_id: str) -> ExcelUploadTask | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM excel_upload_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return _to_task(row)

    def claim_next(
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
        return _to_task(row)

    def complete(
        self,
        *,
        task_id: str,
        result: dict[str, object],
        finished_at: str,
    ) -> ExcelUploadTask | None:
        return self._finish(
            task_id=task_id,
            status=ExcelUploadTaskStatus.READY,
            error_message=None,
            result=result,
            finished_at=finished_at,
        )

    def fail(
        self,
        *,
        task_id: str,
        error_message: str,
        finished_at: str,
    ) -> ExcelUploadTask | None:
        return self._finish(
            task_id=task_id,
            status=ExcelUploadTaskStatus.FAILED,
            error_message=error_message,
            result={},
            finished_at=finished_at,
        )

    def fail_stale_processing(
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

    def _finish(
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
        return _to_task(row)


def _task_values(task: ExcelUploadTask) -> tuple[object, ...]:
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


def _to_task(row: sqlite3.Row | None) -> ExcelUploadTask | None:
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
