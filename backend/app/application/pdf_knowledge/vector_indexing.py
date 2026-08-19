import math
from collections.abc import Callable

from app.core.content_fingerprint import ordered_content_fingerprint
from app.domain.models import (
    PdfFileStatus,
    PdfVectorIndexTask,
    PdfVectorIndexTaskAction,
    PdfVectorIndexTaskStatus,
)
from app.ports.pdf_retrieval import (
    PdfEmbeddingGateway,
    PdfEmbeddingInput,
    PdfVectorPoint,
    PdfVectorStore,
    RetrievalCancellationChecker,
)
from app.ports.pdf_vector_index import PdfVectorIndexRepository

ClaimFence = Callable[[], None]


class PdfVectorIndexingService:
    """Projects authoritative SQLite PDF chunks into a derived vector store."""

    def __init__(
        self,
        *,
        repository: PdfVectorIndexRepository,
        embedding: PdfEmbeddingGateway,
        vector_store: PdfVectorStore,
    ) -> None:
        self._repository = repository
        self._embedding = embedding
        self._vector_store = vector_store

    def process_task(
        self,
        task: PdfVectorIndexTask,
        *,
        claim_fence: ClaimFence,
        cancellation_checker: RetrievalCancellationChecker | None = None,
    ) -> PdfVectorIndexTask | None:
        self._validate_claim(task)
        if task.action is PdfVectorIndexTaskAction.DELETE:
            return self._delete_projection(task, claim_fence=claim_fence)
        return self._index_projection(
            task,
            claim_fence=claim_fence,
            cancellation_checker=cancellation_checker,
        )

    def _index_projection(
        self,
        task: PdfVectorIndexTask,
        *,
        claim_fence: ClaimFence,
        cancellation_checker: RetrievalCancellationChecker | None,
    ) -> PdfVectorIndexTask | None:
        index = self._repository.get_pdf_vector_index(task.file_id)
        file = self._repository.get_pdf_file(task.file_id)
        chunks = self._repository.list_pdf_document_chunks(task.file_id)
        if index is None:
            raise ValueError("PDF vector index state does not exist")
        if file is None or file.status is not PdfFileStatus.ACTIVE:
            raise ValueError("PDF vector source file is not active")
        if self._embedding.revision != task.embedding_revision:
            raise ValueError("embedding gateway revision does not match the queued task")
        if (
            index.source_fingerprint != task.source_fingerprint
            or index.embedding_revision != task.embedding_revision
            or index.generation != task.generation
        ):
            raise ValueError("PDF vector task no longer matches current index state")
        if index.expected_chunk_count != len(chunks):
            raise ValueError("PDF vector source chunk count changed before indexing")
        source_fingerprint = ordered_content_fingerprint(
            [chunk.content_hash for chunk in chunks]
        )
        if (
            source_fingerprint != task.source_fingerprint
            or file.content_fingerprint != task.source_fingerprint
        ):
            raise ValueError("PDF vector source fingerprint changed before indexing")

        embedded = self._embedding.embed_documents(
            [PdfEmbeddingInput(text_id=chunk.chunk_id, text=chunk.text) for chunk in chunks],
            cancellation_checker=cancellation_checker,
        )
        vectors_by_chunk_id = {item.text_id: item.vector for item in embedded}
        expected_chunk_ids = {chunk.chunk_id for chunk in chunks}
        if len(vectors_by_chunk_id) != len(embedded):
            raise ValueError("embedding response contains duplicate chunk IDs")
        if set(vectors_by_chunk_id) != expected_chunk_ids:
            raise ValueError("embedding response does not cover the source chunks exactly")
        for vector in vectors_by_chunk_id.values():
            if len(vector) != index.embedding_dimension:
                raise ValueError("embedding response dimension does not match index state")
            if not all(math.isfinite(value) for value in vector):
                raise ValueError("embedding response contains a non-finite value")

        points = [
            PdfVectorPoint(
                file_id=task.file_id,
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                content_hash=chunk.content_hash,
                source_fingerprint=task.source_fingerprint,
                embedding_revision=task.embedding_revision,
                vector=vectors_by_chunk_id[chunk.chunk_id],
                generation=task.generation,
                page_label=chunk.page_label,
                title=chunk.title,
            )
            for chunk in chunks
        ]
        claim_fence()
        self._vector_store.replace_document_revision(
            file_id=task.file_id,
            source_fingerprint=task.source_fingerprint,
            embedding_revision=task.embedding_revision,
            generation=task.generation,
            points=points,
        )
        claim_fence()
        if task.generation > 1:
            self._vector_store.delete_document_revision(
                file_id=task.file_id,
                maximum_generation=task.generation - 1,
            )
        completed = self._repository.complete_pdf_vector_index_task(
            task_id=task.task_id,
            worker_id=task.worker_id or "",
            claim_token=task.claim_token or "",
            indexed_chunk_count=len(points),
            completed_at=_utc_now_iso(),
        )
        if completed is None:
            self._vector_store.delete_document_revision(
                file_id=task.file_id,
                source_fingerprint=task.source_fingerprint,
                embedding_revision=task.embedding_revision,
                maximum_generation=task.generation,
            )
            raise RuntimeError("PDF vector index publication was rejected by its claim fence")
        return completed

    def _delete_projection(
        self,
        task: PdfVectorIndexTask,
        *,
        claim_fence: ClaimFence,
    ) -> PdfVectorIndexTask | None:
        claim_fence()
        self._vector_store.delete_document_revision(
            file_id=task.file_id,
            maximum_generation=task.generation,
        )
        completed = self._repository.complete_pdf_vector_delete_task(
            task_id=task.task_id,
            worker_id=task.worker_id or "",
            claim_token=task.claim_token or "",
            completed_at=_utc_now_iso(),
        )
        if completed is None:
            raise RuntimeError("PDF vector delete publication was rejected by its claim fence")
        return completed

    @staticmethod
    def _validate_claim(task: PdfVectorIndexTask) -> None:
        if task.status is not PdfVectorIndexTaskStatus.RUNNING:
            raise ValueError("PDF vector task must be running")
        if not task.worker_id or not task.claim_token:
            raise ValueError("PDF vector task is missing its claim identity")


def _utc_now_iso() -> str:
    # Kept behind a tiny seam so completion timestamps can be patched in focused tests.
    from app.core.time import utc_now_iso

    return utc_now_iso()
