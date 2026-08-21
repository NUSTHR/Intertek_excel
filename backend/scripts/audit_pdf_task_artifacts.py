#!/usr/bin/env python3
"""Audit and optionally remove unreferenced PDF parser task artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import Settings


def audit_task_artifacts(
    *,
    database_path: Path,
    storage_root: Path,
    retention_days: int,
    delete: bool = False,
) -> dict[str, object]:
    if retention_days < 0:
        raise ValueError("retention_days must not be negative")
    resolved_database = database_path.expanduser().resolve()
    resolved_storage = storage_root.expanduser().resolve()
    files_root = (resolved_storage / "pdf-knowledge" / "files").resolve()
    if not resolved_database.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {resolved_database}")

    connection = sqlite3.connect(
        f"{resolved_database.as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        referenced_paths, unsafe_references = _referenced_artifact_paths(
            connection,
            storage_root=resolved_storage,
        )
        active_tasks = {
            (str(row["file_id"]), str(row["task_id"]))
            for row in connection.execute(
                """
                SELECT file_id, task_id
                FROM pdf_upload_tasks
                WHERE file_id IS NOT NULL
                  AND status IN ('queued', 'processing')
                """
            ).fetchall()
        }
    finally:
        connection.close()

    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    candidates: list[Path] = []
    retained_referenced = 0
    retained_active = 0
    if files_root.is_dir() and not files_root.is_symlink():
        for file_root in files_root.iterdir():
            task_artifacts_root = file_root / "task-artifacts"
            if (
                not file_root.is_dir()
                or file_root.is_symlink()
                or not task_artifacts_root.is_dir()
                or task_artifacts_root.is_symlink()
            ):
                continue
            for task_root in task_artifacts_root.iterdir():
                if not task_root.is_dir() or task_root.is_symlink():
                    continue
                task_key = (file_root.name, task_root.name)
                for claim_root in task_root.iterdir():
                    resolved_claim = claim_root.resolve()
                    if (
                        not claim_root.is_dir()
                        or claim_root.is_symlink()
                        or resolved_claim.parent != task_root.resolve()
                        or not resolved_claim.is_relative_to(files_root)
                    ):
                        continue
                    if any(
                        path == resolved_claim or path.is_relative_to(resolved_claim)
                        for path in referenced_paths
                    ):
                        retained_referenced += 1
                        continue
                    if task_key in active_tasks:
                        retained_active += 1
                        continue
                    modified_at = datetime.fromtimestamp(
                        resolved_claim.stat().st_mtime,
                        tz=UTC,
                    )
                    if modified_at <= cutoff:
                        candidates.append(resolved_claim)

    deleted: list[str] = []
    if delete:
        for candidate in candidates:
            relative_path = candidate.relative_to(resolved_storage).as_posix()
            shutil.rmtree(candidate)
            deleted.append(relative_path)

    return {
        "status": (
            "warning"
            if unsafe_references or (candidates and not delete)
            else "ok"
        ),
        "database_path": str(resolved_database),
        "storage_root": str(resolved_storage),
        "retention_days": retention_days,
        "referenced_claim_directories": retained_referenced,
        "active_claim_directories": retained_active,
        "unsafe_database_references": unsafe_references,
        "candidate_count": len(candidates),
        "candidates": [
            path.relative_to(resolved_storage).as_posix() for path in candidates
        ],
        "deleted_count": len(deleted),
        "deleted": deleted,
    }


def _referenced_artifact_paths(
    connection: sqlite3.Connection,
    *,
    storage_root: Path,
) -> tuple[list[Path], list[str]]:
    referenced: list[Path] = []
    unsafe: list[str] = []
    rows = connection.execute(
        "SELECT artifact_id, path FROM pdf_parse_artifacts WHERE path IS NOT NULL"
    ).fetchall()
    for row in rows:
        value = str(row["path"])
        path = Path(value).expanduser()
        resolved = path.resolve() if path.is_absolute() else (storage_root / path).resolve()
        if not resolved.is_relative_to(storage_root):
            unsafe.append(str(row["artifact_id"]))
            continue
        referenced.append(resolved)
    return referenced, unsafe


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit unreferenced PDF task-artifact claim directories."
    )
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--storage-root", type=Path, default=None)
    parser.add_argument("--retention-days", type=int, default=7)
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete only the candidates printed by the same safety rules.",
    )
    parser.add_argument("--fail-on-candidates", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    report = audit_task_artifacts(
        database_path=args.database or settings.database_path,
        storage_root=args.storage_root or settings.storage_root,
        retention_days=args.retention_days,
        delete=args.delete,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    if args.fail_on_candidates and (
        int(report["candidate_count"]) > 0
        or bool(report["unsafe_database_references"])
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
