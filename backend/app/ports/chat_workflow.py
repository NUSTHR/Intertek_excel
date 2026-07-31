from dataclasses import dataclass
from typing import Protocol

from app.application.chat.cancellation import ChatCancellationToken
from app.application.excel_assets.access import FileAccessContext
from app.domain.models import ChatAnswer, ChatRouteResult, LlmPreference


@dataclass(frozen=True)
class ChatWorkflowRequest:
    question: str
    session_id: str | None = None
    user_id: str = "legacy"
    enable_deep_thinking: bool = False
    llm_preference: LlmPreference | None = None
    cancellation_token: ChatCancellationToken | None = None
    file_access: FileAccessContext | None = None
    request_id: str | None = None


class ChatWorkflowActions(Protocol):
    def route_question(
        self,
        question: str,
        session_id: str | None = None,
        user_id: str = "legacy",
        *,
        llm_preference: LlmPreference | None = None,
        cancellation_token: ChatCancellationToken | None = None,
        file_access: FileAccessContext | None = None,
        request_id: str | None = None,
    ) -> ChatRouteResult:
        ...

    def answer_routed_question(
        self,
        question: str,
        session_id: str,
        user_id: str = "legacy",
        route_result: ChatRouteResult | None = None,
        *,
        selected_version_ids: list[str] | None = None,
        enable_deep_thinking: bool = False,
        llm_preference: LlmPreference | None = None,
        cancellation_token: ChatCancellationToken | None = None,
        file_access: FileAccessContext | None = None,
        request_id: str | None = None,
    ) -> ChatAnswer:
        ...


class ChatWorkflow(Protocol):
    def answer_question(
        self,
        request: ChatWorkflowRequest,
        actions: ChatWorkflowActions,
    ) -> ChatAnswer:
        ...
