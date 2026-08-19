import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.adapters.repositories import sqlite_repository
from app.adapters.repositories.sqlite.migrations import SQLiteMigrationRunner
from app.adapters.repositories.sqlite.schema import SchemaMigration
from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.core.config import Settings
from app.core.errors import ActiveUploadTaskConflictError, ChatSessionRevisionConflict
from app.domain.models import (
    ChatSession,
    ChatTurn,
    ChatWorkspace,
    ExcelFile,
    ExcelFileVersion,
    ExcelUploadTask,
    ExcelUploadTaskStatus,
    ExcelVersionStatus,
    PdfFile,
    PdfFileKind,
    PdfFileStatus,
    PdfFileVisibility,
    PdfProcessingStatus,
    PdfUploadTask,
    PdfUploadTaskStatus,
)


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

    assert [int(row["version"]) for row in rows] == [
        migration.version for migration in sqlite_repository.SCHEMA_MIGRATIONS
    ]
    assert [row["name"] for row in rows] == [
        migration.name for migration in sqlite_repository.SCHEMA_MIGRATIONS
    ]
    assert all(row["checksum"] for row in rows)

    with sqlite3.connect(database_path) as connection:
        search_index = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'excel_row_search_index'
            """
        ).fetchone()
    assert search_index is not None


def test_schema_migration_failure_rolls_back_all_ddl(tmp_path: Path) -> None:
    database_path = tmp_path / "failed-migration.sqlite3"
    runner = SQLiteMigrationRunner(
        (
            SchemaMigration(
                version=1,
                name="fault_injection",
                statements=(
                    "CREATE TABLE partial_table(id INTEGER PRIMARY KEY)",
                    "THIS IS INVALID SQL",
                ),
            ),
        )
    )

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        with pytest.raises(sqlite3.Error):
            runner.initialize_schema(connection)
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert "partial_table" not in tables
    assert "schema_migrations" not in tables


def test_deleted_pdf_reconciliation_migration_purges_content_and_queues_cleanup(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "deleted-pdf-reconciliation.sqlite3"
    legacy_runner = SQLiteMigrationRunner(
        [
            migration
            for migration in sqlite_repository.SCHEMA_MIGRATIONS
            if migration.version < 35
        ]
    )
    with sqlite3.connect(database_path) as connection:
        legacy_runner.initialize_schema(connection)
    repository = SQLiteExcelAssetRepository(database_path)
    now = "2026-08-14T00:00:00+00:00"
    file = _existing_pdf_file("file_historical_deleted", now)
    repository.create_pdf_file(file)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO pdf_document_tags (file_id, tag, tag_index)
            VALUES (?, 'historical-tag', 0)
            """,
            (file.file_id,),
        )
        connection.execute(
            """
            UPDATE pdf_files
            SET status = 'deleted', deleted_at = ?, updated_at = ?
            WHERE file_id = ?
            """,
            (now, now, file.file_id),
        )

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        SQLiteMigrationRunner(sqlite_repository.SCHEMA_MIGRATIONS).initialize_schema(
            connection
        )
        tag_count = connection.execute(
            "SELECT COUNT(*) FROM pdf_document_tags WHERE file_id = ?",
            (file.file_id,),
        ).fetchone()[0]
        cleanup_job = connection.execute(
            """
            SELECT status, relative_path
            FROM pdf_file_cleanup_jobs
            WHERE file_id = ?
            """,
            (file.file_id,),
        ).fetchone()

    assert tag_count == 0
    assert cleanup_job is not None
    assert tuple(cleanup_job) == (
        "pending",
        f"pdf-knowledge/files/{file.file_id}",
    )


