import math
from collections.abc import Callable
from typing import Any

import httpx2

from app.core.errors import (
    PdfEmbeddingUnavailable,
    PdfRerankerUnavailable,
    PdfRetrievalDependencyError,
)
from app.ports.pdf_retrieval import (
    DenseVector,
    PdfEmbeddedText,
    PdfEmbeddingInput,
    PdfRerankDocument,
    PdfRerankScore,
    RetrievalCancellationChecker,
)


class OpenAiCompatiblePdfEmbeddingGateway:
    def __init__(
        self,
        *,
        api_base_url: str,
        api_key: str,
        model: str,
        revision: str,
        embedding_dimension: int,
        max_input_characters: int = 12_000,
        timeout_seconds: float = 120.0,
        batch_size: int = 16,
        query_instruction: str = (
            "Given a user question, retrieve relevant enterprise PDF evidence passages"
        ),
        post: Callable[..., httpx2.Response] = httpx2.post,
    ) -> None:
        if batch_size < 1:
            raise ValueError("embedding batch size must be positive")
        if embedding_dimension < 1:
            raise ValueError("embedding dimension must be positive")
        if max_input_characters < 1:
            raise ValueError("embedding input character limit must be positive")
        self._url = f"{api_base_url.rstrip('/')}/embeddings"
        self._api_key = api_key.strip()
        self._model = model.strip()
        self._revision = revision.strip()
        self._timeout_seconds = timeout_seconds
        self._batch_size = batch_size
        self._embedding_dimension = embedding_dimension
        self._max_input_characters = max_input_characters
        self._query_instruction = query_instruction.strip()
        self._post = post
        if not self._model or not self._revision:
            raise ValueError("embedding model and projection revision are required")

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
        query = (
            f"Instruct: {self._query_instruction}\nQuery: {text}"
            if self._query_instruction
            else text
        )
        vectors = self._embed([query])
        _raise_if_cancelled(cancellation_checker)
        return vectors[0]

    def embed_documents(
        self,
        documents: list[PdfEmbeddingInput],
        *,
        cancellation_checker: RetrievalCancellationChecker | None = None,
    ) -> list[PdfEmbeddedText]:
        results: list[PdfEmbeddedText] = []
        for start in range(0, len(documents), self._batch_size):
            _raise_if_cancelled(cancellation_checker)
            batch = documents[start : start + self._batch_size]
            vectors = self._embed([document.text for document in batch])
            results.extend(
                PdfEmbeddedText(text_id=document.text_id, vector=vector)
                for document, vector in zip(batch, vectors, strict=True)
            )
        _raise_if_cancelled(cancellation_checker)
        return results

    def _embed(self, texts: list[str]) -> list[DenseVector]:
        if not texts:
            return []
        if any(len(text) > self._max_input_characters for text in texts):
            raise PdfEmbeddingUnavailable(
                "embedding input exceeds the configured character limit",
                retryable=False,
            )
        try:
            response = self._post(
                self._url,
                headers=_authorization_headers(self._api_key),
                json={
                    "model": self._model,
                    "input": texts,
                    "dimensions": self._embedding_dimension,
                    "encoding_format": "float",
                },
                timeout=self._timeout_seconds,
            )
        except PdfRetrievalDependencyError:
            raise
        except Exception as exc:
            raise PdfEmbeddingUnavailable(
                "embedding transport request failed",
                retryable=True,
            ) from exc
        _raise_for_provider_status(
            response,
            error_type=PdfEmbeddingUnavailable,
            operation="embedding request",
        )
        try:
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list) or len(data) != len(texts):
                raise ValueError("embedding response count does not match the request")
            indexes = [_required_index(item) for item in data]
            if len(set(indexes)) != len(indexes) or set(indexes) != set(range(len(texts))):
                raise ValueError("embedding response indexes are incomplete or duplicated")
            ordered = [item for _, item in sorted(zip(indexes, data, strict=True))]
            vectors = [
                tuple(float(value) for value in _list_field(item, "embedding"))
                for item in ordered
            ]
            if any(len(vector) != self._embedding_dimension for vector in vectors):
                raise ValueError("embedding response dimension does not match configuration")
            if any(not all(math.isfinite(value) for value in vector) for vector in vectors):
                raise ValueError("embedding response contains a non-finite value")
            return vectors
        except Exception as exc:
            raise PdfEmbeddingUnavailable(
                "embedding response violated the required contract",
                retryable=False,
                trace_id=_provider_trace_id(response),
            ) from exc


