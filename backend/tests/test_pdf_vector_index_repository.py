from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.adapters.llm.fake_llm_client import FakeLlmClient
from app.adapters.pdf import FakePdfParser
from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.application.pdf_knowledge import PdfKnowledgeService, PdfUploadTaskWorker
from app.domain.models import (
    PdfDocumentChunk,
    PdfFile,
    PdfFileKind,
    PdfFileStatus,
    PdfFileVisibility,
    PdfProcessingStatus,
    PdfVectorIndex,
    PdfVectorIndexStatus,
    PdfVectorIndexTask,
    PdfVectorIndexTaskAction,
    PdfVectorIndexTaskStatus,
)
from app.ports.pdf_parser import PdfParserRuntimeStatus

BASE_TIME = "2026-08-14T00:00:00+00:00"


def repository_with_file(tmp_path: Path) -> SQLiteExcelAssetRepository:
    repository = SQLiteExcelAssetRepository(tmp_path / "pdf-vector.sqlite3")
    repository.initialize()
    repository.create_pdf_file(
        PdfFile(
            file_id="file-1",
            user_id="user-1",
            parent_id=None,
            display_name="file-1.pdf",
            original_filename="file-1.pdf",
            kind=PdfFileKind.PDF,
            size_bytes=100,
            storage_path="pdf-knowledge/files/file-1/file-1.pdf",
            status=PdfFileStatus.ACTIVE,
            visibility=PdfFileVisibility.VISIBLE,
            processing_status=PdfProcessingStatus.READY,
            progress=100,
            status_detail="Ready.",
            error_message=None,
            page_count=1,
            chunk_count=2,
            created_at=BASE_TIME,
            updated_at=BASE_TIME,
            content_fingerprint="fingerprint-1",
        )
    )
    return repository


