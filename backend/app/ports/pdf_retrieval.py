from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

RetrievalCancellationChecker = Callable[[], None]
DenseVector = tuple[float, ...]


@dataclass(frozen=True)
class PdfEmbeddingInput:
    text_id: str
    text: str


@dataclass(frozen=True)
class PdfEmbeddedText:
    text_id: str
    vector: DenseVector


@dataclass(frozen=True)
class PdfVectorPoint:
    file_id: str
    chunk_id: str
    chunk_index: int
    content_hash: str
    source_fingerprint: str
    embedding_revision: str
    vector: DenseVector
    generation: int = 1
    page_label: str | None = None
    title: str = ""


@dataclass(frozen=True)
class PdfVectorChunkHit:
    file_id: str
    chunk_id: str
    chunk_index: int
    score: float
    source_fingerprint: str
    embedding_revision: str
    generation: int = 1
    page_label: str | None = None
    title: str = ""


@dataclass(frozen=True)
class PdfRerankDocument:
    file_id: str
    text: str
    evidence_chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class PdfRerankScore:
    file_id: str
    score: float


class PdfEmbeddingGateway(Protocol):
    @property
    def revision(self) -> str:
        ...

    def embed_query(
        self,
        text: str,
        *,
        cancellation_checker: RetrievalCancellationChecker | None = None,
    ) -> DenseVector:
        ...

    def embed_documents(
        self,
        documents: list[PdfEmbeddingInput],
        *,
        cancellation_checker: RetrievalCancellationChecker | None = None,
    ) -> list[PdfEmbeddedText]:
        ...


class PdfVectorStore(Protocol):
    def replace_document_revision(
        self,
        *,
        file_id: str,
        source_fingerprint: str,
        embedding_revision: str,
        points: list[PdfVectorPoint],
        generation: int = 1,
    ) -> None:
        ...

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
        ...

    def delete_document_revision(
        self,
        *,
        file_id: str,
        source_fingerprint: str | None = None,
        embedding_revision: str | None = None,
        maximum_generation: int | None = None,
    ) -> None:
        ...


class PdfRerankerGateway(Protocol):
    @property
    def revision(self) -> str:
        ...

    def rank_documents(
        self,
        *,
        query: str,
        documents: list[PdfRerankDocument],
        cancellation_checker: RetrievalCancellationChecker | None = None,
    ) -> list[PdfRerankScore]:
        ...