def test_vector_task_lifecycle_migration_normalizes_legacy_failures(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-vector-tasks.sqlite3"
    legacy_runner = SQLiteMigrationRunner(
        [
            migration
            for migration in sqlite_repository.SCHEMA_MIGRATIONS
            if migration.version <= 37
        ]
    )
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        legacy_runner.initialize_schema(connection)
        connection.executemany(
            """
            INSERT INTO pdf_vector_index_tasks (
              task_id, file_id, action, source_fingerprint, embedding_revision,
              status, attempt_count, error_message, created_at, updated_at,
              started_at, finished_at, worker_id, claim_token, lease_expires_at,
              heartbeat_at, state_revision, next_attempt_at
            )
            VALUES (?, ?, 'index', 'fingerprint', 'embedding@1', 'failed', ?,
                    'legacy failure', ?, ?, ?, ?, 'legacy-worker', 'legacy-claim',
                    ?, ?, 3, ?)
            """,
            (
                (
                    "task-retry",
                    "file-retry",
                    2,
                    "2026-08-14T00:00:00+00:00",
                    "2026-08-14T00:02:00+00:00",
                    "2026-08-14T00:01:00+00:00",
                    "2026-08-14T00:02:00+00:00",
                    "2026-08-14T00:10:00+00:00",
                    "2026-08-14T00:01:30+00:00",
                    "2026-08-14T00:02:04+00:00",
                ),
                (
                    "task-exhausted",
                    "file-exhausted",
                    10,
                    "2026-08-14T00:00:00+00:00",
                    "2026-08-14T00:02:00+00:00",
                    "2026-08-14T00:01:00+00:00",
                    "2026-08-14T00:02:00+00:00",
                    "2026-08-14T00:10:00+00:00",
                    "2026-08-14T00:01:30+00:00",
                    "2026-08-14T00:07:00+00:00",
                ),
            ),
        )
        SQLiteMigrationRunner(sqlite_repository.SCHEMA_MIGRATIONS).initialize_schema(
            connection
        )
        rows = connection.execute(
            """
            SELECT task_id, status, error_code, finished_at, worker_id,
                   claim_token, lease_expires_at, heartbeat_at, next_attempt_at
            FROM pdf_vector_index_tasks
            ORDER BY task_id
            """
        ).fetchall()

    assert dict(rows[0]) == {
        "task_id": "task-exhausted",
        "status": "dead_letter",
        "error_code": "LEGACY_RETRY_EXHAUSTED",
        "finished_at": "2026-08-14T00:02:00+00:00",
        "worker_id": None,
        "claim_token": None,
        "lease_expires_at": None,
        "heartbeat_at": None,
        "next_attempt_at": None,
    }
    assert dict(rows[1]) == {
        "task_id": "task-retry",
        "status": "retry_wait",
        "error_code": "LEGACY_RETRYABLE_FAILURE",
        "finished_at": None,
        "worker_id": None,
        "claim_token": None,
        "lease_expires_at": None,
        "heartbeat_at": None,
        "next_attempt_at": "2026-08-14T00:02:04+00:00",
    }


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
            lease_expires_at="2026-06-14T01:00:00+00:00",
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
        lease_expires_at="2026-06-14T01:01:00+00:00",
    ) is None