def pending_index(
    *,
    fingerprint: str = "fingerprint-1",
    revision: str = "embedding-1",
    chunk_count: int = 2,
) -> PdfVectorIndex:
    return PdfVectorIndex(
        file_id="file-1",
        source_fingerprint=fingerprint,
        embedding_revision=revision,
        embedding_dimension=4096,
        status=PdfVectorIndexStatus.PENDING,
        expected_chunk_count=chunk_count,
        indexed_chunk_count=0,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def pending_task(
    task_id: str,
    *,
    action: PdfVectorIndexTaskAction = PdfVectorIndexTaskAction.INDEX,
    fingerprint: str = "fingerprint-1",
    revision: str = "embedding-1",
    updated_at: str = BASE_TIME,
    attempt_count: int = 0,
) -> PdfVectorIndexTask:
    return PdfVectorIndexTask(
        task_id=task_id,
        file_id="file-1",
        action=action,
        source_fingerprint=fingerprint,
        embedding_revision=revision,
        status=PdfVectorIndexTaskStatus.PENDING,
        attempt_count=attempt_count,
        created_at=updated_at,
        updated_at=updated_at,
    )


def test_vector_index_task_claim_and_completion_publish_ready_state(
    tmp_path: Path,
) -> None:
    repository = repository_with_file(tmp_path)
    queued = repository.queue_pdf_vector_index(
        index=pending_index(),
        task=pending_task("task-1"),
    )

    claimed = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-1",
        started_at="2026-08-14T00:01:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )

    assert queued.status is PdfVectorIndexTaskStatus.PENDING
    assert queued.generation == 1
    assert claimed is not None
    assert claimed.status is PdfVectorIndexTaskStatus.RUNNING
    assert claimed.claim_token
    assert claimed.attempt_count == 1
    running_index = repository.get_pdf_vector_index("file-1")
    assert running_index is not None
    assert running_index.status is PdfVectorIndexStatus.RUNNING
    assert running_index.generation == claimed.generation == 1

    completed = repository.complete_pdf_vector_index_task(
        task_id=claimed.task_id,
        worker_id="worker-1",
        claim_token=claimed.claim_token or "",
        indexed_chunk_count=2,
        completed_at="2026-08-14T00:02:00+00:00",
    )

    assert completed is not None
    assert completed.status is PdfVectorIndexTaskStatus.SUCCEEDED
    ready_index = repository.get_pdf_vector_index("file-1")
    assert ready_index is not None
    assert ready_index.status is PdfVectorIndexStatus.READY
    assert ready_index.indexed_chunk_count == ready_index.expected_chunk_count == 2
    assert ready_index.ready_at == "2026-08-14T00:02:00+00:00"


def test_vector_index_completion_count_mismatch_rolls_back_both_states(
    tmp_path: Path,
) -> None:
    repository = repository_with_file(tmp_path)
    repository.queue_pdf_vector_index(
        index=pending_index(chunk_count=2),
        task=pending_task("task-1"),
    )
    claimed = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-1",
        started_at="2026-08-14T00:01:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )
    assert claimed is not None and claimed.claim_token

    completed = repository.complete_pdf_vector_index_task(
        task_id=claimed.task_id,
        worker_id="worker-1",
        claim_token=claimed.claim_token,
        indexed_chunk_count=1,
        completed_at="2026-08-14T00:02:00+00:00",
    )

    assert completed is None
    unchanged_task = repository.get_pdf_vector_index_task(claimed.task_id)
    unchanged_index = repository.get_pdf_vector_index("file-1")
    assert unchanged_task is not None
    assert unchanged_task.status is PdfVectorIndexTaskStatus.RUNNING
    assert unchanged_index is not None
    assert unchanged_index.status is PdfVectorIndexStatus.RUNNING
    assert unchanged_index.indexed_chunk_count == 0


def test_new_projection_cancels_an_older_active_task(tmp_path: Path) -> None:
    repository = repository_with_file(tmp_path)
    repository.queue_pdf_vector_index(
        index=pending_index(),
        task=pending_task("task-old"),
    )

    queued = repository.queue_pdf_vector_index(
        index=pending_index(fingerprint="fingerprint-2"),
        task=pending_task(
            "task-new",
            fingerprint="fingerprint-2",
            updated_at="2026-08-14T00:03:00+00:00",
        ),
    )

    old_task = repository.get_pdf_vector_index_task("task-old")
    assert old_task is not None
    assert old_task.status is PdfVectorIndexTaskStatus.CANCELLED
    assert queued.task_id == "task-new"
    assert queued.generation == 2
    current_index = repository.get_pdf_vector_index("file-1")
    assert current_index is not None
    assert current_index.source_fingerprint == "fingerprint-2"
    assert current_index.status is PdfVectorIndexStatus.PENDING
    assert current_index.generation == queued.generation


def test_concurrent_projection_publications_serialize_generations(
    tmp_path: Path,
) -> None:
    repository = repository_with_file(tmp_path)

    def queue_projection(index: int) -> PdfVectorIndexTask:
        fingerprint = f"fingerprint-{index}"
        return repository.queue_pdf_vector_index(
            index=pending_index(fingerprint=fingerprint),
            task=pending_task(f"task-{index}", fingerprint=fingerprint),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        queued = list(executor.map(queue_projection, (1, 2)))

    persisted = [
        repository.get_pdf_vector_index_task(task.task_id) for task in queued
    ]
    assert sorted(task.generation for task in queued) == [1, 2]
    assert sorted(
        task.status.value for task in persisted if task is not None
    ) == ["cancelled", "pending"]
    current_index = repository.get_pdf_vector_index("file-1")
    assert current_index is not None and current_index.generation == 2
    inspection = repository.inspect_pdf_vector_queue()
    assert inspection.pending_count == 1


def test_expired_worker_cannot_complete_after_another_worker_reclaims_task(
    tmp_path: Path,
) -> None:
    repository = repository_with_file(tmp_path)
    repository.queue_pdf_vector_index(
        index=pending_index(),
        task=pending_task("task-1"),
    )
    first_claim = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-old",
        started_at="2026-08-14T00:01:00+00:00",
        lease_expires_at="2026-08-14T00:02:00+00:00",
    )
    assert first_claim is not None and first_claim.claim_token
    second_claim = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-new",
        started_at="2026-08-14T00:03:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )
    assert second_claim is not None and second_claim.claim_token

    stale_completion = repository.complete_pdf_vector_index_task(
        task_id=first_claim.task_id,
        worker_id="worker-old",
        claim_token=first_claim.claim_token,
        indexed_chunk_count=2,
        completed_at="2026-08-14T00:04:00+00:00",
    )
    current_completion = repository.complete_pdf_vector_index_task(
        task_id=second_claim.task_id,
        worker_id="worker-new",
        claim_token=second_claim.claim_token,
        indexed_chunk_count=2,
        completed_at="2026-08-14T00:05:00+00:00",
    )

    assert stale_completion is None
    assert current_completion is not None
    assert current_completion.status is PdfVectorIndexTaskStatus.SUCCEEDED


def test_failed_vector_index_task_can_be_reclaimed(tmp_path: Path) -> None:
    repository = repository_with_file(tmp_path)
    repository.queue_pdf_vector_index(
        index=pending_index(),
        task=pending_task("task-1"),
    )
    first_claim = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-1",
        started_at="2026-08-14T00:01:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )
    assert first_claim is not None and first_claim.claim_token

    failed = repository.fail_pdf_vector_index_task(
        task_id=first_claim.task_id,
        worker_id="worker-1",
        claim_token=first_claim.claim_token,
        error_message="injected failure",
        error_code="INJECTED_TRANSIENT_FAILURE",
        retryable=True,
        failed_at="2026-08-14T00:02:00+00:00",
    )
    reclaimed = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-2",
        started_at="2026-08-14T00:03:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )

    assert failed is not None
    assert failed.status is PdfVectorIndexTaskStatus.RETRY_WAIT
    assert failed.finished_at is None
    assert failed.next_attempt_at == "2026-08-14T00:02:02+00:00"
    assert failed.worker_id is None
    assert failed.claim_token is None
    assert reclaimed is not None
    assert reclaimed.worker_id == "worker-2"
    assert reclaimed.claim_token != first_claim.claim_token
    assert reclaimed.attempt_count == 2
    assert reclaimed.finished_at is None
    assert reclaimed.next_attempt_at is None


def test_failed_vector_index_task_is_not_reclaimed_before_backoff(tmp_path: Path) -> None:
    repository = repository_with_file(tmp_path)
    repository.queue_pdf_vector_index(
        index=pending_index(),
        task=pending_task("task-1"),
    )
    claimed = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-1",
        started_at="2026-08-14T00:01:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )
    assert claimed is not None and claimed.claim_token
    assert repository.fail_pdf_vector_index_task(
        task_id=claimed.task_id,
        worker_id="worker-1",
        claim_token=claimed.claim_token,
        error_message="temporary outage",
        error_code="TEMPORARY_OUTAGE",
        retryable=True,
        failed_at="2026-08-14T00:02:00+00:00",
    ) is not None

    assert repository.claim_next_pdf_vector_index_task(
        worker_id="worker-2",
        started_at="2026-08-14T00:02:01+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    ) is None
    assert repository.claim_next_pdf_vector_index_task(
        worker_id="worker-2",
        started_at="2026-08-14T00:02:02+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    ) is not None


def test_non_retryable_vector_failure_moves_directly_to_dead_letter(
    tmp_path: Path,
) -> None:
    repository = repository_with_file(tmp_path)
    repository.queue_pdf_vector_index(
        index=pending_index(),
        task=pending_task("task-1"),
    )
    claimed = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-1",
        started_at="2026-08-14T00:01:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )
    assert claimed is not None and claimed.claim_token

    dead_letter = repository.fail_pdf_vector_index_task(
        task_id=claimed.task_id,
        worker_id="worker-1",
        claim_token=claimed.claim_token,
        error_message="embedding dimension mismatch",
        error_code="PDF_VECTOR_INVALID_INPUT",
        retryable=False,
        failed_at="2026-08-14T00:02:00+00:00",
    )

    assert dead_letter is not None
    assert dead_letter.status is PdfVectorIndexTaskStatus.DEAD_LETTER
    assert dead_letter.finished_at == "2026-08-14T00:02:00+00:00"
    assert dead_letter.next_attempt_at is None
    assert dead_letter.error_code == "PDF_VECTOR_INVALID_INPUT"
    assert dead_letter.worker_id is None
    inspection = repository.inspect_pdf_vector_queue()
    assert inspection.dead_letter_count == 1
    assert inspection.pending_count == 0
    assert inspection.running_count == 0
    assert repository.claim_next_pdf_vector_index_task(
        worker_id="worker-2",
        started_at="2026-08-14T01:00:00+00:00",
        lease_expires_at="2026-08-14T01:10:00+00:00",
    ) is None


def test_retry_exhaustion_can_be_requeued_as_a_new_auditable_task(
    tmp_path: Path,
) -> None:
    repository = repository_with_file(tmp_path)
    repository.queue_pdf_vector_index(
        index=pending_index(),
        task=pending_task("task-exhausted", attempt_count=9),
    )
    claimed = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-1",
        started_at="2026-08-14T00:01:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )
    assert claimed is not None and claimed.claim_token
    assert claimed.attempt_count == 10
    dead_letter = repository.fail_pdf_vector_index_task(
        task_id=claimed.task_id,
        worker_id="worker-1",
        claim_token=claimed.claim_token,
        error_message="service remains unavailable",
        error_code="PDF_VECTOR_TRANSIENT_FAILURE",
        retryable=True,
        failed_at="2026-08-14T00:02:00+00:00",
        max_attempts=10,
    )
    assert dead_letter is not None
    assert dead_letter.status is PdfVectorIndexTaskStatus.DEAD_LETTER

    requeued = repository.requeue_pdf_vector_dead_letter_task(
        task_id=dead_letter.task_id,
        requeued_at="2026-08-14T00:03:00+00:00",
    )

    assert requeued is not None
    assert requeued.task_id != dead_letter.task_id
    assert requeued.parent_task_id == dead_letter.task_id
    assert requeued.status is PdfVectorIndexTaskStatus.PENDING
    assert requeued.attempt_count == 0
    index = repository.get_pdf_vector_index("file-1")
    assert index is not None and index.status is PdfVectorIndexStatus.PENDING


def test_vector_reconciliation_backfills_once_and_respects_dead_letter(
    tmp_path: Path,
) -> None:
    repository = repository_with_file(tmp_path)
    repository.replace_pdf_document_chunks(
        "file-1",
        [
            PdfDocumentChunk(
                chunk_id="chunk-1",
                file_id="file-1",
                chunk_index=0,
                text="alpha",
                page_label="1",
                title="Alpha",
                token_count=1,
                content_hash="hash-1",
            ),
            PdfDocumentChunk(
                chunk_id="chunk-2",
                file_id="file-1",
                chunk_index=1,
                text="beta",
                page_label="2",
                title="Beta",
                token_count=1,
                content_hash="hash-2",
            ),
        ],
    )

    assert repository.reconcile_pdf_vector_index_queue(
        embedding_revision="embedding-1",
        embedding_dimension=4096,
        batch_size=10,
        queued_at="2026-08-14T00:01:00+00:00",
    ) == 1
    assert repository.reconcile_pdf_vector_index_queue(
        embedding_revision="embedding-1",
        embedding_dimension=4096,
        batch_size=10,
        queued_at="2026-08-14T00:01:01+00:00",
    ) == 0

    claimed = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-1",
        started_at="2026-08-14T00:02:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )
    assert claimed is not None and claimed.claim_token
    dead_letter = repository.fail_pdf_vector_index_task(
        task_id=claimed.task_id,
        worker_id="worker-1",
        claim_token=claimed.claim_token,
        error_message="invalid embedding contract",
        error_code="PDF_VECTOR_INVALID_INPUT",
        retryable=False,
        failed_at="2026-08-14T00:03:00+00:00",
    )
    assert dead_letter is not None
    assert dead_letter.status is PdfVectorIndexTaskStatus.DEAD_LETTER

    assert repository.reconcile_pdf_vector_index_queue(
        embedding_revision="embedding-1",
        embedding_dimension=4096,
        batch_size=10,
        queued_at="2026-08-14T00:04:00+00:00",
    ) == 0


def test_vector_delete_completion_removes_current_index_state(tmp_path: Path) -> None:
    repository = repository_with_file(tmp_path)
    repository.queue_pdf_vector_index(
        index=pending_index(),
        task=pending_task("task-index"),
    )
    index_claim = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-1",
        started_at="2026-08-14T00:01:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )
    assert index_claim is not None and index_claim.claim_token
    assert repository.complete_pdf_vector_index_task(
        task_id=index_claim.task_id,
        worker_id="worker-1",
        claim_token=index_claim.claim_token,
        indexed_chunk_count=2,
        completed_at="2026-08-14T00:02:00+00:00",
    ) is not None

    repository.queue_pdf_vector_delete(
        task=pending_task(
            "task-delete",
            action=PdfVectorIndexTaskAction.DELETE,
            updated_at="2026-08-14T00:03:00+00:00",
        )
    )
    delete_claim = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-1",
        started_at="2026-08-14T00:04:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )
    assert delete_claim is not None and delete_claim.claim_token

    completed = repository.complete_pdf_vector_delete_task(
        task_id=delete_claim.task_id,
        worker_id="worker-1",
        claim_token=delete_claim.claim_token,
        completed_at="2026-08-14T00:05:00+00:00",
    )

    assert completed is not None
    assert completed.status is PdfVectorIndexTaskStatus.SUCCEEDED
    assert repository.get_pdf_vector_index("file-1") is None


def test_forced_reconciliation_reserves_a_new_generation_for_ready_indexes(
    tmp_path: Path,
) -> None:
    repository = repository_with_file(tmp_path)
    repository.replace_pdf_document_chunks(
        "file-1",
        [
            PdfDocumentChunk(
                chunk_id=f"chunk-{index}",
                file_id="file-1",
                chunk_index=index,
                text=text,
                page_label=str(index + 1),
                title=text.title(),
                token_count=1,
                content_hash=f"hash-{index}",
            )
            for index, text in enumerate(("alpha", "beta"))
        ],
    )
    file = repository.get_pdf_file("file-1")
    assert file is not None and file.content_fingerprint
    repository.queue_pdf_vector_index(
        index=pending_index(fingerprint=file.content_fingerprint),
        task=pending_task(
            "task-initial",
            fingerprint=file.content_fingerprint,
        ),
    )
    claimed = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-1",
        started_at="2026-08-14T00:01:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )
    assert claimed is not None and claimed.claim_token
    assert repository.complete_pdf_vector_index_task(
        task_id=claimed.task_id,
        worker_id="worker-1",
        claim_token=claimed.claim_token,
        indexed_chunk_count=2,
        completed_at="2026-08-14T00:02:00+00:00",
    ) is not None

    queued_count = repository.reconcile_pdf_vector_index_queue(
        embedding_revision="embedding-1",
        embedding_dimension=4096,
        batch_size=10,
        queued_at="2026-08-14T00:03:00+00:00",
        force=True,
    )

    rebuilt_index = repository.get_pdf_vector_index("file-1")
    assert queued_count == 1
    assert rebuilt_index is not None
    assert rebuilt_index.status is PdfVectorIndexStatus.PENDING
    assert rebuilt_index.generation == 2


def test_pdf_delete_atomically_supersedes_index_work_with_vector_delete(
    tmp_path: Path,
) -> None:
    repository = repository_with_file(tmp_path)
    repository.queue_pdf_vector_index(
        index=pending_index(),
        task=pending_task("task-index"),
    )

    counts = repository.delete_pdf_file_tree("file-1")

    assert counts["deleted_files"] == 1
    cancelled = repository.get_pdf_vector_index_task("task-index")
    assert cancelled is not None
    assert cancelled.status is PdfVectorIndexTaskStatus.CANCELLED
    delete_task = repository.claim_next_pdf_vector_index_task(
        worker_id="vector-delete-worker",
        started_at="2026-08-14T00:01:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )
    assert delete_task is not None
    assert delete_task.action is PdfVectorIndexTaskAction.DELETE
    assert delete_task.file_id == "file-1"
    assert delete_task.source_fingerprint == "fingerprint-1"


def test_pdf_parse_publication_atomically_queues_vector_projection(
    tmp_path: Path,
) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "published-vector.sqlite3")
    repository.initialize()
    storage_root = tmp_path / "storage"
    service = PdfKnowledgeService(
        repository=repository,
        storage_root=storage_root,
        parser=FakePdfParser(),
        parser_status=PdfParserRuntimeStatus(
            backend="fake",
            available=True,
            detail="Fake parser for vector publication test.",
        ),
        vector_embedding_revision="Qwen3-Embedding-8B@test-revision",
        vector_embedding_dimension=4096,
        llm_client=FakeLlmClient(),
    )
    upload_task = service.create_upload_task(
        user_id="user-1",
        original_filename="vector-source.pdf",
        content=b"%PDF-1.4 vector publication test",
    )
    worker = PdfUploadTaskWorker(
        repository=repository,
        pdf_knowledge=service,
        storage_root=storage_root,
    )

    assert worker.run_once() is True

    assert upload_task.file_id is not None
    index = repository.get_pdf_vector_index(upload_task.file_id)
    assert index is not None
    assert index.status is PdfVectorIndexStatus.PENDING
    assert index.source_fingerprint
    assert index.embedding_revision == "Qwen3-Embedding-8B@test-revision"
    assert index.expected_chunk_count > 0
    vector_task = repository.claim_next_pdf_vector_index_task(
        worker_id="vector-worker",
        started_at="2026-08-14T01:00:00+00:00",
        lease_expires_at="2026-08-14T01:10:00+00:00",
    )
    assert vector_task is not None
    assert vector_task.file_id == upload_task.file_id
    assert vector_task.source_fingerprint == index.source_fingerprint
