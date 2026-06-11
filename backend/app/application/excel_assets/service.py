import csv
import hashlib
import json
from pathlib import Path

from app.application.excel_assets.models import (
    DeleteExcelFileResult,
    FileNameCheckResult,
    RowLookupResult,
    SheetPreviewResult,
    SheetRowsResult,
    SheetSearchMatch,
    SheetSearchResult,
    UploadExcelResult,
    WorkbookSearchResult,
)
from app.application.excel_assets.profile import WorkbookProfileBuilder
from app.application.excel_assets.search import SheetRowSearchPolicy
from app.core.errors import (
    AssetNotFoundError,
    FileDeleteConfirmationRequiredError,
    FileNameConflictError,
    VersionActivationError,
)
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    ExcelArtifact,
    ExcelArtifactType,
    ExcelFile,
    ExcelFileVersion,
    ExcelRowMapping,
    ExcelSheet,
    ExcelVersionStatus,
    SheetProfile,
    WorkbookProfile,
)
from app.ports.repository import ExcelAssetRepository
from app.ports.storage import ExcelArtifactStorage
from app.ports.workbook_reader import WorkbookReader, WorkbookSheet


class ExcelAssetService:
    def __init__(
        self,
        repository: ExcelAssetRepository,
        storage: ExcelArtifactStorage,
        workbook_reader: WorkbookReader,
        profile_builder: WorkbookProfileBuilder | None = None,
        search_policy: SheetRowSearchPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._workbook_reader = workbook_reader
        self._profile_builder = profile_builder or WorkbookProfileBuilder()
        self._search_policy = search_policy or SheetRowSearchPolicy()

    def initialize(self) -> None:
        self._repository.initialize()

    def check_display_name(self, display_name: str) -> FileNameCheckResult:
        normalized_name = self._normalize_display_name(display_name)
        existing_file = self._repository.find_file_by_display_name(normalized_name)
        if existing_file is None:
            return FileNameCheckResult(display_name=normalized_name, exists=False)
        return FileNameCheckResult(
            display_name=normalized_name,
            exists=True,
            file_id=existing_file.file_id,
            active_version_id=existing_file.active_version_id,
        )

    def upload_workbook(
        self,
        original_filename: str,
        content: bytes,
        replace_existing: bool = False,
    ) -> UploadExcelResult:
        display_name = self._normalize_display_name(original_filename)
        existing_file = self._repository.find_file_by_display_name(display_name)
        if existing_file is not None and not replace_existing:
            raise FileNameConflictError(display_name=display_name, file_id=existing_file.file_id)

        now = utc_now_iso()
        file = existing_file or ExcelFile(
            file_id=new_id("file"),
            display_name=display_name,
            active_version_id=None,
            created_at=now,
            updated_at=now,
        )
        if existing_file is None:
            self._repository.create_file(file)

        file_hash = self._sha256(content)
        version = ExcelFileVersion(
            version_id=new_id("version"),
            file_id=file.file_id,
            original_filename=original_filename,
            file_hash=file_hash,
            status=ExcelVersionStatus.PROCESSING,
            error_message=None,
            created_at=now,
            activated_at=None,
        )
        self._repository.create_version(version)

        try:
            result = self._process_version(file=file, version=version, content=content)
            self._repository.activate_version(
                file_id=file.file_id,
                version_id=version.version_id,
                activated_at=utc_now_iso(),
            )
            activated_file = self._require_file(file.file_id)
            activated_version = self._require_version(version.version_id)
            return UploadExcelResult(
                file=activated_file,
                version=activated_version,
                sheets=result.sheets,
                profile=result.profile,
                artifacts=result.artifacts,
            )
        except Exception as exc:
            self._repository.update_version_status(
                version.version_id,
                ExcelVersionStatus.FAILED,
                error_message=str(exc),
            )
            raise

    def list_files(self) -> list[ExcelFile]:
        return self._repository.list_files()

    def get_file(self, file_id: str) -> ExcelFile:
        return self._require_file(file_id)

    def rename_file(self, file_id: str, display_name: str) -> ExcelFile:
        file = self._require_file(file_id)
        normalized_name = self._normalize_display_name(display_name)
        existing_file = self._repository.find_file_by_display_name(normalized_name)
        if existing_file is not None and existing_file.file_id != file.file_id:
            raise FileNameConflictError(
                display_name=normalized_name,
                file_id=existing_file.file_id,
            )

        updated_file = self._repository.update_file_display_name(
            file_id=file.file_id,
            display_name=normalized_name,
            updated_at=utc_now_iso(),
        )
        if updated_file is None:
            raise AssetNotFoundError("Excel file was not found")
        return updated_file

    def delete_file(
        self,
        file_id: str,
        *,
        confirm_delete: bool = False,
    ) -> DeleteExcelFileResult:
        file = self._require_file(file_id)
        if not confirm_delete:
            raise FileDeleteConfirmationRequiredError(
                display_name=file.display_name,
                file_id=file.file_id,
            )

        counts = self._repository.delete_file(file_id)
        self._storage.delete_file_tree(file_id)
        return DeleteExcelFileResult(
            file_id=file.file_id,
            display_name=file.display_name,
            deleted_versions=counts["deleted_versions"],
            deleted_sheets=counts["deleted_sheets"],
            deleted_artifacts=counts["deleted_artifacts"],
            deleted_row_mappings=counts["deleted_row_mappings"],
            deleted_summaries=counts["deleted_summaries"],
            deleted_chat_session_documents=counts["deleted_chat_session_documents"],
        )

    def get_active_file_version(self, file_id: str) -> ExcelFileVersion:
        file = self._require_file(file_id)
        if file.active_version_id is None:
            raise AssetNotFoundError("Excel file has no active version")
        return self._require_version(file.active_version_id)

    def list_versions(self, file_id: str) -> list[ExcelFileVersion]:
        self._require_file(file_id)
        return self._repository.list_versions(file_id)

    def activate_version(self, file_id: str, version_id: str) -> ExcelFileVersion:
        file = self._require_file(file_id)
        version = self._require_version(version_id)
        if version.file_id != file.file_id:
            raise AssetNotFoundError("version does not belong to the requested file")
        if version.status != ExcelVersionStatus.READY:
            raise VersionActivationError("only ready versions can be activated")
        self._repository.activate_version(
            file_id=file_id,
            version_id=version_id,
            activated_at=utc_now_iso(),
        )
        return self._require_version(version_id)

    def list_sheets(self, version_id: str) -> list[ExcelSheet]:
        self._require_version(version_id)
        return self._repository.list_sheets(version_id)

    def get_profile(self, version_id: str) -> WorkbookProfile:
        version = self._require_version(version_id)
        artifacts = self._repository.list_artifacts(version_id)
        profile_artifact = next(
            (
                artifact
                for artifact in artifacts
                if artifact.artifact_type == ExcelArtifactType.PROFILE
            ),
            None,
        )
        if profile_artifact is None:
            raise AssetNotFoundError("workbook profile was not found")
        return self._read_profile(Path(profile_artifact.path), version=version)

    def get_summary_profile(self, version_id: str) -> WorkbookProfile:
        profile = self.get_profile(version_id)
        sheets = {sheet.sheet_id: sheet for sheet in self._repository.list_sheets(version_id)}
        return WorkbookProfile(
            file_id=profile.file_id,
            version_id=profile.version_id,
            original_filename=profile.original_filename,
            file_hash=profile.file_hash,
            sheets=[
                SheetProfile(
                    sheet_id=sheet_profile.sheet_id,
                    sheet_code=sheet_profile.sheet_code,
                    sheet_name=sheet_profile.sheet_name,
                    row_count=sheet_profile.row_count,
                    column_count=sheet_profile.column_count,
                    sample_rows=sheet_profile.sample_rows,
                    candidate_header=sheet_profile.candidate_header,
                    profile_rows=self._summary_profile_rows(
                        sheet_profile,
                        raw_csv_path=(
                            Path(sheet.raw_csv_path)
                            if (sheet := sheets.get(sheet_profile.sheet_id)) is not None
                            else None
                        ),
                    ),
                )
                for sheet_profile in profile.sheets
            ],
        )

    def list_artifacts(self, version_id: str) -> list[ExcelArtifact]:
        self._require_version(version_id)
        return self._repository.list_artifacts(version_id)

    def preview_sheet(
        self,
        sheet_id: str,
        offset: int = 0,
        limit: int = 500,
    ) -> SheetPreviewResult:
        sheet = self._require_sheet(sheet_id)
        rows = self._read_csv_rows(Path(sheet.raw_csv_path))
        safe_offset = max(0, offset)
        safe_limit = max(1, min(5000, limit))
        return SheetPreviewResult(
            sheet=sheet,
            rows=rows[safe_offset : safe_offset + safe_limit],
            total_rows=len(rows),
            offset=safe_offset,
            limit=safe_limit,
        )

    def list_sheet_rows(
        self,
        sheet_id: str,
        offset: int = 0,
        limit: int = 500,
    ) -> SheetRowsResult:
        sheet = self._require_sheet(sheet_id)
        rows = self._read_csv_rows(Path(sheet.raw_csv_path))
        mappings = self._repository.list_row_mappings_for_sheet(sheet_id)
        safe_offset = max(0, offset)
        safe_limit = max(1, min(5000, limit))
        return SheetRowsResult(
            sheet=sheet,
            mappings=mappings[safe_offset : safe_offset + safe_limit],
            rows=rows[safe_offset : safe_offset + safe_limit],
            total_rows=len(rows),
            offset=safe_offset,
            limit=safe_limit,
        )

    def search_sheet_rows(
        self,
        sheet_id: str,
        query: str,
        limit: int = 50,
    ) -> SheetSearchResult:
        sheet = self._require_sheet(sheet_id)
        normalized_query = self._search_policy.normalize_query(query)
        safe_limit = self._search_policy.normalize_limit(limit)
        if not normalized_query:
            return SheetSearchResult(
                sheet=sheet,
                query=normalized_query,
                matches=[],
                total_matches=0,
                limit=safe_limit,
            )

        return self._search_sheet(sheet=sheet, query=normalized_query, limit=safe_limit)

    def search_version_rows(
        self,
        version_id: str,
        query: str,
        limit: int = 50,
    ) -> WorkbookSearchResult:
        self._require_version(version_id)
        normalized_query = self._search_policy.normalize_query(query)
        safe_limit = self._search_policy.normalize_limit(limit)
        if not normalized_query:
            return WorkbookSearchResult(
                version_id=version_id,
                query=normalized_query,
                matches=[],
                total_matches=0,
                limit=safe_limit,
            )

        matches: list[SheetSearchMatch] = []
        total_matches = 0
        for sheet in self._repository.list_sheets(version_id):
            sheet_result = self._search_sheet(
                sheet=sheet,
                query=normalized_query,
                limit=max(1, safe_limit - len(matches)),
            )
            total_matches += sheet_result.total_matches
            if len(matches) < safe_limit:
                matches.extend(sheet_result.matches[: safe_limit - len(matches)])

        return WorkbookSearchResult(
            version_id=version_id,
            query=normalized_query,
            matches=matches,
            total_matches=total_matches,
            limit=safe_limit,
        )

    def lookup_row(self, sheet_id: str, row_id: str) -> RowLookupResult:
        sheet = self._require_sheet(sheet_id)
        mapping = self._repository.get_row_mapping(sheet_id=sheet_id, row_id=row_id)
        if mapping is None:
            raise AssetNotFoundError("row mapping was not found")
        rows = self._read_csv_rows(Path(sheet.raw_csv_path))
        row_index = mapping.raw_csv_row_number - 1
        if row_index < 0 or row_index >= len(rows):
            raise AssetNotFoundError("mapped CSV row was not found")
        return RowLookupResult(sheet=sheet, mapping=mapping, row=rows[row_index])

    def _process_version(
        self,
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
                path=str(original_path),
                created_at=created_at,
            )
        ]
        self._repository.create_artifact(artifacts[0])

        sheet_tuples: list[tuple[str, str, WorkbookSheet]] = []
        created_sheets: list[ExcelSheet] = []
        all_mappings: list[ExcelRowMapping] = []
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
                raw_csv_path=str(raw_csv_path),
                created_at=created_at,
            )
            self._repository.create_sheet(created_sheet)
            created_sheets.append(created_sheet)
            all_mappings.extend(mappings)
            mapping_csv_rows.extend(mapping_rows)
            artifact = ExcelArtifact(
                artifact_id=new_id("artifact"),
                version_id=version.version_id,
                artifact_type=ExcelArtifactType.RAW_CSV,
                path=str(raw_csv_path),
                created_at=created_at,
            )
            self._repository.create_artifact(artifact)
            artifacts.append(artifact)

        self._repository.create_row_mappings(all_mappings)
        mapping_path = self._storage.write_mapping_csv(
            file_id=file.file_id,
            version_id=version.version_id,
            rows=mapping_csv_rows,
        )
        mapping_artifact = ExcelArtifact(
            artifact_id=new_id("artifact"),
            version_id=version.version_id,
            artifact_type=ExcelArtifactType.ROW_MAPPING,
            path=str(mapping_path),
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
            path=str(profile_path),
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

    def _normalize_display_name(self, filename: str) -> str:
        normalized = Path(filename).name.strip()
        if not normalized:
            raise AssetNotFoundError("filename is required")
        return normalized

    def _sha256(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _column_count(self, rows: list[list[str]]) -> int:
        return max((len(row) for row in rows), default=0)

    def _read_csv_rows(self, path: Path) -> list[list[str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            return [row for row in csv.reader(csv_file)]

    def _search_sheet(
        self,
        sheet: ExcelSheet,
        query: str,
        limit: int,
    ) -> SheetSearchResult:
        safe_limit = self._search_policy.normalize_limit(limit)
        rows = self._read_csv_rows(Path(sheet.raw_csv_path))
        mappings = self._repository.list_row_mappings_for_sheet(sheet.sheet_id)
        matches: list[SheetSearchMatch] = []
        total_matches = 0

        for mapping in mappings:
            row_index = mapping.raw_csv_row_number - 1
            if row_index < 0 or row_index >= len(rows):
                continue
            row = rows[row_index]
            matched_columns = self._search_policy.matched_column_indexes(row, query)
            if not matched_columns:
                continue
            total_matches += 1
            if len(matches) < safe_limit:
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
            limit=safe_limit,
        )

    def _summary_profile_rows(
        self,
        sheet_profile: SheetProfile,
        raw_csv_path: Path | None,
    ) -> list[list[str]]:
        if raw_csv_path is not None:
            rows = self._read_csv_rows(raw_csv_path)
            return [self._strip_internal_row_id(row, sheet_profile.sheet_code) for row in rows]
        return sheet_profile.profile_rows or sheet_profile.sample_rows

    def _strip_internal_row_id(self, row: list[str], sheet_code: str) -> list[str]:
        if row and row[0].startswith(f"{sheet_code}_R"):
            return row[1:]
        return row

    def _read_profile(self, path: Path, version: ExcelFileVersion) -> WorkbookProfile:
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

    def _require_file(self, file_id: str) -> ExcelFile:
        file = self._repository.get_file(file_id)
        if file is None:
            raise AssetNotFoundError("Excel file was not found")
        return file

    def _require_version(self, version_id: str) -> ExcelFileVersion:
        version = self._repository.get_version(version_id)
        if version is None:
            raise AssetNotFoundError("Excel file version was not found")
        return version

    def _require_sheet(self, sheet_id: str) -> ExcelSheet:
        sheet = self._repository.get_sheet(sheet_id)
        if sheet is None:
            raise AssetNotFoundError("Excel sheet was not found")
        return sheet
