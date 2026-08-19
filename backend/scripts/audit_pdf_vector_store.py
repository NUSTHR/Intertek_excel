#!/usr/bin/env python3
"""Compare authoritative READY vector state with live Qdrant point counts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.adapters.retrieval.qdrant_store import QdrantPdfVectorStore
from app.core.config import Settings


@dataclass(frozen=True)
class ReadyProjection:
    file_id: str
    source_fingerprint: str
    embedding_revision: str
    generation: int
    indexed_chunk_count: int


def main() -> int:
    settings = Settings()
    settings.validate_runtime_safety()
    if not settings.pdf_vector_indexing_active:
        raise RuntimeError("PDF vector indexing must be enabled for consistency audit")

    projections = _load_ready_projections(settings.database_path)
    qdrant = QdrantPdfVectorStore(
        api_base_url=settings.pdf_qdrant_api_base_url,
        api_key=settings.pdf_qdrant_api_key,
        collection_name=settings.pdf_qdrant_collection,
        embedding_dimension=settings.pdf_embedding_dimension,
        timeout_seconds=settings.pdf_qdrant_timeout_seconds,
        auto_bootstrap=False,
    )
    qdrant.ensure_ready()

    mismatches: list[dict[str, str | int]] = []
    expected_total = 0
    for projection in projections:
        expected_total += projection.indexed_chunk_count
        actual_count = qdrant.count_document_revision(
            file_id=projection.file_id,
            source_fingerprint=projection.source_fingerprint,
            embedding_revision=projection.embedding_revision,
            generation=projection.generation,
        )
        if actual_count != projection.indexed_chunk_count:
            mismatches.append(
                {
                    "file_id": projection.file_id,
                    "generation": projection.generation,
                    "expected_count": projection.indexed_chunk_count,
                    "actual_count": actual_count,
                }
            )

    total_points = qdrant.collection_point_count()
    possible_orphan_count = max(0, total_points - expected_total)
    status = "failed" if mismatches or total_points < expected_total else (
        "warning" if possible_orphan_count else "ok"
    )
    print(
        json.dumps(
            {
                "status": status,
                "ready_projection_count": len(projections),
                "expected_current_points": expected_total,
                "qdrant_total_points": total_points,
                "possible_orphan_points": possible_orphan_count,
                "mismatches": mismatches,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if status == "failed" else 0


def _load_ready_projections(database_path: Path) -> list[ReadyProjection]:
    if not database_path.exists():
        return []
    connection = sqlite3.connect(
        f"file:{database_path}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("pdf_vector_indexes",),
        ).fetchone()
        if table_exists is None:
            return []
        rows = connection.execute(
            """
            SELECT
              file_id, source_fingerprint, embedding_revision,
              generation, indexed_chunk_count
            FROM pdf_vector_indexes
            WHERE status = 'ready'
            ORDER BY file_id
            """
        ).fetchall()
        return [
            ReadyProjection(
                file_id=str(row["file_id"]),
                source_fingerprint=str(row["source_fingerprint"]),
                embedding_revision=str(row["embedding_revision"]),
                generation=int(row["generation"]),
                indexed_chunk_count=int(row["indexed_chunk_count"]),
            )
            for row in rows
        ]
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
