from fastapi import APIRouter

from app.api.routes.pdf.dependencies import (
    AuthenticatedDependency,
    PdfChatServiceDependency,
)
from app.api.routes.pdf.mappers import (
    to_pdf_chat_answer_response,
    to_pdf_chat_route_response,
    to_pdf_chat_turn_response,
    to_session_response,
)
from app.api.schema_models.common import (
    ChatSessionListResponse,
    ChatSessionResponse,
    PinChatSessionRequest,
    RenameChatSessionRequest,
)
from app.api.schema_models.pdf import (
    PdfChatAnswerRequest,
    PdfChatAnswerResponse,
    PdfChatRequest,
    PdfChatRouteRequest,
    PdfChatRouteResponse,
    PdfChatTurnListResponse,
)
from app.core.errors import AssetNotFoundError

router = APIRouter()


@router.post("/chat", response_model=PdfChatAnswerResponse)
def answer_pdf_question(
    request: PdfChatRequest,
    service: PdfChatServiceDependency,
    user: AuthenticatedDependency,
) -> PdfChatAnswerResponse:
    return to_pdf_chat_answer_response(
        service.answer_question(
            question=request.question,
            file_ids=request.file_ids,
            limit=request.retrieval_limit,
            enable_deep_thinking=request.enable_deep_thinking,
            user_role=user.role,
        )
    )


@router.post("/chat/sessions", response_model=ChatSessionResponse)
def create_pdf_chat_session(
    service: PdfChatServiceDependency,
    user: AuthenticatedDependency,
) -> ChatSessionResponse:
    return to_session_response(service.create_session_for_user(user.user_id))


@router.get("/chat/sessions", response_model=ChatSessionListResponse)
def list_pdf_chat_sessions(
    service: PdfChatServiceDependency,
    user: AuthenticatedDependency,
) -> ChatSessionListResponse:
    return ChatSessionListResponse(
        sessions=[
            to_session_response(session) for session in service.list_sessions(user_id=user.user_id)
        ]
    )


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def get_pdf_chat_session(
    session_id: str,
    service: PdfChatServiceDependency,
    user: AuthenticatedDependency,
) -> ChatSessionResponse:
    session = service.get_session(session_id, user_id=user.user_id)
    if session is None:
        raise AssetNotFoundError("PDF chat session was not found")
    return to_session_response(session)


@router.get(
    "/chat/sessions/{session_id}/turns",
    response_model=PdfChatTurnListResponse,
)
def list_pdf_chat_session_turns(
    session_id: str,
    service: PdfChatServiceDependency,
    user: AuthenticatedDependency,
) -> PdfChatTurnListResponse:
    turns = service.list_turns(session_id, user_id=user.user_id)
    if turns is None:
        raise AssetNotFoundError("PDF chat session was not found")
    return PdfChatTurnListResponse(turns=[to_pdf_chat_turn_response(turn) for turn in turns])


@router.patch("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def rename_pdf_chat_session(
    session_id: str,
    request: RenameChatSessionRequest,
    service: PdfChatServiceDependency,
    user: AuthenticatedDependency,
) -> ChatSessionResponse:
    session = service.rename_session(session_id, request.title, user_id=user.user_id)
    if session is None:
        raise AssetNotFoundError("PDF chat session was not found")
    return to_session_response(session)


@router.patch("/chat/sessions/{session_id}/pin", response_model=ChatSessionResponse)
def pin_pdf_chat_session(
    session_id: str,
    request: PinChatSessionRequest,
    service: PdfChatServiceDependency,
    user: AuthenticatedDependency,
) -> ChatSessionResponse:
    session = service.set_session_pinned(
        session_id,
        request.pinned,
        user_id=user.user_id,
    )
    if session is None:
        raise AssetNotFoundError("PDF chat session was not found")
    return to_session_response(session)


@router.delete("/chat/sessions/{session_id}", status_code=204)
def delete_pdf_chat_session(
    session_id: str,
    service: PdfChatServiceDependency,
    user: AuthenticatedDependency,
) -> None:
    deleted = service.delete_session(session_id, user_id=user.user_id)
    if not deleted:
        raise AssetNotFoundError("PDF chat session was not found")


@router.post(
    "/chat/sessions/{session_id}/route",
    response_model=PdfChatRouteResponse,
)
def route_pdf_session_question(
    session_id: str,
    request: PdfChatRouteRequest,
    service: PdfChatServiceDependency,
    user: AuthenticatedDependency,
) -> PdfChatRouteResponse:
    return to_pdf_chat_route_response(
        service.route_question(
            question=request.question,
            session_id=session_id,
            user_id=user.user_id,
            file_ids=request.file_ids,
            user_role=user.role,
        )
    )


@router.post(
    "/chat/sessions/{session_id}/answer",
    response_model=PdfChatAnswerResponse,
)
def answer_pdf_routed_session_question(
    session_id: str,
    request: PdfChatAnswerRequest,
    service: PdfChatServiceDependency,
    user: AuthenticatedDependency,
) -> PdfChatAnswerResponse:
    return to_pdf_chat_answer_response(
        service.answer_routed_question(
            session_id=session_id,
            user_id=user.user_id,
            question=request.question,
            selected_file_ids=request.selected_file_ids,
            enable_deep_thinking=request.enable_deep_thinking,
            user_role=user.role,
        )
    )


@router.post(
    "/chat/sessions/{session_id}/messages",
    response_model=PdfChatAnswerResponse,
)
def answer_pdf_session_question(
    session_id: str,
    request: PdfChatRequest,
    service: PdfChatServiceDependency,
    user: AuthenticatedDependency,
) -> PdfChatAnswerResponse:
    return to_pdf_chat_answer_response(
        service.answer_session_question(
            session_id=session_id,
            user_id=user.user_id,
            question=request.question,
            file_ids=request.file_ids,
            limit=request.retrieval_limit,
            enable_deep_thinking=request.enable_deep_thinking,
            user_role=user.role,
        )
    )
