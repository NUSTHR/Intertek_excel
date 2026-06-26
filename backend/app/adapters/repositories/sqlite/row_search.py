import json
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager

from app.domain.models import ExcelRowSearchEntry, ExcelRowSearchMatch

SQLiteConnectionFactory = Callable[[], AbstractContextManager[sqlite3.Connection]]


class SQLiteRowSearchIndex:
    def __init__(
        self,
        *,
        connect: SQLiteConnectionFactory,
        dump_json: Callable[[object], str],
    ) -> None:
        self._connect = connect
        self._dump_json = dump_json

    def replace_entries(
        self,
        version_id: str,
        entries: list[ExcelRowSearchEntry],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM excel_row_search_index
                WHERE version_id = ?
                """,
                (version_id,),
            )
            if not entries:
                return
            connection.executemany(
                """
                INSERT INTO excel_row_search_index
                  (
                    mapping_id, version_id, sheet_id, row_id,
                    original_row_number, raw_csv_row_number, created_at,
                    row_json, searchable_text
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        entry.mapping_id,
                        entry.version_id,
                        entry.sheet_id,
                        entry.row_id,
                        entry.original_row_number,
                        entry.raw_csv_row_number,
                        entry.created_at,
                        self._dump_json(entry.row),
                        self._row_search_text(entry.row),
                    )
                    for entry in entries
                ],
            )

    def has_entries(self, version_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM excel_row_search_index
                WHERE version_id = ?
                LIMIT 1
                """,
                (version_id,),
            ).fetchone()
        return row is not None

    def search(
        self,
        *,
        version_id: str,
        query: str,
        sheet_id: str | None = None,
        limit: int | None = None,
    ) -> list[ExcelRowSearchMatch]:
        normalized_query = query.strip()
        if not normalized_query:
            return []
        bounded_limit = max(1, limit) if limit is not None else None
        sql = """
            SELECT
              mapping_id,
              version_id,
              sheet_id,
              row_id,
              original_row_number,
              raw_csv_row_number,
              created_at,
              row_json
            FROM excel_row_search_index
            WHERE excel_row_search_index MATCH ?
              AND version_id = ?
        """
        parameters: list[object] = [self._fts_phrase(normalized_query), version_id]
        if sheet_id is not None:
            sql += " AND sheet_id = ?"
            parameters.append(sheet_id)
        sql += " ORDER BY CAST(raw_csv_row_number AS INTEGER) ASC"
        if bounded_limit is not None:
            sql += " LIMIT ?"
            parameters.append(bounded_limit)
        with self._connect() as connection:
            rows = connection.execute(sql, tuple(parameters)).fetchall()
        return [
            match
            for row in rows
            if (match := self._to_row_search_match(row)) is not None
        ]

    def _to_row_search_match(
        self,
        row: sqlite3.Row | None,
    ) -> ExcelRowSearchMatch | None:
        if row is None:
            return None
        return ExcelRowSearchMatch(
            mapping_id=str(row["mapping_id"]),
            version_id=str(row["version_id"]),
            sheet_id=str(row["sheet_id"]),
            row_id=str(row["row_id"]),
            original_row_number=int(row["original_row_number"]),
            raw_csv_row_number=int(row["raw_csv_row_number"]),
            created_at=str(row["created_at"]),
            row=self._load_row_json(str(row["row_json"])),
        )

    def _row_search_text(self, row: list[str]) -> str:
        return "\n".join(cell for cell in row if cell)

    def _fts_phrase(self, query: str) -> str:
        escaped_query = query.replace('"', '""')
        return f'"{escaped_query}"'

    def _load_row_json(self, value: object) -> list[str]:
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed]
