import sqlite3
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Protocol

from app.core.ids import new_id
from app.domain.models import (
    PdfVectorIndex,
    PdfVectorIndexStatus,
    PdfVectorIndexTask,
    PdfVectorIndexTaskAction,
    PdfVectorIndexTaskStatus,
)
from app.ports.pdf_vector_index import PdfVectorQueueInspection


class _SQLiteConnectionOwner(Protocol):
    def _connect(self) -> sqlite3.Connection:
        ...


class _VectorTaskPublicationRejected(Exception):
    """Rollback sentinel for a fenced vector task publication."""


class SQLitePdfVectorIndexRepositoryMixin:
    def inspect_pdf_vector_queue(
        self: _SQLiteConnectionOwner,
    ) -> PdfVectorQueueInspection:
        from app.core.time import utc_now_iso

        inspected_at = utc_now_iso()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                  SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
                  SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running_count,
                  SUM(CASE WHEN status = 'retry_wait' THEN 1 ELSE 0 END)
                    AS retry_wait_count,
                  SUM(CASE WHEN status = 'dead_letter' THEN 1 ELSE 0 END)
                    AS dead_letter_count,
                  SUM(CASE
                    WHEN status = 'running' AND lease_expires_at < ? THEN 1 ELSE 0
                  END) AS expired_running_count,
                  SUM(CASE
                    WHEN status = 'retry_wait' AND next_attempt_at <= ? THEN 1 ELSE 0
                  END) AS due_retry_count,
                  MIN(CASE
                    WHEN status IN ('pending', 'running', 'retry_wait')
                    THEN created_at ELSE NULL
                  END) AS oldest_active_at
                FROM pdf_vector_index_tasks
                """,
                (inspected_at, inspected_at),
            ).fetchone()
        if row is None:
            raise RuntimeError("PDF vector queue inspection returned no aggregate")
        return PdfVectorQueueInspection(
            pending_count=int(row["pending_count"] or 0),
            running_count=int(row["running_count"] or 0),
            retry_wait_count=int(row["retry_wait_count"] or 0),
            dead_letter_count=int(row["dead_letter_count"] or 0),
            expired_running_count=int(row["expired_running_count"] or 0),
            due_retry_count=int(row["due_retry_count"] or 0),
            oldest_active_at=(
                str(row["oldest_active_at"])
                if row["oldest_active_at"] is not None
                else None
            ),
        )

    def get_pdf_vector_index(
        self: _SQLiteConnectionOwner,
        file_id: str,
    ) -> PdfVectorIndex | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pdf_vector_indexes WHERE file_id = ?",
                (file_id,),
            ).fetchone()
        return _to_pdf_vector_index(row)

    def get_pdf_vector_index_task(
        self: _SQLiteConnectionOwner,
        task_id: str,
    ) -> PdfVectorIndexTask | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pdf_vector_index_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return _to_pdf_vector_index_task(row)

    def queue_pdf_vector_index(
        self: _SQLiteConnectionOwner,
        *,
        index: PdfVectorIndex,
        task: PdfVectorIndexTask,
    ) -> PdfVectorIndexTask:
        with self._connect() as connection:
            return queue_pdf_vector_index_on_connection(
                connection,
                index=index,
                task=task,
            )

    def queue_pdf_vector_delete(
        self: _SQLiteConnectionOwner,
        *,
        task: PdfVectorIndexTask,
    ) -> PdfVectorIndexTask:
        with self._connect() as connection:
            return queue_pdf_vector_delete_on_connection(connection, task=task)

    def reconcile_pdf_vector_index_queue(
        self: _SQLiteConnectionOwner,
        *,
        embedding_revision: str,
        embedding_dimension: int,
        batch_size: int,
        queued_at: str,
        force: bool = False,
    ) -> int:
        revision = embedding_revision.strip()
        if not revision:
            raise ValueError("vector reconciliation requires an embedding revision")
        if embedding_dimension < 1:
            raise ValueError("vector reconciliation dimension must be positive")
        if batch_size < 1:
            raise ValueError("vector reconciliation batch size must be positive")
        with self._connect() as connection:
            rows = connection.execute(
                """
                WITH chunk_counts AS (
                  SELECT file_id, COUNT(*) AS chunk_count
                  FROM pdf_document_chunks
                  GROUP BY file_id
                )
                SELECT
                  file.file_id,
                  file.content_fingerprint,
                  chunk_counts.chunk_count
                FROM pdf_files AS file
                JOIN chunk_counts ON chunk_counts.file_id = file.file_id
                LEFT JOIN pdf_vector_indexes AS vector_index
                  ON vector_index.file_id = file.file_id
                WHERE file.status = 'active'
                  AND file.kind != 'folder'
                  AND file.processing_status IN ('ready', 'partial')
                  AND file.content_fingerprint IS NOT NULL
                  AND file.content_fingerprint != ''
                  AND NOT EXISTS (
                    SELECT 1
                    FROM pdf_vector_index_tasks AS active_task
                    WHERE active_task.file_id = file.file_id
                      AND active_task.status IN ('pending', 'running', 'retry_wait')
                  )
                  AND (
                    ? = 1
                    OR (
                      NOT COALESCE((
                        vector_index.status = 'ready'
                        AND vector_index.source_fingerprint = file.content_fingerprint
                        AND vector_index.embedding_revision = ?
                        AND vector_index.embedding_dimension = ?
                        AND vector_index.expected_chunk_count = chunk_counts.chunk_count
                        AND vector_index.indexed_chunk_count = chunk_counts.chunk_count
                      ), 0)
                      AND NOT EXISTS (
                        SELECT 1
                        FROM pdf_vector_index_tasks AS terminal_task
                        WHERE terminal_task.file_id = file.file_id
                          AND terminal_task.action = 'index'
                          AND terminal_task.status = 'dead_letter'
                          AND terminal_task.source_fingerprint = file.content_fingerprint
                          AND terminal_task.embedding_revision = ?
                          AND terminal_task.generation = vector_index.generation
                      )
                    )
                  )
                ORDER BY file.updated_at ASC, file.file_id ASC
                LIMIT ?
                """,
                (int(force), revision, embedding_dimension, revision, batch_size),
            ).fetchall()
            queued_count = 0
            for row in rows:
                file_id = str(row["file_id"])
                source_fingerprint = str(row["content_fingerprint"])
                chunk_count = int(row["chunk_count"])
                queue_pdf_vector_index_on_connection(
                    connection,
                    index=PdfVectorIndex(
                        file_id=file_id,
                        source_fingerprint=source_fingerprint,
                        embedding_revision=revision,
                        embedding_dimension=embedding_dimension,
                        status=PdfVectorIndexStatus.PENDING,
                        expected_chunk_count=chunk_count,
                        indexed_chunk_count=0,
                        created_at=queued_at,
                        updated_at=queued_at,
                    ),
                    task=PdfVectorIndexTask(
                        task_id=new_id("pdfvector"),
                        file_id=file_id,
                        action=PdfVectorIndexTaskAction.INDEX,
                        source_fingerprint=source_fingerprint,
                        embedding_revision=revision,
                        status=PdfVectorIndexTaskStatus.PENDING,
                        attempt_count=0,
                        created_at=queued_at,
                        updated_at=queued_at,
                    ),
                )
                queued_count += 1
        return queued_count

    def claim_next_pdf_vector_index_task(
        self: _SQLiteConnectionOwner,
        *,
        worker_id: str,
        started_at: str,
        lease_expires_at: str,
        max_attempts: int = 20,
    ) -> PdfVectorIndexTask | None:
        if max_attempts < 1:
            raise ValueError("vector task max attempts must be positive")
        claim_token = new_id("pdfvectorclaim")
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                """
                UPDATE pdf_vector_index_tasks
                SET status = 'running',
                    worker_id = ?,
                    claim_token = ?,
                    lease_expires_at = ?,
                    heartbeat_at = ?,
                    started_at = COALESCE(started_at, ?),
                    updated_at = ?,
                    attempt_count = attempt_count + 1,
                    error_message = NULL,
                    error_code = NULL,
                    finished_at = NULL,
                    next_attempt_at = NULL,
                    state_revision = state_revision + 1
                WHERE task_id = (
                  SELECT task_id
                  FROM pdf_vector_index_tasks
                  WHERE attempt_count < ?
                    AND (
                      status = 'pending'
                      OR (
                        status = 'retry_wait'
                        AND next_attempt_at <= ?
                      )
                      OR (
                        status = 'running'
                        AND lease_expires_at IS NOT NULL
                        AND lease_expires_at < ?
                      )
                    )
                  ORDER BY created_at ASC, task_id ASC
                  LIMIT 1
                )
                """,
                (
                    worker_id,
                    claim_token,
                    lease_expires_at,
                    started_at,
                    started_at,
                    started_at,
                    max_attempts,
                    started_at,
                    started_at,
                ),
            )
                if cursor.rowcount == 0:
                    return None
                row = connection.execute(
                    "SELECT * FROM pdf_vector_index_tasks WHERE claim_token = ?",
                    (claim_token,),
                ).fetchone()
                task = _to_pdf_vector_index_task(row)
                if task is None:
                    raise RuntimeError("claimed PDF vector task was not found")
                if task.action is PdfVectorIndexTaskAction.INDEX:
                    index_cursor = connection.execute(
                    """
                    UPDATE pdf_vector_indexes
                    SET status = 'running',
                        last_error = NULL,
                        updated_at = ?,
                        state_revision = state_revision + 1
                    WHERE file_id = ?
                      AND source_fingerprint = ?
                      AND embedding_revision = ?
                      AND generation = ?
                      AND status IN ('pending', 'running', 'failed')
                    """,
                    (
                        started_at,
                        task.file_id,
                        task.source_fingerprint,
                        task.embedding_revision,
                        task.generation,
                    ),
                )
                    if index_cursor.rowcount == 0:
                        raise _VectorTaskPublicationRejected
        except _VectorTaskPublicationRejected:
            return None
        return task

    def heartbeat_pdf_vector_index_task(
        self: _SQLiteConnectionOwner,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        heartbeat_at: str,
        lease_expires_at: str,
    ) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE pdf_vector_index_tasks
                SET heartbeat_at = ?,
                    lease_expires_at = ?,
                    updated_at = ?,
                    state_revision = state_revision + 1
                WHERE task_id = ?
                  AND status = 'running'
                  AND worker_id = ?
                  AND claim_token = ?
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at >= ?
                """,
                (
                    heartbeat_at,
                    lease_expires_at,
                    heartbeat_at,
                    task_id,
                    worker_id,
                    claim_token,
                    heartbeat_at,
                ),
            )
        return cursor.rowcount == 1

    def complete_pdf_vector_index_task(
        self: _SQLiteConnectionOwner,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        indexed_chunk_count: int,
        completed_at: str,
    ) -> PdfVectorIndexTask | None:
        if indexed_chunk_count < 0:
            raise ValueError("indexed chunk count must not be negative")
        try:
            with self._connect() as connection:
                task = _claimed_task(
                    connection,
                    task_id=task_id,
                    worker_id=worker_id,
                    claim_token=claim_token,
                    checked_at=completed_at,
                    action=PdfVectorIndexTaskAction.INDEX,
                )
                if task is None:
                    raise _VectorTaskPublicationRejected
                index_cursor = connection.execute(
                    """
                    UPDATE pdf_vector_indexes
                    SET status = 'ready',
                        indexed_chunk_count = ?,
                        last_error = NULL,
                        updated_at = ?,
                        ready_at = ?,
                        state_revision = state_revision + 1
                    WHERE file_id = ?
                      AND source_fingerprint = ?
                      AND embedding_revision = ?
                      AND generation = ?
                      AND status = 'running'
                      AND expected_chunk_count = ?
                    """,
                    (
                        indexed_chunk_count,
                        completed_at,
                        completed_at,
                        task.file_id,
                        task.source_fingerprint,
                        task.embedding_revision,
                        task.generation,
                        indexed_chunk_count,
                    ),
                )
                if index_cursor.rowcount == 0:
                    raise _VectorTaskPublicationRejected
                _complete_task(
                    connection,
                    task_id=task_id,
                    worker_id=worker_id,
                    claim_token=claim_token,
                    completed_at=completed_at,
                )
                row = connection.execute(
                    "SELECT * FROM pdf_vector_index_tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
        except _VectorTaskPublicationRejected:
            return None
        return _to_pdf_vector_index_task(row)

    def complete_pdf_vector_delete_task(
        self: _SQLiteConnectionOwner,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        completed_at: str,
    ) -> PdfVectorIndexTask | None:
        try:
            with self._connect() as connection:
                task = _claimed_task(
                    connection,
                    task_id=task_id,
                    worker_id=worker_id,
                    claim_token=claim_token,
                    checked_at=completed_at,
                    action=PdfVectorIndexTaskAction.DELETE,
                )
                if task is None:
                    raise _VectorTaskPublicationRejected
                connection.execute(
                    """
                    DELETE FROM pdf_vector_indexes
                    WHERE file_id = ? AND generation <= ?
                    """,
                    (task.file_id, task.generation),
                )
                _complete_task(
                    connection,
                    task_id=task_id,
                    worker_id=worker_id,
                    claim_token=claim_token,
                    completed_at=completed_at,
                )
                row = connection.execute(
                    "SELECT * FROM pdf_vector_index_tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
        except _VectorTaskPublicationRejected:
            return None
        return _to_pdf_vector_index_task(row)

    def fail_pdf_vector_index_task(
        self: _SQLiteConnectionOwner,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        error_message: str,
        error_code: str,
        retryable: bool,
        failed_at: str,
        max_attempts: int = 20,
        retry_max_seconds: int = 900,
        retry_after_seconds: int | None = None,
    ) -> PdfVectorIndexTask | None:
        if max_attempts < 1:
            raise ValueError("vector task max attempts must be positive")
        if retry_max_seconds < 1:
            raise ValueError("vector task retry maximum must be positive")
        if retry_after_seconds is not None and retry_after_seconds < 0:
            raise ValueError("vector task retry-after must not be negative")
        normalized_error_code = error_code.strip()[:100]
        if not normalized_error_code:
            raise ValueError("vector task failure requires an error code")
        with self._connect() as connection:
            task = _claimed_task(
                connection,
                task_id=task_id,
                worker_id=worker_id,
                claim_token=claim_token,
                checked_at=failed_at,
            )
            if task is None:
                return None
            will_retry = retryable and task.attempt_count < max_attempts
            next_attempt_at = (
                _next_attempt_at(
                    failed_at,
                    task_id=task.task_id,
                    attempt_count=task.attempt_count,
                    retry_max_seconds=retry_max_seconds,
                    retry_after_seconds=retry_after_seconds,
                )
                if will_retry
                else None
            )
            cursor = connection.execute(
                """
                UPDATE pdf_vector_index_tasks
                SET status = ?,
                    error_message = ?,
                    error_code = ?,
                    updated_at = ?,
                    finished_at = ?,
                    next_attempt_at = ?,
                    worker_id = NULL,
                    claim_token = NULL,
                    lease_expires_at = NULL,
                    heartbeat_at = NULL,
                    state_revision = state_revision + 1
                WHERE task_id = ?
                  AND status = 'running'
                  AND worker_id = ?
                  AND claim_token = ?
                """,
                (
                    (
                        PdfVectorIndexTaskStatus.RETRY_WAIT.value
                        if will_retry
                        else PdfVectorIndexTaskStatus.DEAD_LETTER.value
                    ),
                    error_message[:1000],
                    normalized_error_code,
                    failed_at,
                    None if will_retry else failed_at,
                    next_attempt_at,
                    task_id,
                    worker_id,
                    claim_token,
                ),
            )
            if cursor.rowcount == 0:
                return None
            if task.action is PdfVectorIndexTaskAction.INDEX:
                connection.execute(
                    """
                    UPDATE pdf_vector_indexes
                    SET status = 'failed',
                        last_error = ?,
                        updated_at = ?,
                        state_revision = state_revision + 1
                    WHERE file_id = ?
                      AND source_fingerprint = ?
                      AND embedding_revision = ?
                      AND generation = ?
                      AND status = 'running'
                    """,
                    (
                        error_message[:1000],
                        failed_at,
                        task.file_id,
                        task.source_fingerprint,
                        task.embedding_revision,
                        task.generation,
                    ),
                )
            row = connection.execute(
                "SELECT * FROM pdf_vector_index_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return _to_pdf_vector_index_task(row)

    def requeue_pdf_vector_dead_letter_task(
        self: _SQLiteConnectionOwner,
        *,
        task_id: str,
        requeued_at: str,
    ) -> PdfVectorIndexTask | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM pdf_vector_index_tasks
                WHERE task_id = ? AND status = 'dead_letter'
                """,
                (task_id,),
            ).fetchone()
            dead_letter = _to_pdf_vector_index_task(row)
            if dead_letter is None:
                return None
            if _active_task_for_file(connection, dead_letter.file_id) is not None:
                return None
            if dead_letter.action is PdfVectorIndexTaskAction.INDEX:
                current_projection = connection.execute(
                    """
                    SELECT 1
                    FROM pdf_vector_indexes AS vector_index
                    JOIN pdf_files AS file ON file.file_id = vector_index.file_id
                    WHERE vector_index.file_id = ?
                      AND vector_index.source_fingerprint = ?
                      AND vector_index.embedding_revision = ?
                      AND vector_index.generation = ?
                      AND vector_index.status = 'failed'
                      AND file.status = 'active'
                    """,
                    (
                        dead_letter.file_id,
                        dead_letter.source_fingerprint,
                        dead_letter.embedding_revision,
                        dead_letter.generation,
                    ),
                ).fetchone()
                if current_projection is None:
                    return None
                connection.execute(
                    """
                    UPDATE pdf_vector_indexes
                    SET status = 'pending',
                        indexed_chunk_count = 0,
                        last_error = NULL,
                        updated_at = ?,
                        ready_at = NULL,
                        state_revision = state_revision + 1
                    WHERE file_id = ?
                    """,
                    (requeued_at, dead_letter.file_id),
                )
            requeued = PdfVectorIndexTask(
                task_id=new_id("pdfvector"),
                file_id=dead_letter.file_id,
                action=dead_letter.action,
                source_fingerprint=dead_letter.source_fingerprint,
                embedding_revision=dead_letter.embedding_revision,
                status=PdfVectorIndexTaskStatus.PENDING,
                attempt_count=0,
                created_at=requeued_at,
                updated_at=requeued_at,
                parent_task_id=dead_letter.task_id,
                generation=dead_letter.generation,
            )
            _insert_task(connection, requeued, generation=dead_letter.generation)
            row = connection.execute(
                "SELECT * FROM pdf_vector_index_tasks WHERE task_id = ?",
                (requeued.task_id,),
            ).fetchone()
        return _to_pdf_vector_index_task(row)


def _validate_index_queue_input(
    *,
    index: PdfVectorIndex,
    task: PdfVectorIndexTask,
) -> None:
    if task.action is not PdfVectorIndexTaskAction.INDEX:
        raise ValueError("vector index queue requires an index task")
    if task.status is not PdfVectorIndexTaskStatus.PENDING:
        raise ValueError("vector index task must be pending")
    if index.status is not PdfVectorIndexStatus.PENDING:
        raise ValueError("vector index state must be pending")
    if task.file_id != index.file_id:
        raise ValueError("vector index task file does not match index state")
    if task.source_fingerprint != index.source_fingerprint:
        raise ValueError("vector index task fingerprint does not match index state")
    if task.embedding_revision != index.embedding_revision:
        raise ValueError("vector index task revision does not match index state")
    if index.indexed_chunk_count != 0:
        raise ValueError("pending vector index must not contain indexed chunks")


def _next_attempt_at(
    failed_at: str,
    *,
    task_id: str,
    attempt_count: int,
    retry_max_seconds: int,
    retry_after_seconds: int | None,
) -> str:
    failed_datetime = datetime.fromisoformat(failed_at)
    exponential_delay = min(
        retry_max_seconds,
        2 ** min(max(1, attempt_count), 20),
    )
    jitter_seed = sha256(f"{task_id}:{attempt_count}".encode()).digest()
    jitter_factor = 0.8 + (int.from_bytes(jitter_seed[:2], "big") / 65535) * 0.4
    jittered_delay = max(1, round(exponential_delay * jitter_factor))
    delay_seconds = max(jittered_delay, retry_after_seconds or 0)
    return (failed_datetime + timedelta(seconds=delay_seconds)).isoformat(
        timespec="seconds"
    )


def queue_pdf_vector_index_on_connection(
    connection: sqlite3.Connection,
    *,
    index: PdfVectorIndex,
    task: PdfVectorIndexTask,
) -> PdfVectorIndexTask:
    """Queue a vector projection inside an existing business transaction."""
    _validate_index_queue_input(index=index, task=task)
    existing = _active_task_for_file(connection, task.file_id)
    if existing is not None and _same_task_projection(existing, task):
        return existing
    _cancel_active_tasks(connection, file_id=task.file_id, cancelled_at=task.updated_at)
    generation = _reserve_projection_generation(
        connection,
        file_id=task.file_id,
        tombstoned=False,
        updated_at=task.updated_at,
    )
    connection.execute(
        """
        INSERT INTO pdf_vector_indexes
          (
            file_id, source_fingerprint, embedding_revision,
            embedding_dimension, status, expected_chunk_count,
            indexed_chunk_count, last_error, created_at, updated_at,
            ready_at, state_revision, generation
          )
        VALUES (?, ?, ?, ?, 'pending', ?, 0, NULL, ?, ?, NULL, 0, ?)
        ON CONFLICT(file_id) DO UPDATE SET
          source_fingerprint = excluded.source_fingerprint,
          embedding_revision = excluded.embedding_revision,
          embedding_dimension = excluded.embedding_dimension,
          status = 'pending',
          expected_chunk_count = excluded.expected_chunk_count,
          indexed_chunk_count = 0,
          last_error = NULL,
          updated_at = excluded.updated_at,
          ready_at = NULL,
          state_revision = pdf_vector_indexes.state_revision + 1,
          generation = excluded.generation
        """,
        (
            index.file_id,
            index.source_fingerprint,
            index.embedding_revision,
            index.embedding_dimension,
            index.expected_chunk_count,
            index.created_at,
            index.updated_at,
            generation,
        ),
    )
    _insert_task(connection, task, generation=generation)
    row = connection.execute(
        "SELECT * FROM pdf_vector_index_tasks WHERE task_id = ?",
        (task.task_id,),
    ).fetchone()
    queued = _to_pdf_vector_index_task(row)
    if queued is None:
        raise RuntimeError("queued PDF vector task was not found")
    return queued


def queue_pdf_vector_delete_on_connection(
    connection: sqlite3.Connection,
    *,
    task: PdfVectorIndexTask,
) -> PdfVectorIndexTask:
    """Queue deletion of a derived vector projection inside a file transaction."""
    if task.action is not PdfVectorIndexTaskAction.DELETE:
        raise ValueError("vector delete queue requires a delete task")
    if task.status is not PdfVectorIndexTaskStatus.PENDING:
        raise ValueError("vector delete task must be pending")
    existing = _active_task_for_file(connection, task.file_id)
    if existing is not None and _same_task_projection(existing, task):
        return existing
    _cancel_active_tasks(connection, file_id=task.file_id, cancelled_at=task.updated_at)
    generation = _reserve_projection_generation(
        connection,
        file_id=task.file_id,
        tombstoned=True,
        updated_at=task.updated_at,
    )
    _insert_task(connection, task, generation=generation)
    row = connection.execute(
        "SELECT * FROM pdf_vector_index_tasks WHERE task_id = ?",
        (task.task_id,),
    ).fetchone()
    queued = _to_pdf_vector_index_task(row)
    if queued is None:
        raise RuntimeError("queued PDF vector delete task was not found")
    return queued


def _insert_task(
    connection: sqlite3.Connection,
    task: PdfVectorIndexTask,
    *,
    generation: int,
) -> None:
    connection.execute(
        """
        INSERT INTO pdf_vector_index_tasks
          (
            task_id, file_id, action, source_fingerprint, embedding_revision,
            status, attempt_count, error_message, error_code, created_at, updated_at,
            started_at, finished_at, worker_id, claim_token, lease_expires_at,
            heartbeat_at, next_attempt_at, parent_task_id, state_revision,
            generation
          )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task.task_id,
            task.file_id,
            task.action.value,
            task.source_fingerprint,
            task.embedding_revision,
            task.status.value,
            task.attempt_count,
            task.error_message,
            task.error_code,
            task.created_at,
            task.updated_at,
            task.started_at,
            task.finished_at,
            task.worker_id,
            task.claim_token,
            task.lease_expires_at,
            task.heartbeat_at,
            task.next_attempt_at,
            task.parent_task_id,
            task.state_revision,
            generation,
        ),
    )


def _reserve_projection_generation(
    connection: sqlite3.Connection,
    *,
    file_id: str,
    tombstoned: bool,
    updated_at: str,
) -> int:
    row = connection.execute(
        """
        INSERT INTO pdf_vector_projection_epochs (
          file_id, current_generation, tombstoned, updated_at
        )
        VALUES (?, 1, ?, ?)
        ON CONFLICT(file_id) DO UPDATE SET
          current_generation = pdf_vector_projection_epochs.current_generation + 1,
          tombstoned = excluded.tombstoned,
          updated_at = excluded.updated_at
        RETURNING current_generation
        """,
        (file_id, int(tombstoned), updated_at),
    ).fetchone()
    if row is None:
        raise RuntimeError("PDF vector projection generation was not reserved")
    return int(row["current_generation"])


def _active_task_for_file(
    connection: sqlite3.Connection,
    file_id: str,
) -> PdfVectorIndexTask | None:
    row = connection.execute(
        """
        SELECT * FROM pdf_vector_index_tasks
        WHERE file_id = ? AND status IN ('pending', 'running', 'retry_wait')
        ORDER BY created_at DESC, task_id DESC
        LIMIT 1
        """,
        (file_id,),
    ).fetchone()
    return _to_pdf_vector_index_task(row)


def _same_task_projection(
    left: PdfVectorIndexTask,
    right: PdfVectorIndexTask,
) -> bool:
    return (
        left.file_id == right.file_id
        and left.action is right.action
        and left.source_fingerprint == right.source_fingerprint
        and left.embedding_revision == right.embedding_revision
    )


def _cancel_active_tasks(
    connection: sqlite3.Connection,
    *,
    file_id: str,
    cancelled_at: str,
) -> None:
    connection.execute(
        """
        UPDATE pdf_vector_index_tasks
        SET status = 'cancelled',
            error_message = 'Superseded by a newer vector index operation.',
            error_code = 'SUPERSEDED',
            updated_at = ?,
            finished_at = ?,
            worker_id = NULL,
            claim_token = NULL,
            lease_expires_at = NULL,
            heartbeat_at = NULL,
            next_attempt_at = NULL,
            state_revision = state_revision + 1
        WHERE file_id = ? AND status IN ('pending', 'running', 'retry_wait')
        """,
        (cancelled_at, cancelled_at, file_id),
    )


def _claimed_task(
    connection: sqlite3.Connection,
    *,
    task_id: str,
    worker_id: str,
    claim_token: str,
    checked_at: str,
    action: PdfVectorIndexTaskAction | None = None,
) -> PdfVectorIndexTask | None:
    row = connection.execute(
        """
        SELECT * FROM pdf_vector_index_tasks
        WHERE task_id = ?
          AND status = 'running'
          AND worker_id = ?
          AND claim_token = ?
          AND lease_expires_at IS NOT NULL
          AND lease_expires_at >= ?
        """,
        (task_id, worker_id, claim_token, checked_at),
    ).fetchone()
    task = _to_pdf_vector_index_task(row)
    if task is None or (action is not None and task.action is not action):
        return None
    return task


def _complete_task(
    connection: sqlite3.Connection,
    *,
    task_id: str,
    worker_id: str,
    claim_token: str,
    completed_at: str,
) -> None:
    cursor = connection.execute(
        """
        UPDATE pdf_vector_index_tasks
        SET status = 'succeeded',
            error_message = NULL,
            error_code = NULL,
            updated_at = ?,
            finished_at = ?,
            worker_id = NULL,
            claim_token = NULL,
            lease_expires_at = NULL,
            heartbeat_at = NULL,
            next_attempt_at = NULL,
            state_revision = state_revision + 1
        WHERE task_id = ?
          AND status = 'running'
          AND worker_id = ?
          AND claim_token = ?
        """,
        (completed_at, completed_at, task_id, worker_id, claim_token),
    )
    if cursor.rowcount == 0:
        raise _VectorTaskPublicationRejected


def _to_pdf_vector_index(row: sqlite3.Row | None) -> PdfVectorIndex | None:
    if row is None:
        return None
    return PdfVectorIndex(
        file_id=str(row["file_id"]),
        source_fingerprint=str(row["source_fingerprint"]),
        embedding_revision=str(row["embedding_revision"]),
        embedding_dimension=int(row["embedding_dimension"]),
        status=PdfVectorIndexStatus(str(row["status"])),
        expected_chunk_count=int(row["expected_chunk_count"]),
        indexed_chunk_count=int(row["indexed_chunk_count"]),
        last_error=(str(row["last_error"]) if row["last_error"] is not None else None),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        ready_at=(str(row["ready_at"]) if row["ready_at"] is not None else None),
        state_revision=int(row["state_revision"]),
        generation=int(row["generation"]),
    )


def _to_pdf_vector_index_task(
    row: sqlite3.Row | None,
) -> PdfVectorIndexTask | None:
    if row is None:
        return None
    return PdfVectorIndexTask(
        task_id=str(row["task_id"]),
        file_id=str(row["file_id"]),
        action=PdfVectorIndexTaskAction(str(row["action"])),
        source_fingerprint=str(row["source_fingerprint"]),
        embedding_revision=str(row["embedding_revision"]),
        status=PdfVectorIndexTaskStatus(str(row["status"])),
        attempt_count=int(row["attempt_count"]),
        error_message=(
            str(row["error_message"])
            if row["error_message"] is not None
            else None
        ),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        started_at=(str(row["started_at"]) if row["started_at"] is not None else None),
        finished_at=(
            str(row["finished_at"]) if row["finished_at"] is not None else None
        ),
        worker_id=(str(row["worker_id"]) if row["worker_id"] is not None else None),
        claim_token=(
            str(row["claim_token"]) if row["claim_token"] is not None else None
        ),
        lease_expires_at=(
            str(row["lease_expires_at"])
            if row["lease_expires_at"] is not None
            else None
        ),
        heartbeat_at=(
            str(row["heartbeat_at"]) if row["heartbeat_at"] is not None else None
        ),
        next_attempt_at=(
            str(row["next_attempt_at"])
            if row["next_attempt_at"] is not None
            else None
        ),
        error_code=(
            str(row["error_code"]) if row["error_code"] is not None else None
        ),
        parent_task_id=(
            str(row["parent_task_id"])
            if row["parent_task_id"] is not None
            else None
        ),
        state_revision=int(row["state_revision"]),
        generation=int(row["generation"]),
    )
