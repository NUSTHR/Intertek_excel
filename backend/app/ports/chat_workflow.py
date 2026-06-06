from dataclasses import dataclass
from typing import Protocol

from app.domain.models import ChatAnswer, ChatRouteResult


@dataclass(frozen=True)
class ChatWorkflowRequest:
    question: str
    session_id: str | None = None
    router_model: str | None = None
    router_provider: str | None = None
    answer_model: str | None = None
    answer_provider: str | None = None


class ChatWorkflowActions(Protocol):
    def route_question(
        self,
        question: str,
        session_id: str | None = None,
        *,
        router_model: str | None = None,
        router_provider: str | None = None,
    ) -> ChatRouteResult:
        ...

    def answer_routed_question(
        self,
        question: str,
        session_id: str,
        route_result: ChatRouteResult | None = None,
        *,
        answer_model: str | None = None,
        answer_provider: str | None = None,
        selected_version_ids: list[str] | None = None,
    ) -> ChatAnswer:
        ...


class ChatWorkflow(Protocol):
    def answer_question(
        self,
        request: ChatWorkflowRequest,
        actions: ChatWorkflowActions,
    ) -> ChatAnswer:
        ...
