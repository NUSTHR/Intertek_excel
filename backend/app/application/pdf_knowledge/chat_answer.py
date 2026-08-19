from app.application.pdf_knowledge.models import (
    PdfAnswerBlock,
    PdfChatAnswer,
    PdfCitation,
    PdfGroundingChunk,
)
from app.core.errors import AssetNotFoundError
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    AttachedDocument,
    ChatAnswerBlock,
    ChatTurn,
    DraftChatAnswer,
    DraftCitation,
    ExcelCitation,
    PdfAttachedDocument,
    SelectedDocument,
)


def build_pdf_answer(
    *,
    session_id: str | None,
    question: str,
    draft_answer: DraftChatAnswer,
    grounding_chunks: list[PdfGroundingChunk],
    selected_documents: list[SelectedDocument],
    newly_attached_documents: list[SelectedDocument],
    attached_documents: list[PdfAttachedDocument],
    warnings: list[str],
    request_id: str | None = None,
) -> PdfChatAnswer:
    citation_index = {evidence_id(item): item for item in grounding_chunks}
    draft_quotes = _draft_quotes_by_evidence_id(draft_answer.citations, citation_index)
    cited_evidence_ids = [
        item_evidence_id
        for block in draft_answer.answer_blocks
        for item_evidence_id in block.evidence_ids
        if item_evidence_id in citation_index
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
                for item_evidence_id in block.evidence_ids
                if (citation_id := citation_ids.get(item_evidence_id)) is not None
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
        session_id=session_id,
        question=question,
        answer_blocks=answer_blocks,
        citations=citations,
        selected_documents=selected_documents,
        newly_attached_documents=newly_attached_documents,
        attached_documents=attached_documents,
        insufficient_evidence=draft_answer.insufficient_evidence or not citations,
        follow_up_suggestions=draft_answer.follow_up_suggestions,
        warnings=warnings,
        created_at=utc_now_iso(),
        request_id=request_id,
    )


def insufficient_evidence_answer(
    *,
    session_id: str,
    question: str,
    selected_documents: list[SelectedDocument],
    newly_attached_documents: list[SelectedDocument],
    attached_documents: list[PdfAttachedDocument],
    warnings: list[str],
    request_id: str | None = None,
) -> PdfChatAnswer:
    return PdfChatAnswer(
        session_id=session_id,
        question=question,
        answer_blocks=[
            PdfAnswerBlock(
                text="No visible PDF evidence is available for this question.",
                citation_ids=[],
            )
        ],
        citations=[],
        selected_documents=selected_documents,
        newly_attached_documents=newly_attached_documents,
        attached_documents=attached_documents,
        insufficient_evidence=True,
        follow_up_suggestions=[],
        warnings=warnings,
        created_at=utc_now_iso(),
        request_id=request_id,
    )


def chat_turn_from_pdf_answer(answer: PdfChatAnswer) -> ChatTurn:
    if answer.session_id is None:
        raise AssetNotFoundError("PDF chat session was not found")
    return ChatTurn(
        turn_id=new_id("turn"),
        session_id=answer.session_id,
        question=answer.question,
        answer_text="\n".join(block.text for block in answer.answer_blocks),
        citation_ids=[
            citation_id
            for block in answer.answer_blocks
            for citation_id in block.citation_ids
        ],
        selected_documents=answer.selected_documents,
        created_at=answer.created_at,
        answer_blocks=[
            ChatAnswerBlock(
                text=block.text,
                citation_ids=block.citation_ids,
                reasoning=block.reasoning,
            )
            for block in answer.answer_blocks
        ],
        newly_attached_documents=answer.newly_attached_documents,
        attached_documents=[
            attached_pdf_to_routing_document(document)
            for document in answer.attached_documents
        ],
        citations=[
            ExcelCitation(
                citation_id=citation.citation_id,
                evidence_id=citation.evidence_id,
                file_id=citation.file_id,
                version_id=citation.chunk_id,
                sheet_id=citation.chunk_id,
                sheet_name=citation.title,
                row_id=str(citation.chunk_index),
                row=[
                    citation.file_name,
                    citation.page_label or "",
                    citation.title,
                ],
                quote=citation.quote,
            )
            for citation in answer.citations
        ],
        insufficient_evidence=answer.insufficient_evidence,
        follow_up_suggestions=answer.follow_up_suggestions,
        warnings=answer.warnings,
        request_id=answer.request_id,
    )


