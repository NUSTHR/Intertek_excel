from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock, RLock

from app.application.pdf_knowledge.model_settings import pdf_model_selection
from app.application.pdf_knowledge.models import (
    PdfAnswerBlock,
    PdfChatAnswer,
    PdfChunkSearchMatch,
    PdfCitation,
)
from app.application.pdf_knowledge.retrieval import PdfRetrievalService
from app.core.errors import AssetNotFoundError, UploadValidationError
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    AttachedDocument,
    ChatAnswerBlock,
    ChatSession,
    ChatTurn,
    ChatWorkspace,
    DocumentSummary,
    DraftChatAnswer,
    DraftCitation,
    ExcelCitation,
    PdfAttachedDocument,
    PdfChatRouteResult,
    PdfDocumentChunk,
    PdfFile,
    PdfFileKind,
    PdfFileVisibility,
    PdfProcessingStatus,
    SelectedDocument,
    SheetSummary,
    UserRole,
)
from app.ports.llm_client import LlmClient
from app.ports.repository import PdfChatRepository

DEFAULT_PDF_CHAT_RETRIEVAL_LIMIT = 8
MAX_PDF_CHAT_RETRIEVAL_LIMIT = 20
PDF_CHAT_WORKSPACE = ChatWorkspace.PDF.value


@dataclass
class _SessionOperationLock:
    lock: RLock = field(default_factory=RLock)
    users: int = 0
    discard_when_idle: bool = False