def test_excel_upload_task_claim_token_and_lease_fence_terminal_writes(
    tmp_path: Path,
) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    repository.initialize()
    repository.create_upload_task(
        ExcelUploadTask(
            task_id="task_fenced",
            user_id="user_admin",
            original_filename="fenced.xlsx",
            staging_path="staging/fenced.xlsx",
            replace_existing=False,
            status=ExcelUploadTaskStatus.QUEUED,
            error_message=None,
            result={},
            created_at="2026-08-14T00:00:00+00:00",
            updated_at="2026-08-14T00:00:00+00:00",
        )
    )
    claimed = repository.claim_next_upload_task(
        worker_id="worker_owner",
        started_at="2026-08-14T00:00:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )
    assert claimed is not None and claimed.claim_token

    assert repository.complete_upload_task(
        task_id=claimed.task_id,
        worker_id="worker_intruder",
        claim_token=claimed.claim_token,
        result={},
        finished_at="2026-08-14T00:01:00+00:00",
    ) is None
    assert repository.heartbeat_upload_task(
        task_id=claimed.task_id,
        worker_id="worker_owner",
        claim_token=claimed.claim_token,
        heartbeat_at="2026-08-14T00:05:00+00:00",
        lease_expires_at="2026-08-14T00:20:00+00:00",
    )
    completed = repository.complete_upload_task(
        task_id=claimed.task_id,
        worker_id="worker_owner",
        claim_token=claimed.claim_token,
        result={"file_id": "file_ready"},
        finished_at="2026-08-14T00:15:00+00:00",
    )
    assert completed is not None
    assert completed.status == ExcelUploadTaskStatus.READY
    assert completed.state_revision >= 3


def test_expired_excel_upload_claim_cannot_activate_materialized_version(
    tmp_path: Path,
) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "activation.sqlite3")
    repository.initialize()
    now = "2026-08-14T00:00:00+00:00"
    repository.create_file(
        ExcelFile(
            file_id="file_claim_guard",
            display_name="claim-guard.xlsx",
            active_version_id=None,
            created_at=now,
            updated_at=now,
        )
    )
    repository.create_version(
        ExcelFileVersion(
            version_id="version_claim_guard",
            file_id="file_claim_guard",
            original_filename="claim-guard.xlsx",
            file_hash="hash",
            status=ExcelVersionStatus.PROCESSING,
            error_message=None,
            created_at=now,
            activated_at=None,
        )
    )
    repository.create_upload_task(
        ExcelUploadTask(
            task_id="task_claim_guard",
            user_id="user_admin",
            original_filename="claim-guard.xlsx",
            staging_path="staging/claim-guard.xlsx",
            replace_existing=False,
            status=ExcelUploadTaskStatus.QUEUED,
            error_message=None,
            result={},
            created_at=now,
            updated_at=now,
        )
    )
    claimed = repository.claim_next_upload_task(
        worker_id="worker_claim_guard",
        started_at=now,
        lease_expires_at="2026-08-14T00:01:00+00:00",
    )
    assert claimed is not None and claimed.claim_token

    activated = repository.activate_version_for_upload_task(
        file_id="file_claim_guard",
        version_id="version_claim_guard",
        task_id=claimed.task_id,
        worker_id=claimed.worker_id or "",
        claim_token=claimed.claim_token,
        activated_at="2026-08-14T00:02:00+00:00",
        task_result={
            "file_id": "file_claim_guard",
            "version_id": "version_claim_guard",
        },
    )

    assert activated is False
    file = repository.get_file("file_claim_guard")
    assert file is not None
    assert file.active_version_id is None


def test_excel_upload_publication_activates_version_and_completes_task_atomically(
    tmp_path: Path,
) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "atomic-activation.sqlite3")
    repository.initialize()
    now = "2026-08-14T00:00:00+00:00"
    repository.create_file(
        ExcelFile(
            file_id="file_atomic_publish",
            display_name="atomic-publish.xlsx",
            active_version_id=None,
            created_at=now,
            updated_at=now,
        )
    )
    repository.create_version(
        ExcelFileVersion(
            version_id="version_atomic_publish",
            file_id="file_atomic_publish",
            original_filename="atomic-publish.xlsx",
            file_hash="hash",
            status=ExcelVersionStatus.PROCESSING,
            error_message=None,
            created_at=now,
            activated_at=None,
        )
    )
    repository.create_upload_task(
        ExcelUploadTask(
            task_id="task_atomic_publish",
            user_id="user_admin",
            original_filename="atomic-publish.xlsx",
            staging_path="staging/atomic-publish.xlsx",
            replace_existing=False,
            status=ExcelUploadTaskStatus.QUEUED,
            error_message=None,
            result={},
            created_at=now,
            updated_at=now,
        )
    )
    claimed = repository.claim_next_upload_task(
        worker_id="worker_atomic_publish",
        started_at=now,
        lease_expires_at="2026-08-14T00:05:00+00:00",
    )
    assert claimed is not None and claimed.claim_token
    task_result = {
        "file_id": "file_atomic_publish",
        "version_id": "version_atomic_publish",
    }

    activated = repository.activate_version_for_upload_task(
        file_id="file_atomic_publish",
        version_id="version_atomic_publish",
        task_id=claimed.task_id,
        worker_id=claimed.worker_id or "",
        claim_token=claimed.claim_token,
        activated_at="2026-08-14T00:01:00+00:00",
        task_result=task_result,
    )

    assert activated is True
    file = repository.get_file("file_atomic_publish")
    version = repository.get_version("version_atomic_publish")
    task = repository.get_upload_task("task_atomic_publish")
    assert file is not None and file.active_version_id == "version_atomic_publish"
    assert version is not None and version.status == ExcelVersionStatus.READY
    assert task is not None and task.status == ExcelUploadTaskStatus.READY
    assert task.result == task_result
    assert task.finished_at == "2026-08-14T00:01:00+00:00"


