from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.api.dependencies import get_excel_asset_service
from app.api.schemas import (
    ActiveExcelFileResponse,
    CheckFileNameRequest,
    CheckFileNameResponse,
    ExcelArtifactResponse,
    ExcelFileResponse,
    ExcelFileVersionResponse,
    ExcelSheetResponse,
    ListExcelArtifactsResponse,
    ListExcelFilesResponse,
    ListExcelSheetsResponse,
    ListExcelVersionsResponse,
    RowLookupResponse,
    RowMappingResponse,
    SheetPreviewResponse,
    SheetProfileResponse,
    SheetRowResponse,
    SheetRowsResponse,
    UploadExcelResponse,
    WorkbookProfileResponse,
)
from app.application.excel_assets.service import ExcelAssetService
from app.core.config import get_settings
from app.core.errors import UploadValidationError
from app.domain.models import (
    ExcelArtifact,
    ExcelFile,
    ExcelFileVersion,
    ExcelRowMapping,
    ExcelSheet,
    SheetProfile,
    WorkbookProfile,
)

router = APIRouter(prefix="/api/excel", tags=["excel-assets"])
SUPPORTED_EXCEL_EXTENSIONS = {".xls", ".xlsx", ".xlsm", ".xltx", ".xltm"}
ExcelAssetServiceDependency = Annotated[
    ExcelAssetService,
    Depends(get_excel_asset_service),
]


@router.post("/files/check-name", response_model=CheckFileNameResponse)
def check_file_name(
    request: CheckFileNameRequest,
    service: ExcelAssetServiceDependency,
) -> CheckFileNameResponse:
    result = service.check_display_name(request.display_name)
    return CheckFileNameResponse(
        display_name=result.display_name,
        exists=result.exists,
        file_id=result.file_id,
        active_version_id=result.active_version_id,
    )


@router.post("/files", response_model=UploadExcelResponse)
async def upload_excel_file(
    file: Annotated[UploadFile, File(...)],
    service: ExcelAssetServiceDependency,
    replace_existing: Annotated[bool, Form()] = False,
) -> UploadExcelResponse:
    content = await file.read()
    _validate_upload(file.filename or "", content)
    result = service.upload_workbook(
        original_filename=file.filename or "uploaded.xlsx",
        content=content,
        replace_existing=replace_existing,
    )
    return UploadExcelResponse(
        file=_to_file_response(result.file),
        version=_to_version_response(result.version),
        sheets=[_to_sheet_response(sheet) for sheet in result.sheets],
        profile=_to_profile_response(result.profile),
    )


@router.get("/files", response_model=ListExcelFilesResponse)
def list_excel_files(
    service: ExcelAssetServiceDependency,
) -> ListExcelFilesResponse:
    return ListExcelFilesResponse(
        files=[_to_file_response(file) for file in service.list_files()]
    )


@router.get("/files/{file_id}", response_model=ExcelFileResponse)
def get_excel_file(
    file_id: str,
    service: ExcelAssetServiceDependency,
) -> ExcelFileResponse:
    return _to_file_response(service.get_file(file_id))


@router.get("/files/{file_id}/active", response_model=ActiveExcelFileResponse)
def get_active_excel_file_version(
    file_id: str,
    service: ExcelAssetServiceDependency,
) -> ActiveExcelFileResponse:
    return ActiveExcelFileResponse(
        file=_to_file_response(service.get_file(file_id)),
        version=_to_version_response(service.get_active_file_version(file_id)),
    )


@router.get("/files/{file_id}/versions", response_model=ListExcelVersionsResponse)
def list_excel_file_versions(
    file_id: str,
    service: ExcelAssetServiceDependency,
) -> ListExcelVersionsResponse:
    return ListExcelVersionsResponse(
        versions=[_to_version_response(version) for version in service.list_versions(file_id)]
    )


@router.post(
    "/files/{file_id}/versions/{version_id}/activate",
    response_model=ExcelFileVersionResponse,
)
def activate_excel_file_version(
    file_id: str,
    version_id: str,
    service: ExcelAssetServiceDependency,
) -> ExcelFileVersionResponse:
    return _to_version_response(service.activate_version(file_id, version_id))


@router.get("/versions/{version_id}/sheets", response_model=ListExcelSheetsResponse)
def list_excel_sheets(
    version_id: str,
    service: ExcelAssetServiceDependency,
) -> ListExcelSheetsResponse:
    return ListExcelSheetsResponse(
        sheets=[_to_sheet_response(sheet) for sheet in service.list_sheets(version_id)]
    )


@router.get("/versions/{version_id}/profile", response_model=WorkbookProfileResponse)
def get_excel_version_profile(
    version_id: str,
    service: ExcelAssetServiceDependency,
) -> WorkbookProfileResponse:
    return _to_profile_response(service.get_profile(version_id))


@router.get("/versions/{version_id}/artifacts", response_model=ListExcelArtifactsResponse)
def list_excel_version_artifacts(
    version_id: str,
    service: ExcelAssetServiceDependency,
) -> ListExcelArtifactsResponse:
    return ListExcelArtifactsResponse(
        artifacts=[
            _to_artifact_response(artifact)
            for artifact in service.list_artifacts(version_id)
        ]
    )


