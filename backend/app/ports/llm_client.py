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


class DocumentSummaryGenerator(Protocol):
    def generate_document_summary(
        self,
        profile: WorkbookProfile,
        *,
        model: str | None = None,
        provider: str | None = None,
    ) -> DocumentSummary:
        ...


class ExcelDocumentRouter(Protocol):
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


class PdfDocumentRouter(Protocol):
    def route_pdf_documents(
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


class ExcelAnswerGenerator(Protocol):
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


class PdfAnswerGenerator(Protocol):
    def answer_with_pdf_chunks(
        self,
        question: str,
        chunks: list[dict],
        document_manifest: dict[str, object] | None = None,
        previous_turns: list[ChatTurn] | None = None,
        model: str | None = None,
        provider: str | None = None,
        enable_deep_thinking: bool = False,
        cancellation_checker: CancellationChecker | None = None,
    ) -> DraftChatAnswer:
        ...


class PdfAnswerGroundingVerifier(Protocol):
    def verify_and_repair_pdf_answer(
        self,
        *,
        question: str,
        chunks: list[dict],
        document_manifest: dict[str, object],
        draft_answer: DraftChatAnswer,
        model: str | None = None,
        provider: str | None = None,
        cancellation_checker: CancellationChecker | None = None,
    ) -> DraftChatAnswer | None:
        """Return a grounded answer or ``None`` after one failed repair attempt."""
        ...


class PdfChatLlmClient(PdfDocumentRouter, PdfAnswerGenerator, Protocol):
    """The minimal LLM capabilities required by PDF chat orchestration."""


class LlmClient(
    DocumentSummaryGenerator,
    ExcelDocumentRouter,
    PdfDocumentRouter,
    ExcelAnswerGenerator,
    PdfAnswerGenerator,
    Protocol,
):
    """Compatibility protocol for adapters that implement every LLM capability."""
