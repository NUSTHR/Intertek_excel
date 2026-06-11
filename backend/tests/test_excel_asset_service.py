from pathlib import Path

import pytest

from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.adapters.storage.filesystem_storage import FilesystemExcelArtifactStorage
from app.application.excel_assets.service import ExcelAssetService
from app.core.errors import (
    AssetNotFoundError,
    FileDeleteConfirmationRequiredError,
    FileNameConflictError,
    InvalidExcelFileError,
)
from app.domain.models import ExcelArtifactType, ExcelVersionStatus
from app.ports.workbook_reader import WorkbookData, WorkbookSheet


class FakeWorkbookReader:
    def read(self, path: Path) -> WorkbookData:
        if path.read_bytes() == b"invalid workbook":
            raise InvalidExcelFileError("failed to read Excel workbook")
        return WorkbookData(
            sheets=[
                WorkbookSheet(
                    sheet_index=1,
                    sheet_name="Suppliers",
                    rows=[
                        ["Supplier", "Status"],
                        ["Apex", "High"],
                        ["Beacon", "Low"],
                    ],
                ),
                WorkbookSheet(
                    sheet_index=2,
                    sheet_name="Regions",
                    rows=[
                        ["Region", "Owner"],
                        ["East", "Liu"],
                    ],
                ),
            ]
        )


@pytest.fixture
def service(tmp_path: Path) -> ExcelAssetService:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    service = ExcelAssetService(
        repository=repository,
        storage=FilesystemExcelArtifactStorage(tmp_path / "storage"),
        workbook_reader=FakeWorkbookReader(),
    )
    service.initialize()
    return service


def test_upload_creates_version_sheets_mapping_and_preview(
    service: ExcelAssetService,
) -> None:
    result = service.upload_workbook(
        original_filename="risk.xlsx",
        content=b"fake workbook",
    )

    assert result.file.display_name == "risk.xlsx"
    assert result.version.status == ExcelVersionStatus.READY
    assert result.file.active_version_id == result.version.version_id
    assert [sheet.sheet_code for sheet in result.sheets] == ["S001", "S002"]

    preview = service.preview_sheet(result.sheets[0].sheet_id)
    assert preview.rows[0] == ["S001_R1", "Supplier", "Status"]
    assert preview.rows[2] == ["S001_R3", "Beacon", "Low"]

    row = service.lookup_row(result.sheets[0].sheet_id, "S001_R2")
    assert row.mapping.original_row_number == 2
    assert row.row == ["S001_R2", "Apex", "High"]


def test_duplicate_upload_requires_explicit_replacement(
    service: ExcelAssetService,
) -> None:
    first = service.upload_workbook("risk.xlsx", b"first")

    with pytest.raises(FileNameConflictError):
        service.upload_workbook("risk.xlsx", b"second")

    replacement = service.upload_workbook(
        "risk.xlsx",
        b"second",
        replace_existing=True,
    )

    assert replacement.file.file_id == first.file.file_id
    assert replacement.version.version_id != first.version.version_id
    assert replacement.file.active_version_id == replacement.version.version_id
    assert len(service.list_versions(first.file.file_id)) == 2


def test_rename_file_updates_display_name_and_rejects_conflict(
    service: ExcelAssetService,
) -> None:
    first = service.upload_workbook("risk.xlsx", b"first")
    second = service.upload_workbook("audit.xlsx", b"second")

    renamed = service.rename_file(first.file.file_id, "risk-renamed.xlsx")

    assert renamed.file_id == first.file.file_id
    assert renamed.display_name == "risk-renamed.xlsx"
    assert service.get_file(first.file.file_id).display_name == "risk-renamed.xlsx"

    with pytest.raises(FileNameConflictError):
        service.rename_file(second.file.file_id, "risk-renamed.xlsx")


