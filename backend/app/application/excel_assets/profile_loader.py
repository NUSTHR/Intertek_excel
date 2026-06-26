import json
from pathlib import Path

from app.application.excel_assets.csv_rows import CsvRowReader, strip_internal_row_id
from app.core.errors import AssetNotFoundError
from app.domain.models import ExcelFileVersion, SheetProfile, WorkbookProfile


class WorkbookProfileLoader:
    def __init__(self, csv_reader: CsvRowReader | None = None) -> None:
        self._csv_reader = csv_reader or CsvRowReader()

    def read_profile(self, path: Path, *, version: ExcelFileVersion) -> WorkbookProfile:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise AssetNotFoundError("workbook profile was not found") from exc
        sheets = [
            SheetProfile(
                sheet_id=str(sheet["sheet_id"]),
                sheet_code=str(sheet["sheet_code"]),
                sheet_name=str(sheet["sheet_name"]),
                row_count=int(sheet["row_count"]),
                column_count=int(sheet["column_count"]),
                candidate_header=[str(value) for value in sheet.get("candidate_header", [])],
                sample_rows=[
                    [str(cell) for cell in row]
                    for row in sheet.get("sample_rows", [])
                ],
                profile_rows=[
                    [str(cell) for cell in row]
                    for row in sheet.get("profile_rows", sheet.get("sample_rows", []))
                ],
            )
            for sheet in payload.get("sheets", [])
        ]
        return WorkbookProfile(
            file_id=str(payload.get("file_id", version.file_id)),
            version_id=str(payload.get("version_id", version.version_id)),
            original_filename=str(payload.get("original_filename", version.original_filename)),
            file_hash=str(payload.get("file_hash", version.file_hash)),
            sheets=sheets,
        )

    def summary_profile_rows(
        self,
        sheet_profile: SheetProfile,
        raw_csv_path: Path | None,
    ) -> list[list[str]]:
        if raw_csv_path is not None:
            rows = self._csv_reader.read_rows(raw_csv_path)
            return [
                strip_internal_row_id(row, sheet_profile.sheet_code)
                for row in rows
            ]
        return sheet_profile.profile_rows or sheet_profile.sample_rows
