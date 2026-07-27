import shutil
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
from app.domain.models import (
    AttachedDocument,
    ChatSession,
    DocumentSummary,
    ExcelArtifactType,
    ExcelFileStatus,
    ExcelVersionStatus,
    SheetSummary,
)
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


class LargeWorkbookReader:
    def read(self, _path: Path) -> WorkbookData:
        return WorkbookData(
            sheets=[
                WorkbookSheet(
                    sheet_index=1,
                    sheet_name="Large",
                    rows=[
                        ["Index", "Value"],
                        *[[str(index), f"value-{index}"] for index in range(1, 1201)],
                    ],
                )
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


@pytest.fixture
def large_service(tmp_path: Path) -> ExcelAssetService:
    repository = SQLiteExcelAssetRepository(tmp_path / "large.sqlite3")
    service = ExcelAssetService(
        repository=repository,
        storage=FilesystemExcelArtifactStorage(tmp_path / "storage"),
        workbook_reader=LargeWorkbookReader(),
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


def test_upload_persists_storage_relative_artifact_references(
    service: ExcelAssetService,
) -> None:
    result = service.upload_workbook(
        original_filename="risk.xlsx",
        content=b"fake workbook",
    )

    stored_sheet = service._repository.get_sheet(result.sheets[0].sheet_id)
    artifacts = service.list_artifacts(result.version.version_id)

    assert stored_sheet is not None
    assert not Path(stored_sheet.raw_csv_path).is_absolute()
    assert stored_sheet.raw_csv_path == (
        f"files/{result.file.file_id}/{result.version.version_id}/sheets/S001.csv"
    )
    assert all(not Path(artifact.path).is_absolute() for artifact in artifacts)
    assert {
        artifact.path
        for artifact in artifacts
        if artifact.artifact_type == ExcelArtifactType.RAW_CSV
    } == {
        f"files/{result.file.file_id}/{result.version.version_id}/sheets/S001.csv",
        f"files/{result.file.file_id}/{result.version.version_id}/sheets/S002.csv",
    }


def test_storage_relative_references_survive_project_directory_move(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    moved_root = tmp_path / "moved"
    first_repository = SQLiteExcelAssetRepository(first_root / "excel.sqlite3")
    first_service = ExcelAssetService(
        repository=first_repository,
        storage=FilesystemExcelArtifactStorage(first_root / "storage"),
        workbook_reader=FakeWorkbookReader(),
    )
    first_service.initialize()
    result = first_service.upload_workbook("risk.xlsx", b"fake workbook")

    with first_repository._connect() as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    moved_root.mkdir()
    shutil.copy2(first_root / "excel.sqlite3", moved_root / "excel.sqlite3")
    shutil.copytree(first_root / "storage", moved_root / "storage")

    moved_service = ExcelAssetService(
        repository=SQLiteExcelAssetRepository(moved_root / "excel.sqlite3"),
        storage=FilesystemExcelArtifactStorage(moved_root / "storage"),
        workbook_reader=FakeWorkbookReader(),
    )
    moved_service.initialize()

    preview = moved_service.preview_sheet(result.sheets[0].sheet_id)
    profile = moved_service.get_profile(result.version.version_id)

    assert preview.rows[1] == ["S001_R2", "Apex", "High"]
    assert profile.sheets[0].profile_rows[1] == ["Apex", "High"]


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


def test_rename_file_preserves_version_sheet_summary_and_chat_links(
    service: ExcelAssetService,
) -> None:
    result = service.upload_workbook("risk.xlsx", b"first")
    _save_summary_and_attachment(service, result)

    renamed = service.rename_file(result.file.file_id, "risk-renamed.xlsx")

    assert renamed.file_id == result.file.file_id
    assert renamed.active_version_id == result.version.version_id
    assert service.get_version(result.version.version_id).file_id == result.file.file_id
    assert service.list_sheets(result.version.version_id)[0].version_id == (
        result.version.version_id
    )

    summary = service._repository.get_summary(result.version.version_id)
    assert summary is not None
    assert summary.file_id == result.file.file_id
    assert summary.version_id == result.version.version_id

    attached = service._repository.list_attached_documents("session-risk")
    assert len(attached) == 1
    assert attached[0].file_id == result.file.file_id
    assert attached[0].version_id == result.version.version_id


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


def test_atomic_artifact_write_cleans_temporary_file_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = FilesystemExcelArtifactStorage(tmp_path / "storage")

    def fail_fsync(_file_descriptor: int) -> None:
        raise OSError("disk sync failed")

    monkeypatch.setattr(
        "app.adapters.storage.filesystem_storage.os.fsync",
        fail_fsync,
    )

    with pytest.raises(OSError, match="disk sync failed"):
        storage.save_original(
            file_id="file_1",
            version_id="version_1",
            original_filename="risk.xlsx",
            content=b"workbook",
        )

    original_dir = tmp_path / "storage" / "files" / "file_1" / "version_1" / "original"
    assert not (original_dir / "risk.xlsx").exists()
    assert list(original_dir.glob("*.tmp")) == []


def test_filesystem_storage_references_are_relative_and_relocatable(
    tmp_path: Path,
) -> None:
    storage = FilesystemExcelArtifactStorage(tmp_path / "storage")

    path = storage.write_csv(
        file_id="file_1",
        version_id="version_1",
        sheet_code="S001",
        rows=[["S001_R1", "value"]],
    )
    reference = storage.artifact_reference(path)

    assert reference == "files/file_1/version_1/sheets/S001.csv"
    assert storage.resolve_artifact_reference(reference) == path
    assert storage.resolve_artifact_reference(
        "/old/project/storage/files/file_1/version_1/sheets/S001.csv"
    ) == path
    assert storage.resolve_artifact_reference(
        r"C:\old\project\storage\files\file_1\version_1\sheets\S001.csv"
    ) == path
    with pytest.raises(ValueError, match="artifact reference must stay within storage root"):
        storage.resolve_artifact_reference("nested/files/file_1/version_1/sheets/S001.csv")

    with pytest.raises(ValueError, match="absolute artifact reference"):
        storage.resolve_artifact_reference(str(tmp_path / "outside.csv"))
    with pytest.raises(ValueError, match="absolute artifact reference"):
        storage.resolve_artifact_reference(r"C:\outside\sheet.csv")


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


def test_large_sheet_preview_and_rows_keep_pagination_contract(
    large_service: ExcelAssetService,
) -> None:
    result = large_service.upload_workbook("large.xlsx", b"large workbook")
    sheet_id = result.sheets[0].sheet_id

    preview = large_service.preview_sheet(sheet_id, offset=1000, limit=2)
    rows = large_service.list_sheet_rows(sheet_id, offset=1000, limit=2)
    lookup = large_service.lookup_row(sheet_id, "S001_R1001")

    assert preview.total_rows == 1201
    assert preview.rows == [
        ["S001_R1001", "1000", "value-1000"],
        ["S001_R1002", "1001", "value-1001"],
    ]
    assert rows.total_rows == 1201
    assert [mapping.row_id for mapping in rows.mappings] == ["S001_R1001", "S001_R1002"]
    assert rows.rows == preview.rows
    assert lookup.row == ["S001_R1001", "1000", "value-1000"]


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


def test_search_sheet_rows_keeps_short_query_scan_fallback(
    service: ExcelAssetService,
) -> None:
    result = service.upload_workbook("risk.xlsx", b"first")

    search = service.search_sheet_rows(result.sheets[1].sheet_id, query="Li", limit=10)

    assert search.total_matches == 1
    assert search.matches[0].mapping.row_id == "S002_R2"
    assert search.matches[0].matched_columns == [2]


def test_search_sheet_rows_handles_special_characters_from_index(
    service: ExcelAssetService,
) -> None:
    result = service.upload_workbook("risk.xlsx", b"first")

    search = service.search_sheet_rows(result.sheets[0].sheet_id, query="S001_R2", limit=10)

    assert search.total_matches == 1
    assert search.matches[0].row == ["S001_R2", "Apex", "High"]
    assert search.matches[0].matched_columns == [0]


def test_search_rebuilds_missing_row_index_for_existing_versions(
    service: ExcelAssetService,
) -> None:
    result = service.upload_workbook("risk.xlsx", b"first")
    service._repository.replace_row_search_entries(result.version.version_id, [])

    search = service.search_sheet_rows(result.sheets[0].sheet_id, query="apex", limit=10)

    assert search.total_matches == 1
    assert search.matches[0].row == ["S001_R2", "Apex", "High"]
    assert service._repository.has_row_search_entries(result.version.version_id)


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


def test_delete_file_requires_confirmation_and_soft_deletes_management_record(
    service: ExcelAssetService,
) -> None:
    result = service.upload_workbook("risk.xlsx", b"first")

    with pytest.raises(FileDeleteConfirmationRequiredError):
        service.delete_file(result.file.file_id)

    deleted = service.delete_file(result.file.file_id, confirm_delete=True)

    assert deleted.file_id == result.file.file_id
    assert deleted.display_name == "risk.xlsx"
    assert deleted.deleted_versions == 0
    assert deleted.deleted_sheets == 0
    assert deleted.deleted_artifacts == 0
    assert deleted.deleted_row_mappings == 0
    assert deleted.deleted_summaries == 0
    assert deleted.deleted_chat_session_documents == 0
    assert (service._storage._storage_root / "files" / result.file.file_id).exists()
    assert service.check_display_name("risk.xlsx").exists is False

    with pytest.raises(AssetNotFoundError):
        service.get_file(result.file.file_id)


def test_delete_file_hides_directory_record_and_preserves_historical_links(
    service: ExcelAssetService,
) -> None:
    result = service.upload_workbook("risk.xlsx", b"first")
    _save_summary_and_attachment(service, result)
    old_file_id = result.file.file_id
    old_version_id = result.version.version_id
    old_sheet_id = result.sheets[0].sheet_id

    deleted = service.delete_file(old_file_id, confirm_delete=True)
    replacement = service.upload_workbook("risk.xlsx", b"second")

    deleted_file = service._repository.get_file_including_deleted(old_file_id)
    assert deleted.file_id == old_file_id
    assert deleted_file is not None
    assert deleted_file.status == ExcelFileStatus.DELETED
    assert deleted_file.active_version_id is None
    assert deleted_file.display_name == f"deleted:{old_file_id}:risk.xlsx"
    assert service.check_display_name("risk.xlsx").file_id == replacement.file.file_id
    assert replacement.file.file_id != old_file_id
    assert replacement.version.file_id == replacement.file.file_id

    old_version = service._repository.get_version(old_version_id)
    old_sheet = service._repository.get_sheet(old_sheet_id)
    old_summary = service._repository.get_summary(old_version_id)
    old_attachments = service._repository.list_attached_documents("session-risk")

    assert old_version is not None
    assert old_version.file_id == old_file_id
    assert old_sheet is not None
    assert old_sheet.version_id == old_version_id
    assert old_summary is not None
    assert old_summary.file_id == old_file_id
    assert old_summary.version_id == old_version_id
    assert len(old_attachments) == 1
    assert old_attachments[0].file_id == old_file_id
    assert old_attachments[0].version_id == old_version_id

    with pytest.raises(AssetNotFoundError):
        service.get_version(old_version_id)
    legacy_sheets = service.list_sheets_for_legacy_chat_context(old_version_id)
    assert [sheet.sheet_id for sheet in legacy_sheets] == [
        sheet.sheet_id for sheet in result.sheets
    ]


def _save_summary_and_attachment(service: ExcelAssetService, result) -> None:
    service._repository.save_summary(
        DocumentSummary(
            summary_id=f"summary-{result.file.file_id}",
            file_id=result.file.file_id,
            version_id=result.version.version_id,
            summary_text="Risk workbook summary",
            business_domain="compliance",
            key_topics=["risk"],
            suitable_questions=["What risks are listed?"],
            unsuitable_questions=[],
            sheet_summaries=[
                SheetSummary(
                    sheet_id=result.sheets[0].sheet_id,
                    sheet_name=result.sheets[0].sheet_name,
                    summary="Supplier risk data",
                    important_columns=["Supplier", "Status"],
                    likely_question_types=["lookup"],
                )
            ],
            created_at="2026-07-01T00:00:00+00:00",
            document_title=result.file.display_name,
        )
    )
    service._repository.create_session(
        ChatSession(
            session_id="session-risk",
            user_id="user-risk",
            created_at="2026-07-01T00:00:00+00:00",
            updated_at="2026-07-01T00:00:00+00:00",
        )
    )
    service._repository.attach_document(
        AttachedDocument(
            session_id="session-risk",
            file_id=result.file.file_id,
            version_id=result.version.version_id,
            attached_at="2026-07-01T00:00:00+00:00",
            row_count=3,
            context_hash="risk-hash",
        )
    )
