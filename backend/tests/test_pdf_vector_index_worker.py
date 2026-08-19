from pathlib import Path

from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.adapters.retrieval.fake_retrieval import (
    FakePdfEmbeddingGateway,
    FakePdfVectorStore,
)
from app.application.pdf_knowledge.vector_indexing import PdfVectorIndexingService
from app.application.pdf_knowledge.vector_worker import PdfVectorIndexTaskWorker
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
from app.ports.pdf_retrieval import PdfVectorPoint

NOW = "2026-08-14T00:00:00+00:00"


def _repository_with_projection(
    tmp_path: Path,
    *,
    dimension: int = 4,
) -> tuple[SQLiteExcelAssetRepository, PdfVectorIndexTask]:
    repository = SQLiteExcelAssetRepository(tmp_path / "vector-worker.sqlite3")
    repository.initialize()
    repository.create_pdf_file(
        PdfFile(
            file_id="file-1",
            user_id="user-1",
            parent_id=None,
            display_name="source.pdf",
            original_filename="source.pdf",
            kind=PdfFileKind.PDF,
            size_bytes=100,
            storage_path="pdf-knowledge/files/file-1/source.pdf",
            status=PdfFileStatus.ACTIVE,
            visibility=PdfFileVisibility.VISIBLE,
            processing_status=PdfProcessingStatus.READY,
            progress=100,
            status_detail="Ready.",
            error_message=None,
            page_count=2,
            chunk_count=2,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    repository.replace_pdf_document_chunks(
        "file-1",
        [
            PdfDocumentChunk(
                chunk_id="chunk-1",
                file_id="file-1",
                chunk_index=0,
                text="alpha policy",
                page_label="1",
                title="Alpha",
                token_count=2,
                content_hash="hash-1",
            ),
            PdfDocumentChunk(
                chunk_id="chunk-2",
                file_id="file-1",
                chunk_index=1,
                text="beta requirement",
                page_label="2",
                title="Beta",
                token_count=2,
                content_hash="hash-2",
            ),
        ],
    )
    file = repository.get_pdf_file("file-1")
    assert file is not None and file.content_fingerprint
    index = PdfVectorIndex(
        file_id="file-1",
        source_fingerprint=file.content_fingerprint,
        embedding_revision="embedding@test",
        embedding_dimension=dimension,
        status=PdfVectorIndexStatus.PENDING,
        expected_chunk_count=2,
        indexed_chunk_count=0,
        created_at=NOW,
        updated_at=NOW,
    )
    task = PdfVectorIndexTask(
        task_id="task-index",
        file_id="file-1",
        action=PdfVectorIndexTaskAction.INDEX,
        source_fingerprint=file.content_fingerprint,
        embedding_revision="embedding@test",
        status=PdfVectorIndexTaskStatus.PENDING,
        attempt_count=0,
        created_at=NOW,
        updated_at=NOW,
    )
    repository.queue_pdf_vector_index(index=index, task=task)
    return repository, task


def _worker(
    repository: SQLiteExcelAssetRepository,
    embedding: FakePdfEmbeddingGateway,
    vector_store: FakePdfVectorStore,
) -> PdfVectorIndexTaskWorker:
    return PdfVectorIndexTaskWorker(
        repository=repository,
        indexing=PdfVectorIndexingService(
            repository=repository,
            embedding=embedding,
            vector_store=vector_store,
        ),
        lease_seconds=30,
    )


def test_vector_worker_publishes_only_after_complete_projection(tmp_path: Path) -> None:
    repository, task = _repository_with_projection(tmp_path)
    embedding = FakePdfEmbeddingGateway(revision="embedding@test", dimension=4)
    vector_store = FakePdfVectorStore()

    assert _worker(repository, embedding, vector_store).run_once() is True

    completed = repository.get_pdf_vector_index_task(task.task_id)
    index = repository.get_pdf_vector_index(task.file_id)
    assert completed is not None
    assert completed.status is PdfVectorIndexTaskStatus.SUCCEEDED
    assert index is not None
    assert index.status is PdfVectorIndexStatus.READY
    assert index.indexed_chunk_count == index.expected_chunk_count == 2
    assert len(embedding.document_calls) == 1
    assert vector_store.replace_calls == [
        (task.file_id, task.source_fingerprint, task.embedding_revision, 1)
    ]


def test_vector_worker_rejects_wrong_embedding_dimension_without_writing(
    tmp_path: Path,
) -> None:
    repository, task = _repository_with_projection(tmp_path, dimension=4)
    embedding = FakePdfEmbeddingGateway(revision="embedding@test", dimension=3)
    vector_store = FakePdfVectorStore()

    assert _worker(repository, embedding, vector_store).run_once() is True

    failed = repository.get_pdf_vector_index_task(task.task_id)
    index = repository.get_pdf_vector_index(task.file_id)
    assert failed is not None
    assert failed.status is PdfVectorIndexTaskStatus.DEAD_LETTER
    assert failed.error_code == "PDF_VECTOR_INVALID_INPUT"
    assert "dimension" in (failed.error_message or "")
    assert index is not None and index.status is PdfVectorIndexStatus.FAILED
    assert vector_store.replace_calls == []


def test_vector_worker_records_embedding_failure_and_keeps_index_unready(
    tmp_path: Path,
) -> None:
    repository, task = _repository_with_projection(tmp_path)
    embedding = FakePdfEmbeddingGateway(
        revision="embedding@test",
        dimension=4,
        error=RuntimeError("embedding service unavailable"),
    )
    vector_store = FakePdfVectorStore()

    assert _worker(repository, embedding, vector_store).run_once() is True

    failed = repository.get_pdf_vector_index_task(task.task_id)
    index = repository.get_pdf_vector_index(task.file_id)
    assert failed is not None
    assert failed.status is PdfVectorIndexTaskStatus.RETRY_WAIT
    assert failed.error_code == "PDF_VECTOR_TRANSIENT_FAILURE"
    assert failed.error_message == "embedding service unavailable"
    assert index is not None and index.status is PdfVectorIndexStatus.FAILED
    assert vector_store.replace_calls == []


def test_vector_worker_records_vector_store_failure(tmp_path: Path) -> None:
    repository, task = _repository_with_projection(tmp_path)
    embedding = FakePdfEmbeddingGateway(revision="embedding@test", dimension=4)
    vector_store = FakePdfVectorStore(error=RuntimeError("qdrant unavailable"))

    assert _worker(repository, embedding, vector_store).run_once() is True

    failed = repository.get_pdf_vector_index_task(task.task_id)
    index = repository.get_pdf_vector_index(task.file_id)
    assert failed is not None
    assert failed.status is PdfVectorIndexTaskStatus.RETRY_WAIT
    assert failed.error_code == "PDF_VECTOR_TRANSIENT_FAILURE"
    assert failed.error_message == "qdrant unavailable"
    assert index is not None and index.status is PdfVectorIndexStatus.FAILED


def test_claim_fence_prevents_vector_write_after_claim_loss(tmp_path: Path) -> None:
    repository, _task = _repository_with_projection(tmp_path)
    embedding = FakePdfEmbeddingGateway(revision="embedding@test", dimension=4)
    vector_store = FakePdfVectorStore()
    claimed = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-old",
        started_at="2026-08-14T00:01:00+00:00",
        lease_expires_at="2026-08-14T00:02:00+00:00",
    )
    assert claimed is not None
    service = PdfVectorIndexingService(
        repository=repository,
        embedding=embedding,
        vector_store=vector_store,
    )

    try:
        service.process_task(
            claimed,
            claim_fence=lambda: (_ for _ in ()).throw(RuntimeError("claim lost")),
        )
    except RuntimeError as error:
        assert str(error) == "claim lost"
    else:
        raise AssertionError("claim loss must stop vector publication")

    assert vector_store.replace_calls == []


def test_stale_publication_is_cleaned_without_touching_new_generation(
    tmp_path: Path,
) -> None:
    repository, _task = _repository_with_projection(tmp_path)
    embedding = FakePdfEmbeddingGateway(revision="embedding@test", dimension=4)

    class SupersedingVectorStore(FakePdfVectorStore):
        def replace_document_revision(
            self,
            *,
            file_id: str,
            source_fingerprint: str,
            embedding_revision: str,
            points: list[PdfVectorPoint],
            generation: int = 1,
        ) -> None:
            super().replace_document_revision(
                file_id=file_id,
                source_fingerprint=source_fingerprint,
                embedding_revision=embedding_revision,
                points=points,
                generation=generation,
            )
            repository.queue_pdf_vector_index(
                index=PdfVectorIndex(
                    file_id=file_id,
                    source_fingerprint="new-fingerprint",
                    embedding_revision=embedding_revision,
                    embedding_dimension=4,
                    status=PdfVectorIndexStatus.PENDING,
                    expected_chunk_count=2,
                    indexed_chunk_count=0,
                    created_at="2026-08-14T00:03:00+00:00",
                    updated_at="2026-08-14T00:03:00+00:00",
                ),
                task=PdfVectorIndexTask(
                    task_id="task-new-generation",
                    file_id=file_id,
                    action=PdfVectorIndexTaskAction.INDEX,
                    source_fingerprint="new-fingerprint",
                    embedding_revision=embedding_revision,
                    status=PdfVectorIndexTaskStatus.PENDING,
                    attempt_count=0,
                    created_at="2026-08-14T00:03:00+00:00",
                    updated_at="2026-08-14T00:03:00+00:00",
                ),
            )

    vector_store = SupersedingVectorStore()
    claimed = repository.claim_next_pdf_vector_index_task(
        worker_id="worker-old",
        started_at="2026-08-14T00:01:00+00:00",
        lease_expires_at="2026-08-14T00:10:00+00:00",
    )
    assert claimed is not None
    service = PdfVectorIndexingService(
        repository=repository,
        embedding=embedding,
        vector_store=vector_store,
    )

    try:
        service.process_task(claimed, claim_fence=lambda: None)
    except RuntimeError as error:
        assert "publication was rejected" in str(error)
    else:
        raise AssertionError("superseded publication must be rejected")

    assert vector_store.search_document_chunks(
        file_id=claimed.file_id,
        source_fingerprint=claimed.source_fingerprint,
        embedding_revision=claimed.embedding_revision,
        generation=claimed.generation,
        query_vector=(1.0, 0.0, 0.0, 0.0),
        limit=4,
    ) == []
    current_index = repository.get_pdf_vector_index(claimed.file_id)
    current_task = repository.get_pdf_vector_index_task("task-new-generation")
    assert current_index is not None and current_index.generation == 2
    assert current_task is not None and current_task.generation == 2
