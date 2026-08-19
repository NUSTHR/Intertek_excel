from dataclasses import dataclass
from typing import Protocol

from app.domain.models import (
    PdfDocumentChunk,
    PdfFile,
    PdfVectorIndex,
    PdfVectorIndexTask,
)


@dataclass(frozen=True)
class PdfVectorQueueInspection:
    pending_count: int
    running_count: int
    retry_wait_count: int
    dead_letter_count: int
    expired_running_count: int
    due_retry_count: int
    oldest_active_at: str | None


class PdfVectorIndexRepository(Protocol):
    def inspect_pdf_vector_queue(self) -> PdfVectorQueueInspection:
        ...

    def get_pdf_file(self, file_id: str) -> PdfFile | None:
        ...

    def list_pdf_document_chunks(self, file_id: str) -> list[PdfDocumentChunk]:
        ...

    def get_pdf_vector_index(self, file_id: str) -> PdfVectorIndex | None:
        ...

    def get_pdf_vector_index_task(self, task_id: str) -> PdfVectorIndexTask | None:
        ...

    def queue_pdf_vector_index(
        self,
        *,
        index: PdfVectorIndex,
        task: PdfVectorIndexTask,
    ) -> PdfVectorIndexTask:
        ...

    def queue_pdf_vector_delete(
        self,
        *,
        task: PdfVectorIndexTask,
    ) -> PdfVectorIndexTask:
        ...

    def reconcile_pdf_vector_index_queue(
        self,
        *,
        embedding_revision: str,
        embedding_dimension: int,
        batch_size: int,
        queued_at: str,
        force: bool = False,
    ) -> int:
        ...

    def claim_next_pdf_vector_index_task(
        self,
        *,
        worker_id: str,
        started_at: str,
        lease_expires_at: str,
        max_attempts: int = 20,
    ) -> PdfVectorIndexTask | None:
        ...

    def heartbeat_pdf_vector_index_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        heartbeat_at: str,
        lease_expires_at: str,
    ) -> bool:
        ...

    def complete_pdf_vector_index_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        indexed_chunk_count: int,
        completed_at: str,
    ) -> PdfVectorIndexTask | None:
        ...

    def complete_pdf_vector_delete_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        completed_at: str,
    ) -> PdfVectorIndexTask | None:
        ...

    def fail_pdf_vector_index_task(
        self,
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
        ...

    def requeue_pdf_vector_dead_letter_task(
        self,
        *,
        task_id: str,
        requeued_at: str,
    ) -> PdfVectorIndexTask | None:
        ...