def test_pdf_existing_file_queue_and_cancel_update_file_in_same_transaction(
    tmp_path: Path,
) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "pdf-queue-cancel.sqlite3")
    repository.initialize()
    now = "2026-08-14T00:00:00+00:00"
    file = _existing_pdf_file("file_queue_cancel", now)
    repository.create_pdf_file(file)
    task = _queued_pdf_task("task_queue_cancel", file.file_id, now)

    repository.queue_pdf_upload_task_for_existing_file(
        task,
        status_detail="Queued for test.",
        mark_summary_stale=False,
    )

    queued_file = repository.get_pdf_file(file.file_id)
    assert queued_file is not None
    assert queued_file.processing_status == PdfProcessingStatus.QUEUED
    cancelled = repository.cancel_pdf_upload_task(
        task_id=task.task_id,
        cancelled_at="2026-08-14T00:01:00+00:00",
        detail="Cancelled for test.",
    )
    cancelled_file = repository.get_pdf_file(file.file_id)
    assert cancelled is not None
    assert cancelled.status == PdfUploadTaskStatus.CANCELLED
    assert cancelled_file is not None
    assert cancelled_file.processing_status == PdfProcessingStatus.CANCELLED


def test_pdf_queue_conflict_rolls_back_file_state_change(tmp_path: Path) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "pdf-queue-conflict.sqlite3")
    repository.initialize()
    now = "2026-08-14T00:00:00+00:00"
    file = _existing_pdf_file("file_queue_conflict", now)
    repository.create_pdf_file(file)
    first_task = _queued_pdf_task("task_queue_first", file.file_id, now)
    repository.create_pdf_upload_task(first_task)

    with pytest.raises(ActiveUploadTaskConflictError):
        repository.queue_pdf_upload_task_for_existing_file(
            _queued_pdf_task("task_queue_second", file.file_id, now),
            status_detail="This update must roll back.",
            mark_summary_stale=False,
        )

    unchanged_file = repository.get_pdf_file(file.file_id)
    assert unchanged_file is not None
    assert unchanged_file.processing_status == PdfProcessingStatus.READY
    assert unchanged_file.status_detail == "Ready before queue attempt."


def _existing_pdf_file(file_id: str, now: str) -> PdfFile:
    return PdfFile(
        file_id=file_id,
        user_id="user_admin",
        parent_id=None,
        display_name=f"{file_id}.pdf",
        original_filename=f"{file_id}.pdf",
        kind=PdfFileKind.PDF,
        size_bytes=100,
        storage_path=f"pdf-knowledge/files/{file_id}/{file_id}.pdf",
        status=PdfFileStatus.ACTIVE,
        visibility=PdfFileVisibility.VISIBLE,
        processing_status=PdfProcessingStatus.READY,
        progress=100,
        status_detail="Ready before queue attempt.",
        error_message=None,
        page_count=1,
        chunk_count=1,
        created_at=now,
        updated_at=now,
    )


def _queued_pdf_task(task_id: str, file_id: str, now: str) -> PdfUploadTask:
    return PdfUploadTask(
        task_id=task_id,
        user_id="user_admin",
        file_id=file_id,
        original_filename=f"{file_id}.pdf",
        staging_path=f"pdf-knowledge/upload-tasks/{task_id}/{file_id}.pdf",
        status=PdfUploadTaskStatus.QUEUED,
        progress=5,
        detail="Queued for test.",
        error_message=None,
        result={},
        created_at=now,
        updated_at=now,
    )


