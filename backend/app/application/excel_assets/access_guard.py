from app.application.excel_assets.access import FileAccessContext
from app.core.errors import AssetNotFoundError
from app.domain.models import (
    ExcelFile,
    ExcelFileStatus,
    ExcelFileVersion,
    ExcelFileVisibility,
    ExcelSheet,
)
from app.ports.repository import ExcelAssetRepository


class ExcelAssetAccessGuard:
    def __init__(self, repository: ExcelAssetRepository) -> None:
        self._repository = repository

    def can_access_file(
        self,
        file: ExcelFile,
        access: FileAccessContext | None,
    ) -> bool:
        if access is None or access.can_manage_files:
            return True
        return file.visibility == ExcelFileVisibility.VISIBLE

    def require_file(
        self,
        file_id: str,
        access: FileAccessContext | None = None,
    ) -> ExcelFile:
        file = self._repository.get_file(file_id)
        if file is None or not self.can_access_file(file, access):
            raise AssetNotFoundError("Excel file was not found")
        return file

    def require_version(
        self,
        version_id: str,
        access: FileAccessContext | None = None,
    ) -> ExcelFileVersion:
        version = self._repository.get_version(version_id)
        if version is None:
            raise AssetNotFoundError("Excel file version was not found")
        self.require_file(version.file_id, access=access)
        return version

    def require_version_from_archived_file(self, version_id: str) -> ExcelFileVersion:
        version = self._repository.get_version(version_id)
        if version is None:
            raise AssetNotFoundError("Excel file version was not found")
        file = self._repository.get_file_including_deleted(version.file_id)
        if file is None or file.status != ExcelFileStatus.ARCHIVED:
            raise AssetNotFoundError("Excel file version was not found")
        return version

    def require_sheet(
        self,
        sheet_id: str,
        access: FileAccessContext | None = None,
    ) -> ExcelSheet:
        sheet = self._repository.get_sheet(sheet_id)
        if sheet is None:
            raise AssetNotFoundError("Excel sheet was not found")
        self.require_version(sheet.version_id, access=access)
        return sheet

    def require_sheet_from_archived_file(self, sheet_id: str) -> ExcelSheet:
        sheet = self._repository.get_sheet(sheet_id)
        if sheet is None:
            raise AssetNotFoundError("Excel sheet was not found")
        self.require_version_from_archived_file(sheet.version_id)
        return sheet
