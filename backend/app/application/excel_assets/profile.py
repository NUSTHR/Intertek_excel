from app.domain.models import SheetProfile, WorkbookProfile
from app.ports.workbook_reader import WorkbookSheet


class WorkbookProfileBuilder:
    def build(
        self,
        file_id: str,
        version_id: str,
        original_filename: str,
        file_hash: str,
        sheets: list[tuple[str, str, WorkbookSheet]],
    ) -> WorkbookProfile:
        return WorkbookProfile(
            file_id=file_id,
            version_id=version_id,
            original_filename=original_filename,
            file_hash=file_hash,
            sheets=[
                SheetProfile(
                    sheet_id=sheet_id,
                    sheet_code=sheet_code,
                    sheet_name=sheet.sheet_name,
                    row_count=len(sheet.rows),
                    column_count=self._column_count(sheet.rows),
                    sample_rows=sheet.rows[:10],
                    candidate_header=self._candidate_header(sheet.rows),
                )
                for sheet_id, sheet_code, sheet in sheets
            ],
        )

    def to_json_payload(self, profile: WorkbookProfile) -> dict:
        return {
            "file_id": profile.file_id,
            "version_id": profile.version_id,
            "original_filename": profile.original_filename,
            "file_hash": profile.file_hash,
            "sheets": [
                {
                    "sheet_id": sheet.sheet_id,
                    "sheet_code": sheet.sheet_code,
                    "sheet_name": sheet.sheet_name,
                    "row_count": sheet.row_count,
                    "column_count": sheet.column_count,
                    "candidate_header": sheet.candidate_header,
                    "sample_rows": sheet.sample_rows,
                }
                for sheet in profile.sheets
            ],
        }

    def _column_count(self, rows: list[list[str]]) -> int:
        return max((len(row) for row in rows), default=0)

    def _candidate_header(self, rows: list[list[str]]) -> list[str]:
        for row in rows[:20]:
            values = [cell.strip() for cell in row]
            non_empty_values = [cell for cell in values if cell]
            if len(non_empty_values) >= 2:
                return values
        return rows[0] if rows else []
