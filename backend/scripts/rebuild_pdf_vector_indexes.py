#!/usr/bin/env python3
"""Atomically enqueue a new projection generation for every eligible PDF."""

from __future__ import annotations

import argparse
import json

from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.core.config import Settings
from app.core.time import utc_now_iso


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Queue a full PDF vector rebuild after Qdrant data loss or an embedding "
            "projection contract change. Existing answer data is not modified."
        )
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm the potentially costly full embedding rebuild.",
    )
    args = parser.parse_args()
    if not args.confirm:
        raise RuntimeError("full vector rebuild requires --confirm")

    settings = Settings()
    settings.validate_runtime_safety()
    if not settings.pdf_vector_indexing_active:
        raise RuntimeError("PDF vector indexing must be enabled before rebuilding")

    repository = SQLiteExcelAssetRepository(settings.database_path)
    repository.initialize()
    queued_count = repository.reconcile_pdf_vector_index_queue(
        embedding_revision=settings.pdf_embedding_revision,
        embedding_dimension=settings.pdf_embedding_dimension,
        batch_size=1_000_000,
        queued_at=utc_now_iso(),
        force=True,
    )
    print(
        json.dumps(
            {
                "status": "queued",
                "queued_count": queued_count,
                "embedding_revision": settings.pdf_embedding_revision,
                "embedding_dimension": settings.pdf_embedding_dimension,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
