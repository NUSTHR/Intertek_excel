from dataclasses import dataclass

from app.domain.models import (
    ExcelArtifact,
    ExcelFile,
    ExcelFileVersion,
    ExcelRowMapping,
    ExcelSheet,
    WorkbookProfile,
)


@dataclass(frozen=True)
class FileNameCheckResult:
    display_name: str
    exists: bool
    file_id: str | None = None
    active_version_id: str | None = None


@dataclass(frozen=True)
class UploadExcelResult:
    file: ExcelFile
    version: ExcelFileVersion
    sheets: list[ExcelSheet]
    profile: WorkbookProfile
    artifacts: list[ExcelArtifact]


@dataclass(frozen=True)
class SheetPreviewResult:
    sheet: ExcelSheet
    rows: list[list[str]]
    total_rows: int
    offset: int
    limit: int


@dataclass(frozen=True)
class SheetRowsResult:
    sheet: ExcelSheet
    mappings: list[ExcelRowMapping]
    rows: list[list[str]]
    total_rows: int
    offset: int
    limit: int


@dataclass(frozen=True)
class RowLookupResult:
    sheet: ExcelSheet
    mapping: ExcelRowMapping
    row: list[str]
