from dataclasses import dataclass


@dataclass(frozen=True)
class SheetRowSearchPolicy:
    default_limit: int = 50
    max_limit: int = 200

    def normalize_query(self, query: str) -> str:
        return query.strip()

    def normalize_limit(self, limit: int | None) -> int:
        requested_limit = self.default_limit if limit is None else limit
        return max(1, min(self.max_limit, requested_limit))

    def matched_column_indexes(self, row: list[str], query: str) -> list[int]:
        normalized_query = query.casefold()
        return [
            index
            for index, cell in enumerate(row)
            if normalized_query in cell.casefold()
        ]
