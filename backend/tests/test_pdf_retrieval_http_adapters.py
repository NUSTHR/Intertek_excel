import httpx2
import pytest

from app.adapters.retrieval.http_models import (
    HttpPdfRerankerGateway,
    OpenAiCompatiblePdfEmbeddingGateway,
)
from app.adapters.retrieval.qdrant_store import QdrantPdfVectorStore
from app.core.errors import (
    PdfEmbeddingUnavailable,
    PdfRerankerUnavailable,
    PdfVectorStoreUnavailable,
)
from app.ports.pdf_retrieval import (
    PdfEmbeddingInput,
    PdfRerankDocument,
    PdfVectorPoint,
)


def _response(status_code: int, *, json=None) -> httpx2.Response:
    return httpx2.Response(
        status_code,
        json=json,
        request=httpx2.Request("POST", "http://adapter.test"),
    )


def test_embedding_adapter_batches_documents_and_preserves_ids() -> None:
    calls: list[dict] = []

    def post(_url, **kwargs):
        calls.append(kwargs["json"])
        return _response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": [float(index), 1.0]}
                    for index, _text in enumerate(kwargs["json"]["input"])
                ]
            },
        )

    gateway = OpenAiCompatiblePdfEmbeddingGateway(
        api_base_url="http://embedding.test/v1",
        api_key="secret",
        model="Qwen/Qwen3-Embedding-8B",
        revision="Qwen/Qwen3-Embedding-8B@commit",
        embedding_dimension=2,
        batch_size=2,
        post=post,
    )
    embedded = gateway.embed_documents(
        [PdfEmbeddingInput(text_id=f"chunk-{index}", text=str(index)) for index in range(3)]
    )

    assert [item.text_id for item in embedded] == ["chunk-0", "chunk-1", "chunk-2"]
    assert len(calls) == 2
    assert all(call["model"] == "Qwen/Qwen3-Embedding-8B" for call in calls)
    assert all(call["dimensions"] == 2 for call in calls)
    assert all(call["encoding_format"] == "float" for call in calls)


def test_embedding_adapter_rejects_incomplete_response() -> None:
    gateway = OpenAiCompatiblePdfEmbeddingGateway(
        api_base_url="http://embedding.test/v1",
        api_key="",
        model="embedding",
        revision="embedding@commit",
        embedding_dimension=2,
        post=lambda *_args, **_kwargs: _response(200, json={"data": []}),
    )

    with pytest.raises(PdfEmbeddingUnavailable, match="contract"):
        gateway.embed_query("question")


def test_embedding_adapter_classifies_rate_limit_as_retryable() -> None:
    gateway = OpenAiCompatiblePdfEmbeddingGateway(
        api_base_url="http://embedding.test/v1",
        api_key="secret",
        model="embedding",
        revision="embedding-v1",
        embedding_dimension=2,
        post=lambda *_args, **_kwargs: httpx2.Response(
            429,
            headers={
                "retry-after": "17",
                "x-siliconcloud-trace-id": "trace-123",
            },
            request=httpx2.Request("POST", "http://adapter.test"),
        ),
    )

    with pytest.raises(PdfEmbeddingUnavailable) as captured:
        gateway.embed_query("question")

    assert captured.value.retryable is True
    assert captured.value.status_code == 429
    assert captured.value.retry_after_seconds == 17
    assert captured.value.trace_id == "trace-123"


def test_embedding_adapter_rejects_wrong_dimension_without_retry() -> None:
    gateway = OpenAiCompatiblePdfEmbeddingGateway(
        api_base_url="http://embedding.test/v1",
        api_key="secret",
        model="embedding",
        revision="embedding-v1",
        embedding_dimension=2,
        post=lambda *_args, **_kwargs: _response(
            200,
            json={"data": [{"index": 0, "embedding": [1.0]}]},
        ),
    )

    with pytest.raises(PdfEmbeddingUnavailable) as captured:
        gateway.embed_query("question")

    assert captured.value.retryable is False


