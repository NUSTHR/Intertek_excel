from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import (
    get_current_user,
    get_pdf_chat_service,
    get_pdf_knowledge_service,
    require_admin_user,
)
from app.api.schemas import (
    CreatePdfUploadTasksResponse,
    GeneratePdfSummaryResponse,
    ListPdfDocumentChunksResponse,
    ListPdfFilesResponse,
    ListPdfModelSettingsResponse,
    ListPdfUploadTasksResponse,
    PdfChatAnswerBlockResponse,
    PdfChatAnswerResponse,
    PdfChatRequest,
    PdfChunkSearchMatchResponse,
    PdfCitationResponse,
    PdfDocumentChunkResponse,
    PdfDocumentDetailResponse,
    PdfDocumentSummaryResponse,
    PdfFileResponse,
    PdfModelSettingResponse,
    PdfParserStatusResponse,
    PdfPreviewBlockResponse,
    PdfSchemaItemResponse,
    PdfUploadTaskResponse,
    SearchPdfChunksRequest,
    SearchPdfChunksResponse,
    UpdatePdfModelSettingRequest,
)
from app.application.pdf_knowledge import PdfChatService, PdfKnowledgeService
from app.application.pdf_knowledge.models import (
    PdfChatAnswer,
    PdfChunkSearchMatch,
)
from app.application.pdf_knowledge.service import MAX_UPLOAD_BYTES
from app.core.errors import UploadValidationError
from app.domain.models import (
    AuthenticatedUser,
    PdfDocumentChunk,
    PdfDocumentDetail,
    PdfDocumentSummary,
    PdfFile,
    PdfModelSetting,
    PdfUploadTask,
    PdfUploadTaskStatus,
)

router = APIRouter(prefix="/api/pdf", tags=["pdf-knowledge"])
PdfKnowledgeServiceDependency = Annotated[
    PdfKnowledgeService,
    Depends(get_pdf_knowledge_service),
]
PdfChatServiceDependency = Annotated[
    PdfChatService,
    Depends(get_pdf_chat_service),
]
AuthenticatedDependency = Annotated[AuthenticatedUser, Depends(get_current_user)]
AdminDependency = Annotated[AuthenticatedUser, Depends(require_admin_user)]


@router.get("/files", response_model=ListPdfFilesResponse)
def list_pdf_files(
    service: PdfKnowledgeServiceDependency,
    user: AuthenticatedDependency,
) -> ListPdfFilesResponse:
    return ListPdfFilesResponse(
        files=[
            _to_pdf_file_response(file)
            for file in service.list_files(user_role=user.role)
        ]
    )


@router.get("/parser/status", response_model=PdfParserStatusResponse)
def get_pdf_parser_status(
    service: PdfKnowledgeServiceDependency,
    _user: AuthenticatedDependency,
) -> PdfParserStatusResponse:
    status = service.get_parser_status()
    return PdfParserStatusResponse(
        backend=status.backend,
        available=status.available,
        command=status.command,
        version=status.version,
        detail=status.detail,
    )


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
    tasks: list[PdfUploadTask] = []
    for upload in files:
        original_filename = upload.filename or "uploaded.pdf"
        if not service.is_supported_filename(original_filename):
            await upload.close()
            continue
        content = await _read_upload_content(upload)
        task = await run_in_threadpool(
            service.create_upload_task,
            user_id=user.user_id,
            original_filename=Path(original_filename).name,
            content=content,
            relative_path=original_filename,
        )
        tasks.append(task)
    if not tasks:
        raise UploadValidationError("no supported PDF knowledge files were found")
    return CreatePdfUploadTasksResponse(
        tasks=[_to_pdf_upload_task_response(task) for task in tasks]
    )