def test_failed_replacement_does_not_change_active_version(
    service: ExcelAssetService,
) -> None:
    first = service.upload_workbook("risk.xlsx", b"first")

    with pytest.raises(InvalidExcelFileError):
        service.upload_workbook(
            "risk.xlsx",
            b"invalid workbook",
            replace_existing=True,
        )

    file = service.get_file(first.file.file_id)
    versions = service.list_versions(first.file.file_id)

    assert file.active_version_id == first.version.version_id
    assert sorted(version.status for version in versions) == [
        ExcelVersionStatus.FAILED,
        ExcelVersionStatus.READY,
    ]


def test_profile_artifacts_active_version_and_paginated_rows(
    service: ExcelAssetService,
) -> None:
    result = service.upload_workbook("risk.xlsx", b"first")

    active_version = service.get_active_file_version(result.file.file_id)
    profile = service.get_profile(result.version.version_id)
    artifacts = service.list_artifacts(result.version.version_id)
    rows = service.list_sheet_rows(result.sheets[0].sheet_id, offset=1, limit=1)

    assert active_version.version_id == result.version.version_id
    assert profile.sheets[0].candidate_header == ["Supplier", "Status"]
    assert profile.sheets[0].profile_rows == [
        ["Supplier", "Status"],
        ["Apex", "High"],
        ["Beacon", "Low"],
    ]
    assert {artifact.artifact_type for artifact in artifacts} == {
        ExcelArtifactType.ORIGINAL,
        ExcelArtifactType.RAW_CSV,
        ExcelArtifactType.PROFILE,
        ExcelArtifactType.ROW_MAPPING,
    }
    assert rows.total_rows == 3
    assert rows.mappings[0].row_id == "S001_R2"
    assert rows.rows[0] == ["S001_R2", "Apex", "High"]


def test_search_sheet_rows_returns_bounded_matches_with_columns(
    service: ExcelAssetService,
) -> None:
    result = service.upload_workbook("risk.xlsx", b"first")

    search = service.search_sheet_rows(result.sheets[0].sheet_id, query="apex", limit=10)

    assert search.sheet.sheet_id == result.sheets[0].sheet_id
    assert search.query == "apex"
    assert search.total_matches == 1
    assert search.matches[0].mapping.row_id == "S001_R2"
    assert search.matches[0].row == ["S001_R2", "Apex", "High"]
    assert search.matches[0].matched_columns == [1]


def test_search_version_rows_searches_all_sheets(
    service: ExcelAssetService,
) -> None:
    result = service.upload_workbook("risk.xlsx", b"first")

    search = service.search_version_rows(result.version.version_id, query="liu", limit=10)

    assert search.version_id == result.version.version_id
    assert search.total_matches == 1
    assert search.matches[0].sheet.sheet_name == "Regions"
    assert search.matches[0].mapping.row_id == "S002_R2"
    assert search.matches[0].matched_columns == [2]


def test_summary_profile_loads_full_rows_without_internal_row_ids(
    service: ExcelAssetService,
) -> None:
    result = service.upload_workbook("risk.xlsx", b"first")

    profile = service.get_summary_profile(result.version.version_id)

    assert profile.sheets[0].profile_rows == [
        ["Supplier", "Status"],
        ["Apex", "High"],
        ["Beacon", "Low"],
    ]


def test_delete_file_requires_confirmation_and_removes_related_data(
    service: ExcelAssetService,
) -> None:
    result = service.upload_workbook("risk.xlsx", b"first")

    with pytest.raises(FileDeleteConfirmationRequiredError):
        service.delete_file(result.file.file_id)

    deleted = service.delete_file(result.file.file_id, confirm_delete=True)

    assert deleted.file_id == result.file.file_id
    assert deleted.display_name == "risk.xlsx"
    assert deleted.deleted_versions == 1
    assert deleted.deleted_sheets == 2
    assert deleted.deleted_artifacts == 5
    assert deleted.deleted_row_mappings == 5
    assert deleted.deleted_summaries == 0
    assert deleted.deleted_chat_session_documents == 0
    assert not (service._storage._storage_root / "files" / result.file.file_id).exists()

    with pytest.raises(AssetNotFoundError):
        service.get_file(result.file.file_id)