def test_reranker_maps_provider_indexes_back_to_file_ids() -> None:
    gateway = HttpPdfRerankerGateway(
        api_base_url="http://reranker.test/v1",
        api_key="",
        model="Qwen/Qwen3-Reranker-8B",
        revision="Qwen/Qwen3-Reranker-8B@commit",
        post=lambda *_args, **_kwargs: _response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.2},
                ]
            },
        ),
    )

    scores = gateway.rank_documents(
        query="question",
        documents=[
            PdfRerankDocument("file-a", "alpha", ("chunk-a",)),
            PdfRerankDocument("file-b", "beta", ("chunk-b",)),
        ],
    )

    assert [(score.file_id, score.score) for score in scores] == [
        ("file-b", 0.9),
        ("file-a", 0.2),
    ]


def test_reranker_rejects_non_finite_score_without_retry() -> None:
    gateway = HttpPdfRerankerGateway(
        api_base_url="http://reranker.test/v1",
        api_key="secret",
        model="reranker",
        revision="reranker-v1",
        post=lambda *_args, **_kwargs: _response(
            200,
            json={"results": [{"index": 0, "relevance_score": "nan"}]},
        ),
    )

    with pytest.raises(PdfRerankerUnavailable) as captured:
        gateway.rank_documents(
            query="question",
            documents=[PdfRerankDocument("file-a", "alpha", ("chunk-a",))],
        )

    assert captured.value.retryable is False


def test_reranker_batches_every_candidate_without_dropping_documents() -> None:
    calls: list[dict] = []

    def post(_url, **kwargs):
        calls.append(kwargs["json"])
        return _response(
            200,
            json={"results": [{"index": 0, "relevance_score": 0.5}]},
        )

    gateway = HttpPdfRerankerGateway(
        api_base_url="http://reranker.test/v1",
        api_key="secret",
        model="reranker",
        revision="reranker-v1",
        batch_size=1,
        max_batch_characters=100,
        post=post,
    )
    scores = gateway.rank_documents(
        query="question",
        documents=[
            PdfRerankDocument("file-a", "alpha", ("chunk-a",)),
            PdfRerankDocument("file-b", "beta", ("chunk-b",)),
        ],
    )

    assert [score.file_id for score in scores] == ["file-a", "file-b"]
    assert len(calls) == 2
    assert all(call["top_n"] == 1 for call in calls)


def test_qdrant_store_creates_collection_replaces_and_searches_projection() -> None:
    puts: list[tuple[str, dict]] = []
    posts: list[tuple[str, dict]] = []

    def get(_url, **_kwargs):
        return _response(404)

    def put(url, **kwargs):
        puts.append((url, kwargs["json"]))
        return _response(200, json={"result": {}})

    def post(url, **kwargs):
        posts.append((url, kwargs["json"]))
        if url.endswith("/points/search"):
            return _response(
                200,
                json={
                    "result": [
                        {
                            "score": 0.8,
                            "payload": {
                                "file_id": "file-1",
                                "chunk_id": "chunk-1",
                                "chunk_index": 0,
                                "source_fingerprint": "fingerprint-1",
                                "embedding_revision": "embedding@commit",
                                "page_label": "1",
                                "title": "Title",
                            },
                        }
                    ]
                },
            )
        return _response(200, json={"result": {}})

    store = QdrantPdfVectorStore(
        api_base_url="http://qdrant.test",
        collection_name="pdf_chunks",
        embedding_dimension=2,
        get=get,
        put=put,
        post=post,
    )
    point = PdfVectorPoint(
        file_id="file-1",
        chunk_id="chunk-1",
        chunk_index=0,
        content_hash="hash-1",
        source_fingerprint="fingerprint-1",
        embedding_revision="embedding@commit",
        vector=(0.1, 0.2),
    )

    store.replace_document_revision(
        file_id="file-1",
        source_fingerprint="fingerprint-1",
        embedding_revision="embedding@commit",
        points=[point],
    )
    hits = store.search_document_chunks(
        file_id="file-1",
        source_fingerprint="fingerprint-1",
        embedding_revision="embedding@commit",
        query_vector=(0.1, 0.2),
        limit=4,
    )
    store.delete_document_revision(file_id="file-1", maximum_generation=2)

    assert puts[0][1] == {"vectors": {"size": 2, "distance": "Cosine"}}
    assert [request[1] for request in puts[1:5]] == [
        {"field_name": "file_id", "field_schema": "keyword"},
        {"field_name": "source_fingerprint", "field_schema": "keyword"},
        {"field_name": "embedding_revision", "field_schema": "keyword"},
        {"field_name": "generation", "field_schema": "integer"},
    ]
    assert len(puts[5][1]["points"]) == 1
    assert puts[5][1]["points"][0]["payload"]["generation"] == 1
    assert "/points/delete?wait=true" in posts[0][0]
    assert posts[-1][1]["filter"]["should"] == [
        {"key": "generation", "range": {"lte": 2}},
        {"is_empty": {"key": "generation"}},
    ]
    assert hits[0].chunk_id == "chunk-1"
    assert hits[0].score == 0.8
    assert hits[0].generation == 1