def test_pdf_cleanup_job_can_only_be_claimed_and_completed_once(tmp_path: Path) -> None:
    database_path = tmp_path / "cleanup.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)
    repository.initialize()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO pdf_file_cleanup_jobs
              (
                job_id, file_id, relative_path, status, attempt_count,
                error_message, created_at, updated_at, completed_at
              )
            VALUES (?, ?, ?, 'pending', 0, NULL, ?, ?, NULL)
            """,
            (
                "cleanup_once",
                "file_deleted",
                "pdf-knowledge/files/file_deleted",
                "2026-08-14T00:00:00+00:00",
                "2026-08-14T00:00:00+00:00",
            ),
        )

    def claim(worker_index: int):
        return repository.claim_pdf_file_cleanup_job(
            job_id="cleanup_once",
            worker_id=f"cleanup_worker_{worker_index}",
            claim_token=f"cleanup_claim_{worker_index}",
            claimed_at="2026-08-14T00:01:00+00:00",
            lease_expires_at="2026-08-14T01:00:00+00:00",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = [job for job in executor.map(claim, range(2)) if job is not None]

    assert len(claims) == 1
    claimed = claims[0]
    assert repository.complete_pdf_file_cleanup_job(
        job_id=claimed.job_id,
        worker_id="wrong_worker",
        claim_token=claimed.claim_token or "",
        completed_at="2026-08-14T00:02:00+00:00",
    ) is None
    completed = repository.complete_pdf_file_cleanup_job(
        job_id=claimed.job_id,
        worker_id=claimed.worker_id or "",
        claim_token=claimed.claim_token or "",
        completed_at="2026-08-14T00:02:00+00:00",
    )
    assert completed is not None
    assert completed.status == "completed"
    assert completed.attempt_count == 1


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


def test_repository_creates_chat_turn_idempotency_index(tmp_path: Path) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)

    repository.initialize()

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info('chat_turns')")
        }
        session_columns = {
            row[1] for row in connection.execute("PRAGMA table_info('chat_sessions')")
        }
        request_execution_table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'chat_request_executions'
            """
        ).fetchone()
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('chat_turns')")
        }

    assert "request_id" in columns
    assert "conversation_revision" in session_columns
    assert request_execution_table is not None
    assert "idx_chat_turns_session_request" in indexes

    with sqlite3.connect(database_path) as connection:
        pdf_columns = {
            row[1] for row in connection.execute("PRAGMA table_info('pdf_files')")
        }
        pdf_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('pdf_files')")
        }

    assert "content_fingerprint" in pdf_columns
    assert "idx_pdf_files_content_fingerprint" in pdf_indexes


def test_pdf_chat_turn_commit_is_atomic_and_revision_guarded(tmp_path: Path) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    repository.initialize()
    session = ChatSession(
        session_id="pdfsession_atomic",
        user_id="user_admin",
        created_at="2026-07-29T00:00:00+00:00",
        updated_at="2026-07-29T00:00:00+00:00",
        workspace=ChatWorkspace.PDF,
    )
    repository.create_session(session)
    failed_turn = ChatTurn(
        turn_id="turn_atomic_failed",
        session_id=session.session_id,
        question="must roll back",
        answer_text="must not persist",
        citation_ids=[],
        selected_documents=[],
        created_at="2026-07-29T00:00:00.500000+00:00",
    )
    original_insert_turn = repository._insert_turn_on_connection

    def fail_turn_insert(
        _connection: sqlite3.Connection,
        _turn: ChatTurn,
    ) -> None:
        raise RuntimeError("injected PDF turn insert failure")

    repository._insert_turn_on_connection = fail_turn_insert  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="injected PDF turn insert failure"):
        repository.commit_pdf_chat_turn(
            session_id=session.session_id,
            user_id=session.user_id,
            expected_conversation_revision=0,
            context_file_ids=["failed_scope"],
            attached_documents=[],
            turn=failed_turn,
            title_if_new="must roll back",
            request_fingerprint=None,
        )
    repository._insert_turn_on_connection = original_insert_turn  # type: ignore[method-assign]

    after_failure = repository.get_session(
        session.session_id,
        workspace=ChatWorkspace.PDF.value,
    )
    assert after_failure is not None
    assert after_failure.conversation_revision == 0
    assert after_failure.context_file_ids == []
    assert after_failure.title == "New chat"
    assert after_failure.updated_at == session.updated_at
    assert repository.list_turns(
        session.session_id,
        workspace=ChatWorkspace.PDF.value,
    ) == []

    first_turn = ChatTurn(
        turn_id="turn_atomic_first",
        session_id=session.session_id,
        question="first",
        answer_text="answer",
        citation_ids=[],
        selected_documents=[],
        created_at="2026-07-29T00:00:01+00:00",
        request_id="pdfreq_atomic_first",
    )
    request_fingerprint = "pdf-chat-atomic-fingerprint"
    claimed = repository.claim_pdf_chat_request(
        session_id=session.session_id,
        user_id=session.user_id,
        request_id=first_turn.request_id,
        request_fingerprint=request_fingerprint,
        claimed_at="2026-07-29T00:00:00+00:00",
        lease_expires_at="2026-07-29T00:10:00+00:00",
    )
    assert claimed is None

    committed = repository.commit_pdf_chat_turn(
        session_id=session.session_id,
        user_id=session.user_id,
        expected_conversation_revision=0,
        context_file_ids=["folder_scope"],
        attached_documents=[],
        turn=first_turn,
        title_if_new="first",
        request_fingerprint=request_fingerprint,
    )

    assert committed == first_turn
    updated_session = repository.get_session(
        session.session_id,
        workspace=ChatWorkspace.PDF.value,
    )
    assert updated_session is not None
    assert updated_session.revision == 0
    assert updated_session.conversation_revision == 1
    assert updated_session.context_file_ids == ["folder_scope"]
    assert updated_session.title == "first"

    stale_turn = ChatTurn(
        turn_id="turn_atomic_stale",
        session_id=session.session_id,
        question="stale",
        answer_text="must not persist",
        citation_ids=[],
        selected_documents=[],
        created_at="2026-07-29T00:00:02+00:00",
    )
    with pytest.raises(ChatSessionRevisionConflict):
        repository.commit_pdf_chat_turn(
            session_id=session.session_id,
            user_id=session.user_id,
            expected_conversation_revision=0,
            context_file_ids=["stale_scope"],
            attached_documents=[],
            turn=stale_turn,
            title_if_new="stale",
            request_fingerprint=None,
        )

    persisted_turns = repository.list_turns(
        session.session_id,
        workspace=ChatWorkspace.PDF.value,
    )
    assert [turn.turn_id for turn in persisted_turns] == [first_turn.turn_id]
    unchanged_session = repository.get_session(
        session.session_id,
        workspace=ChatWorkspace.PDF.value,
    )
    assert unchanged_session is not None
    assert unchanged_session.revision == 0
    assert unchanged_session.conversation_revision == 1
    assert unchanged_session.context_file_ids == ["folder_scope"]

    retried = repository.commit_pdf_chat_turn(
        session_id=session.session_id,
        user_id=session.user_id,
        expected_conversation_revision=0,
        context_file_ids=["ignored_retry_scope"],
        attached_documents=[],
        turn=first_turn,
        title_if_new="ignored retry",
        request_fingerprint=request_fingerprint,
    )
    assert retried.turn_id == first_turn.turn_id
    assert retried.request_id == first_turn.request_id


