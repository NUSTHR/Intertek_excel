import csv
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from app.application.excel_assets.models import SheetSearchMatch, SheetSearchResult
from app.domain.models import (
    ExcelRowMapping,
    ExcelRowSearchEntry,
    ExcelRowSearchMatch,
    ExcelSheet,
)
from app.ports.repository import ExcelAssetRepository

logger = logging.getLogger(__name__)


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


class SheetRowSearchEngine:
    def __init__(
        self,
        *,
        repository: ExcelAssetRepository,
        resolve_artifact_path: Callable[[str], Path],
        policy: SheetRowSearchPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._resolve_artifact_path = resolve_artifact_path
        self._policy = policy or SheetRowSearchPolicy()

    def search_sheet(
        self,
        *,
        sheet: ExcelSheet,
        query: str,
        limit: int,
    ) -> SheetSearchResult:
        safe_limit = self._policy.normalize_limit(limit)
        self._ensure_row_search_index(sheet.version_id)
        if self._can_use_row_search_index(query):
            indexed_result = self._search_sheet_index(
                sheet=sheet,
                query=query,
                limit=safe_limit,
            )
            if indexed_result is not None:
                return indexed_result
        return self._search_sheet_by_scan(sheet=sheet, query=query, limit=safe_limit)

    def _search_sheet_index(
        self,
        sheet: ExcelSheet,
        query: str,
        limit: int,
    ) -> SheetSearchResult | None:
        try:
            indexed_matches = self._repository.search_row_index(
                version_id=sheet.version_id,
                sheet_id=sheet.sheet_id,
                query=query,
            )
        except Exception:
            logger.warning(
                "Row search index lookup failed; falling back to CSV scan",
                extra={"version_id": sheet.version_id, "sheet_id": sheet.sheet_id},
                exc_info=True,
            )
            return None
        return self._sheet_search_result_from_index_matches(
            sheet=sheet,
            query=query,
            limit=limit,
            indexed_matches=indexed_matches,
        )

    def _search_sheet_by_scan(
        self,
        sheet: ExcelSheet,
        query: str,
        limit: int,
    ) -> SheetSearchResult:
        mappings = self._repository.list_row_mappings_for_sheet(sheet.sheet_id)
        matches: list[SheetSearchMatch] = []
        total_matches = 0

        for mapping, row in self._iter_csv_rows_for_mappings(
            self._resolve_artifact_path(sheet.raw_csv_path),
            mappings,
        ):
            matched_columns = self._policy.matched_column_indexes(row, query)
            if not matched_columns:
                continue
            total_matches += 1
            if len(matches) < limit:
                matches.append(
                    SheetSearchMatch(
                        sheet=sheet,
                        mapping=mapping,
                        row=row,
                        matched_columns=matched_columns,
                    )
                )

        return SheetSearchResult(
            sheet=sheet,
            query=query,
            matches=matches,
            total_matches=total_matches,
            limit=limit,
        )

    def _sheet_search_result_from_index_matches(
        self,
        sheet: ExcelSheet,
        query: str,
        limit: int,
        indexed_matches: list[ExcelRowSearchMatch],
    ) -> SheetSearchResult:
        matches: list[SheetSearchMatch] = []
        total_matches = 0
        for indexed_match in indexed_matches:
            if indexed_match.sheet_id != sheet.sheet_id:
                continue
            matched_columns = self._policy.matched_column_indexes(
                indexed_match.row,
                query,
            )
            if not matched_columns:
                continue
            total_matches += 1
            if len(matches) < limit:
                matches.append(
                    SheetSearchMatch(
                        sheet=sheet,
                        mapping=self._mapping_from_search_match(indexed_match),
                        row=indexed_match.row,
                        matched_columns=matched_columns,
                    )
                )
        return SheetSearchResult(
            sheet=sheet,
            query=query,
            matches=matches,
            total_matches=total_matches,
            limit=limit,
        )

    def _ensure_row_search_index(self, version_id: str) -> None:
        try:
            if self._repository.has_row_search_entries(version_id):
                return
            self._repository.replace_row_search_entries(
                version_id,
                self._build_row_search_entries(version_id),
            )
        except Exception:
            logger.warning(
                "Row search index rebuild failed; CSV scan fallback remains available",
                extra={"version_id": version_id},
                exc_info=True,
            )

    def _build_row_search_entries(self, version_id: str) -> list[ExcelRowSearchEntry]:
        entries: list[ExcelRowSearchEntry] = []
        for sheet in self._repository.list_sheets(version_id):
            mappings = {
                mapping.raw_csv_row_number: mapping
                for mapping in self._repository.list_row_mappings_for_sheet(sheet.sheet_id)
            }
            if not mappings:
                continue
            with self._resolve_artifact_path(sheet.raw_csv_path).open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as csv_file:
                reader = csv.reader(csv_file)
                for row_number, row in enumerate(reader, start=1):
                    mapping = mappings.get(row_number)
                    if mapping is None:
                        continue
                    entries.append(
                        ExcelRowSearchEntry(
                            mapping_id=mapping.mapping_id,
                            version_id=version_id,
                            sheet_id=sheet.sheet_id,
                            row_id=mapping.row_id,
                            original_row_number=mapping.original_row_number,
                            raw_csv_row_number=mapping.raw_csv_row_number,
                            created_at=mapping.created_at,
                            row=row,
                        )
                    )
        return entries

    def _mapping_from_search_match(
        self,
        match: ExcelRowSearchMatch,
    ) -> ExcelRowMapping:
        return ExcelRowMapping(
            mapping_id=match.mapping_id,
            version_id=match.version_id,
            sheet_id=match.sheet_id,
            row_id=match.row_id,
            original_row_number=match.original_row_number,
            raw_csv_row_number=match.raw_csv_row_number,
            created_at=match.created_at,
        )

    def _can_use_row_search_index(self, query: str) -> bool:
        return len(query.casefold()) >= 3

    def _iter_csv_rows_for_mappings(
        self,
        path: Path,
        mappings: list[ExcelRowMapping],
    ) -> Iterator[tuple[ExcelRowMapping, list[str]]]:
        pending_mappings = sorted(
            (
                mapping
                for mapping in mappings
                if mapping.raw_csv_row_number > 0
            ),
            key=lambda item: item.raw_csv_row_number,
        )
        if not pending_mappings:
            return
        mapping_index = 0
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.reader(csv_file)
            for row_index, row in enumerate(reader, start=1):
                while (
                    mapping_index < len(pending_mappings)
                    and pending_mappings[mapping_index].raw_csv_row_number < row_index
                ):
                    mapping_index += 1
                if mapping_index >= len(pending_mappings):
                    break
                while (
                    mapping_index < len(pending_mappings)
                    and pending_mappings[mapping_index].raw_csv_row_number == row_index
                ):
                    yield pending_mappings[mapping_index], row
                    mapping_index += 1
