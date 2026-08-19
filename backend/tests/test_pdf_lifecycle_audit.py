import sqlite3
from pathlib import Path

from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.domain.models import (
    PdfFile,
    PdfFileKind,
    PdfFileStatus,
    PdfFileVisibility,
    PdfProcessingStatus,
    PdfUploadTask,
    PdfUploadTaskStatus,
)
from scripts.audit_pdf_lifecycle import audit

NOW = "2026-08-14T00:00:00+00:00"


def test_pdf_lifecycle_audit_reports_clean_database(tmp_path: Path) -> None:
    database_path = tmp_path / "clean.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)
    repository.initialize()
    repository.create_pdf_file(_pdf_file("file_clean", "clean.pdf"))
    repository.create_pdf_upload_task(_upload_task("task_clean", "file_clean"))

    report = audit(database_path)

    assert report["integrity_check"] == "ok"
    assert report["critical_violation_count"] == 0


def test_pdf_lifecycle_audit_detects_cross_table_invariant_violations(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "dirty.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)
    repository.initialize()
    repository.create_pdf_file(_pdf_file("file_duplicate", "duplicate.pdf"))
    repository.create_pdf_upload_task(_upload_task("task_first", "file_duplicate"))

    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP INDEX idx_pdf_upload_tasks_one_active_file")
        connection.execute("DROP INDEX idx_pdf_files_unique_active_sibling_name")

    repository.create_pdf_file(_pdf_file("file_same_name", "duplicate.pdf"))
    repository.create_pdf_upload_task(_upload_task("task_second", "file_duplicate"))
    repository.create_pdf_file(_pdf_file("file_deleted", "deleted.pdf"))
    repository.create_pdf_upload_task(_upload_task("task_deleted", "file_deleted"))

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE pdf_files
            SET status = 'deleted', deleted_at = ?, updated_at = ?
            WHERE file_id = 'file_deleted'
            """,
            (NOW, NOW),
        )

    report = audit(database_path)

    assert report["active_upload_task_duplicate_groups"] == 1
    assert report["active_sibling_name_duplicate_groups"] == 1
    assert report["active_upload_tasks_for_deleted_files"] == 1
    assert int(report["critical_violation_count"]) >= 3


def test_pdf_lifecycle_audit_treats_deleted_file_content_as_critical(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "deleted-content.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)
    repository.initialize()
    repository.create_pdf_file(_pdf_file("file_deleted_content", "deleted-content.pdf"))
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO pdf_document_tags (file_id, tag, tag_index)
            VALUES ('file_deleted_content', 'retained-tag', 0)
            """
        )
        connection.execute(
            """
            UPDATE pdf_files
            SET status = 'deleted', deleted_at = ?, updated_at = ?
            WHERE file_id = 'file_deleted_content'
            """,
            (NOW, NOW),
        )

    report = audit(database_path)

    retained = report["content_rows_retained_for_deleted_files"]
    assert isinstance(retained, dict)
    assert retained["pdf_document_tags"] == 1
    assert int(report["critical_violation_count"]) >= 1


def _pdf_file(file_id: str, display_name: str) -> PdfFile:
    return PdfFile(
        file_id=file_id,
        user_id="admin",
        parent_id=None,
        display_name=display_name,
        original_filename=display_name,
        kind=PdfFileKind.PDF,
        size_bytes=100,
        storage_path=f"pdf-knowledge/files/{file_id}/{display_name}",
        status=PdfFileStatus.ACTIVE,
        visibility=PdfFileVisibility.VISIBLE,
        processing_status=PdfProcessingStatus.QUEUED,
        progress=5,
        status_detail="queued",
        error_message=None,
        page_count=None,
        chunk_count=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _upload_task(task_id: str, file_id: str) -> PdfUploadTask:
    return PdfUploadTask(
        task_id=task_id,
        user_id="admin",
        file_id=file_id,
        original_filename=f"{file_id}.pdf",
        staging_path=f"pdf-knowledge/staging/{task_id}.pdf",
        status=PdfUploadTaskStatus.QUEUED,
        progress=5,
        detail="queued",
        error_message=None,
        result={},
        created_at=NOW,
        updated_at=NOW,
    )
