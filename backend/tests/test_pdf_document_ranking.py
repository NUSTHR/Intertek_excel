from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.adapters.retrieval.fake_retrieval import (
    FakePdfEmbeddingGateway,
    FakePdfRerankerGateway,
    FakePdfVectorStore,
)
from app.application.pdf_knowledge.document_ranking import PdfDocumentRankingService
from app.application.pdf_knowledge.document_selection import PdfSelectionMode
from app.core.errors import PdfRankingIncomplete
from app.domain.models import (
    PdfDocumentChunk,
    PdfVectorIndex,
    PdfVectorIndexStatus,
    SelectedDocument,
)
from app.ports.pdf_retrieval import PdfVectorPoint


@dataclass
class _RankingRepository:
    indexes: dict[str, PdfVectorIndex]
    chunks: dict[str, list[PdfDocumentChunk]]
    fingerprints: dict[str, str]

    def get_pdf_vector_index(self, file_id: str) -> PdfVectorIndex | None:
        return self.indexes.get(file_id)

    def get_pdf_file(self, file_id: str):
        fingerprint = self.fingerprints.get(file_id)
        if fingerprint is None:
            return None
        return SimpleNamespace(content_fingerprint=fingerprint)

    def list_pdf_document_chunks_by_file_ids(
        self,
        file_ids: list[str],
    ) -> dict[str, list[PdfDocumentChunk]]:
        return {file_id: list(self.chunks.get(file_id, [])) for file_id in file_ids}


def _ranking_fixture(
    count: int,
) -> tuple[
    _RankingRepository,
    FakePdfEmbeddingGateway,
    FakePdfVectorStore,
    list[SelectedDocument],
]:
    embedding = FakePdfEmbeddingGateway(revision="embedding@test", dimension=4)
    vector_store = FakePdfVectorStore()
    indexes: dict[str, PdfVectorIndex] = {}
    chunks_by_file_id: dict[str, list[PdfDocumentChunk]] = {}
    documents: list[SelectedDocument] = []
    for index in range(count):
        file_id = f"file-{index}"
        chunk_id = f"chunk-{index}"
        fingerprint = f"fingerprint-{index}"
        text = f"document evidence {index}"
        vector = embedding.embed_query(text)
        chunk = PdfDocumentChunk(
            chunk_id=chunk_id,
            file_id=file_id,
            chunk_index=0,
            text=text,
            page_label="1",
            title=f"Document {index}",
            token_count=3,
            content_hash=f"hash-{index}",
        )
        indexes[file_id] = PdfVectorIndex(
            file_id=file_id,
            source_fingerprint=fingerprint,
            embedding_revision=embedding.revision,
            embedding_dimension=4,
            status=PdfVectorIndexStatus.READY,
            expected_chunk_count=1,
            indexed_chunk_count=1,
            created_at="2026-08-14T00:00:00+00:00",
            updated_at="2026-08-14T00:00:00+00:00",
            ready_at="2026-08-14T00:00:00+00:00",
        )
        chunks_by_file_id[file_id] = [chunk]
        vector_store.replace_document_revision(
            file_id=file_id,
            source_fingerprint=fingerprint,
            embedding_revision=embedding.revision,
            points=[
                PdfVectorPoint(
                    file_id=file_id,
                    chunk_id=chunk_id,
                    chunk_index=0,
                    content_hash=chunk.content_hash,
                    source_fingerprint=fingerprint,
                    embedding_revision=embedding.revision,
                    vector=vector,
                )
            ],
        )
        documents.append(
            SelectedDocument(
                file_id=file_id,
                version_id=file_id,
                reason="router match",
                confidence=0.8,
            )
        )
    embedding.query_calls.clear()
    return (
        _RankingRepository(
            indexes,
            chunks_by_file_id,
            {
                file_id: index.source_fingerprint
                for file_id, index in indexes.items()
            },
        ),
        embedding,
        vector_store,
        documents,
    )


def test_four_or_fewer_router_documents_bypass_retrieval_unchanged() -> None:
    repository, embedding, vector_store, documents = _ranking_fixture(4)
    reranker = FakePdfRerankerGateway()
    service = PdfDocumentRankingService(
        repository=repository,  # type: ignore[arg-type]
        embedding=embedding,
        vector_store=vector_store,
        reranker=reranker,
    )

    selection = service.select(question="policy", router_documents=documents)

    assert selection.mode is PdfSelectionMode.ROUTER_ONLY
    assert list(selection.documents) == documents
    assert embedding.query_calls == []
    assert vector_store.search_calls == []
    assert reranker.calls == []


def test_more_than_four_documents_are_all_retrieved_and_reranked_to_four() -> None:
    repository, embedding, vector_store, documents = _ranking_fixture(6)
    scores = {f"file-{index}": float(index) for index in range(6)}
    reranker = FakePdfRerankerGateway(revision="reranker@test", scores=scores)
    service = PdfDocumentRankingService(
        repository=repository,  # type: ignore[arg-type]
        embedding=embedding,
        vector_store=vector_store,
        reranker=reranker,
        hits_per_document=2,
    )

    selection = service.select(question="policy", router_documents=documents)

    assert selection.mode is PdfSelectionMode.VECTOR_RERANK
    assert [document.file_id for document in selection.documents] == [
        "file-5",
        "file-4",
        "file-3",
        "file-2",
    ]
    assert len(selection.rankings) == 6
    assert len(vector_store.search_calls) == 6
    assert {call[0] for call in vector_store.search_calls} == {
        document.file_id for document in documents
    }
    assert len(reranker.calls) == 1
    assert len(reranker.calls[0][1]) == 6
    assert selection.ranking_revision == "embedding@test+reranker@test"


def test_missing_ready_index_fails_without_partial_ranking() -> None:
    repository, embedding, vector_store, documents = _ranking_fixture(5)
    repository.indexes.pop("file-3")
    reranker = FakePdfRerankerGateway()
    service = PdfDocumentRankingService(
        repository=repository,  # type: ignore[arg-type]
        embedding=embedding,
        vector_store=vector_store,
        reranker=reranker,
    )

    with pytest.raises(PdfRankingIncomplete, match="file-3"):
        service.select(question="policy", router_documents=documents)

    assert reranker.calls == []


def test_stale_source_fingerprint_fails_before_vector_search() -> None:
    repository, embedding, vector_store, documents = _ranking_fixture(5)
    repository.fingerprints["file-2"] = "new-fingerprint"
    reranker = FakePdfRerankerGateway()
    service = PdfDocumentRankingService(
        repository=repository,  # type: ignore[arg-type]
        embedding=embedding,
        vector_store=vector_store,
        reranker=reranker,
    )

    with pytest.raises(PdfRankingIncomplete, match="file-2"):
        service.select(question="policy", router_documents=documents)

    assert reranker.calls == []