def test_qdrant_store_rejects_existing_collection_dimension_mismatch() -> None:
    store = QdrantPdfVectorStore(
        api_base_url="http://qdrant.test",
        collection_name="pdf_chunks",
        embedding_dimension=4096,
        get=lambda *_args, **_kwargs: _response(
            200,
            json={
                "result": {
                    "config": {
                        "params": {"vectors": {"size": 1024, "distance": "Cosine"}}
                    }
                }
            },
        ),
    )

    with pytest.raises(PdfVectorStoreUnavailable, match="does not match"):
        store.delete_document_revision(file_id="file-1")


def test_qdrant_store_refuses_runtime_bootstrap_when_collection_is_missing() -> None:
    store = QdrantPdfVectorStore(
        api_base_url="http://qdrant.test",
        collection_name="pdf_chunks",
        embedding_dimension=2,
        auto_bootstrap=False,
        get=lambda *_args, **_kwargs: _response(404),
    )

    with pytest.raises(PdfVectorStoreUnavailable) as captured:
        store.ensure_ready()

    assert captured.value.retryable is False
    assert captured.value.status_code == 404


def test_qdrant_store_requires_payload_indexes_when_bootstrap_is_disabled() -> None:
    store = QdrantPdfVectorStore(
        api_base_url="http://qdrant.test",
        collection_name="pdf_chunks",
        embedding_dimension=2,
        auto_bootstrap=False,
        get=lambda *_args, **_kwargs: _response(
            200,
            json={
                "result": {
                    "config": {
                        "params": {"vectors": {"size": 2, "distance": "Cosine"}}
                    },
                    "payload_schema": {
                        "file_id": {"data_type": "keyword"},
                    },
                }
            },
        ),
    )

    with pytest.raises(PdfVectorStoreUnavailable, match="payload indexes") as captured:
        store.ensure_ready()

    assert captured.value.retryable is False


def test_qdrant_store_counts_an_exact_projection_for_consistency_audit() -> None:
    collection_payload = {
        "result": {
            "config": {
                "params": {"vectors": {"size": 2, "distance": "Cosine"}}
            },
            "payload_schema": {
                "file_id": {"data_type": "keyword"},
                "source_fingerprint": {"data_type": "keyword"},
                "embedding_revision": {"data_type": "keyword"},
                "generation": {"data_type": "integer"},
            },
            "points_count": 2,
        }
    }
    store = QdrantPdfVectorStore(
        api_base_url="http://qdrant.test",
        collection_name="pdf_chunks",
        embedding_dimension=2,
        auto_bootstrap=False,
        get=lambda *_args, **_kwargs: _response(200, json=collection_payload),
        post=lambda *_args, **_kwargs: _response(
            200,
            json={"result": {"count": 2}},
        ),
    )

    assert store.count_document_revision(
        file_id="file-1",
        source_fingerprint="fingerprint-1",
        embedding_revision="embedding-v1",
        generation=3,
    ) == 2
    assert store.collection_point_count() == 2