def pdf_answer_from_chat_turn(turn: ChatTurn) -> PdfChatAnswer:
    return PdfChatAnswer(
        session_id=turn.session_id,
        question=turn.question,
        answer_blocks=[
            PdfAnswerBlock(
                text=block.text,
                citation_ids=block.citation_ids,
                reasoning=block.reasoning,
            )
            for block in turn.answer_blocks
        ],
        citations=[
            PdfCitation(
                citation_id=citation.citation_id,
                evidence_id=citation.evidence_id,
                file_id=citation.file_id,
                file_name=(
                    citation.row[0] if len(citation.row) >= 1 else citation.file_id
                ),
                chunk_id=citation.version_id,
                chunk_index=_safe_int(citation.row_id),
                page_label=citation.row[1] if len(citation.row) >= 2 else None,
                title=citation.sheet_name,
                quote=citation.quote,
            )
            for citation in turn.citations
        ],
        selected_documents=turn.selected_documents,
        newly_attached_documents=turn.newly_attached_documents,
        attached_documents=[
            PdfAttachedDocument(
                session_id=document.session_id,
                file_id=document.file_id,
                attached_at=document.attached_at,
                chunk_count=document.row_count,
                context_hash=document.context_hash,
                status=document.status,
            )
            for document in turn.attached_documents
        ],
        insufficient_evidence=turn.insufficient_evidence,
        follow_up_suggestions=turn.follow_up_suggestions,
        warnings=turn.warnings,
        created_at=turn.created_at,
        request_id=turn.request_id,
    )


def chunk_payload(
    item: PdfGroundingChunk,
    *,
    max_characters: int | None,
) -> dict[str, object]:
    chunk = item.chunk
    return {
        "evidence_id": evidence_id(item),
        "file_id": item.file.file_id,
        "file_name": item.file.display_name,
        "chunk_id": chunk.chunk_id,
        "chunk_index": chunk.chunk_index,
        "token_count": chunk.token_count,
        "page_label": chunk.page_label,
        "title": chunk.title,
        "text": chunk.text if max_characters is None else chunk.text[:max_characters],
        "excerpt": item.excerpt,
    }


def attached_pdf_to_routing_document(
    document: PdfAttachedDocument,
) -> AttachedDocument:
    return AttachedDocument(
        session_id=document.session_id,
        file_id=document.file_id,
        version_id=document.file_id,
        attached_at=document.attached_at,
        row_count=document.chunk_count,
        context_hash=document.context_hash,
        status=document.status,
    )


def evidence_id(item: PdfGroundingChunk) -> str:
    return f"{item.file.file_id}::{item.chunk.chunk_id}"


def _safe_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def _draft_quotes_by_evidence_id(
    draft_citations: list[DraftCitation],
    citation_index: dict[str, PdfGroundingChunk],
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
    citation_index: dict[str, PdfGroundingChunk],
    draft_quotes: dict[str, str],
) -> tuple[list[PdfCitation], dict[str, str]]:
    citations: list[PdfCitation] = []
    citation_ids: dict[str, str] = {}
    for item_evidence_id in evidence_ids:
        if item_evidence_id in citation_ids:
            continue
        item = citation_index.get(item_evidence_id)
        if item is None:
            continue
        citation_id = f"P{len(citations) + 1}"
        citation_ids[item_evidence_id] = citation_id
        chunk = item.chunk
        citations.append(
            PdfCitation(
                citation_id=citation_id,
                evidence_id=item_evidence_id,
                file_id=item.file.file_id,
                file_name=item.file.display_name,
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                page_label=chunk.page_label,
                title=chunk.title,
                quote=draft_quotes.get(item_evidence_id) or item.excerpt,
            )
        )
    return citations, citation_ids
