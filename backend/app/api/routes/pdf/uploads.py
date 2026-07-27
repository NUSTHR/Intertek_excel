from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.routes.pdf.dependencies import (
    AdminDependency,
    PdfKnowledgeServiceDependency,
)
from app.api.routes.pdf.mappers import (
    to_pdf_upload_batch_response,
    to_pdf_upload_task_response,
)
from app.api.schema_models.pdf import (
    CreatePdfUploadTasksResponse,
    ListPdfUploadBatchesResponse,
    ListPdfUploadTasksResponse,
    PdfUploadBatchDetailResponse,
    PdfUploadTaskResponse,
)
from app.application.pdf_knowledge.uploads import MAX_UPLOAD_BYTES, PdfUploadCandidate
from app.core.errors import UploadValidationError

router = APIRouter()


@router.post(
    "/files/upload-tasks",
    response_model=CreatePdfUploadTasksResponse,
    status_code=202,
)
async def create_pdf_upload_tasks(
    files: Annotated[list[UploadFile], File(...)],
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> CreatePdfUploadTasksResponse:
    candidates: list[PdfUploadCandidate] = []
    for upload in files:
        original_filename = upload.filename or "uploaded.pdf"
        content = await _read_upload_content(upload)
        candidates.append(
            PdfUploadCandidate(
                original_filename=Path(original_filename).name,
                content=content,
                relative_path=original_filename,
            )
        )
    if not candidates:
        raise UploadValidationError("no supported PDF knowledge files were found")
    result = await run_in_threadpool(
        service.create_upload_batch,
        user_id=user.user_id,
        candidates=candidates,
    )
    return CreatePdfUploadTasksResponse(
        batch=to_pdf_upload_batch_response(result.batch),
        tasks=[to_pdf_upload_task_response(task) for task in result.tasks],
    )


@router.get("/files/upload-tasks", response_model=ListPdfUploadTasksResponse)
def list_pdf_upload_tasks(
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> ListPdfUploadTasksResponse:
    return ListPdfUploadTasksResponse(
        tasks=[
            to_pdf_upload_task_response(task)
            for task in service.list_upload_tasks(user_id=user.user_id)
        ]
    )


@router.get("/files/upload-batches", response_model=ListPdfUploadBatchesResponse)
def list_pdf_upload_batches(
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> ListPdfUploadBatchesResponse:
    return ListPdfUploadBatchesResponse(
        batches=[
            to_pdf_upload_batch_response(batch)
            for batch in service.list_upload_batches(user_id=user.user_id)
        ]
    )


@router.get(
    "/files/upload-batches/{batch_id}",
    response_model=PdfUploadBatchDetailResponse,
)
def get_pdf_upload_batch(
    batch_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> PdfUploadBatchDetailResponse:
    batch = service.get_upload_batch(batch_id, user_id=user.user_id)
    tasks = service.list_upload_batch_tasks(batch_id, user_id=user.user_id)
    return PdfUploadBatchDetailResponse(
        batch=to_pdf_upload_batch_response(batch),
        tasks=[to_pdf_upload_task_response(task) for task in tasks],
    )


@router.post(
    "/files/upload-batches/{batch_id}/cancel",
    response_model=PdfUploadBatchDetailResponse,
)
def cancel_pdf_upload_batch(
    batch_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> PdfUploadBatchDetailResponse:
    batch = service.cancel_upload_batch(batch_id, user_id=user.user_id)
    tasks = service.list_upload_batch_tasks(batch_id, user_id=user.user_id)
    return PdfUploadBatchDetailResponse(
        batch=to_pdf_upload_batch_response(batch),
        tasks=[to_pdf_upload_task_response(task) for task in tasks],
    )


@router.post(
    "/files/upload-batches/{batch_id}/retry",
    response_model=CreatePdfUploadTasksResponse,
    status_code=202,
)
def retry_pdf_upload_batch(
    batch_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> CreatePdfUploadTasksResponse:
    result = service.retry_upload_batch(batch_id, user_id=user.user_id)
    return CreatePdfUploadTasksResponse(
        batch=to_pdf_upload_batch_response(result.batch),
        tasks=[to_pdf_upload_task_response(task) for task in result.tasks],
    )


@router.get("/files/upload-tasks/{task_id}", response_model=PdfUploadTaskResponse)
def get_pdf_upload_task(
    task_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> PdfUploadTaskResponse:
    return to_pdf_upload_task_response(service.get_upload_task(task_id, user_id=user.user_id))


@router.post(
    "/files/upload-tasks/{task_id}/cancel",
    response_model=PdfUploadTaskResponse,
)
def cancel_pdf_upload_task(
    task_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> PdfUploadTaskResponse:
    return to_pdf_upload_task_response(service.cancel_upload_task(task_id, user_id=user.user_id))


@router.post(
    "/files/upload-tasks/{task_id}/retry",
    response_model=PdfUploadTaskResponse,
    status_code=202,
)
def retry_pdf_upload_task(
    task_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> PdfUploadTaskResponse:
    return to_pdf_upload_task_response(service.retry_upload_task(task_id, user_id=user.user_id))


async def _read_upload_content(file: UploadFile) -> bytes:
    try:
        return await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()