def test_excel_chat_turn_commit_is_atomic_and_revision_guarded(
    tmp_path: Path,
) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    repository.initialize()
    session = ChatSession(
        session_id="excelsession_atomic",
        user_id="user_admin",
        created_at="2026-07-30T00:00:00+00:00",
        updated_at="2026-07-30T00:00:00+00:00",
        workspace=ChatWorkspace.EXCEL,
    )
    repository.create_session(session)
    failed_turn = ChatTurn(
        turn_id="turn_excel_failed",
        session_id=session.session_id,
        question="must roll back",
        answer_text="must not persist",
        citation_ids=[],
        selected_documents=[],
        created_at="2026-07-30T00:00:01+00:00",
    )
    original_insert_turn = repository._insert_turn_on_connection

    def fail_turn_insert(
        _connection: sqlite3.Connection,
        _turn: ChatTurn,
    ) -> None:
        raise RuntimeError("injected turn insert failure")

    repository._insert_turn_on_connection = fail_turn_insert  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="injected turn insert failure"):
        repository.commit_excel_chat_turn(
            session_id=session.session_id,
            user_id=session.user_id,
            expected_conversation_revision=0,
            attached_documents=[],
            turn=failed_turn,
            request_fingerprint=None,
        )
    repository._insert_turn_on_connection = original_insert_turn  # type: ignore[method-assign]

    after_failure = repository.get_session(
        session.session_id,
        workspace=ChatWorkspace.EXCEL.value,
    )
    assert after_failure is not None
    assert after_failure.conversation_revision == 0
    assert after_failure.updated_at == session.updated_at
    assert repository.list_turns(
        session.session_id,
        workspace=ChatWorkspace.EXCEL.value,
    ) == []

    first_turn = ChatTurn(
        turn_id="turn_excel_first",
        session_id=session.session_id,
        question="first",
        answer_text="answer",
        citation_ids=[],
        selected_documents=[],
        created_at="2026-07-30T00:00:02+00:00",
    )
    repository.commit_excel_chat_turn(
        session_id=session.session_id,
        user_id=session.user_id,
        expected_conversation_revision=0,
        attached_documents=[],
        turn=first_turn,
        request_fingerprint=None,
    )

    stale_turn = ChatTurn(
        turn_id="turn_excel_stale",
        session_id=session.session_id,
        question="stale",
        answer_text="must not persist",
        citation_ids=[],
        selected_documents=[],
        created_at="2026-07-30T00:00:03+00:00",
    )
    with pytest.raises(ChatSessionRevisionConflict):
        repository.commit_excel_chat_turn(
            session_id=session.session_id,
            user_id=session.user_id,
            expected_conversation_revision=0,
            attached_documents=[],
            turn=stale_turn,
            request_fingerprint=None,
        )

    committed_session = repository.get_session(
        session.session_id,
        workspace=ChatWorkspace.EXCEL.value,
    )
    assert committed_session is not None
    assert committed_session.conversation_revision == 1
    assert [
        turn.turn_id
        for turn in repository.list_turns(
            session.session_id,
            workspace=ChatWorkspace.EXCEL.value,
        )
    ] == [first_turn.turn_id]


