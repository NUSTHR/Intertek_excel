import math

from app.application.pdf_knowledge.document_selection import (
    MAX_FINAL_PDF_DOCUMENTS,
    PdfFinalDocumentSelection,
    PdfRankedDocument,
    PdfRoutingCandidateSet,
)
from app.core.errors import PdfRankingIncomplete
from app.domain.models import PdfDocumentChunk, PdfVectorIndexStatus, SelectedDocument
from app.ports.pdf_retrieval import (
    PdfEmbeddingGateway,
    PdfRerankDocument,
    PdfRerankerGateway,
    PdfVectorStore,
    RetrievalCancellationChecker,
)
from app.ports.repository import PdfChatRepository


class PdfDocumentRankingService:
    def __init__(
        self,
        *,
        repository: PdfChatRepository,
        embedding: PdfEmbeddingGateway,
        vector_store: PdfVectorStore,
        reranker: PdfRerankerGateway,
        hits_per_document: int = 8,
        rerank_max_document_characters: int = 24_000,
    ) -> None:
        if hits_per_document < 1:
            raise ValueError("vector hits per document must be positive")
        if rerank_max_document_characters < 1:
            raise ValueError("reranker document character limit must be positive")
        self._repository = repository
        self._embedding = embedding
        self._vector_store = vector_store
        self._reranker = reranker
        self._hits_per_document = hits_per_document
        self._rerank_max_document_characters = rerank_max_document_characters

    def select(
        self,
        *,
        question: str,
        router_documents: list[SelectedDocument],
        cancellation_checker: RetrievalCancellationChecker | None = None,
    ) -> PdfFinalDocumentSelection:
        candidates = PdfRoutingCandidateSet(tuple(router_documents))
        if len(candidates.documents) <= MAX_FINAL_PDF_DOCUMENTS:
            return PdfFinalDocumentSelection.router_only(candidates)
        _raise_if_cancelled(cancellation_checker)
        query_vector = self._embedding.embed_query(
            question,
            cancellation_checker=cancellation_checker,
        )
        rerank_documents: list[PdfRerankDocument] = []
        vector_scores: dict[str, float] = {}
        evidence_by_file_id: dict[str, tuple[str, ...]] = {}
        chunks_by_file_id = self._repository.list_pdf_document_chunks_by_file_ids(
            list(candidates.file_ids)
        )
        for document in candidates.documents:
            index = self._repository.get_pdf_vector_index(document.file_id)
            file = self._repository.get_pdf_file(document.file_id)
            if (
                index is None
                or index.status is not PdfVectorIndexStatus.READY
                or index.embedding_revision != self._embedding.revision
                or file is None
                or file.content_fingerprint != index.source_fingerprint
            ):
                raise PdfRankingIncomplete(
                    f"vector index is not ready for routed PDF {document.file_id}"
                )
            if index.expected_chunk_count != len(
                chunks_by_file_id.get(document.file_id, [])
            ):
                raise PdfRankingIncomplete(
                    f"vector index chunk count is stale for routed PDF {document.file_id}"
                )
            hits = self._vector_store.search_document_chunks(
                file_id=document.file_id,
                source_fingerprint=index.source_fingerprint,
                embedding_revision=index.embedding_revision,
                generation=index.generation,
                query_vector=query_vector,
                limit=self._hits_per_document,
            )
            if not hits:
                raise PdfRankingIncomplete(
                    f"vector retrieval returned no evidence for routed PDF {document.file_id}"
                )
            chunks = {
                chunk.chunk_id: chunk
                for chunk in chunks_by_file_id.get(document.file_id, [])
            }
            matching_chunk_ids = tuple(
                hit.chunk_id for hit in hits if hit.chunk_id in chunks
            )
            if len(matching_chunk_ids) != len(hits):
                raise PdfRankingIncomplete(
                    f"vector retrieval returned stale evidence for routed PDF {document.file_id}"
                )
            if any(hit.generation != index.generation for hit in hits):
                raise PdfRankingIncomplete(
                    f"vector retrieval returned a stale generation for routed PDF "
                    f"{document.file_id}"
                )
            evidence_chunk_ids = _bounded_evidence_chunk_ids(
                matching_chunk_ids,
                chunks=chunks,
                max_characters=self._rerank_max_document_characters,
            )
            evidence_by_file_id[document.file_id] = evidence_chunk_ids
            vector_scores[document.file_id] = max(hit.score for hit in hits)
            rerank_documents.append(
                PdfRerankDocument(
                    file_id=document.file_id,
                    text="\n\n".join(chunks[chunk_id].text for chunk_id in evidence_chunk_ids),
                    evidence_chunk_ids=evidence_chunk_ids,
                )
            )
        rerank_scores = self._reranker.rank_documents(
            query=question,
            documents=rerank_documents,
            cancellation_checker=cancellation_checker,
        )
        scores_by_file_id = {result.file_id: result.score for result in rerank_scores}
        if len(scores_by_file_id) != len(rerank_scores):
            raise PdfRankingIncomplete("reranker returned duplicate document IDs")
        if set(scores_by_file_id) != set(candidates.file_ids):
            raise PdfRankingIncomplete("reranker did not score every routed PDF")
        if not all(math.isfinite(score) for score in scores_by_file_id.values()):
            raise PdfRankingIncomplete("reranker returned a non-finite score")
        router_order = {
            document.file_id: index
            for index, document in enumerate(candidates.documents)
        }
        ordered_file_ids = sorted(
            candidates.file_ids,
            key=lambda file_id: (
                -scores_by_file_id[file_id],
                -vector_scores[file_id],
                router_order[file_id],
                file_id,
            ),
        )
        rankings = tuple(
            PdfRankedDocument(
                file_id=file_id,
                rank=rank,
                score=scores_by_file_id[file_id],
                evidence_chunk_ids=evidence_by_file_id[file_id],
            )
            for rank, file_id in enumerate(ordered_file_ids, start=1)
        )
        return PdfFinalDocumentSelection.vector_rerank(
            candidates=candidates,
            rankings=rankings,
            ranking_revision=(
                f"{self._embedding.revision}+{self._reranker.revision}"
            ),
        )


def _raise_if_cancelled(
    cancellation_checker: RetrievalCancellationChecker | None,
) -> None:
    if cancellation_checker is not None:
        cancellation_checker()


def _bounded_evidence_chunk_ids(
    chunk_ids: tuple[str, ...],
    *,
    chunks: dict[str, PdfDocumentChunk],
    max_characters: int,
) -> tuple[str, ...]:
    selected: list[str] = []
    used_characters = 0
    for chunk_id in chunk_ids:
        chunk = chunks[chunk_id]
        text = chunk.text
        separator_characters = 2 if selected else 0
        required_characters = separator_characters + len(text)
        if selected and used_characters + required_characters > max_characters:
            break
        if not selected and len(text) > max_characters:
            raise PdfRankingIncomplete(
                "vector evidence chunk exceeds the configured reranker capacity"
            )
        selected.append(chunk_id)
        used_characters += required_characters
    if not selected:
        raise PdfRankingIncomplete("vector retrieval produced no rerankable evidence")
    return tuple(selected)