class PdfChatService:
    def __init__(
        self,
        *,
        retrieval: PdfRetrievalService,
        llm_client: LlmClient,
        sessions: PdfChatRepository,
    ) -> None:
        self._retrieval = retrieval
        self._llm_client = llm_client
        self._sessions = sessions
        self._session_locks: dict[str, _SessionOperationLock] = {}
        self._session_locks_guard = Lock()

    def create_session_for_user(self, user_id: str) -> ChatSession:
        now = utc_now_iso()
        session = ChatSession(
            session_id=new_id("pdfsession"),
            user_id=user_id,
            created_at=now,
            updated_at=now,
            workspace=ChatWorkspace.PDF,
        )
        self._sessions.create_session(session)
        return session

    def get_session(self, session_id: str, user_id: str | None = None) -> ChatSession | None:
        session = self._sessions.get_session(session_id, workspace=PDF_CHAT_WORKSPACE)
        if user_id is not None and session is not None and session.user_id != user_id:
            return None
        return session

    def list_sessions(self, user_id: str | None = None) -> list[ChatSession]:
        sessions = self._sessions.list_sessions(workspace=PDF_CHAT_WORKSPACE)
        if user_id is None:
            return sessions
        return [session for session in sessions if session.user_id == user_id]

    def rename_session(
        self,
        session_id: str,
        title: str,
        user_id: str | None = None,
    ) -> ChatSession | None:
        with self._session_operation_lock(session_id):
            if self.get_session(session_id, user_id=user_id) is None:
                return None
            return self._sessions.rename_session(
                session_id=session_id,
                title=self._normalize_session_title(title),
                updated_at=utc_now_iso(),
                workspace=PDF_CHAT_WORKSPACE,
            )

    def set_session_pinned(
        self,
        session_id: str,
        pinned: bool,
        user_id: str | None = None,
    ) -> ChatSession | None:
        with self._session_operation_lock(session_id):
            if self.get_session(session_id, user_id=user_id) is None:
                return None
            now = utc_now_iso()
            return self._sessions.set_session_pinned(
                session_id=session_id,
                pinned_at=now if pinned else None,
                updated_at=now,
                workspace=PDF_CHAT_WORKSPACE,
            )

    def delete_session(self, session_id: str, user_id: str | None = None) -> bool:
        with self._session_operation_lock(session_id):
            if self.get_session(session_id, user_id=user_id) is None:
                return False
            deleted = self._sessions.delete_session(
                session_id,
                workspace=PDF_CHAT_WORKSPACE,
            )
        if deleted:
            self._discard_session_operation_lock(session_id)
        return deleted

    def list_turns(
        self,
        session_id: str,
        user_id: str | None = None,
    ) -> list[ChatTurn] | None:
        if self.get_session(session_id, user_id=user_id) is None:
            return None
        return self._sessions.list_turns(session_id, workspace=PDF_CHAT_WORKSPACE)

    def answer_question(
        self,
        *,
        question: str,
        file_ids: list[str] | None,
        limit: int | None = None,
        enable_deep_thinking: bool = False,
        user_role: UserRole,
    ) -> PdfChatAnswer:
        _ = limit
        normalized_question = _normalize_question(question)
        route_result = self.route_question(
            question=normalized_question,
            session_id=None,
            user_id="legacy",
            file_ids=file_ids,
            user_role=user_role,
        )
        return self.answer_routed_question(
            session_id=route_result.session_id,
            user_id="legacy",
            question=normalized_question,
            route_result=route_result,
            enable_deep_thinking=enable_deep_thinking,
            user_role=user_role,
            persist_turn=True,
        )

    def answer_session_question(
        self,
        *,
        session_id: str,
        user_id: str,
        question: str,
        file_ids: list[str] | None,
        limit: int | None = None,
        enable_deep_thinking: bool = False,
        user_role: UserRole,
    ) -> PdfChatAnswer:
        _ = limit
        with self._session_operation_lock(session_id):
            session = self.get_session(session_id, user_id=user_id)
            if session is None:
                raise AssetNotFoundError("PDF chat session was not found")
            normalized_question = _normalize_question(question)
            route_result = self._route_question_locked(
                question=normalized_question,
                session=session,
                file_ids=file_ids,
                user_role=user_role,
            )
            return self._answer_routed_question_locked(
                question=normalized_question,
                session=session,
                route_result=route_result,
                selected_file_ids=None,
                enable_deep_thinking=enable_deep_thinking,
                user_role=user_role,
                persist_turn=True,
            )

    def route_question(
        self,
        *,
        question: str,
        session_id: str | None,
        user_id: str,
        file_ids: list[str] | None,
        user_role: UserRole,
    ) -> PdfChatRouteResult:
        normalized_question = _normalize_question(question)
        if session_id is not None:
            with self._session_operation_lock(session_id):
                session = self.get_session(session_id, user_id=user_id)
                if session is None:
                    raise AssetNotFoundError("PDF chat session was not found")
                return self._route_question_locked(
                    question=normalized_question,
                    session=session,
                    file_ids=file_ids,
                    user_role=user_role,
                )
        session = self.create_session_for_user(user_id)
        return self._route_question_locked(
            question=normalized_question,
            session=session,
            file_ids=file_ids,
            user_role=user_role,
        )

    def answer_routed_question(
        self,
        *,
        session_id: str,
        user_id: str,
        question: str,
        route_result: PdfChatRouteResult | None = None,
        selected_file_ids: list[str] | None = None,
        enable_deep_thinking: bool = False,
        user_role: UserRole,
        persist_turn: bool = True,
    ) -> PdfChatAnswer:
        with self._session_operation_lock(session_id):
            session = self.get_session(session_id, user_id=user_id)
            if session is None:
                raise AssetNotFoundError("PDF chat session was not found")
            return self._answer_routed_question_locked(
                question=_normalize_question(question),
                session=session,
                route_result=route_result,
                selected_file_ids=selected_file_ids,
                enable_deep_thinking=enable_deep_thinking,
                user_role=user_role,
                persist_turn=persist_turn,
            )

    def _route_question_locked(
        self,
        *,
        question: str,
        session: ChatSession,
        file_ids: list[str] | None,
        user_role: UserRole,
    ) -> PdfChatRouteResult:
        model_selection = pdf_model_selection(
            self._sessions.list_pdf_model_settings(),
            "router",
        )
        scope_file_ids = self._resolve_scope_pdf_file_ids(
            file_ids=file_ids,
            user_role=user_role,
        )
        has_explicit_scope = bool(_dedupe_file_ids(file_ids or []))
        existing_turns = self._filter_accessible_turns(
            self._sessions.list_turns(session.session_id, workspace=PDF_CHAT_WORKSPACE),
            user_role=user_role,
        )
        attached_before = self._filter_accessible_attached_documents(
            self._sessions.list_pdf_attached_documents(session.session_id),
            user_role=user_role,
        )
        attached_before = self._filter_attached_documents_by_scope(
            attached_before,
            scope_file_ids=scope_file_ids,
            has_explicit_scope=has_explicit_scope,
        )
        summaries = self._routing_summaries(file_ids=file_ids, user_role=user_role)
        selected_documents = self._llm_client.route_documents(
            question=question,
            summaries=summaries,
            max_documents=3,
            user_questions=[turn.question for turn in existing_turns] + [question],
            attached_documents=[
                _attached_pdf_to_excel_document(document)
                for document in attached_before
            ],
            previous_turns=existing_turns,
            model=model_selection.model,
            provider=model_selection.provider,
        )
        selected_documents = self._filter_accessible_selected_documents(
            selected_documents,
            user_role=user_role,
        )
        newly_attached = self._attach_new_documents(
            session_id=session.session_id,
            selected_documents=selected_documents,
            attached_documents=attached_before,
            user_role=user_role,
        )
        attached_after = self._filter_accessible_attached_documents(
            self._sessions.list_pdf_attached_documents(session.session_id),
            user_role=user_role,
        )
        attached_after = self._filter_attached_documents_by_scope(
            attached_after,
            scope_file_ids=scope_file_ids,
            has_explicit_scope=has_explicit_scope,
        )
        created_at = utc_now_iso()
        self._sessions.touch_session(session.session_id, created_at)
        return PdfChatRouteResult(
            session_id=session.session_id,
            question=question,
            selected_documents=selected_documents,
            newly_attached_documents=newly_attached,
            attached_documents=attached_after,
            created_at=created_at,
        )

    def _answer_routed_question_locked(
        self,
        *,
        question: str,
        session: ChatSession,
        route_result: PdfChatRouteResult | None,
        selected_file_ids: list[str] | None,
        enable_deep_thinking: bool,
        user_role: UserRole,
        persist_turn: bool,
    ) -> PdfChatAnswer:
        attached_documents = self._filter_accessible_attached_documents(
            self._sessions.list_pdf_attached_documents(session.session_id),
            user_role=user_role,
        )
        if route_result is not None:
            attached_documents = route_result.attached_documents
        documents = self._resolve_documents_for_answer(
            attached_documents=attached_documents,
            route_result=route_result,
            selected_file_ids=selected_file_ids,
        )
        documents = self._filter_accessible_selected_documents(
            documents,
            user_role=user_role,
        )
        matches = self._matches_for_documents(documents, user_role=user_role)
        if not matches:
            answer = _insufficient_evidence_answer(
                session_id=session.session_id,
                question=question,
                selected_documents=documents,
                newly_attached_documents=(
                    route_result.newly_attached_documents
                    if route_result is not None
                    else []
                ),
                attached_documents=attached_documents,
            )
        else:
            model_selection = pdf_model_selection(
                self._sessions.list_pdf_model_settings(),
                "chat",
            )
            draft_answer = self._llm_client.answer_with_pdf_chunks(
                question,
                [_chunk_payload(match) for match in matches],
                model=model_selection.model,
                provider=model_selection.provider,
                enable_deep_thinking=enable_deep_thinking,
            )
            answer = _build_pdf_answer(
                session_id=session.session_id,
                question=question,
                draft_answer=draft_answer,
                matches=matches,
                selected_documents=documents,
                newly_attached_documents=(
                    route_result.newly_attached_documents
                    if route_result is not None
                    else []
                ),
                attached_documents=attached_documents,
            )
        if persist_turn:
            self._sessions.create_turn(_chat_turn_from_pdf_answer(answer))
            self._sessions.touch_session(session.session_id, answer.created_at)
        return answer

    def _routing_summaries(
        self,
        *,
        file_ids: list[str] | None,
        user_role: UserRole,
    ) -> list[DocumentSummary]:
        has_explicit_scope = bool(_dedupe_file_ids(file_ids or []))
        allowed_file_ids = set(
            self._resolve_scope_pdf_file_ids(file_ids=file_ids, user_role=user_role)
        )
        if has_explicit_scope and not allowed_file_ids:
            return []
        files = {
            file.file_id: file
            for file in self._sessions.list_pdf_files()
            if _is_visible_ready_pdf(file, user_role)
        }
        summaries = [
            summary
            for summary in self._sessions.list_pdf_document_summaries()
            if summary.status == "ready"
            and summary.file_id in files
            and (not has_explicit_scope or summary.file_id in allowed_file_ids)
        ]
        return [
            _pdf_summary_to_document_summary(
                summary=summary,
                file=files[summary.file_id],
            )
            for summary in summaries
        ]

    def _filter_accessible_turns(
        self,
        turns: list[ChatTurn],
        *,
        user_role: UserRole,
    ) -> list[ChatTurn]:
        return [
            turn
            for turn in turns
            if all(
                self._can_use_file(document.file_id, user_role=user_role)
                for document in [
                    *turn.selected_documents,
                    *turn.newly_attached_documents,
                ]
            )
            and all(
                self._can_use_file(citation.file_id, user_role=user_role)
                for citation in turn.citations
            )
        ]

    def _filter_accessible_attached_documents(
        self,
        documents: list[PdfAttachedDocument],
        *,
        user_role: UserRole,
    ) -> list[PdfAttachedDocument]:
        return [
            document
            for document in documents
            if self._can_use_file(document.file_id, user_role=user_role)
        ]

    def _filter_accessible_selected_documents(
        self,
        documents: list[SelectedDocument],
        *,
        user_role: UserRole,
    ) -> list[SelectedDocument]:
        filtered: list[SelectedDocument] = []
        seen: set[str] = set()
        for document in documents:
            file_id = document.file_id.strip()
            if not file_id or file_id in seen:
                continue
            if not self._can_use_file(file_id, user_role=user_role):
                continue
            seen.add(file_id)
            filtered.append(
                SelectedDocument(
                    file_id=file_id,
                    version_id=document.version_id or file_id,
                    reason=document.reason,
                    confidence=document.confidence,
                )
            )
        return filtered

    def _resolve_scope_pdf_file_ids(
        self,
        *,
        file_ids: list[str] | None,
        user_role: UserRole,
    ) -> list[str]:
        explicit_file_ids = _dedupe_file_ids(file_ids or [])
        if not explicit_file_ids:
            return []
        files = self._sessions.list_pdf_files()
        files_by_id = {file.file_id: file for file in files}
        selected: list[PdfFile] = []
        for file_id in explicit_file_ids:
            file = files_by_id.get(file_id)
            if file is None or not _is_visible_pdf_scope(file, user_role):
                raise AssetNotFoundError("PDF file was not found")
            if file.kind == PdfFileKind.FOLDER:
                selected.extend(_descendant_ready_pdf_files(file.file_id, files_by_id, user_role))
                continue
            if _is_visible_ready_pdf(file, user_role):
                selected.append(file)
        deduped: list[str] = []
        seen: set[str] = set()
        for file in selected:
            if file.file_id in seen:
                continue
            seen.add(file.file_id)
            deduped.append(file.file_id)
        return deduped

    def _filter_attached_documents_by_scope(
        self,
        documents: list[PdfAttachedDocument],
        *,
        scope_file_ids: list[str],
        has_explicit_scope: bool,
    ) -> list[PdfAttachedDocument]:
        if not has_explicit_scope:
            return documents
        allowed_file_ids = set(scope_file_ids)
        return [document for document in documents if document.file_id in allowed_file_ids]

    def _attach_new_documents(
        self,
        *,
        session_id: str,
        selected_documents: list[SelectedDocument],
        attached_documents: list[PdfAttachedDocument],
        user_role: UserRole,
    ) -> list[SelectedDocument]:
        attached_file_ids = {document.file_id for document in attached_documents}
        newly_attached: list[SelectedDocument] = []
        for document in selected_documents:
            if document.file_id in attached_file_ids:
                continue
            chunks = self._sessions.list_pdf_document_chunks(document.file_id)
            attached = PdfAttachedDocument(
                session_id=session_id,
                file_id=document.file_id,
                attached_at=utc_now_iso(),
                chunk_count=len(chunks),
                context_hash=_document_context_hash(document.file_id, chunks),
            )
            if self._can_use_file(document.file_id, user_role=user_role) and (
                self._sessions.attach_pdf_document(attached)
            ):
                newly_attached.append(document)
        return newly_attached

    def _resolve_documents_for_answer(
        self,
        *,
        attached_documents: list[PdfAttachedDocument],
        route_result: PdfChatRouteResult | None,
        selected_file_ids: list[str] | None,
    ) -> list[SelectedDocument]:
        if route_result is not None:
            if route_result.selected_documents:
                return route_result.selected_documents
            return [_attached_pdf_to_selected_document(document) for document in attached_documents]
        if selected_file_ids:
            selected_file_id_set = set(_dedupe_file_ids(selected_file_ids))
            return [
                _attached_pdf_to_selected_document(document)
                for document in attached_documents
                if document.file_id in selected_file_id_set
            ]
        return [_attached_pdf_to_selected_document(document) for document in attached_documents]

    def _matches_for_documents(
        self,
        documents: list[SelectedDocument],
        *,
        user_role: UserRole,
    ) -> list[PdfChunkSearchMatch]:
        matches: list[PdfChunkSearchMatch] = []
        for document in documents:
            file = self._sessions.get_pdf_file(document.file_id)
            if file is None or not _is_visible_ready_pdf(file, user_role):
                continue
            for chunk in self._sessions.list_pdf_document_chunks(file.file_id):
                matches.append(
                    PdfChunkSearchMatch(
                        file=file,
                        chunk=chunk,
                        score=1.0,
                        excerpt=_chunk_excerpt(chunk.text),
                        matched_terms=[],
                    )
                )
        return matches

    def _can_use_file(self, file_id: str, *, user_role: UserRole) -> bool:
        file = self._sessions.get_pdf_file(file_id)
        return file is not None and _is_visible_ready_pdf(file, user_role)

    @contextmanager
    def _session_operation_lock(self, session_id: str) -> Iterator[None]:
        with self._session_locks_guard:
            entry = self._session_locks.setdefault(session_id, _SessionOperationLock())
            entry.users += 1
        try:
            with entry.lock:
                yield
        finally:
            with self._session_locks_guard:
                entry.users -= 1
                if entry.users == 0 and entry.discard_when_idle:
                    self._session_locks.pop(session_id, None)

    def _discard_session_operation_lock(self, session_id: str) -> None:
        with self._session_locks_guard:
            entry = self._session_locks.get(session_id)
            if entry is None:
                return
            if entry.users == 0:
                self._session_locks.pop(session_id, None)
            else:
                entry.discard_when_idle = True

    def _normalize_session_title(self, title: str) -> str:
        normalized = " ".join(title.split())
        return normalized[:120] if normalized else "New chat"