class HttpPdfRerankerGateway:
    def __init__(
        self,
        *,
        api_base_url: str,
        api_key: str,
        model: str,
        revision: str,
        timeout_seconds: float = 120.0,
        batch_size: int = 16,
        max_batch_characters: int = 120_000,
        instruction: str = (
            "Rank enterprise PDF evidence by how completely it can answer the question"
        ),
        post: Callable[..., httpx2.Response] = httpx2.post,
    ) -> None:
        self._url = f"{api_base_url.rstrip('/')}/rerank"
        self._api_key = api_key.strip()
        self._model = model.strip()
        self._revision = revision.strip()
        self._timeout_seconds = timeout_seconds
        if batch_size < 1:
            raise ValueError("reranker batch size must be positive")
        if max_batch_characters < 1:
            raise ValueError("reranker batch character limit must be positive")
        self._batch_size = batch_size
        self._max_batch_characters = max_batch_characters
        self._instruction = instruction.strip()
        self._post = post
        if not self._model or not self._revision:
            raise ValueError("reranker model and contract revision are required")

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
        if not documents:
            return []
        batches = self._build_batches(query=query, documents=documents)
        scores: list[PdfRerankScore] = []
        for batch in batches:
            _raise_if_cancelled(cancellation_checker)
            scores.extend(self._rank_batch(query=query, documents=batch))
        _raise_if_cancelled(cancellation_checker)
        return scores

    def _build_batches(
        self,
        *,
        query: str,
        documents: list[PdfRerankDocument],
    ) -> list[list[PdfRerankDocument]]:
        if len(query) >= self._max_batch_characters:
            raise PdfRerankerUnavailable(
                "reranker query exceeds the configured batch capacity",
                retryable=False,
            )
        batches: list[list[PdfRerankDocument]] = []
        batch: list[PdfRerankDocument] = []
        batch_characters = len(query)
        for document in documents:
            document_characters = len(document.text)
            if len(query) + document_characters > self._max_batch_characters:
                raise PdfRerankerUnavailable(
                    "reranker document exceeds the configured batch capacity",
                    retryable=False,
                )
            if batch and (
                len(batch) >= self._batch_size
                or batch_characters + document_characters
                > self._max_batch_characters
            ):
                batches.append(batch)
                batch = []
                batch_characters = len(query)
            batch.append(document)
            batch_characters += document_characters
        if batch:
            batches.append(batch)
        return batches

    def _rank_batch(
        self,
        *,
        query: str,
        documents: list[PdfRerankDocument],
    ) -> list[PdfRerankScore]:
        try:
            response = self._post(
                self._url,
                headers=_authorization_headers(self._api_key),
                json={
                    "model": self._model,
                    "query": query,
                    "documents": [document.text for document in documents],
                    "top_n": len(documents),
                    "return_documents": False,
                    **({"instruction": self._instruction} if self._instruction else {}),
                },
                timeout=self._timeout_seconds,
            )
        except PdfRetrievalDependencyError:
            raise
        except Exception as exc:
            raise PdfRerankerUnavailable(
                "reranker transport request failed",
                retryable=True,
            ) from exc
        _raise_for_provider_status(
            response,
            error_type=PdfRerankerUnavailable,
            operation="reranker request",
        )
        try:
            payload = response.json()
            raw_results = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(raw_results, list):
                raise ValueError("reranker response is missing results")
            scores: list[PdfRerankScore] = []
            seen_indexes: set[int] = set()
            for item in raw_results:
                if not isinstance(item, dict):
                    raise ValueError("reranker result must be an object")
                index = int(item.get("index", -1))
                if index < 0 or index >= len(documents) or index in seen_indexes:
                    raise ValueError("reranker returned an invalid document index")
                seen_indexes.add(index)
                score = item.get("relevance_score", item.get("score"))
                parsed_score = float(score)
                if not math.isfinite(parsed_score):
                    raise ValueError("reranker returned a non-finite score")
                scores.append(
                    PdfRerankScore(
                        file_id=documents[index].file_id,
                        score=parsed_score,
                    )
                )
            if len(scores) != len(documents):
                raise ValueError("reranker did not score every document")
        except Exception as exc:
            if isinstance(exc, PdfRerankerUnavailable):
                raise
            raise PdfRerankerUnavailable(
                "reranker response violated the required contract",
                retryable=False,
                trace_id=_provider_trace_id(response),
            ) from exc
        return scores


def _authorization_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _list_field(item: Any, field: str) -> list[Any]:
    if not isinstance(item, dict) or not isinstance(item.get(field), list):
        raise ValueError(f"response item is missing {field}")
    return item[field]


def _required_index(item: Any) -> int:
    if not isinstance(item, dict) or "index" not in item:
        raise ValueError("embedding response item is missing index")
    return int(item["index"])


def _raise_for_provider_status(
    response: httpx2.Response,
    *,
    error_type: type[PdfRetrievalDependencyError],
    operation: str,
) -> None:
    status_code = int(response.status_code)
    if status_code < 400:
        return
    retryable = status_code in {408, 425, 429} or status_code >= 500
    raise error_type(
        f"{operation} failed with HTTP {status_code}",
        retryable=retryable,
        status_code=status_code,
        retry_after_seconds=_retry_after_seconds(response),
        trace_id=_provider_trace_id(response),
    )


def _retry_after_seconds(response: httpx2.Response) -> int | None:
    raw_value = response.headers.get("retry-after", "").strip()
    if not raw_value:
        return None
    try:
        return max(0, int(raw_value))
    except ValueError:
        return None


def _provider_trace_id(response: httpx2.Response) -> str | None:
    for header_name in (
        "x-siliconcloud-trace-id",
        "x-request-id",
        "request-id",
    ):
        trace_id = response.headers.get(header_name, "").strip()
        if trace_id:
            return trace_id[:200]
    return None


def _raise_if_cancelled(
    cancellation_checker: RetrievalCancellationChecker | None,
) -> None:
    if cancellation_checker is not None:
        cancellation_checker()
