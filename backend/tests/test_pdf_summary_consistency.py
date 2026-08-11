from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.adapters.repositories.sqlite_repository import (
    SQLiteExcelAssetRepository,
)
from app.domain.models import (
    PdfDocumentChunk,
    PdfDocumentSummary,
    PdfFile,
    PdfFileKind,
    PdfFileStatus,
    PdfFileVisibility,
    PdfProcessingStatus,
    PdfSummaryTask,
    PdfSummaryTaskStatus,
)

NOW = "2026-08-11T00:00:00+00:00"


def test_pdf_summary_task_creation_is_atomic_per_file(tmp_path: Path) -> None:
    repository = _repository_with_ready_pdf(tmp_path)
    file = repository.get_pdf_file("pdf_test")
    assert file is not None

    first = _queued_task("task_first", file.content_fingerprint)
    second = _queued_task("task_second", file.content_fingerprint)
    with ThreadPoolExecutor(max_workers=2) as executor:
        created = list(executor.map(repository.create_pdf_summary_task, [first, second]))

    assert created[0].task_id == created[1].task_id
    active = [
        task
        for task in repository.list_pdf_summary_tasks("admin")
        if task.status in {PdfSummaryTaskStatus.QUEUED, PdfSummaryTaskStatus.RUNNING}
    ]
    assert len(active) == 1


def test_stale_worker_claim_cannot_overwrite_retried_task(tmp_path: Path) -> None:
    repository = _repository_with_ready_pdf(tmp_path)
    file = repository.get_pdf_file("pdf_test")
    assert file is not None
    repository.create_pdf_summary_task(
        _queued_task("task_claim", file.content_fingerprint)
    )
    stale_claim = repository.claim_next_pdf_summary_task(
        worker_id="worker-old",
        started_at=NOW,
    )
    assert stale_claim is not None and stale_claim.claim_token

    assert repository.fail_stale_running_pdf_summary_tasks(
        cutoff_started_at="9999-01-01T00:00:00+00:00",
        failed_at="2026-08-11T00:01:00+00:00",
    ) == 1
    assert repository.retry_pdf_summary_task(
        task_id=stale_claim.task_id,
        retried_at="2026-08-11T00:02:00+00:00",
    ) is not None
    current_claim = repository.claim_next_pdf_summary_task(
        worker_id="worker-new",
        started_at="2026-08-11T00:03:00+00:00",
    )
    assert current_claim is not None and current_claim.claim_token

    assert repository.complete_pdf_summary_task(
        task_id=stale_claim.task_id,
        worker_id="worker-old",
        claim_token=stale_claim.claim_token,
        result={},
        detail="stale completion",
        finished_at="2026-08-11T00:04:00+00:00",
    ) is None
    still_running = repository.get_pdf_summary_task(stale_claim.task_id)
    assert still_running is not None
    assert still_running.status == PdfSummaryTaskStatus.RUNNING
    assert still_running.worker_id == "worker-new"

    completed = repository.complete_pdf_summary_task(
        task_id=current_claim.task_id,
        worker_id="worker-new",
        claim_token=current_claim.claim_token,
        result={"summary_status": "ready"},
        detail="completed",
        finished_at="2026-08-11T00:05:00+00:00",
    )
    assert completed is not None
    assert completed.status == PdfSummaryTaskStatus.READY


def test_summary_write_rejects_changed_pdf_fingerprint(tmp_path: Path) -> None:
    repository = _repository_with_ready_pdf(tmp_path)
    file = repository.get_pdf_file("pdf_test")
    assert file is not None
    summary = PdfDocumentSummary(
        file_id=file.file_id,
        status="ready",
        content="summary for the first parse",
        updated_at=NOW,
        source_fingerprint=file.content_fingerprint,
        source_updated_at=file.updated_at,
    )
    assert repository.save_pdf_document_summary(summary) is True

    repository.replace_pdf_document_chunks(
        file.file_id,
        [_chunk("chunk_new", "new-content-hash", "new parsed content")],
    )
    changed_file = repository.get_pdf_file(file.file_id)
    assert changed_file is not None
    assert changed_file.content_fingerprint != file.content_fingerprint
    assert repository.save_pdf_document_summary(summary) is False

    stored = repository.get_pdf_document_detail(file.file_id)
    assert stored is not None
    assert stored.summary.content == "summary for the first parse"
    assert stored.summary.source_fingerprint == file.content_fingerprint


def _repository_with_ready_pdf(tmp_path: Path) -> SQLiteExcelAssetRepository:
    repository = SQLiteExcelAssetRepository(tmp_path / "pdf.sqlite3")
    repository.initialize()
    repository.create_pdf_file(
        PdfFile(
            file_id="pdf_test",
            user_id="admin",
            parent_id=None,
            display_name="test.pdf",
            original_filename="test.pdf",
            kind=PdfFileKind.PDF,
            size_bytes=100,
            storage_path="pdf-knowledge/files/pdf_test/test.pdf",
            status=PdfFileStatus.ACTIVE,
            visibility=PdfFileVisibility.VISIBLE,
            processing_status=PdfProcessingStatus.READY,
            progress=100,
            status_detail="ready",
            error_message=None,
            page_count=1,
            chunk_count=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    repository.replace_pdf_document_chunks(
        "pdf_test",
        [_chunk("chunk_initial", "initial-content-hash", "initial parsed content")],
    )
    return repository


def _queued_task(task_id: str, source_fingerprint: str) -> PdfSummaryTask:
    return PdfSummaryTask(
        task_id=task_id,
        user_id="admin",
        file_id="pdf_test",
        status=PdfSummaryTaskStatus.QUEUED,
        progress=5,
        detail="queued",
        error_message=None,
        result={},
        created_at=NOW,
        updated_at=NOW,
        source_fingerprint=source_fingerprint,
    )


def _chunk(chunk_id: str, content_hash: str, text: str) -> PdfDocumentChunk:
    return PdfDocumentChunk(
        chunk_id=chunk_id,
        file_id="pdf_test",
        chunk_index=0,
        text=text,
        page_label="1",
        title="Page 1",
        token_count=3,
        content_hash=content_hash,
    )
