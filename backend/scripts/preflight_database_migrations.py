#!/usr/bin/env python3
"""Read-only preflight for data conflicts in pending SQLite migrations."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from app.adapters.repositories.sqlite.migrations import SQLiteMigrationRunner
from app.adapters.repositories.sqlite.schema import SCHEMA_MIGRATIONS
from app.core.config import Settings


def preflight(database_path: Path) -> dict[str, object]:
    resolved_path = database_path.expanduser().resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {resolved_path}")
    connection = sqlite3.connect(
        f"{resolved_path.as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        runner = SQLiteMigrationRunner(SCHEMA_MIGRATIONS)
        schema = runner.inspect_schema(connection)
        conflicts = runner.inspect_pending_data_conflicts(connection)
        return {
            "status": "conflict" if conflicts else "ok",
            "database_path": str(resolved_path),
            "applied_version": schema.applied_version,
            "expected_version": schema.expected_version,
            "pending_versions": list(schema.missing_versions),
            "conflict_count": len(conflicts),
            "conflicts": [conflict.to_dict() for conflict in conflicts],
        }
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check pending SQLite migrations for blocking data conflicts."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite database path. Defaults to the configured application database.",
    )
    args = parser.parse_args()
    database_path = args.database or Settings().database_path
    report = preflight(database_path)
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 1 if report["status"] == "conflict" else 0


if __name__ == "__main__":
    raise SystemExit(main())
