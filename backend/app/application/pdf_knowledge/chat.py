from app.application.llm_preferences import WorkspaceLlmPreferenceService
from app.application.pdf_knowledge.models import (
    PdfAnswerBlock,
    PdfChatAnswer,
    PdfChunkSearchMatch,
    PdfCitation,
)
from app.application.pdf_knowledge.retrieval import PdfRetrievalService
from app.core.errors import UploadValidationError
from app.core.time import utc_now_iso
from app.domain.models import DraftChatAnswer, DraftCitation, UserRole
from app.ports.llm_client import LlmClient

DEFAULT_PDF_CHAT_RETRIEVAL_LIMIT = 8
MAX_PDF_CHAT_RETRIEVAL_LIMIT = 20


class PdfChatService:
    def __init__(
        self,
        *,
        retrieval: PdfRetrievalService,
        llm_client: LlmClient,
        llm_preferences: WorkspaceLlmPreferenceService,
    ) -> None:
        self._retrieval = retrieval
        self._llm_client = llm_client
        self._llm_preferences = llm_preferences

    def answer_question(
        self,
        *,
        question: str,
        file_ids: list[str] | None,
        limit: int | None = None,
        enable_deep_thinking: bool = False,
        user_role: UserRole,
    ) -> PdfChatAnswer:
        normalized_question = " ".join(question.split())
        if not normalized_question:
            raise UploadValidationError("PDF chat question is required")
        retrieval_limit = _normalize_limit(limit)
        retrieval_result = self._retrieval.search_chunks(
            query=normalized_question,
            file_ids=file_ids,
            limit=retrieval_limit,
            user_role=user_role,
        )
        matches = retrieval_result.matches
        if not matches:
            return PdfChatAnswer(
                question=normalized_question,
                answer_blocks=[
                    PdfAnswerBlock(
                        text="No visible PDF evidence is available for this question.",
                        citation_ids=[],
                    )
                ],
                citations=[],
                retrieval_matches=[],
                insufficient_evidence=True,
                follow_up_suggestions=[],
                warnings=[],
                created_at=utc_now_iso(),
            )
        preference = self._llm_preferences.get_preference()
        draft_answer = self._llm_client.answer_with_pdf_chunks(
            normalized_question,
            [_chunk_payload(match) for match in matches],
            model=preference.answer_model,
            provider=preference.answer_provider,
            enable_deep_thinking=enable_deep_thinking,
        )
        return _build_pdf_answer(
            question=normalized_question,
            draft_answer=draft_answer,
            matches=matches,
        )


def _build_pdf_answer(
    *,
    question: str,
    draft_answer: DraftChatAnswer,
    matches: list[PdfChunkSearchMatch],
) -> PdfChatAnswer:
    citation_index = {_evidence_id(match): match for match in matches}
    draft_quotes = _draft_quotes_by_evidence_id(draft_answer.citations, citation_index)
    cited_evidence_ids = [
        evidence_id
        for block in draft_answer.answer_blocks
        for evidence_id in block.evidence_ids
        if evidence_id in citation_index
    ]
    citations, citation_ids = _build_citations(
        evidence_ids=[*draft_quotes, *cited_evidence_ids],
        citation_index=citation_index,
        draft_quotes=draft_quotes,
    )
    answer_blocks = [
        PdfAnswerBlock(
            text=block.text,
            citation_ids=[
                citation_id
                for evidence_id in block.evidence_ids
                if (citation_id := citation_ids.get(evidence_id)) is not None
            ],
            reasoning=block.reasoning,
        )
        for block in draft_answer.answer_blocks
        if block.text.strip()
    ]
    if not answer_blocks:
        answer_blocks = [
            PdfAnswerBlock(
                text="The PDF evidence was retrieved, but no answer text was generated.",
                citation_ids=[],
            )
        ]
    return PdfChatAnswer(
        question=question,
        answer_blocks=answer_blocks,
        citations=citations,
        retrieval_matches=matches,
        insufficient_evidence=draft_answer.insufficient_evidence or not citations,
        follow_up_suggestions=draft_answer.follow_up_suggestions,
        warnings=[],
        created_at=utc_now_iso(),
    )


def _chunk_payload(match: PdfChunkSearchMatch) -> dict[str, object]:
    chunk = match.chunk
    return {
        "evidence_id": _evidence_id(match),
        "file_id": match.file.file_id,
        "file_name": match.file.display_name,
        "chunk_id": chunk.chunk_id,
        "chunk_index": chunk.chunk_index,
        "page_label": chunk.page_label,
        "title": chunk.title,
        "text": chunk.text,
        "excerpt": match.excerpt,
        "score": match.score,
        "matched_terms": match.matched_terms,
    }


def _evidence_id(match: PdfChunkSearchMatch) -> str:
    return f"{match.file.file_id}::{match.chunk.chunk_id}"


def _draft_quotes_by_evidence_id(
    draft_citations: list[DraftCitation],
    citation_index: dict[str, PdfChunkSearchMatch],
) -> dict[str, str]:
    quotes: dict[str, str] = {}
    for draft in draft_citations:
        if draft.evidence_id not in citation_index:
            continue
        quotes[draft.evidence_id] = draft.quote
    return quotes


def _build_citations(
    *,
    evidence_ids: list[str],
    citation_index: dict[str, PdfChunkSearchMatch],
    draft_quotes: dict[str, str],
) -> tuple[list[PdfCitation], dict[str, str]]:
    citations: list[PdfCitation] = []
    citation_ids: dict[str, str] = {}
    for evidence_id in evidence_ids:
        if evidence_id in citation_ids:
            continue
        match = citation_index.get(evidence_id)
        if match is None:
            continue
        citation_id = f"P{len(citations) + 1}"
        citation_ids[evidence_id] = citation_id
        chunk = match.chunk
        citations.append(
            PdfCitation(
                citation_id=citation_id,
                evidence_id=evidence_id,
                file_id=match.file.file_id,
                file_name=match.file.display_name,
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                page_label=chunk.page_label,
                title=chunk.title,
                quote=draft_quotes.get(evidence_id) or match.excerpt,
            )
        )
    return citations, citation_ids


def _normalize_limit(limit: int | None) -> int:
    requested_limit = DEFAULT_PDF_CHAT_RETRIEVAL_LIMIT if limit is None else limit
    return max(1, min(MAX_PDF_CHAT_RETRIEVAL_LIMIT, requested_limit))
