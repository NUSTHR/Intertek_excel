import math
import threading
import uuid
from collections.abc import Callable
from typing import Any

import httpx2

from app.core.errors import PdfVectorStoreUnavailable
from app.ports.pdf_retrieval import (
    DenseVector,
    PdfVectorChunkHit,
    PdfVectorPoint,
)

_POINT_NAMESPACE = uuid.UUID("f41ce1b5-a15d-4c89-88d3-f3e3f57401dd")


class QdrantPdfVectorStore:
    def __init__(
        self,
        *,
        api_base_url: str,
        collection_name: str,
        embedding_dimension: int,
        api_key: str = "",
        timeout_seconds: float = 30.0,
        auto_bootstrap: bool = True,
        get: Callable[..., httpx2.Response] = httpx2.get,
        put: Callable[..., httpx2.Response] = httpx2.put,
        post: Callable[..., httpx2.Response] = httpx2.post,
    ) -> None:
        if embedding_dimension < 1:
            raise ValueError("Qdrant embedding dimension must be positive")
        self._base_url = api_base_url.rstrip("/")
        self._collection_name = collection_name.strip()
        self._embedding_dimension = embedding_dimension
        self._api_key = api_key.strip()
        self._timeout_seconds = timeout_seconds
        self._auto_bootstrap = auto_bootstrap
        self._get = get
        self._put = put
        self._post = post
        self._collection_ready = False
        self._collection_lock = threading.Lock()
        if not self._collection_name:
            raise ValueError("Qdrant collection name is required")

    def ensure_ready(self) -> None:
        """Initialize or validate the collection according to bootstrap policy."""
        self._ensure_collection()

    def collection_exists(self) -> bool:
        """Check collection existence without creating or changing database state."""
        try:
            response = self._get(
                f"{self._base_url}/collections/{self._collection_name}",
                headers=self._headers(),
                timeout=self._timeout_seconds,
            )
        except Exception as exc:
            raise PdfVectorStoreUnavailable(
                "Qdrant collection inspection transport failed",
                retryable=True,
            ) from exc
        if response.status_code == 404:
            return False
        _raise_for_qdrant_status(response, operation="collection inspection")
        return True

    def inspect_runtime(self) -> None:
        """Perform a read-only live probe including collection schema validation."""
        try:
            response = self._get(
                f"{self._base_url}/collections/{self._collection_name}",
                headers=self._headers(),
                timeout=self._timeout_seconds,
            )
        except Exception as exc:
            raise PdfVectorStoreUnavailable(
                "Qdrant runtime probe transport failed",
                retryable=True,
            ) from exc
        _raise_for_qdrant_status(response, operation="runtime probe")
        try:
            payload = response.json()
        except Exception as exc:
            raise PdfVectorStoreUnavailable(
                "Qdrant runtime probe returned invalid JSON",
                retryable=False,
            ) from exc
        self._validate_collection(payload)
        self._validate_payload_indexes(payload)

    def collection_point_count(self) -> int:
        """Return the collection point count for operational consistency audits."""
        try:
            response = self._get(
                f"{self._base_url}/collections/{self._collection_name}",
                headers=self._headers(),
                timeout=self._timeout_seconds,
            )
        except Exception as exc:
            raise PdfVectorStoreUnavailable(
                "Qdrant point-count inspection transport failed",
                retryable=True,
            ) from exc
        _raise_for_qdrant_status(response, operation="point-count inspection")
        try:
            return int(response.json()["result"]["points_count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PdfVectorStoreUnavailable(
                "Qdrant collection point count is invalid",
                retryable=False,
            ) from exc

    def count_document_revision(
        self,
        *,
        file_id: str,
        source_fingerprint: str,
        embedding_revision: str,
        generation: int,
    ) -> int:
        """Count exactly one authoritative projection generation."""
        if generation < 1:
            raise ValueError("Qdrant projection generation must be positive")
        self._ensure_collection()
        payload = self._request(
            self._post,
            f"/collections/{self._collection_name}/points/count",
            json={
                "filter": _projection_filter(
                    file_id,
                    source_fingerprint,
                    embedding_revision,
                    generation,
                ),
                "exact": True,
            },
        )
        try:
            return int(payload["result"]["count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PdfVectorStoreUnavailable(
                "Qdrant document point count is invalid",
                retryable=False,
            ) from exc

    def replace_document_revision(
        self,
        *,
        file_id: str,
        source_fingerprint: str,
        embedding_revision: str,
        points: list[PdfVectorPoint],
        generation: int = 1,
    ) -> None:
        if generation < 1:
            raise ValueError("Qdrant projection generation must be positive")
        if any(point.file_id != file_id for point in points):
            raise ValueError("Qdrant points must belong to the requested file")
        if any(point.source_fingerprint != source_fingerprint for point in points):
            raise ValueError("Qdrant points must use the requested source fingerprint")
        if any(point.embedding_revision != embedding_revision for point in points):
            raise ValueError("Qdrant points must use the requested embedding revision")
        if any(point.generation != generation for point in points):
            raise ValueError("Qdrant points must use the requested generation")
        if any(len(point.vector) != self._embedding_dimension for point in points):
            raise ValueError("Qdrant point dimension does not match the collection")
        if any(
            not all(math.isfinite(value) for value in point.vector) for point in points
        ):
            raise ValueError("Qdrant point contains a non-finite vector value")
        self._ensure_collection()
        self._delete_by_filter(
            _projection_filter(
                file_id,
                source_fingerprint,
                embedding_revision,
                generation,
            )
        )
        if not points:
            return
        self._request(
            self._put,
            f"/collections/{self._collection_name}/points?wait=true",
            json={
                "points": [
                    {
                        "id": str(
                            uuid.uuid5(
                                _POINT_NAMESPACE,
                                "\x1f".join(
                                    [
                                        point.file_id,
                                        point.chunk_id,
                                        point.source_fingerprint,
                                        point.embedding_revision,
                                        str(point.generation),
                                    ]
                                ),
                            )
                        ),
                        "vector": list(point.vector),
                        "payload": {
                            "file_id": point.file_id,
                            "chunk_id": point.chunk_id,
                            "chunk_index": point.chunk_index,
                            "content_hash": point.content_hash,
                            "source_fingerprint": point.source_fingerprint,
                            "embedding_revision": point.embedding_revision,
                            "generation": point.generation,
                            "page_label": point.page_label,
                            "title": point.title,
                        },
                    }
                    for point in points
                ]
            },
        )

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
        if limit < 1:
            raise ValueError("Qdrant search limit must be positive")
        if len(query_vector) != self._embedding_dimension:
            raise ValueError("Qdrant query dimension does not match the collection")
        if not all(math.isfinite(value) for value in query_vector):
            raise ValueError("Qdrant query contains a non-finite vector value")
        self._ensure_collection()
        payload = self._request(
            self._post,
            f"/collections/{self._collection_name}/points/search",
            json={
                "vector": list(query_vector),
                "filter": _projection_filter(
                    file_id,
                    source_fingerprint,
                    embedding_revision,
                    generation,
                ),
                "limit": limit,
                "with_payload": True,
                "with_vector": False,
            },
        )
        raw_results = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(raw_results, list):
            raise PdfVectorStoreUnavailable(
                "Qdrant search response is missing result",
                retryable=False,
            )
        return [_to_hit(item) for item in raw_results]

    def delete_document_revision(
        self,
        *,
        file_id: str,
        source_fingerprint: str | None = None,
        embedding_revision: str | None = None,
        maximum_generation: int | None = None,
    ) -> None:
        self._ensure_collection()
        conditions = [_match("file_id", file_id)]
        if source_fingerprint is not None:
            conditions.append(_match("source_fingerprint", source_fingerprint))
        if embedding_revision is not None:
            conditions.append(_match("embedding_revision", embedding_revision))
        projection_filter: dict[str, Any] = {"must": conditions}
        if maximum_generation is not None:
            if maximum_generation < 1:
                raise ValueError("Qdrant maximum generation must be positive")
            projection_filter["should"] = [
                {
                    "key": "generation",
                    "range": {"lte": maximum_generation},
                },
                {"is_empty": {"key": "generation"}},
            ]
        self._delete_by_filter(projection_filter)

    def _ensure_collection(self) -> None:
        if self._collection_ready:
            return
        with self._collection_lock:
            if self._collection_ready:
                return
            try:
                response = self._get(
                    f"{self._base_url}/collections/{self._collection_name}",
                    headers=self._headers(),
                    timeout=self._timeout_seconds,
                )
                if response.status_code == 404:
                    if not self._auto_bootstrap:
                        raise PdfVectorStoreUnavailable(
                            "Qdrant collection does not exist and automatic bootstrap is disabled",
                            retryable=False,
                            status_code=404,
                        )
                    self._request(
                        self._put,
                        f"/collections/{self._collection_name}",
                        json={
                            "vectors": {
                                "size": self._embedding_dimension,
                                "distance": "Cosine",
                            }
                        },
                    )
                else:
                    _raise_for_qdrant_status(response, operation="collection inspection")
                    self._validate_collection(response.json())
                if self._auto_bootstrap:
                    self._ensure_payload_indexes()
                else:
                    self._validate_payload_indexes(response.json())
                self._collection_ready = True
            except Exception as exc:
                if isinstance(exc, PdfVectorStoreUnavailable):
                    raise
                raise PdfVectorStoreUnavailable(
                    f"Qdrant collection initialization failed: {exc}",
                    retryable=True,
                ) from exc

    def _ensure_payload_indexes(self) -> None:
        for field_name, field_schema in (
            ("file_id", "keyword"),
            ("source_fingerprint", "keyword"),
            ("embedding_revision", "keyword"),
            ("generation", "integer"),
        ):
            self._request(
                self._put,
                f"/collections/{self._collection_name}/index?wait=true",
                json={
                    "field_name": field_name,
                    "field_schema": field_schema,
                },
            )

    def _validate_collection(self, payload: Any) -> None:
        try:
            vectors = payload["result"]["config"]["params"]["vectors"]
            size = int(vectors["size"])
            distance = str(vectors["distance"]).casefold()
        except (KeyError, TypeError, ValueError) as exc:
            raise PdfVectorStoreUnavailable(
                f"Qdrant collection configuration is invalid: {exc}",
                retryable=False,
            ) from exc
        if size != self._embedding_dimension or distance != "cosine":
            raise PdfVectorStoreUnavailable(
                "Qdrant collection vector size or distance does not match configuration",
                retryable=False,
            )

    def _validate_payload_indexes(self, payload: Any) -> None:
        try:
            payload_schema = payload["result"]["payload_schema"]
        except (KeyError, TypeError) as exc:
            raise PdfVectorStoreUnavailable(
                "Qdrant collection payload schema is missing",
                retryable=False,
            ) from exc
        if not isinstance(payload_schema, dict):
            raise PdfVectorStoreUnavailable(
                "Qdrant collection payload schema is invalid",
                retryable=False,
            )
        expected = {
            "file_id": "keyword",
            "source_fingerprint": "keyword",
            "embedding_revision": "keyword",
            "generation": "integer",
        }
        mismatches = [
            field_name
            for field_name, field_type in expected.items()
            if _payload_schema_type(payload_schema.get(field_name)) != field_type
        ]
        if mismatches:
            raise PdfVectorStoreUnavailable(
                "Qdrant collection is missing required payload indexes: "
                + ", ".join(mismatches),
                retryable=False,
            )

    def _delete_by_filter(self, filter_payload: dict[str, Any]) -> None:
        self._request(
            self._post,
            f"/collections/{self._collection_name}/points/delete?wait=true",
            json={"filter": filter_payload},
        )

    def _request(
        self,
        request: Callable[..., httpx2.Response],
        path: str,
        *,
        json: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = request(
                f"{self._base_url}{path}",
                headers=self._headers(),
                json=json,
                timeout=self._timeout_seconds,
            )
        except Exception as exc:
            raise PdfVectorStoreUnavailable(
                "Qdrant transport request failed",
                retryable=True,
            ) from exc
        try:
            _raise_for_qdrant_status(response, operation="request")
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Qdrant response must be an object")
            return payload
        except Exception as exc:
            if isinstance(exc, PdfVectorStoreUnavailable):
                raise
            raise PdfVectorStoreUnavailable(
                "Qdrant response violated the required contract",
                retryable=False,
            ) from exc

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["api-key"] = self._api_key
        return headers


def _projection_filter(
    file_id: str,
    source_fingerprint: str,
    embedding_revision: str,
    generation: int,
) -> dict[str, Any]:
    projection_filter: dict[str, Any] = {
        "must": [
            _match("file_id", file_id),
            _match("source_fingerprint", source_fingerprint),
            _match("embedding_revision", embedding_revision),
        ]
    }
    if generation == 1:
        projection_filter["should"] = [
            _match("generation", generation),
            {"is_empty": {"key": "generation"}},
        ]
    else:
        projection_filter["must"].append(_match("generation", generation))
    return projection_filter


def _match(key: str, value: str | int) -> dict[str, Any]:
    return {"key": key, "match": {"value": value}}


def _to_hit(item: Any) -> PdfVectorChunkHit:
    if not isinstance(item, dict) or not isinstance(item.get("payload"), dict):
        raise PdfVectorStoreUnavailable(
            "Qdrant hit is missing payload",
            retryable=False,
        )
    payload = item["payload"]
    try:
        score = float(item["score"])
        if not math.isfinite(score):
            raise ValueError("Qdrant hit score is non-finite")
        return PdfVectorChunkHit(
            file_id=str(payload["file_id"]),
            chunk_id=str(payload["chunk_id"]),
            chunk_index=int(payload["chunk_index"]),
            score=score,
            source_fingerprint=str(payload["source_fingerprint"]),
            embedding_revision=str(payload["embedding_revision"]),
            generation=int(payload.get("generation", 1)),
            page_label=(
                str(payload["page_label"])
                if payload.get("page_label") is not None
                else None
            ),
            title=str(payload.get("title", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PdfVectorStoreUnavailable(
            "Qdrant hit payload is invalid",
            retryable=False,
        ) from exc


def _payload_schema_type(schema: Any) -> str:
    if isinstance(schema, str):
        return schema.casefold()
    if isinstance(schema, dict):
        return str(schema.get("data_type", "")).casefold()
    return ""


def _raise_for_qdrant_status(
    response: httpx2.Response,
    *,
    operation: str,
) -> None:
    status_code = int(response.status_code)
    if status_code < 400:
        return
    retryable = status_code in {408, 425, 429} or status_code >= 500
    retry_after_seconds: int | None = None
    raw_retry_after = response.headers.get("retry-after", "").strip()
    if raw_retry_after:
        try:
            retry_after_seconds = max(0, int(raw_retry_after))
        except ValueError:
            retry_after_seconds = None
    trace_id = (
        response.headers.get("x-request-id", "").strip()
        or response.headers.get("request-id", "").strip()
        or None
    )
    raise PdfVectorStoreUnavailable(
        f"Qdrant {operation} failed with HTTP {status_code}",
        retryable=retryable,
        status_code=status_code,
        retry_after_seconds=retry_after_seconds,
        trace_id=trace_id[:200] if trace_id else None,
    )