def _build_pdf_answer(
    *,
    session_id: str | None,
    question: str,
    draft_answer: DraftChatAnswer,
    matches: list[PdfChunkSearchMatch],
    selected_documents: list[SelectedDocument],
    newly_attached_documents: list[SelectedDocument],
    attached_documents: list[PdfAttachedDocument],
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
        session_id=session_id,
        question=question,
        answer_blocks=answer_blocks,
        citations=citations,
        retrieval_matches=matches,
        selected_documents=selected_documents,
        newly_attached_documents=newly_attached_documents,
        attached_documents=attached_documents,
        insufficient_evidence=draft_answer.insufficient_evidence or not citations,
        follow_up_suggestions=draft_answer.follow_up_suggestions,
        warnings=[],
        created_at=utc_now_iso(),
    )


def _insufficient_evidence_answer(
    *,
    session_id: str,
    question: str,
    selected_documents: list[SelectedDocument],
    newly_attached_documents: list[SelectedDocument],
    attached_documents: list[PdfAttachedDocument],
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
        retrieval_matches=[],
        selected_documents=selected_documents,
        newly_attached_documents=newly_attached_documents,
        attached_documents=attached_documents,
        insufficient_evidence=True,
        follow_up_suggestions=[],
        warnings=[],
        created_at=utc_now_iso(),
    )


