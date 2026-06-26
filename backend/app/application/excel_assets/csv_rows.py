import csv
from pathlib import Path


class CsvRowReader:
    def read_rows(self, path: Path) -> list[list[str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            return [row for row in csv.reader(csv_file)]

    def read_rows_page(self, path: Path, offset: int, limit: int) -> list[list[str]]:
        safe_offset = max(0, offset)
        safe_limit = max(1, limit)
        rows: list[list[str]] = []
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.reader(csv_file)
            for index, row in enumerate(reader):
                if index < safe_offset:
                    continue
                if len(rows) >= safe_limit:
                    break
                rows.append(row)
        return rows

    def read_row(self, path: Path, row_index: int) -> list[str] | None:
        if row_index < 0:
            return None
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.reader(csv_file)
            for index, row in enumerate(reader):
                if index == row_index:
                    return row
        return None


def strip_internal_row_id(row: list[str], sheet_code: str) -> list[str]:
    if row and row[0].startswith(f"{sheet_code}_R"):
        return row[1:]
    return row
