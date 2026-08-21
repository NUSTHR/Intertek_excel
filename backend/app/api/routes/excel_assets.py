from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import (
    get_current_user,
    get_excel_asset_service,
    get_upload_task_service,
    require_admin_user,
)
from app.api.schemas import (
    ActiveExcelFileResponse,
    ArchivedExcelFileResponse,
    ArchiveExcelFileResponse,
    CheckFileNameRequest,
    CheckFileNameResponse,
    CreateUploadTaskResponse,
    ExcelArtifactResponse,
    ExcelFileResponse,
    ExcelFileVersionResponse,
    ExcelSheetResponse,
    ListArchivedExcelFilesResponse,
    ListExcelArtifactsResponse,
    ListExcelFilesResponse,
    ListExcelSheetsResponse,
    ListExcelVersionsResponse,
    PurgeExcelFileRequest,
    PurgeExcelFileResponse,
    RenameExcelFileRequest,
    RestoreExcelFileRequest,
    RowLookupResponse,
    RowMappingResponse,
    SetExcelFileVisibilityRequest,
    SheetPreviewResponse,
    SheetProfileResponse,
    SheetRowResponse,
    SheetRowsResponse,
    SheetSearchMatchResponse,
    SheetSearchResponse,
    UploadExcelResponse,
    UploadTaskResponse,
    WorkbookProfileResponse,
    WorkbookSearchResponse,
)
from app.application.excel_assets.access import FileAccessContext
from app.application.excel_assets.models import SheetSearchMatch
from app.application.excel_assets.service import ExcelAssetService
from app.application.excel_assets.upload_policy import ExcelUploadPolicy
from app.application.excel_assets.upload_tasks import UploadTaskService
from app.core.config import get_settings
from app.core.errors import AssetNotFoundError, FileNameConflictError
from app.domain.models import (
    AuthenticatedUser,
    ExcelArtifact,
    ExcelFile,
    ExcelFileVersion,
    ExcelFileVisibility,
    ExcelRowMapping,
    ExcelSheet,
    ExcelUploadTask,
    SheetProfile,
    WorkbookProfile,
)

router = APIRouter(prefix="/api/excel", tags=["excel-assets"])
ExcelAssetServiceDependency = Annotated[
    ExcelAssetService,
    Depends(get_excel_asset_service),
]
UploadTaskServiceDependency = Annotated[
    UploadTaskService,
    Depends(get_upload_task_service),
]
AuthenticatedDependency = Annotated[AuthenticatedUser, Depends(get_current_user)]
AdminDependency = Annotated[AuthenticatedUser, Depends(require_admin_user)]


