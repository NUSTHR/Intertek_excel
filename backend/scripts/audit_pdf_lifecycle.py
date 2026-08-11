"""Read-only audit for PDF summary, deletion, and cleanup consistency."""

import argparse
import json
import sqlite3
from pathlib import Path

CONTENT_TABLES = (
    "pdf_document_chunks",
    "pdf_document_summaries",
    "pdf_preview_blocks",
    "pdf_schema_items",
    "pdf_parse_reports",
    "pdf_parse_pages",
    "pdf_parse_artifacts",
    "pdf_chat_session_documents",
)


def audit(database_path: Path) -> dict[str, object]:
    resolved_path = database_path.expanduser().resolve()
    connection = sqlite3.connect(f"file:{resolved_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        deleted_content = {
            table: _scalar(
                connection,
                f"""
                SELECT COUNT(*)
                FROM {table} AS content
                JOIN pdf_files AS file ON file.file_id = content.file_id
                WHERE file.status = 'deleted'
                """,
            )
            for table in CONTENT_TABLES
        }
        return {
            "database_path": str(resolved_path),
            "schema_version": _scalar(
                connection,
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations",
            ),
            "integrity_check": str(connection.execute("PRAGMA integrity_check").fetchone()[0]),
            "foreign_key_violations": len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            ),
            "active_summary_task_duplicate_groups": _scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM (
                  SELECT file_id
                  FROM pdf_summary_tasks
                  WHERE status IN ('queued', 'running')
                  GROUP BY file_id
                  HAVING COUNT(*) > 1
                )
                """,
            ),
            "ready_summary_fingerprint_mismatches": _scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM pdf_document_summaries AS summary
                JOIN pdf_files AS file ON file.file_id = summary.file_id
                WHERE summary.status = 'ready'
                  AND summary.source_fingerprint <> file.content_fingerprint
                """,
            ),
            "deleted_file_tombstones": _scalar(
                connection,
                "SELECT COUNT(*) FROM pdf_files WHERE status = 'deleted'",
            ),
            "content_rows_retained_for_deleted_files": deleted_content,
            "pending_or_failed_cleanup_jobs": _scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM pdf_file_cleanup_jobs
                WHERE status IN ('pending', 'failed')
                """,
            ),
        }
    finally:
        connection.close()


def _scalar(connection: sqlite3.Connection, query: str) -> int:
    row = connection.execute(query).fetchone()
    return int(row[0]) if row is not None else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="Path to excel-workspace.sqlite3")
    args = parser.parse_args()
    print(json.dumps(audit(args.database), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
