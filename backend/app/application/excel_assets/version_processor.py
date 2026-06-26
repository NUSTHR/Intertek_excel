from pathlib import Path

from app.application.excel_assets.models import UploadExcelResult
from app.application.excel_assets.profile import WorkbookProfileBuilder
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    ExcelArtifact,
    ExcelArtifactType,
    ExcelFile,
    ExcelFileVersion,
    ExcelRowMapping,
    ExcelRowSearchEntry,
    ExcelSheet,
)
from app.ports.repository import ExcelAssetRepository
from app.ports.storage import ExcelArtifactStorage
from app.ports.workbook_reader import WorkbookReader, WorkbookSheet


class WorkbookVersionProcessor:
    def __init__(
        self,
        *,
        repository: ExcelAssetRepository,
        storage: ExcelArtifactStorage,
        workbook_reader: WorkbookReader,
        profile_builder: WorkbookProfileBuilder | None = None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._workbook_reader = workbook_reader
        self._profile_builder = profile_builder or WorkbookProfileBuilder()

    def process_version(
        self,
        *,
        file: ExcelFile,
        version: ExcelFileVersion,
        content: bytes,
    ) -> UploadExcelResult:
        original_path = self._storage.save_original(
            file_id=file.file_id,
            version_id=version.version_id,
            original_filename=version.original_filename,
            content=content,
        )
        workbook = self._workbook_reader.read(original_path)
        created_at = utc_now_iso()
        artifacts = [
            ExcelArtifact(
                artifact_id=new_id("artifact"),
                version_id=version.version_id,
                artifact_type=ExcelArtifactType.ORIGINAL,
                path=self._artifact_reference(original_path),
                created_at=created_at,
            )
        ]
        self._repository.create_artifact(artifacts[0])

        sheet_tuples: list[tuple[str, str, WorkbookSheet]] = []
        created_sheets: list[ExcelSheet] = []
        all_mappings: list[ExcelRowMapping] = []
        search_entries: list[ExcelRowSearchEntry] = []
        mapping_csv_rows = [
            [
                "row_id",
                "version_id",
                "sheet_id",
                "sheet_name",
                "original_row_number",
                "raw_csv_row_number",
            ]
        ]

        for sheet in workbook.sheets:
            sheet_code = f"S{sheet.sheet_index:03d}"
            sheet_id = new_id("sheet")
            sheet_tuples.append((sheet_id, sheet_code, sheet))
            csv_rows, mappings, mapping_rows = self._build_sheet_rows(
                version_id=version.version_id,
                sheet_id=sheet_id,
                sheet_code=sheet_code,
                sheet=sheet,
                created_at=created_at,
            )
            raw_csv_path = self._storage.write_csv(
                file_id=file.file_id,
                version_id=version.version_id,
                sheet_code=sheet_code,
                rows=csv_rows,
            )
            created_sheet = ExcelSheet(
                sheet_id=sheet_id,
                version_id=version.version_id,
                sheet_index=sheet.sheet_index,
                sheet_code=sheet_code,
                sheet_name=sheet.sheet_name,
                row_count=len(sheet.rows),
                column_count=self._column_count(sheet.rows) + 1,
                raw_csv_path=self._artifact_reference(raw_csv_path),
                created_at=created_at,
            )
            self._repository.create_sheet(created_sheet)
            created_sheets.append(created_sheet)
            all_mappings.extend(mappings)
            search_entries.extend(
                ExcelRowSearchEntry(
                    mapping_id=mapping.mapping_id,
                    version_id=version.version_id,
                    sheet_id=sheet_id,
                    row_id=mapping.row_id,
                    original_row_number=mapping.original_row_number,
                    raw_csv_row_number=mapping.raw_csv_row_number,
                    created_at=mapping.created_at,
                    row=row,
                )
                for mapping, row in zip(mappings, csv_rows, strict=True)
            )
            mapping_csv_rows.extend(mapping_rows)
            artifact = ExcelArtifact(
                artifact_id=new_id("artifact"),
                version_id=version.version_id,
                artifact_type=ExcelArtifactType.RAW_CSV,
                path=self._artifact_reference(raw_csv_path),
                created_at=created_at,
            )
            self._repository.create_artifact(artifact)
            artifacts.append(artifact)

        self._repository.create_row_mappings(all_mappings)
        self._repository.replace_row_search_entries(version.version_id, search_entries)
        mapping_path = self._storage.write_mapping_csv(
            file_id=file.file_id,
            version_id=version.version_id,
            rows=mapping_csv_rows,
        )
        mapping_artifact = ExcelArtifact(
            artifact_id=new_id("artifact"),
            version_id=version.version_id,
            artifact_type=ExcelArtifactType.ROW_MAPPING,
            path=self._artifact_reference(mapping_path),
            created_at=created_at,
        )
        self._repository.create_artifact(mapping_artifact)
        artifacts.append(mapping_artifact)

        profile = self._profile_builder.build(
            file_id=file.file_id,
            version_id=version.version_id,
            original_filename=version.original_filename,
            file_hash=version.file_hash,
            sheets=sheet_tuples,
        )
        profile_path = self._storage.write_json(
            file_id=file.file_id,
            version_id=version.version_id,
            relative_name="profile.json",
            payload=self._profile_builder.to_json_payload(profile),
        )
        profile_artifact = ExcelArtifact(
            artifact_id=new_id("artifact"),
            version_id=version.version_id,
            artifact_type=ExcelArtifactType.PROFILE,
            path=self._artifact_reference(profile_path),
            created_at=created_at,
        )
        self._repository.create_artifact(profile_artifact)
        artifacts.append(profile_artifact)

        return UploadExcelResult(
            file=file,
            version=version,
            sheets=created_sheets,
            profile=profile,
            artifacts=artifacts,
        )

    def _build_sheet_rows(
        self,
        version_id: str,
        sheet_id: str,
        sheet_code: str,
        sheet: WorkbookSheet,
        created_at: str,
    ) -> tuple[list[list[str]], list[ExcelRowMapping], list[list[str]]]:
        width = self._column_count(sheet.rows)
        csv_rows: list[list[str]] = []
        mappings: list[ExcelRowMapping] = []
        mapping_csv_rows: list[list[str]] = []

        for index, row in enumerate(sheet.rows, start=1):
            row_id = f"{sheet_code}_R{index}"
            padded_row = row + [""] * max(0, width - len(row))
            csv_rows.append([row_id, *padded_row])
            mapping = ExcelRowMapping(
                mapping_id=new_id("mapping"),
                version_id=version_id,
                sheet_id=sheet_id,
                row_id=row_id,
                original_row_number=index,
                raw_csv_row_number=index,
                created_at=created_at,
            )
            mappings.append(mapping)
            mapping_csv_rows.append(
                [
                    row_id,
                    version_id,
                    sheet_id,
                    sheet.sheet_name,
                    str(index),
                    str(index),
                ]
            )
        return csv_rows, mappings, mapping_csv_rows

    def _artifact_reference(self, path: Path) -> str:
        return self._storage.artifact_reference(path)

    def _column_count(self, rows: list[list[str]]) -> int:
        return max((len(row) for row in rows), default=0)
