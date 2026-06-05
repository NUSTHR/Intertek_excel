from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_chat_service
from app.api.schemas import (
    AttachedDocumentResponse,
    ChatAnswerBlockResponse,
    ChatAnswerRequest,
    ChatAnswerResponse,
    ChatRouteRequest,
    ChatRequest,
    ChatRouteResponse,
    ChatSessionResponse,
    ChatStageTimingResponse,
    ExcelCitationResponse,
    LlmModelDefaultsResponse,
    LlmModelOptionsResponse,
    SelectedDocumentResponse,
)
from app.application.chat.service import ChatService
from app.core.config import get_settings
from app.core.llm_catalog import list_supported_llm_models
from app.core.errors import AssetNotFoundError
from app.domain.models import ChatAnswer, ChatRouteResult, ChatSession

router = APIRouter(prefix="/api/excel", tags=["chat"])
ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]


@router.post("/chat", response_model=ChatAnswerResponse)
def answer_excel_question(
    request: ChatRequest,
    service: ChatServiceDependency,
) -> ChatAnswerResponse:
    return _to_chat_answer_response(
        service.answer_question(
            request.question,
            session_id=request.session_id,
            router_model=request.router_model,
            answer_model=request.answer_model,
        )
    )


@router.post("/chat/sessions", response_model=ChatSessionResponse)
def create_chat_session(service: ChatServiceDependency) -> ChatSessionResponse:
    return _to_session_response(service.create_session())


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def get_chat_session(
    session_id: str,
    service: ChatServiceDependency,
) -> ChatSessionResponse:
    session = service.get_session(session_id)
    if session is None:
        raise AssetNotFoundError("chat session was not found")
    return _to_session_response(session)


@router.post(
    "/chat/sessions/{session_id}/messages",
    response_model=ChatAnswerResponse,
)
def answer_excel_session_question(
    session_id: str,
    request: ChatRequest,
    service: ChatServiceDependency,
) -> ChatAnswerResponse:
    return _to_chat_answer_response(
        service.answer_question(
            request.question,
            session_id=session_id,
            router_model=request.router_model,
            answer_model=request.answer_model,
        )
    )


@router.post(
    "/chat/sessions/{session_id}/route",
    response_model=ChatRouteResponse,
)
def route_excel_session_question(
    session_id: str,
    request: ChatRouteRequest,
    service: ChatServiceDependency,
) -> ChatRouteResponse:
    return _to_chat_route_response(
        service.route_question(
            request.question,
            session_id=session_id,
            router_model=request.router_model,
        )
    )


@router.post(
    "/chat/sessions/{session_id}/answer",
    response_model=ChatAnswerResponse,
)
def answer_excel_routed_session_question(
    session_id: str,
    request: ChatAnswerRequest,
    service: ChatServiceDependency,
) -> ChatAnswerResponse:
    return _to_chat_answer_response(
        service.answer_routed_question(
            request.question,
            session_id=session_id,
            answer_model=request.answer_model,
            selected_version_ids=request.selected_version_ids,
        )
    )


@router.get("/llm/options", response_model=LlmModelOptionsResponse)
def get_llm_model_options() -> LlmModelOptionsResponse:
    settings = get_settings()
    return LlmModelOptionsResponse(
        models=list_supported_llm_models(),
        defaults=LlmModelDefaultsResponse(
            summary_model=settings.llm_summary_model,
            router_model=settings.llm_router_model,
            answer_model=settings.llm_answer_model,
        ),
    )


def _to_chat_answer_response(answer: ChatAnswer) -> ChatAnswerResponse:
    return ChatAnswerResponse(
        session_id=answer.session_id,
        question=answer.question,
        answer_blocks=[
            ChatAnswerBlockResponse(
                text=block.text,
                citation_ids=block.citation_ids,
            )
            for block in answer.answer_blocks
        ],
        selected_documents=[
            SelectedDocumentResponse(
                file_id=document.file_id,
                version_id=document.version_id,
                reason=document.reason,
                confidence=document.confidence,
            )
            for document in answer.selected_documents
        ],
        newly_attached_documents=[
            SelectedDocumentResponse(
                file_id=document.file_id,
                version_id=document.version_id,
                reason=document.reason,
                confidence=document.confidence,
            )
            for document in answer.newly_attached_documents
        ],
        attached_documents=[
            AttachedDocumentResponse(
                file_id=document.file_id,
                version_id=document.version_id,
                attached_at=document.attached_at,
                row_count=document.row_count,
                context_hash=document.context_hash,
                status=document.status,
            )
            for document in answer.attached_documents
        ],
        citations=[
            ExcelCitationResponse(
                citation_id=citation.citation_id,
                file_id=citation.file_id,
                version_id=citation.version_id,
                sheet_id=citation.sheet_id,
                sheet_name=citation.sheet_name,
                row_id=citation.row_id,
                row=citation.row,
                quote=citation.quote,
            )
            for citation in answer.citations
        ],
        insufficient_evidence=answer.insufficient_evidence,
        follow_up_suggestions=answer.follow_up_suggestions,
        warnings=answer.warnings,
        timings=[
            ChatStageTimingResponse(
                stage=timing.stage,
                duration_seconds=timing.duration_seconds,
            )
            for timing in answer.timings
        ],
        created_at=answer.created_at,
    )


def _to_chat_route_response(route_result: ChatRouteResult) -> ChatRouteResponse:
    return ChatRouteResponse(
        session_id=route_result.session_id,
        question=route_result.question,
        selected_documents=[
            SelectedDocumentResponse(
                file_id=document.file_id,
                version_id=document.version_id,
                reason=document.reason,
                confidence=document.confidence,
            )
            for document in route_result.selected_documents
        ],
        newly_attached_documents=[
            SelectedDocumentResponse(
                file_id=document.file_id,
                version_id=document.version_id,
                reason=document.reason,
                confidence=document.confidence,
            )
            for document in route_result.newly_attached_documents
        ],
        attached_documents=[
            AttachedDocumentResponse(
                file_id=document.file_id,
                version_id=document.version_id,
                attached_at=document.attached_at,
                row_count=document.row_count,
                context_hash=document.context_hash,
                status=document.status,
            )
            for document in route_result.attached_documents
        ],
        timings=[
            ChatStageTimingResponse(
                stage=timing.stage,
                duration_seconds=timing.duration_seconds,
            )
            for timing in route_result.timings
        ],
        created_at=route_result.created_at,
    )


def _to_session_response(session: ChatSession) -> ChatSessionResponse:
    return ChatSessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        status=session.status,
    )