def test_repository_migration_normalizes_storage_references(tmp_path: Path) -> None:
    database_path = tmp_path / "excel.sqlite3"
    repository = SQLiteExcelAssetRepository(database_path)
    repository.initialize()

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO excel_files
              (file_id, display_name, active_version_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "file_legacy_paths",
                "legacy.xlsx",
                "version_legacy_paths",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
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
                "version_legacy_paths",
                "file_legacy_paths",
                "legacy.xlsx",
                "hash",
                "ready",
                None,
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
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
                "sheet_legacy_paths",
                "version_legacy_paths",
                1,
                "S001",
                "Legacy",
                1,
                1,
                "/old/root/excel_workspace/storage/files/file_legacy_paths/"
                "version_legacy_paths/sheets/S001.csv",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO excel_artifacts
              (artifact_id, version_id, artifact_type, path, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "artifact_legacy_paths",
                "version_legacy_paths",
                "raw_csv",
                "/old/root/excel_workspace/storage/files/file_legacy_paths/"
                "version_legacy_paths/sheets/S001.csv",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO excel_upload_tasks
              (
                task_id, user_id, original_filename, staging_path,
                replace_existing, status, result_json, created_at, updated_at
              )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload_legacy_paths",
                "user_admin",
                "legacy.xlsx",
                "/old/root/excel_workspace/storage/upload-tasks/"
                "upload_legacy_paths/legacy.xlsx",
                0,
                "queued",
                "{}",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = 13"
        )

    repository.initialize()

    with sqlite3.connect(database_path) as connection:
        raw_csv_path = connection.execute(
            "SELECT raw_csv_path FROM excel_sheets WHERE sheet_id = ?",
            ("sheet_legacy_paths",),
        ).fetchone()[0]
        artifact_path = connection.execute(
            "SELECT path FROM excel_artifacts WHERE artifact_id = ?",
            ("artifact_legacy_paths",),
        ).fetchone()[0]
        staging_path = connection.execute(
            "SELECT staging_path FROM excel_upload_tasks WHERE task_id = ?",
            ("upload_legacy_paths",),
        ).fetchone()[0]

    assert raw_csv_path == (
        "files/file_legacy_paths/version_legacy_paths/sheets/S001.csv"
    )
    assert artifact_path == (
        "files/file_legacy_paths/version_legacy_paths/sheets/S001.csv"
    )
    assert staging_path == "upload-tasks/upload_legacy_paths/legacy.xlsx"


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
        "pdf_summary_tasks": 0,
        "pdf_file_cleanup_jobs": 0,
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


def test_relative_runtime_paths_are_project_root_relative() -> None:
    settings = Settings(
        _env_file=None,
        excel_database_path="runtime/excel.sqlite3",
        excel_storage_root="runtime/storage",
        log_file_path="runtime/logs/backend.log",
    )

    assert settings.database_path == settings.workspace_root / "runtime/excel.sqlite3"
    assert settings.storage_root == settings.workspace_root / "runtime/storage"
    assert settings.log_path == settings.workspace_root / "runtime/logs/backend.log"


def test_relative_runtime_paths_cannot_escape_project_root() -> None:
    settings = Settings(
        _env_file=None,
        excel_database_path="../escape/excel.sqlite3",
    )

    with pytest.raises(ValueError, match="relative runtime path"):
        _ = settings.database_path


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