def _chat_turn_from_pdf_answer(answer: PdfChatAnswer) -> ChatTurn:
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
            _attached_pdf_to_excel_document(document)
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


def _normalize_question(question: str) -> str:
    normalized = " ".join(question.split())
    if not normalized:
        raise UploadValidationError("PDF chat question is required")
    return normalized


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


def _dedupe_file_ids(file_ids: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for file_id in file_ids:
        normalized = file_id.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _is_visible_ready_pdf(file: PdfFile, user_role: UserRole) -> bool:
    return (
        file.kind == PdfFileKind.PDF
        and file.processing_status == PdfProcessingStatus.READY
        and (
            user_role == UserRole.ADMIN
            or file.visibility == PdfFileVisibility.VISIBLE
        )
    )


def _is_visible_pdf_scope(file: PdfFile, user_role: UserRole) -> bool:
    return user_role == UserRole.ADMIN or file.visibility == PdfFileVisibility.VISIBLE


def _descendant_ready_pdf_files(
    parent_id: str,
    files_by_id: dict[str, PdfFile],
    user_role: UserRole,
) -> list[PdfFile]:
    children_by_parent: dict[str | None, list[PdfFile]] = {}
    for file in files_by_id.values():
        children_by_parent.setdefault(file.parent_id, []).append(file)
    descendants: list[PdfFile] = []
    stack = list(children_by_parent.get(parent_id, []))
    while stack:
        file = stack.pop(0)
        if file.kind == PdfFileKind.PDF:
            if _is_visible_ready_pdf(file, user_role):
                descendants.append(file)
            continue
        if file.kind == PdfFileKind.FOLDER and _is_visible_pdf_scope(file, user_role):
            stack.extend(children_by_parent.get(file.file_id, []))
    return descendants


def _pdf_summary_to_document_summary(
    *,
    summary,
    file: PdfFile,
) -> DocumentSummary:
    title = summary.document_title.strip() or file.display_name
    key_topics = summary.key_topics or [file.display_name]
    positive_terms = summary.positive_routing_terms or key_topics
    return DocumentSummary(
        summary_id=f"pdf-summary::{summary.file_id}",
        file_id=summary.file_id,
        version_id=summary.file_id,
        document_title=title,
        document_type=summary.document_type or "pdf_document",
        summary_text=summary.content,
        business_domain=summary.business_domain or "pdf knowledge",
        coverage_scope={"business_processes": ["pdf knowledge chat"]},
        key_topics=key_topics,
        positive_routing_terms=positive_terms,
        negative_routing_terms=summary.negative_routing_terms,
        exact_identifiers=summary.exact_identifiers or [file.display_name],
        suitable_questions=summary.suitable_questions,
        unsuitable_questions=summary.unsuitable_questions,
        sheet_summaries=[
            SheetSummary(
                sheet_id=summary.file_id,
                sheet_name=file.display_name,
                summary=summary.content,
                important_columns=[],
                likely_question_types=summary.suitable_questions,
                header_terms=positive_terms,
                sampled_identifiers=summary.exact_identifiers,
            )
        ],
        routing_notes=summary.routing_notes,
        created_at=summary.updated_at or file.updated_at,
    )


def _attached_pdf_to_selected_document(
    document: PdfAttachedDocument,
) -> SelectedDocument:
    return SelectedDocument(
        file_id=document.file_id,
        version_id=document.file_id,
        reason="already attached to PDF chat session",
        confidence=1.0,
    )


def _attached_pdf_to_excel_document(document: PdfAttachedDocument) -> AttachedDocument:
    return AttachedDocument(
        session_id=document.session_id,
        file_id=document.file_id,
        version_id=document.file_id,
        attached_at=document.attached_at,
        row_count=document.chunk_count,
        context_hash=document.context_hash,
        status=document.status,
    )


def _document_context_hash(file_id: str, chunks: list[PdfDocumentChunk]) -> str:
    import hashlib

    digest = hashlib.sha256()
    digest.update(file_id.encode("utf-8"))
    for chunk in chunks:
        digest.update(chunk.chunk_id.encode("utf-8"))
        digest.update(chunk.content_hash.encode("utf-8"))
    return digest.hexdigest()


def _chunk_excerpt(text: str, radius: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= radius:
        return normalized
    return f"{normalized[:radius].strip()}..."
