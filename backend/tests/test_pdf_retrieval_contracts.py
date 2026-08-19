import math

import pytest

from app.adapters.retrieval.fake_retrieval import (
    FakePdfEmbeddingGateway,
    FakePdfRerankerGateway,
    FakePdfVectorStore,
)
from app.core.errors import PdfEmbeddingUnavailable
from app.ports.pdf_retrieval import (
    PdfEmbeddingInput,
    PdfRerankDocument,
    PdfVectorPoint,
)


def vector_point(
    *,
    file_id: str,
    chunk_id: str,
    chunk_index: int,
    vector: tuple[float, ...],
    fingerprint: str = "fingerprint-1",
    revision: str = "embedding-1",
) -> PdfVectorPoint:
    return PdfVectorPoint(
        file_id=file_id,
        chunk_id=chunk_id,
        chunk_index=chunk_index,
        content_hash=f"hash-{chunk_id}",
        source_fingerprint=fingerprint,
        embedding_revision=revision,
        vector=vector,
    )


def test_fake_embedding_is_deterministic_normalized_and_preserves_ids() -> None:
    gateway = FakePdfEmbeddingGateway(dimension=8)
    inputs = [
        PdfEmbeddingInput(text_id="chunk-1", text="alpha evidence"),
        PdfEmbeddingInput(text_id="chunk-2", text="beta evidence"),
    ]

    first = gateway.embed_documents(inputs)
    second = gateway.embed_documents(inputs)

    assert first == second
    assert [item.text_id for item in first] == ["chunk-1", "chunk-2"]
    assert all(len(item.vector) == 8 for item in first)
    assert all(
        math.isclose(
            math.sqrt(sum(value * value for value in item.vector)),
            1.0,
        )
        for item in first
    )


def test_fake_embedding_propagates_configured_failure() -> None:
    failure = PdfEmbeddingUnavailable("embedding service unavailable")
    gateway = FakePdfEmbeddingGateway(error=failure)

    with pytest.raises(PdfEmbeddingUnavailable) as captured:
        gateway.embed_query("question")

    assert captured.value is failure


def test_fake_vector_store_isolates_file_fingerprint_and_revision() -> None:
    store = FakePdfVectorStore()
    store.replace_document_revision(
        file_id="file-1",
        source_fingerprint="fingerprint-1",
        embedding_revision="embedding-1",
        points=[
            vector_point(
                file_id="file-1",
                chunk_id="chunk-near",
                chunk_index=0,
                vector=(1.0, 0.0),
            ),
            vector_point(
                file_id="file-1",
                chunk_id="chunk-far",
                chunk_index=1,
                vector=(0.0, 1.0),
            ),
        ],
    )

    hits = store.search_document_chunks(
        file_id="file-1",
        source_fingerprint="fingerprint-1",
        embedding_revision="embedding-1",
        query_vector=(1.0, 0.0),
        limit=2,
    )
    missing_revision = store.search_document_chunks(
        file_id="file-1",
        source_fingerprint="fingerprint-1",
        embedding_revision="embedding-2",
        query_vector=(1.0, 0.0),
        limit=2,
    )

    assert [hit.chunk_id for hit in hits] == ["chunk-near", "chunk-far"]
    assert missing_revision == []


def test_fake_vector_delete_can_target_one_revision() -> None:
    store = FakePdfVectorStore()
    for revision in ("embedding-1", "embedding-2"):
        store.replace_document_revision(
            file_id="file-1",
            source_fingerprint="fingerprint-1",
            embedding_revision=revision,
            points=[
                vector_point(
                    file_id="file-1",
                    chunk_id=f"chunk-{revision}",
                    chunk_index=0,
                    vector=(1.0, 0.0),
                    revision=revision,
                )
            ],
        )

    store.delete_document_revision(
        file_id="file-1",
        source_fingerprint="fingerprint-1",
        embedding_revision="embedding-1",
    )

    assert store.search_document_chunks(
        file_id="file-1",
        source_fingerprint="fingerprint-1",
        embedding_revision="embedding-1",
        query_vector=(1.0, 0.0),
        limit=1,
    ) == []
    assert len(
        store.search_document_chunks(
            file_id="file-1",
            source_fingerprint="fingerprint-1",
            embedding_revision="embedding-2",
            query_vector=(1.0, 0.0),
            limit=1,
        )
    ) == 1


def test_fake_vector_store_isolates_generations_and_bounded_delete() -> None:
    store = FakePdfVectorStore()
    for generation in (1, 2):
        store.replace_document_revision(
            file_id="file-1",
            source_fingerprint="fingerprint-1",
            embedding_revision="embedding-1",
            generation=generation,
            points=[
                PdfVectorPoint(
                    file_id="file-1",
                    chunk_id=f"chunk-generation-{generation}",
                    chunk_index=0,
                    content_hash=f"hash-{generation}",
                    source_fingerprint="fingerprint-1",
                    embedding_revision="embedding-1",
                    vector=(1.0, 0.0),
                    generation=generation,
                )
            ],
        )

    store.delete_document_revision(file_id="file-1", maximum_generation=1)

    assert store.search_document_chunks(
        file_id="file-1",
        source_fingerprint="fingerprint-1",
        embedding_revision="embedding-1",
        generation=1,
        query_vector=(1.0, 0.0),
        limit=1,
    ) == []
    generation_two_hits = store.search_document_chunks(
        file_id="file-1",
        source_fingerprint="fingerprint-1",
        embedding_revision="embedding-1",
        generation=2,
        query_vector=(1.0, 0.0),
        limit=1,
    )
    assert [hit.chunk_id for hit in generation_two_hits] == ["chunk-generation-2"]
    assert generation_two_hits[0].generation == 2


def test_fake_reranker_returns_one_score_per_input_document() -> None:
    reranker = FakePdfRerankerGateway()
    documents = [
        PdfRerankDocument(
            file_id="matched",
            text="alpha requirement evidence",
            evidence_chunk_ids=("chunk-1",),
        ),
        PdfRerankDocument(
            file_id="unmatched",
            text="unrelated material",
            evidence_chunk_ids=("chunk-2",),
        ),
    ]

    scores = reranker.rank_documents(query="alpha requirement", documents=documents)

    assert [score.file_id for score in scores] == ["matched", "unmatched"]
    assert scores[0].score > scores[1].score
