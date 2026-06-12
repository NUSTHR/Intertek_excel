from collections.abc import Callable
from typing import Protocol

from app.domain.models import (
    AttachedDocument,
    ChatTurn,
    DocumentSummary,
    DraftChatAnswer,
    SelectedDocument,
    WorkbookProfile,
)

CancellationChecker = Callable[[], None]


class LlmClient(Protocol):
    def generate_document_summary(
        self,
        profile: WorkbookProfile,
        *,
        model: str | None = None,
        provider: str | None = None,
    ) -> DocumentSummary:
        ...

    def route_documents(
        self,
        question: str,
        summaries: list[DocumentSummary],
        max_documents: int,
        user_questions: list[str] | None = None,
        attached_documents: list[AttachedDocument] | None = None,
        previous_turns: list[ChatTurn] | None = None,
        model: str | None = None,
        provider: str | None = None,
        cancellation_checker: CancellationChecker | None = None,
    ) -> list[SelectedDocument]:
        ...

    def answer_with_rows(
        self,
        question: str,
        documents: list[SelectedDocument],
        rows: list[dict],
        previous_turns: list[ChatTurn] | None = None,
        model: str | None = None,
        provider: str | None = None,
        enable_deep_thinking: bool = False,
        cancellation_checker: CancellationChecker | None = None,
    ) -> DraftChatAnswer:
        ...
