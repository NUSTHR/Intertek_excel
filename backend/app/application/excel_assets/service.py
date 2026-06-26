import hashlib
import sqlite3
from pathlib import Path

from app.application.excel_assets.access import FileAccessContext
from app.application.excel_assets.access_guard import ExcelAssetAccessGuard
from app.application.excel_assets.csv_rows import CsvRowReader
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
from app.application.excel_assets.profile_loader import WorkbookProfileLoader
from app.application.excel_assets.search import SheetRowSearchEngine, SheetRowSearchPolicy
from app.application.excel_assets.version_processor import WorkbookVersionProcessor
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
    ExcelFileVisibility,
    ExcelSheet,
    ExcelVersionStatus,
    SheetProfile,
    WorkbookProfile,
)
from app.ports.repository import ExcelAssetRepository
from app.ports.storage import ExcelArtifactStorage
from app.ports.workbook_reader import WorkbookReader


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
        profile_builder = profile_builder or WorkbookProfileBuilder()
        self._csv_reader = CsvRowReader()
        self._profile_loader = WorkbookProfileLoader(self._csv_reader)
        self._access_guard = ExcelAssetAccessGuard(repository)
        self._version_processor = WorkbookVersionProcessor(
            repository=repository,
            storage=storage,
            workbook_reader=workbook_reader,
            profile_builder=profile_builder,
        )
        self._search_policy = search_policy or SheetRowSearchPolicy()
        self._search_engine = SheetRowSearchEngine(
            repository=repository,
            resolve_artifact_path=self._artifact_path,
            policy=self._search_policy,
        )

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
            try:
                self._repository.create_file(file)
            except sqlite3.IntegrityError as exc:
                conflict = self._repository.find_file_by_display_name(display_name)
                raise FileNameConflictError(
                    display_name=display_name,
                    file_id=conflict.file_id if conflict is not None else file.file_id,
                ) from exc

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
            result = self._version_processor.process_version(
                file=file,
                version=version,
                content=content,
            )
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

    def list_files(self, access: FileAccessContext | None = None) -> list[ExcelFile]:
        return [
            file
            for file in self._repository.list_files()
            if self._access_guard.can_access_file(file, access)
        ]

    def get_file(
        self,
        file_id: str,
        access: FileAccessContext | None = None,
    ) -> ExcelFile:
        return self._require_file(file_id, access=access)

    def rename_file(self, file_id: str, display_name: str) -> ExcelFile:
        file = self._require_file(file_id)
        normalized_name = self._normalize_display_name(display_name)
        existing_file = self._repository.find_file_by_display_name(normalized_name)
        if existing_file is not None and existing_file.file_id != file.file_id:
            raise FileNameConflictError(
                display_name=normalized_name,
                file_id=existing_file.file_id,
            )

        try:
            updated_file = self._repository.update_file_display_name(
                file_id=file.file_id,
                display_name=normalized_name,
                updated_at=utc_now_iso(),
            )
        except sqlite3.IntegrityError as exc:
            conflict = self._repository.find_file_by_display_name(normalized_name)
            raise FileNameConflictError(
                display_name=normalized_name,
                file_id=conflict.file_id if conflict is not None else file.file_id,
            ) from exc
        if updated_file is None:
            raise AssetNotFoundError("Excel file was not found")
        return updated_file

    def set_file_visibility(
        self,
        file_id: str,
        visible_to_members: bool,
    ) -> ExcelFile:
        self._require_file(file_id)
        updated_file = self._repository.update_file_visibility(
            file_id=file_id,
            visibility=(
                ExcelFileVisibility.VISIBLE
                if visible_to_members
                else ExcelFileVisibility.HIDDEN
            ),
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

    def get_active_file_version(
        self,
        file_id: str,
        access: FileAccessContext | None = None,
    ) -> ExcelFileVersion:
        file = self._require_file(file_id, access=access)
        if file.active_version_id is None:
            raise AssetNotFoundError("Excel file has no active version")
        return self._require_version(file.active_version_id)

    def get_version(
        self,
        version_id: str,
        access: FileAccessContext | None = None,
    ) -> ExcelFileVersion:
        return self._require_version(version_id, access=access)

    def list_versions(
        self,
        file_id: str,
        access: FileAccessContext | None = None,
    ) -> list[ExcelFileVersion]:
        self._require_file(file_id, access=access)
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

    def list_sheets(
        self,
        version_id: str,
        access: FileAccessContext | None = None,
    ) -> list[ExcelSheet]:
        self._require_version(version_id, access=access)
        return self._repository.list_sheets(version_id)

    def list_sheets_for_legacy_chat_context(
        self,
        version_id: str,
    ) -> list[ExcelSheet]:
        version = self._require_version_from_deleted_file(version_id)
        return self._repository.list_sheets(version.version_id)

    def get_profile(
        self,
        version_id: str,
        access: FileAccessContext | None = None,
    ) -> WorkbookProfile:
        version = self._require_version(version_id, access=access)
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
        return self._read_profile(self._artifact_path(profile_artifact.path), version=version)

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
                            self._artifact_path(sheet.raw_csv_path)
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
        access: FileAccessContext | None = None,
    ) -> SheetPreviewResult:
        sheet = self._require_sheet(sheet_id, access=access)
        safe_offset = max(0, offset)
        safe_limit = max(1, min(5000, limit))
        return SheetPreviewResult(
            sheet=sheet,
            rows=self._read_csv_rows_page(
                self._artifact_path(sheet.raw_csv_path),
                safe_offset,
                safe_limit,
            ),
            total_rows=sheet.row_count,
            offset=safe_offset,
            limit=safe_limit,
        )

    def list_sheet_rows(
        self,
        sheet_id: str,
        offset: int = 0,
        limit: int = 500,
        access: FileAccessContext | None = None,
    ) -> SheetRowsResult:
        sheet = self._require_sheet(sheet_id, access=access)
        safe_offset = max(0, offset)
        safe_limit = max(1, min(5000, limit))
        return SheetRowsResult(
            sheet=sheet,
            mappings=self._repository.list_row_mappings_for_sheet_page(
                sheet_id,
                safe_offset,
                safe_limit,
            ),
            rows=self._read_csv_rows_page(
                self._artifact_path(sheet.raw_csv_path),
                safe_offset,
                safe_limit,
            ),
            total_rows=sheet.row_count,
            offset=safe_offset,
            limit=safe_limit,
        )

    def list_sheet_rows_for_legacy_chat_context(
        self,
        sheet_id: str,
        offset: int = 0,
        limit: int = 500,
    ) -> SheetRowsResult:
        sheet = self._require_sheet_from_deleted_file(sheet_id)
        safe_offset = max(0, offset)
        safe_limit = max(1, min(5000, limit))
        return SheetRowsResult(
            sheet=sheet,
            mappings=self._repository.list_row_mappings_for_sheet_page(
                sheet_id,
                safe_offset,
                safe_limit,
            ),
            rows=self._read_csv_rows_page(
                self._artifact_path(sheet.raw_csv_path),
                safe_offset,
                safe_limit,
            ),
            total_rows=sheet.row_count,
            offset=safe_offset,
            limit=safe_limit,
        )

    def search_sheet_rows(
        self,
        sheet_id: str,
        query: str,
        limit: int = 50,
        access: FileAccessContext | None = None,
    ) -> SheetSearchResult:
        sheet = self._require_sheet(sheet_id, access=access)
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
        access: FileAccessContext | None = None,
    ) -> WorkbookSearchResult:
        self._require_version(version_id, access=access)
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
            if len(matches) < limit:
                matches.extend(sheet_result.matches[: safe_limit - len(matches)])

        return WorkbookSearchResult(
            version_id=version_id,
            query=normalized_query,
            matches=matches,
            total_matches=total_matches,
            limit=safe_limit,
        )

    def lookup_row(
        self,
        sheet_id: str,
        row_id: str,
        access: FileAccessContext | None = None,
    ) -> RowLookupResult:
        sheet = self._require_sheet(sheet_id, access=access)
        mapping = self._repository.get_row_mapping(sheet_id=sheet_id, row_id=row_id)
        if mapping is None:
            raise AssetNotFoundError("row mapping was not found")
        row_index = mapping.raw_csv_row_number - 1
        row = self._read_csv_row(self._artifact_path(sheet.raw_csv_path), row_index)
        if row is None:
            raise AssetNotFoundError("mapped CSV row was not found")
        return RowLookupResult(sheet=sheet, mapping=mapping, row=row)

    def _normalize_display_name(self, filename: str) -> str:
        normalized = Path(filename).name.strip()
        if not normalized:
            raise AssetNotFoundError("filename is required")
        return normalized

    def _sha256(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _artifact_path(self, reference: str) -> Path:
        return self._storage.resolve_artifact_reference(reference)

    def _read_csv_rows(self, path: Path) -> list[list[str]]:
        return self._csv_reader.read_rows(path)

    def _read_csv_rows_page(self, path: Path, offset: int, limit: int) -> list[list[str]]:
        return self._csv_reader.read_rows_page(path, offset, limit)

    def _read_csv_row(self, path: Path, row_index: int) -> list[str] | None:
        return self._csv_reader.read_row(path, row_index)

    def _search_sheet(
        self,
        sheet: ExcelSheet,
        query: str,
        limit: int,
    ) -> SheetSearchResult:
        return self._search_engine.search_sheet(
            sheet=sheet,
            query=query,
            limit=limit,
        )

    def _summary_profile_rows(
        self,
        sheet_profile: SheetProfile,
        raw_csv_path: Path | None,
    ) -> list[list[str]]:
        return self._profile_loader.summary_profile_rows(sheet_profile, raw_csv_path)

    def _read_profile(self, path: Path, version: ExcelFileVersion) -> WorkbookProfile:
        return self._profile_loader.read_profile(path, version=version)

    def _require_file(
        self,
        file_id: str,
        access: FileAccessContext | None = None,
    ) -> ExcelFile:
        return self._access_guard.require_file(file_id, access=access)

    def _require_version(
        self,
        version_id: str,
        access: FileAccessContext | None = None,
    ) -> ExcelFileVersion:
        return self._access_guard.require_version(version_id, access=access)

    def _require_version_from_deleted_file(self, version_id: str) -> ExcelFileVersion:
        return self._access_guard.require_version_from_deleted_file(version_id)

    def _require_sheet(
        self,
        sheet_id: str,
        access: FileAccessContext | None = None,
    ) -> ExcelSheet:
        return self._access_guard.require_sheet(sheet_id, access=access)

    def _require_sheet_from_deleted_file(self, sheet_id: str) -> ExcelSheet:
        return self._access_guard.require_sheet_from_deleted_file(sheet_id)
