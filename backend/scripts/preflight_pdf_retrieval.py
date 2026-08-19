#!/usr/bin/env python3
"""Validate the real PDF retrieval path without exposing document content or secrets."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from app.adapters.retrieval.http_models import (
    HttpPdfRerankerGateway,
    OpenAiCompatiblePdfEmbeddingGateway,
)
from app.adapters.retrieval.qdrant_store import QdrantPdfVectorStore
from app.core.config import Settings
from app.ports.pdf_retrieval import PdfRerankDocument, PdfVectorPoint

_SMOKE_FILE_ID = "__pdf_retrieval_preflight__"
_SMOKE_FINGERPRINT = "pdf-retrieval-preflight-v1"
_SMOKE_CHUNK_ID = "__pdf_retrieval_preflight_chunk__"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate SiliconFlow embedding/reranking and the configured Qdrant "
            "collection using an isolated point that is deleted afterwards."
        )
    )
    parser.add_argument(
        "--bootstrap-qdrant",
        action="store_true",
        help="Create the collection and payload indexes if they do not exist.",
    )
    args = parser.parse_args()

    settings = Settings()
    settings.validate_runtime_safety()
    if not settings.pdf_vector_indexing_active:
        raise RuntimeError("PDF vector indexing must be enabled for retrieval preflight")

    qdrant = QdrantPdfVectorStore(
        api_base_url=settings.pdf_qdrant_api_base_url,
        api_key=settings.pdf_qdrant_api_key,
        collection_name=settings.pdf_qdrant_collection,
        embedding_dimension=settings.pdf_embedding_dimension,
        timeout_seconds=settings.pdf_qdrant_timeout_seconds,
        auto_bootstrap=args.bootstrap_qdrant,
    )
    collection_exists = qdrant.collection_exists()
    ready_index_count = _ready_index_count(settings.database_path)
    if args.bootstrap_qdrant and not collection_exists and ready_index_count:
        raise RuntimeError(
            "refusing to create an empty Qdrant collection while SQLite contains "
            f"{ready_index_count} READY vector indexes; restore Qdrant or run an "
            "explicit full rebuild"
        )
    qdrant.ensure_ready()

    embedding = OpenAiCompatiblePdfEmbeddingGateway(
        api_base_url=settings.pdf_embedding_resolved_api_base_url,
        api_key=settings.pdf_embedding_resolved_api_key,
        model=settings.pdf_embedding_model,
        revision=settings.pdf_embedding_revision,
        embedding_dimension=settings.pdf_embedding_dimension,
        timeout_seconds=settings.pdf_embedding_timeout_seconds,
        batch_size=settings.pdf_embedding_batch_size,
        max_input_characters=settings.pdf_document_chunk_max_characters,
    )
    vector = embedding.embed_query(
        "Verify retrieval connectivity for the enterprise PDF knowledge base."
    )
    point = PdfVectorPoint(
        file_id=_SMOKE_FILE_ID,
        chunk_id=_SMOKE_CHUNK_ID,
        chunk_index=0,
        content_hash=_SMOKE_FINGERPRINT,
        source_fingerprint=_SMOKE_FINGERPRINT,
        embedding_revision=settings.pdf_embedding_revision,
        vector=vector,
        generation=1,
        title="PDF retrieval preflight",
    )
    try:
        qdrant.replace_document_revision(
            file_id=_SMOKE_FILE_ID,
            source_fingerprint=_SMOKE_FINGERPRINT,
            embedding_revision=settings.pdf_embedding_revision,
            generation=1,
            points=[point],
        )
        hits = qdrant.search_document_chunks(
            file_id=_SMOKE_FILE_ID,
            source_fingerprint=_SMOKE_FINGERPRINT,
            embedding_revision=settings.pdf_embedding_revision,
            generation=1,
            query_vector=vector,
            limit=1,
        )
        if len(hits) != 1 or hits[0].chunk_id != _SMOKE_CHUNK_ID:
            raise RuntimeError("Qdrant smoke point could not be retrieved exactly")
    except Exception:
        try:
            qdrant.delete_document_revision(
                file_id=_SMOKE_FILE_ID,
                maximum_generation=1,
            )
        except Exception:
            # Preserve the primary preflight failure; a subsequent consistency
            # audit will report an orphan if cleanup also failed.
            pass
        raise
    else:
        qdrant.delete_document_revision(
            file_id=_SMOKE_FILE_ID,
            maximum_generation=1,
        )

    reranker_checked = False
    if settings.pdf_vector_ranking_active:
        reranker = HttpPdfRerankerGateway(
            api_base_url=settings.pdf_reranker_resolved_api_base_url,
            api_key=settings.pdf_reranker_resolved_api_key,
            model=settings.pdf_reranker_model,
            revision=settings.pdf_reranker_revision,
            timeout_seconds=settings.pdf_reranker_timeout_seconds,
            batch_size=settings.pdf_reranker_batch_size,
            max_batch_characters=settings.pdf_reranker_max_batch_characters,
        )
        scores = reranker.rank_documents(
            query="Which passage describes retrieval connectivity?",
            documents=[
                PdfRerankDocument(
                    file_id="preflight-relevant",
                    text="This passage describes retrieval connectivity.",
                    evidence_chunk_ids=("relevant",),
                ),
                PdfRerankDocument(
                    file_id="preflight-irrelevant",
                    text="This passage describes cafeteria opening hours.",
                    evidence_chunk_ids=("irrelevant",),
                ),
            ],
        )
        if {score.file_id for score in scores} != {
            "preflight-relevant",
            "preflight-irrelevant",
        }:
            raise RuntimeError("reranker preflight did not score every document")
        reranker_checked = True

    print(
        json.dumps(
            {
                "status": "ok",
                "embedding_model": settings.pdf_embedding_model,
                "embedding_dimension": len(vector),
                "qdrant_collection": settings.pdf_qdrant_collection,
                "qdrant_bootstrapped": args.bootstrap_qdrant and not collection_exists,
                "reranker_checked": reranker_checked,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _ready_index_count(database_path: Path) -> int:
    if not database_path.exists():
        return 0
    connection = sqlite3.connect(
        f"file:{database_path}?mode=ro",
        uri=True,
    )
    try:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("pdf_vector_indexes",),
        ).fetchone()
        if table_exists is None:
            return 0
        row = connection.execute(
            "SELECT COUNT(*) FROM pdf_vector_indexes WHERE status = 'ready'"
        ).fetchone()
        return int(row[0]) if row is not None else 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