@router.get("/sheets/{sheet_id}/preview", response_model=SheetPreviewResponse)
def preview_excel_sheet(
    sheet_id: str,
    service: ExcelAssetServiceDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> SheetPreviewResponse:
    result = service.preview_sheet(sheet_id=sheet_id, offset=offset, limit=limit)
    return SheetPreviewResponse(
        sheet=_to_sheet_response(result.sheet),
        rows=result.rows,
        total_rows=result.total_rows,
        offset=result.offset,
        limit=result.limit,
    )


@router.get("/sheets/{sheet_id}/rows", response_model=SheetRowsResponse)
def list_excel_sheet_rows(
    sheet_id: str,
    service: ExcelAssetServiceDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> SheetRowsResponse:
    result = service.list_sheet_rows(sheet_id=sheet_id, offset=offset, limit=limit)
    return SheetRowsResponse(
        sheet=_to_sheet_response(result.sheet),
        rows=[
            SheetRowResponse(
                mapping=_to_mapping_response(mapping),
                row=row,
            )
            for mapping, row in zip(result.mappings, result.rows, strict=False)
        ],
        total_rows=result.total_rows,
        offset=result.offset,
        limit=result.limit,
    )


@router.get("/sheets/{sheet_id}/rows/{row_id}", response_model=RowLookupResponse)
def lookup_excel_row(
    sheet_id: str,
    row_id: str,
    service: ExcelAssetServiceDependency,
) -> RowLookupResponse:
    result = service.lookup_row(sheet_id=sheet_id, row_id=row_id)
    return RowLookupResponse(
        sheet=_to_sheet_response(result.sheet),
        mapping=_to_mapping_response(result.mapping),
        row=result.row,
    )


def _to_file_response(file: ExcelFile) -> ExcelFileResponse:
    return ExcelFileResponse(
        file_id=file.file_id,
        display_name=file.display_name,
        active_version_id=file.active_version_id,
        created_at=file.created_at,
        updated_at=file.updated_at,
    )


def _to_version_response(version: ExcelFileVersion) -> ExcelFileVersionResponse:
    return ExcelFileVersionResponse(
        version_id=version.version_id,
        file_id=version.file_id,
        original_filename=version.original_filename,
        file_hash=version.file_hash,
        status=version.status.value,
        error_message=version.error_message,
        created_at=version.created_at,
        activated_at=version.activated_at,
    )


def _to_sheet_response(sheet: ExcelSheet) -> ExcelSheetResponse:
    return ExcelSheetResponse(
        sheet_id=sheet.sheet_id,
        version_id=sheet.version_id,
        sheet_index=sheet.sheet_index,
        sheet_code=sheet.sheet_code,
        sheet_name=sheet.sheet_name,
        row_count=sheet.row_count,
        column_count=sheet.column_count,
        created_at=sheet.created_at,
    )


def _to_profile_response(profile: WorkbookProfile) -> WorkbookProfileResponse:
    return WorkbookProfileResponse(
        file_id=profile.file_id,
        version_id=profile.version_id,
        original_filename=profile.original_filename,
        file_hash=profile.file_hash,
        sheets=[_to_sheet_profile_response(sheet) for sheet in profile.sheets],
    )


def _to_sheet_profile_response(sheet: SheetProfile) -> SheetProfileResponse:
    return SheetProfileResponse(
        sheet_id=sheet.sheet_id,
        sheet_code=sheet.sheet_code,
        sheet_name=sheet.sheet_name,
        row_count=sheet.row_count,
        column_count=sheet.column_count,
        candidate_header=sheet.candidate_header,
        sample_rows=sheet.sample_rows,
    )


def _to_mapping_response(mapping: ExcelRowMapping) -> RowMappingResponse:
    return RowMappingResponse(
        row_id=mapping.row_id,
        version_id=mapping.version_id,
        sheet_id=mapping.sheet_id,
        original_row_number=mapping.original_row_number,
        raw_csv_row_number=mapping.raw_csv_row_number,
    )


def _to_artifact_response(artifact: ExcelArtifact) -> ExcelArtifactResponse:
    return ExcelArtifactResponse(
        artifact_id=artifact.artifact_id,
        version_id=artifact.version_id,
        artifact_type=artifact.artifact_type.value,
        path=artifact.path,
        created_at=artifact.created_at,
    )


def _validate_upload(filename: str, content: bytes) -> None:
    extension = f".{filename.rsplit('.', maxsplit=1)[-1].lower()}" if "." in filename else ""
    if extension not in SUPPORTED_EXCEL_EXTENSIONS:
        raise UploadValidationError(
            "unsupported Excel file extension; supported extensions are "
            ".xls, .xlsx, .xlsm, .xltx, and .xltm"
        )
    if not content:
        raise UploadValidationError("uploaded Excel file is empty")
    max_upload_bytes = get_settings().excel_max_upload_bytes
    if len(content) > max_upload_bytes:
        raise UploadValidationError(
            f"uploaded Excel file exceeds the {max_upload_bytes} byte limit"
        )
