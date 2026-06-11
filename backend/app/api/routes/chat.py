from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_chat_service, get_current_user, require_admin_user
from app.api.schemas import (
    AttachedDocumentResponse,
    ChatAnswerBlockResponse,
    ChatAnswerRequest,
    ChatAnswerResponse,
    ChatRequest,
    ChatRouteRequest,
    ChatRouteResponse,
    ChatSessionListResponse,
    ChatSessionResponse,
    ChatStageTimingResponse,
    ChatTurnListResponse,
    ChatTurnResponse,
    ExcelCitationResponse,
    LlmModelDefaultsResponse,
    LlmModelOptionsResponse,
    LlmPreferenceRequest,
    LlmPreferenceResponse,
    PinChatSessionRequest,
    RenameChatSessionRequest,
    SelectedDocumentResponse,
)
from app.application.chat.service import ChatService
from app.core.config import get_settings
from app.core.errors import AssetNotFoundError, InvalidLlmModelError
from app.core.llm_catalog import (
    is_supported_llm_model_for_provider,
    is_supported_llm_provider,
    list_supported_llm_models,
    list_supported_llm_provider_options,
)
from app.domain.models import (
    AuthenticatedUser,
    ChatAnswer,
    ChatRouteResult,
    ChatSession,
    ChatTurn,
    LlmPreference,
)

router = APIRouter(prefix="/api/excel", tags=["chat"])
ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]
CurrentUserDependency = Annotated[AuthenticatedUser, Depends(get_current_user)]
AdminDependency = Annotated[AuthenticatedUser, Depends(require_admin_user)]


@router.post("/chat", response_model=ChatAnswerResponse)
def answer_excel_question(
    request: ChatRequest,
    service: ChatServiceDependency,
    user: CurrentUserDependency,
) -> ChatAnswerResponse:
    return _to_chat_answer_response(
        service.answer_question(
            request.question,
            session_id=request.session_id,
            user_id=user.user_id,
            router_model=request.router_model,
            router_provider=request.router_provider,
            answer_model=request.answer_model,
            answer_provider=request.answer_provider,
            enable_deep_thinking=request.enable_deep_thinking,
        )
    )


@router.post("/chat/sessions", response_model=ChatSessionResponse)
def create_chat_session(
    service: ChatServiceDependency,
    user: CurrentUserDependency,
) -> ChatSessionResponse:
    return _to_session_response(service.create_session_for_user(user.user_id))


@router.get("/chat/sessions", response_model=ChatSessionListResponse)
def list_chat_sessions(
    service: ChatServiceDependency,
    user: CurrentUserDependency,
) -> ChatSessionListResponse:
    return ChatSessionListResponse(
        sessions=[
            _to_session_response(session)
            for session in service.list_sessions(user_id=user.user_id)
        ]
    )


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def get_chat_session(
    session_id: str,
    service: ChatServiceDependency,
    user: CurrentUserDependency,
) -> ChatSessionResponse:
    session = service.get_session(session_id, user_id=user.user_id)
    if session is None:
        raise AssetNotFoundError("chat session was not found")
    return _to_session_response(session)


@router.get(
    "/chat/sessions/{session_id}/turns",
    response_model=ChatTurnListResponse,
)
def list_chat_session_turns(
    session_id: str,
    service: ChatServiceDependency,
    user: CurrentUserDependency,
) -> ChatTurnListResponse:
    turns = service.list_turns(session_id, user_id=user.user_id)
    if turns is None:
        raise AssetNotFoundError("chat session was not found")
    return ChatTurnListResponse(turns=[_to_chat_turn_response(turn) for turn in turns])


@router.patch("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def rename_chat_session(
    session_id: str,
    request: RenameChatSessionRequest,
    service: ChatServiceDependency,
    user: CurrentUserDependency,
) -> ChatSessionResponse:
    session = service.rename_session(session_id, request.title, user_id=user.user_id)
    if session is None:
        raise AssetNotFoundError("chat session was not found")
    return _to_session_response(session)


@router.patch("/chat/sessions/{session_id}/pin", response_model=ChatSessionResponse)
def pin_chat_session(
    session_id: str,
    request: PinChatSessionRequest,
    service: ChatServiceDependency,
    user: CurrentUserDependency,
) -> ChatSessionResponse:
    session = service.set_session_pinned(
        session_id,
        request.pinned,
        user_id=user.user_id,
    )
    if session is None:
        raise AssetNotFoundError("chat session was not found")
    return _to_session_response(session)


@router.delete("/chat/sessions/{session_id}", status_code=204)
def delete_chat_session(
    session_id: str,
    service: ChatServiceDependency,
    user: CurrentUserDependency,
) -> None:
    deleted = service.delete_session(session_id, user_id=user.user_id)
    if not deleted:
        raise AssetNotFoundError("chat session was not found")