@router.post("/files/check-name", response_model=CheckFileNameResponse)
def check_file_name(
    request: CheckFileNameRequest,
    service: ExcelAssetServiceDependency,
    _admin: AdminDependency,
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
    _admin: AdminDependency,
    replace_existing: Annotated[bool, Form()] = False,
) -> UploadExcelResponse:
    content = await _read_upload_content(file)
    _validate_upload(file.filename or "", content)
    result = await run_in_threadpool(
        service.upload_workbook,
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


@router.post(
    "/files/upload-tasks",
    response_model=CreateUploadTaskResponse,
    status_code=202,
)
async def create_upload_task(
    file: Annotated[UploadFile, File(...)],
    upload_tasks: UploadTaskServiceDependency,
    service: ExcelAssetServiceDependency,
    user: AdminDependency,
    replace_existing: Annotated[bool, Form()] = False,
) -> CreateUploadTaskResponse:
    content = await _read_upload_content(file)
    original_filename = file.filename or "uploaded.xlsx"
    _validate_upload(original_filename, content)
    name_check = service.check_display_name(original_filename)
    if name_check.exists and not replace_existing:
        raise FileNameConflictError(
            display_name=name_check.display_name,
            file_id=name_check.file_id or "",
        )
    task = upload_tasks.create_task(
        user_id=user.user_id,
        original_filename=original_filename,
        content=content,
        replace_existing=replace_existing,
    )
    return CreateUploadTaskResponse(
        task_id=task.task_id,
        status=task.status.value,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("/files/upload-tasks/{task_id}", response_model=UploadTaskResponse)
def get_upload_task(
    task_id: str,
    upload_tasks: UploadTaskServiceDependency,
    user: AdminDependency,
    service: ExcelAssetServiceDependency,
) -> UploadTaskResponse:
    task = upload_tasks.get_task(task_id, user_id=user.user_id)
    return _to_upload_task_response(task, service)


@router.get("/files", response_model=ListExcelFilesResponse)
def list_excel_files(
    service: ExcelAssetServiceDependency,
    user: AuthenticatedDependency,
) -> ListExcelFilesResponse:
    return ListExcelFilesResponse(
        files=[
            _to_file_response(file)
            for file in service.list_files(access=_file_access(user))
        ]
    )


@router.get("/files/archived", response_model=ListArchivedExcelFilesResponse)
def list_archived_excel_files(
    service: ExcelAssetServiceDependency,
    _admin: AdminDependency,
) -> ListArchivedExcelFilesResponse:
    return ListArchivedExcelFilesResponse(
        files=[
            ArchivedExcelFileResponse(
                file_id=file.file_id,
                display_name=file.archived_display_name or file.display_name,
                archived_at=file.deleted_at or file.updated_at,
                purge_eligible_at=file.purge_after or file.updated_at,
            )
            for file in service.list_archived_files()
        ]
    )


@router.get("/files/{file_id}", response_model=ExcelFileResponse)
def get_excel_file(
    file_id: str,
    service: ExcelAssetServiceDependency,
    user: AuthenticatedDependency,
) -> ExcelFileResponse:
    return _to_file_response(service.get_file(file_id, access=_file_access(user)))


@router.patch("/files/{file_id}", response_model=ExcelFileResponse)
def rename_excel_file(
    file_id: str,
    request: RenameExcelFileRequest,
    service: ExcelAssetServiceDependency,
    _admin: AdminDependency,
) -> ExcelFileResponse:
    return _to_file_response(service.rename_file(file_id, request.display_name))


@router.patch("/files/{file_id}/visibility", response_model=ExcelFileResponse)
def set_excel_file_visibility(
    file_id: str,
    request: SetExcelFileVisibilityRequest,
    service: ExcelAssetServiceDependency,
    _admin: AdminDependency,
) -> ExcelFileResponse:
    return _to_file_response(
        service.set_file_visibility(
            file_id,
            visible_to_members=request.visible_to_members,
        )
    )


@router.delete("/files/{file_id}", response_model=ArchiveExcelFileResponse)
def delete_excel_file(
    file_id: str,
    service: ExcelAssetServiceDependency,
    _admin: AdminDependency,
    confirm_delete: Annotated[bool, Query()] = False,
) -> ArchiveExcelFileResponse:
    result = service.archive_file(file_id, confirm_delete=confirm_delete)
    return ArchiveExcelFileResponse(
        file_id=result.file_id,
        display_name=result.display_name,
        disposition=result.disposition,
        data_retained=result.data_retained,
        archived_at=result.archived_at,
        purge_eligible_at=result.purge_eligible_at,
    )


@router.post("/files/{file_id}/restore", response_model=ExcelFileResponse)
def restore_excel_file(
    file_id: str,
    request: RestoreExcelFileRequest,
    service: ExcelAssetServiceDependency,
    _admin: AdminDependency,
) -> ExcelFileResponse:
    return _to_file_response(
        service.restore_file(file_id, display_name=request.display_name)
    )


@router.post("/files/{file_id}/purge", response_model=PurgeExcelFileResponse)
def purge_excel_file(
    file_id: str,
    request: PurgeExcelFileRequest,
    service: ExcelAssetServiceDependency,
    admin: AdminDependency,
) -> PurgeExcelFileResponse:
    result = service.purge_file(
        file_id,
        confirmation_display_name=request.confirmation_display_name,
        requested_by=admin.user_id,
        force=request.force,
    )
    return PurgeExcelFileResponse(
        file_id=result.file_id,
        job_id=result.job.job_id,
        status=result.job.status,
        attempt_count=result.job.attempt_count,
        deleted_counts=result.job.counts,
        error_message=result.job.error_message,
        requested_at=result.job.created_at,
        completed_at=result.job.completed_at,
    )


@router.get("/files/purge-jobs/{job_id}", response_model=PurgeExcelFileResponse)
def get_excel_purge_job(
    job_id: str,
    service: ExcelAssetServiceDependency,
    _admin: AdminDependency,
) -> PurgeExcelFileResponse:
    job = service.get_purge_job(job_id)
    return PurgeExcelFileResponse(
        file_id=job.file_id,
        job_id=job.job_id,
        status=job.status,
        attempt_count=job.attempt_count,
        deleted_counts=job.counts,
        error_message=job.error_message,
        requested_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get("/files/{file_id}/active", response_model=ActiveExcelFileResponse)
def get_active_excel_file_version(
    file_id: str,
    service: ExcelAssetServiceDependency,
    user: AuthenticatedDependency,
) -> ActiveExcelFileResponse:
    return ActiveExcelFileResponse(
        file=_to_file_response(service.get_file(file_id, access=_file_access(user))),
        version=_to_version_response(
            service.get_active_file_version(file_id, access=_file_access(user))
        ),
    )


@router.get("/files/{file_id}/versions", response_model=ListExcelVersionsResponse)
def list_excel_file_versions(
    file_id: str,
    service: ExcelAssetServiceDependency,
    user: AuthenticatedDependency,
) -> ListExcelVersionsResponse:
    return ListExcelVersionsResponse(
        versions=[
            _to_version_response(version)
            for version in service.list_versions(file_id, access=_file_access(user))
        ]
    )


@router.post(
    "/files/{file_id}/versions/{version_id}/activate",
    response_model=ExcelFileVersionResponse,
)
def activate_excel_file_version(
    file_id: str,
    version_id: str,
    service: ExcelAssetServiceDependency,
    _admin: AdminDependency,
) -> ExcelFileVersionResponse:
    return _to_version_response(service.activate_version(file_id, version_id))


@router.get("/versions/{version_id}/sheets", response_model=ListExcelSheetsResponse)
def list_excel_sheets(
    version_id: str,
    service: ExcelAssetServiceDependency,
    user: AuthenticatedDependency,
) -> ListExcelSheetsResponse:
    return ListExcelSheetsResponse(
        sheets=[
            _to_sheet_response(sheet)
            for sheet in service.list_sheets(version_id, access=_file_access(user))
        ]
    )


@router.get("/versions/{version_id}/profile", response_model=WorkbookProfileResponse)
def get_excel_version_profile(
    version_id: str,
    service: ExcelAssetServiceDependency,
    user: AuthenticatedDependency,
) -> WorkbookProfileResponse:
    return _to_profile_response(service.get_profile(version_id, access=_file_access(user)))


@router.get("/versions/{version_id}/artifacts", response_model=ListExcelArtifactsResponse)
def list_excel_version_artifacts(
    version_id: str,
    service: ExcelAssetServiceDependency,
    _admin: AdminDependency,
) -> ListExcelArtifactsResponse:
    return ListExcelArtifactsResponse(
        artifacts=[
            _to_artifact_response(artifact)
            for artifact in service.list_artifacts(version_id)
        ]
    )


@router.get("/versions/{version_id}/search", response_model=WorkbookSearchResponse)
def search_excel_version_rows(
    version_id: str,
    service: ExcelAssetServiceDependency,
    user: AuthenticatedDependency,
    query: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> WorkbookSearchResponse:
    result = service.search_version_rows(
        version_id=version_id,
        query=query,
        limit=limit,
        access=_file_access(user),
    )
    return WorkbookSearchResponse(
        version_id=result.version_id,
        query=result.query,
        matches=[_to_search_match_response(match) for match in result.matches],
        total_matches=result.total_matches,
        limit=result.limit,
    )


@router.get("/sheets/{sheet_id}/preview", response_model=SheetPreviewResponse)
def preview_excel_sheet(
    sheet_id: str,
    service: ExcelAssetServiceDependency,
    user: AuthenticatedDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> SheetPreviewResponse:
    result = service.preview_sheet(
        sheet_id=sheet_id,
        offset=offset,
        limit=limit,
        access=_file_access(user),
    )
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
    user: AuthenticatedDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> SheetRowsResponse:
    result = service.list_sheet_rows(
        sheet_id=sheet_id,
        offset=offset,
        limit=limit,
        access=_file_access(user),
    )
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


@router.get("/sheets/{sheet_id}/search", response_model=SheetSearchResponse)
def search_excel_sheet_rows(
    sheet_id: str,
    service: ExcelAssetServiceDependency,
    user: AuthenticatedDependency,
    query: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SheetSearchResponse:
    result = service.search_sheet_rows(
        sheet_id=sheet_id,
        query=query,
        limit=limit,
        access=_file_access(user),
    )
    return SheetSearchResponse(
        sheet=_to_sheet_response(result.sheet),
        query=result.query,
        matches=[_to_search_match_response(match) for match in result.matches],
        total_matches=result.total_matches,
        limit=result.limit,
    )


@router.get("/sheets/{sheet_id}/rows/{row_id}", response_model=RowLookupResponse)
def lookup_excel_row(
    sheet_id: str,
    row_id: str,
    service: ExcelAssetServiceDependency,
    user: AuthenticatedDependency,
) -> RowLookupResponse:
    result = service.lookup_row(
        sheet_id=sheet_id,
        row_id=row_id,
        access=_file_access(user),
    )
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
        visible_to_members=file.visibility == ExcelFileVisibility.VISIBLE,
    )


def _to_upload_task_response(
    task: ExcelUploadTask,
    service: ExcelAssetService,
) -> UploadTaskResponse:
    return UploadTaskResponse(
        task_id=task.task_id,
        status=task.status.value,
        original_filename=task.original_filename,
        replace_existing=task.replace_existing,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        result=_upload_task_result(task, service),
    )


def _upload_task_result(
    task: ExcelUploadTask,
    service: ExcelAssetService,
) -> UploadExcelResponse | None:
    version_id = str(task.result.get("version_id", "") or "")
    if task.status.value != "ready" or not version_id:
        return None
    try:
        version = service.get_version(version_id)
        file = service.get_file(version.file_id)
        sheets = service.list_sheets(version.version_id)
        profile = service.get_profile(version.version_id)
    except AssetNotFoundError:
        return None
    return UploadExcelResponse(
        file=_to_file_response(file),
        version=_to_version_response(version),
        sheets=[_to_sheet_response(sheet) for sheet in sheets],
        profile=_to_profile_response(profile),
    )


def _file_access(user: AuthenticatedUser) -> FileAccessContext:
    return FileAccessContext(user_id=user.user_id, role=user.role)


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


def _to_search_match_response(match: SheetSearchMatch) -> SheetSearchMatchResponse:
    return SheetSearchMatchResponse(
        sheet=_to_sheet_response(match.sheet),
        mapping=_to_mapping_response(match.mapping),
        row=match.row,
        matched_columns=match.matched_columns,
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
    settings = get_settings()
    ExcelUploadPolicy(
        supported_extensions=settings.supported_excel_extensions,
        max_bytes=settings.excel_max_upload_bytes,
    ).validate(filename, content)


async def _read_upload_content(file: UploadFile) -> bytes:
    settings = get_settings()
    try:
        return await file.read(settings.excel_max_upload_bytes + 1)
    finally:
        close = getattr(file, "close", None)
        if close is not None:
            await close()
