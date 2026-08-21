from dataclasses import dataclass

from app.domain.models import (
    ExcelArtifact,
    ExcelFile,
    ExcelFilePurgeJob,
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
class ArchiveExcelFileResult:
    file_id: str
    display_name: str
    disposition: str
    data_retained: bool
    archived_at: str
    purge_eligible_at: str


@dataclass(frozen=True)
class PurgeExcelFileResult:
    file_id: str
    job: ExcelFilePurgeJob


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
class SheetSearchMatch:
    sheet: ExcelSheet
    mapping: ExcelRowMapping
    row: list[str]
    matched_columns: list[int]


@dataclass(frozen=True)
class SheetSearchResult:
    sheet: ExcelSheet
    query: str
    matches: list[SheetSearchMatch]
    total_matches: int
    limit: int


@dataclass(frozen=True)
class WorkbookSearchResult:
    version_id: str
    query: str
    matches: list[SheetSearchMatch]
    total_matches: int
    limit: int


@dataclass(frozen=True)
class RowLookupResult:
    sheet: ExcelSheet
    mapping: ExcelRowMapping
    row: list[str]