@router.post(
    "/chat/sessions/{session_id}/messages",
    response_model=ChatAnswerResponse,
)
def answer_excel_session_question(
    session_id: str,
    request: ChatRequest,
    service: ChatServiceDependency,
    user: CurrentUserDependency,
) -> ChatAnswerResponse:
    return _to_chat_answer_response(
        service.answer_question(
            request.question,
            session_id=session_id,
            user_id=user.user_id,
            router_model=request.router_model,
            router_provider=request.router_provider,
            answer_model=request.answer_model,
            answer_provider=request.answer_provider,
            enable_deep_thinking=request.enable_deep_thinking,
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
    user: CurrentUserDependency,
) -> ChatRouteResponse:
    return _to_chat_route_response(
        service.route_question(
            request.question,
            session_id=session_id,
            user_id=user.user_id,
            router_model=request.router_model,
            router_provider=request.router_provider,
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
    user: CurrentUserDependency,
) -> ChatAnswerResponse:
    return _to_chat_answer_response(
        service.answer_routed_question(
            request.question,
            session_id=session_id,
            user_id=user.user_id,
            answer_model=request.answer_model,
            answer_provider=request.answer_provider,
            selected_version_ids=request.selected_version_ids,
            enable_deep_thinking=request.enable_deep_thinking,
        )
    )


@router.get("/llm/options", response_model=LlmModelOptionsResponse)
def get_llm_model_options(_user: CurrentUserDependency) -> LlmModelOptionsResponse:
    return _default_llm_model_options()


def _default_llm_model_options() -> LlmModelOptionsResponse:
    settings = get_settings()
    return LlmModelOptionsResponse(
        models=list_supported_llm_models(),
        providers=list_supported_llm_provider_options(),
        defaults=LlmModelDefaultsResponse(
            summary_provider=settings.llm_summary_provider,
            summary_model=settings.llm_summary_model,
            router_provider=settings.llm_router_provider,
            router_model=settings.llm_router_model,
            answer_provider=settings.llm_answer_provider,
            answer_model=settings.llm_answer_model,
        ),
    )


@router.get("/llm/preferences", response_model=LlmPreferenceResponse)
def get_llm_preference(
    service: ChatServiceDependency,
    _user: CurrentUserDependency,
) -> LlmPreferenceResponse:
    preference = service.get_llm_preference()
    if preference is not None:
        return _to_llm_preference_response(preference)

    defaults = _default_llm_model_options().defaults
    return LlmPreferenceResponse(
        scope="workspace",
        summary_provider=defaults.summary_provider,
        summary_model=defaults.summary_model,
        router_provider=defaults.router_provider,
        router_model=defaults.router_model,
        answer_provider=defaults.answer_provider,
        answer_model=defaults.answer_model,
        created_at="",
        updated_at="",
    )


@router.patch("/llm/preferences", response_model=LlmPreferenceResponse)
def save_llm_preference(
    request: LlmPreferenceRequest,
    service: ChatServiceDependency,
    _admin: AdminDependency,
) -> LlmPreferenceResponse:
    _validate_llm_preference(request)
    return _to_llm_preference_response(
        service.save_llm_preference(
            summary_provider=request.summary_provider,
            summary_model=request.summary_model,
            router_provider=request.router_provider,
            router_model=request.router_model,
            answer_provider=request.answer_provider,
            answer_model=request.answer_model,
        )
    )


def _validate_llm_preference(request: LlmPreferenceRequest) -> None:
    _validate_stage_model("summary", request.summary_provider, request.summary_model)
    _validate_stage_model("router", request.router_provider, request.router_model)
    _validate_stage_model("answer", request.answer_provider, request.answer_model)


def _validate_stage_model(stage: str, provider: str, model: str) -> None:
    if not is_supported_llm_provider(provider):
        raise InvalidLlmModelError(stage=stage, model=f"{provider}:{model}")
    if not is_supported_llm_model_for_provider(provider, model):
        raise InvalidLlmModelError(stage=stage, model=f"{provider}:{model}")


def _to_chat_turn_response(turn: ChatTurn) -> ChatTurnResponse:
    return ChatTurnResponse(
        turn_id=turn.turn_id,
        session_id=turn.session_id,
        question=turn.question,
        answer=_to_chat_answer_response(
            ChatAnswer(
                session_id=turn.session_id,
                question=turn.question,
                answer_blocks=turn.answer_blocks,
                selected_documents=turn.selected_documents,
                newly_attached_documents=turn.newly_attached_documents,
                attached_documents=turn.attached_documents,
                citations=turn.citations,
                insufficient_evidence=turn.insufficient_evidence,
                follow_up_suggestions=turn.follow_up_suggestions,
                warnings=turn.warnings,
                timings=turn.timings,
                created_at=turn.created_at,
            )
        ),
        created_at=turn.created_at,
    )


def _to_chat_answer_response(answer: ChatAnswer) -> ChatAnswerResponse:
    return ChatAnswerResponse(
        session_id=answer.session_id,
        question=answer.question,
        answer_blocks=[
            ChatAnswerBlockResponse(
                text=block.text,
                citation_ids=block.citation_ids,
                reasoning=block.reasoning,
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
                evidence_id=citation.evidence_id,
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


def _to_llm_preference_response(preference: LlmPreference) -> LlmPreferenceResponse:
    return LlmPreferenceResponse(
        scope=preference.scope,
        summary_provider=preference.summary_provider,
        summary_model=preference.summary_model,
        router_provider=preference.router_provider,
        router_model=preference.router_model,
        answer_provider=preference.answer_provider,
        answer_model=preference.answer_model,
        created_at=preference.created_at,
        updated_at=preference.updated_at,
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
        user_id=session.user_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        title=session.title,
        pinned_at=session.pinned_at,
        status=session.status,
    )