@router.get("/files/upload-tasks", response_model=ListPdfUploadTasksResponse)
def list_pdf_upload_tasks(
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> ListPdfUploadTasksResponse:
    return ListPdfUploadTasksResponse(
        tasks=[
            _to_pdf_upload_task_response(task)
            for task in service.list_upload_tasks(user_id=user.user_id)
        ]
    )


@router.get("/files/upload-tasks/{task_id}", response_model=PdfUploadTaskResponse)
def get_pdf_upload_task(
    task_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> PdfUploadTaskResponse:
    return _to_pdf_upload_task_response(
        service.get_upload_task(task_id, user_id=user.user_id)
    )


@router.get("/files/{file_id}/detail", response_model=PdfDocumentDetailResponse)
def get_pdf_document_detail(
    file_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AuthenticatedDependency,
) -> PdfDocumentDetailResponse:
    return _to_pdf_document_detail_response(
        service.get_document_detail(file_id, user_role=user.role)
    )


@router.get("/files/{file_id}/chunks", response_model=ListPdfDocumentChunksResponse)
def list_pdf_document_chunks(
    file_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AuthenticatedDependency,
) -> ListPdfDocumentChunksResponse:
    return ListPdfDocumentChunksResponse(
        chunks=[
            _to_pdf_document_chunk_response(chunk)
            for chunk in service.list_document_chunks(file_id, user_role=user.role)
        ]
    )


@router.post("/retrieval/search", response_model=SearchPdfChunksResponse)
def search_pdf_document_chunks(
    request: SearchPdfChunksRequest,
    service: PdfKnowledgeServiceDependency,
    user: AuthenticatedDependency,
) -> SearchPdfChunksResponse:
    result = service.search_document_chunks(
        query=request.query,
        file_ids=request.file_ids,
        limit=request.limit,
        user_role=user.role,
    )
    return SearchPdfChunksResponse(
        query=result.query,
        matches=[_to_pdf_chunk_search_match_response(match) for match in result.matches],
        total_matches=result.total_matches,
        limit=result.limit,
    )


@router.post("/chat", response_model=PdfChatAnswerResponse)
def answer_pdf_question(
    request: PdfChatRequest,
    service: PdfChatServiceDependency,
    user: AuthenticatedDependency,
) -> PdfChatAnswerResponse:
    return _to_pdf_chat_answer_response(
        service.answer_question(
            question=request.question,
            file_ids=request.file_ids,
            limit=request.retrieval_limit,
            enable_deep_thinking=request.enable_deep_thinking,
            user_role=user.role,
        )
    )


@router.post(
    "/files/{file_id}/summary/generate",
    response_model=GeneratePdfSummaryResponse,
)
def generate_pdf_document_summary(
    file_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AuthenticatedDependency,
) -> GeneratePdfSummaryResponse:
    return GeneratePdfSummaryResponse(
        summary=_to_pdf_summary_response(
            service.generate_summary(file_id, user_role=user.role)
        )
    )


@router.get("/model-settings", response_model=ListPdfModelSettingsResponse)
def list_pdf_model_settings(
    service: PdfKnowledgeServiceDependency,
    _user: AuthenticatedDependency,
) -> ListPdfModelSettingsResponse:
    return ListPdfModelSettingsResponse(
        settings=[
            _to_pdf_model_setting_response(setting)
            for setting in service.list_model_settings()
        ]
    )


@router.patch("/model-settings/{setting_id}", response_model=ListPdfModelSettingsResponse)
def update_pdf_model_setting(
    setting_id: str,
    request: UpdatePdfModelSettingRequest,
    service: PdfKnowledgeServiceDependency,
    _admin: AdminDependency,
) -> ListPdfModelSettingsResponse:
    return ListPdfModelSettingsResponse(
        settings=[
            _to_pdf_model_setting_response(setting)
            for setting in service.update_model_setting(
                setting_id=setting_id,
                selected_provider=request.selected_provider,
                selected_model=request.selected_model,
            )
        ]
    )


def _to_pdf_file_response(file: PdfFile) -> PdfFileResponse:
    return PdfFileResponse(
        file_id=file.file_id,
        parent_id=file.parent_id,
        kind=file.kind.value,
        display_name=file.display_name,
        original_filename=file.original_filename,
        size_bytes=file.size_bytes,
        status=file.status.value,
        processing_status=file.processing_status.value,
        progress=file.progress,
        status_detail=file.status_detail,
        error_message=file.error_message,
        page_count=file.page_count,
        chunk_count=file.chunk_count,
        created_at=file.created_at,
        updated_at=file.updated_at,
        visible_to_members=file.visibility.value == "visible",
    )


def _to_pdf_upload_task_response(task: PdfUploadTask) -> PdfUploadTaskResponse:
    return PdfUploadTaskResponse(
        task_id=task.task_id,
        file_id=task.file_id,
        original_filename=task.original_filename,
        status=_task_status_for_ui(task),
        stage=task.stage.value,
        progress=task.progress,
        detail=task.detail,
        error_message=task.error_message,
        error_code=task.error_code,
        parser_backend=task.parser_backend,
        retry_count=task.retry_count,
        result=task.result,
        created_at=task.created_at,
        updated_at=task.updated_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        last_retry_at=task.last_retry_at,
    )


def _task_status_for_ui(task: PdfUploadTask) -> str:
    if task.status == PdfUploadTaskStatus.PROCESSING:
        if task.stage.value in {"parsing", "indexing"}:
            return task.stage.value
        if task.progress >= 90:
            return "indexing"
        return "parsing"
    return task.status.value


def _to_pdf_document_detail_response(
    detail: PdfDocumentDetail,
) -> PdfDocumentDetailResponse:
    return PdfDocumentDetailResponse(
        file_id=detail.file_id,
        summary=_to_pdf_summary_response(detail.summary),
        preview_blocks=[
            PdfPreviewBlockResponse(
                block_id=block.block_id,
                page_label=block.page_label,
                title=block.title,
                content=block.content,
            )
            for block in detail.preview_blocks
        ],
        schema=[
            PdfSchemaItemResponse(
                item_id=item.item_id,
                label=item.label,
                value=item.value,
            )
            for item in detail.schema
        ],
        tags=detail.tags,
    )


def _to_pdf_document_chunk_response(
    chunk: PdfDocumentChunk,
) -> PdfDocumentChunkResponse:
    return PdfDocumentChunkResponse(
        chunk_id=chunk.chunk_id,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        page_label=chunk.page_label,
        title=chunk.title,
        token_count=chunk.token_count,
        content_hash=chunk.content_hash,
        metadata=chunk.metadata,
    )


def _to_pdf_chunk_search_match_response(
    match: PdfChunkSearchMatch,
) -> PdfChunkSearchMatchResponse:
    return PdfChunkSearchMatchResponse(
        file=_to_pdf_file_response(match.file),
        chunk=_to_pdf_document_chunk_response(match.chunk),
        score=match.score,
        excerpt=match.excerpt,
        matched_terms=match.matched_terms,
    )


def _to_pdf_chat_answer_response(answer: PdfChatAnswer) -> PdfChatAnswerResponse:
    return PdfChatAnswerResponse(
        question=answer.question,
        answer_blocks=[
            PdfChatAnswerBlockResponse(
                text=block.text,
                citation_ids=block.citation_ids,
                reasoning=block.reasoning,
            )
            for block in answer.answer_blocks
        ],
        citations=[
            PdfCitationResponse(
                citation_id=citation.citation_id,
                evidence_id=citation.evidence_id,
                file_id=citation.file_id,
                file_name=citation.file_name,
                chunk_id=citation.chunk_id,
                chunk_index=citation.chunk_index,
                page_label=citation.page_label,
                title=citation.title,
                quote=citation.quote,
            )
            for citation in answer.citations
        ],
        retrieval_matches=[
            _to_pdf_chunk_search_match_response(match)
            for match in answer.retrieval_matches
        ],
        insufficient_evidence=answer.insufficient_evidence,
        follow_up_suggestions=answer.follow_up_suggestions,
        warnings=answer.warnings,
        created_at=answer.created_at,
    )


def _to_pdf_summary_response(
    summary: PdfDocumentSummary,
) -> PdfDocumentSummaryResponse:
    return PdfDocumentSummaryResponse(
        file_id=summary.file_id,
        status=summary.status,
        content=summary.content,
        updated_at=summary.updated_at,
        error_message=summary.error_message,
    )


def _to_pdf_model_setting_response(
    setting: PdfModelSetting,
) -> PdfModelSettingResponse:
    return PdfModelSettingResponse(
        id=setting.setting_id,
        label=setting.label,
        providers=setting.providers,
        models=setting.models,
        selected_provider=setting.selected_provider,
        selected_model=setting.selected_model,
    )


async def _read_upload_content(file: UploadFile) -> bytes:
    try:
        return await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()
