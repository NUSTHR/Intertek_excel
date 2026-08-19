import math
from hashlib import sha256

from app.ports.pdf_retrieval import (
    DenseVector,
    PdfEmbeddedText,
    PdfEmbeddingInput,
    PdfRerankDocument,
    PdfRerankScore,
    PdfVectorChunkHit,
    PdfVectorPoint,
    RetrievalCancellationChecker,
)


class FakePdfEmbeddingGateway:
    def __init__(
        self,
        *,
        revision: str = "fake-embedding@1",
        dimension: int = 8,
        error: Exception | None = None,
    ) -> None:
        if dimension < 1:
            raise ValueError("fake embedding dimension must be positive")
        self._revision = revision
        self._dimension = dimension
        self._error = error
        self.query_calls: list[str] = []
        self.document_calls: list[list[PdfEmbeddingInput]] = []

    @property
    def revision(self) -> str:
        return self._revision

    def embed_query(
        self,
        text: str,
        *,
        cancellation_checker: RetrievalCancellationChecker | None = None,
    ) -> DenseVector:
        _raise_if_cancelled(cancellation_checker)
        self._raise_configured_error()
        self.query_calls.append(text)
        vector = self._vector(text)
        _raise_if_cancelled(cancellation_checker)
        return vector

    def embed_documents(
        self,
        documents: list[PdfEmbeddingInput],
        *,
        cancellation_checker: RetrievalCancellationChecker | None = None,
    ) -> list[PdfEmbeddedText]:
        _raise_if_cancelled(cancellation_checker)
        self._raise_configured_error()
        self.document_calls.append(list(documents))
        embedded = [
            PdfEmbeddedText(
                text_id=document.text_id,
                vector=self._vector(document.text),
            )
            for document in documents
        ]
        _raise_if_cancelled(cancellation_checker)
        return embedded

    def _vector(self, text: str) -> DenseVector:
        digest = sha256(text.encode("utf-8")).digest()
        raw = [
            (digest[index % len(digest)] - 127.5) / 127.5
            for index in range(self._dimension)
        ]
        magnitude = math.sqrt(sum(value * value for value in raw)) or 1.0
        return tuple(value / magnitude for value in raw)

    def _raise_configured_error(self) -> None:
        if self._error is not None:
            raise self._error


class FakePdfVectorStore:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self._revisions: dict[
            tuple[str, str, str, int], tuple[PdfVectorPoint, ...]
        ] = {}
        self.replace_calls: list[tuple[str, str, str, int]] = []
        self.search_calls: list[tuple[str, str, str, int, int]] = []
        self.delete_calls: list[tuple[str, str | None, str | None, int | None]] = []

    def replace_document_revision(
        self,
        *,
        file_id: str,
        source_fingerprint: str,
        embedding_revision: str,
        points: list[PdfVectorPoint],
        generation: int = 1,
    ) -> None:
        self._raise_configured_error()
        if any(point.file_id != file_id for point in points):
            raise ValueError("all vector points must belong to the requested file")
        if any(point.source_fingerprint != source_fingerprint for point in points):
            raise ValueError("all vector points must use the requested fingerprint")
        if any(point.embedding_revision != embedding_revision for point in points):
            raise ValueError("all vector points must use the requested revision")
        if any(point.generation != generation for point in points):
            raise ValueError("all vector points must use the requested generation")
        chunk_ids = [point.chunk_id for point in points]
        if len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("vector point chunk IDs must be unique")
        key = (file_id, source_fingerprint, embedding_revision, generation)
        self._revisions[key] = tuple(points)
        self.replace_calls.append(key)

    def search_document_chunks(
        self,
        *,
        file_id: str,
        source_fingerprint: str,
        embedding_revision: str,
        query_vector: DenseVector,
        limit: int,
        generation: int = 1,
    ) -> list[PdfVectorChunkHit]:
        self._raise_configured_error()
        if limit < 1:
            raise ValueError("vector search limit must be positive")
        key = (file_id, source_fingerprint, embedding_revision, generation)
        self.search_calls.append((*key, limit))
        points = self._revisions.get(key, ())
        scored = sorted(
            (
                PdfVectorChunkHit(
                    file_id=point.file_id,
                    chunk_id=point.chunk_id,
                    chunk_index=point.chunk_index,
                    score=_cosine_similarity(query_vector, point.vector),
                    source_fingerprint=point.source_fingerprint,
                    embedding_revision=point.embedding_revision,
                    generation=point.generation,
                    page_label=point.page_label,
                    title=point.title,
                )
                for point in points
            ),
            key=lambda hit: (-hit.score, hit.chunk_id),
        )
        return scored[:limit]

    def delete_document_revision(
        self,
        *,
        file_id: str,
        source_fingerprint: str | None = None,
        embedding_revision: str | None = None,
        maximum_generation: int | None = None,
    ) -> None:
        self._raise_configured_error()
        matching_keys = [
            key
            for key in self._revisions
            if key[0] == file_id
            and (source_fingerprint is None or key[1] == source_fingerprint)
            and (embedding_revision is None or key[2] == embedding_revision)
            and (maximum_generation is None or key[3] <= maximum_generation)
        ]
        for key in matching_keys:
            self._revisions.pop(key, None)
        self.delete_calls.append(
            (file_id, source_fingerprint, embedding_revision, maximum_generation)
        )

    def _raise_configured_error(self) -> None:
        if self._error is not None:
            raise self._error


class FakePdfRerankerGateway:
    def __init__(
        self,
        *,
        revision: str = "fake-reranker@1",
        scores: dict[str, float] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._revision = revision
        self._scores = scores
        self._error = error
        self.calls: list[tuple[str, list[PdfRerankDocument]]] = []

    @property
    def revision(self) -> str:
        return self._revision

    def rank_documents(
        self,
        *,
        query: str,
        documents: list[PdfRerankDocument],
        cancellation_checker: RetrievalCancellationChecker | None = None,
    ) -> list[PdfRerankScore]:
        _raise_if_cancelled(cancellation_checker)
        if self._error is not None:
            raise self._error
        self.calls.append((query, list(documents)))
        query_terms = set(query.casefold().split())
        results = [
            PdfRerankScore(
                file_id=document.file_id,
                score=(
                    self._scores[document.file_id]
                    if self._scores is not None
                    else _term_overlap_score(query_terms, document.text)
                ),
            )
            for document in documents
        ]
        _raise_if_cancelled(cancellation_checker)
        return results


def _raise_if_cancelled(
    cancellation_checker: RetrievalCancellationChecker | None,
) -> None:
    if cancellation_checker is not None:
        cancellation_checker()


def _term_overlap_score(query_terms: set[str], document_text: str) -> float:
    if not query_terms:
        return 0.0
    document_terms = set(document_text.casefold().split())
    return len(query_terms & document_terms) / len(query_terms)


def _cosine_similarity(left: DenseVector, right: DenseVector) -> float:
    if len(left) != len(right):
        raise ValueError("fake vector dimensions must match")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )
