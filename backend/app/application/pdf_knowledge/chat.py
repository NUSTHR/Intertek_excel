import hashlib
import json
import logging
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock, RLock

from app.application.chat.cancellation import ChatCancellationToken
from app.application.pdf_knowledge.chat_answer import (
    attached_pdf_to_routing_document,
    build_pdf_answer,
    chat_turn_from_pdf_answer,
    chunk_payload,
    insufficient_evidence_answer,
    pdf_answer_from_chat_turn,
)
from app.application.pdf_knowledge.chat_context import (
    PdfContextAllocation,
    PdfContextAssembler,
)
from app.application.pdf_knowledge.chat_policy import (
    DEFAULT_PDF_CHAT_POLICY,
    PdfChatPolicy,
)
from app.application.pdf_knowledge.chat_routing import PdfRoutingCatalogBuilder
from app.application.pdf_knowledge.chat_scope import (
    PdfChatScopeResolver,
    is_visible_ready_pdf,
)
from app.application.pdf_knowledge.document_ranking import PdfDocumentRankingService
from app.application.pdf_knowledge.model_settings import (
    PdfModelSelection,
    pdf_model_selection,
)
from app.application.pdf_knowledge.models import (
    PdfChatAnswer,
)
from app.core.errors import (
    AssetNotFoundError,
    ChatSessionRevisionConflict,
    PdfRankingIncomplete,
    UploadValidationError,
)
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    ChatSession,
    ChatTurn,
    ChatWorkspace,
    DraftChatAnswer,
    PdfAttachedDocument,
    PdfChatRouteResult,
    PdfDocumentChunk,
    SelectedDocument,
    UserRole,
)
from app.ports.llm_client import PdfChatLlmClient
from app.ports.repository import PdfChatRepository

PDF_CHAT_WORKSPACE = ChatWorkspace.PDF.value
logger = logging.getLogger(__name__)


@dataclass
class _SessionOperationLock:
    lock: RLock = field(default_factory=RLock)
    users: int = 0
    discard_when_idle: bool = False


class PdfChatService:
    def __init__(
        self,
        *,
        llm_client: PdfChatLlmClient,
        sessions: PdfChatRepository,
        policy: PdfChatPolicy = DEFAULT_PDF_CHAT_POLICY,
        document_ranking: PdfDocumentRankingService | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._sessions = sessions
        self._policy = policy
        self._document_ranking = document_ranking
        self._scope_resolver = PdfChatScopeResolver(sessions)
        self._routing_catalog = PdfRoutingCatalogBuilder(
            repository=sessions,
            policy=policy,
        )
        self._context_assembler = PdfContextAssembler(
            repository=sessions,
            policy=policy,
        )
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
        expected_revision: int | None = None,
    ) -> ChatSession | None:
        with self._session_operation_lock(session_id):
            if self.get_session(session_id, user_id=user_id) is None:
                return None
            return self._sessions.rename_session(
                session_id=session_id,
                title=self._normalize_session_title(title),
                updated_at=utc_now_iso(),
                workspace=PDF_CHAT_WORKSPACE,
                expected_revision=expected_revision,
            )

    def set_session_pinned(
        self,
        session_id: str,
        pinned: bool,
        user_id: str | None = None,
        expected_revision: int | None = None,
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
                expected_revision=expected_revision,
            )

    def delete_session(
        self,
        session_id: str,
        user_id: str | None = None,
        expected_revision: int | None = None,
    ) -> bool:
        with self._session_operation_lock(session_id):
            if self.get_session(session_id, user_id=user_id) is None:
                return False
            deleted = self._sessions.delete_session(
                session_id,
                workspace=PDF_CHAT_WORKSPACE,
                expected_revision=expected_revision,
            )
        if deleted:
            self._discard_session_operation_lock(session_id)
        return deleted

    def batch_mutate_sessions(
        self,
        *,
        action: str,
        session_items: list[tuple[str, int]],
        user_id: str,
    ) -> tuple[list[ChatSession], list[str]]:
        session_revisions: dict[str, int] = {}
        for session_id, expected_revision in session_items:
            existing_revision = session_revisions.get(session_id)
            if (
                existing_revision is not None
                and existing_revision != expected_revision
            ):
                raise ChatSessionRevisionConflict(session_id)
            session_revisions[session_id] = expected_revision
        session_ids = sorted(session_revisions)
        with self._session_operation_locks(session_ids):
            for session_id in session_ids:
                session = self.get_session(session_id, user_id=user_id)
                if session is None:
                    raise AssetNotFoundError("PDF chat session was not found")
                if session.revision != session_revisions[session_id]:
                    raise ChatSessionRevisionConflict(session_id)
            if action in {"pin", "unpin"}:
                now = utc_now_iso()
                updated_sessions = self._sessions.batch_set_sessions_pinned(
                    session_revisions,
                    pinned_at=now if action == "pin" else None,
                    updated_at=now,
                    workspace=PDF_CHAT_WORKSPACE,
                )
                return updated_sessions, []
            if action != "delete":
                raise UploadValidationError("unsupported PDF chat session batch action")
            deleted_session_ids = self._sessions.batch_delete_sessions(
                session_revisions,
                workspace=PDF_CHAT_WORKSPACE,
            )
        for session_id in deleted_session_ids:
            self._discard_session_operation_lock(session_id)
        return [], deleted_session_ids

    def list_turns(
        self,
        session_id: str,
        user_id: str | None = None,
    ) -> list[ChatTurn] | None:
        if self.get_session(session_id, user_id=user_id) is None:
            return None
        return self._sessions.list_turns(session_id, workspace=PDF_CHAT_WORKSPACE)

    def get_session_snapshot(
        self,
        session_id: str,
        user_id: str | None = None,
    ) -> tuple[ChatSession, list[ChatTurn]] | None:
        return self._sessions.get_session_with_turns(
            session_id,
            workspace=PDF_CHAT_WORKSPACE,
            user_id=user_id,
        )

    def answer_question(
        self,
        *,
        question: str,
        file_ids: list[str] | None,
        enable_deep_thinking: bool = False,
        user_role: UserRole,
        request_id: str | None = None,
        cancellation_token: ChatCancellationToken | None = None,
    ) -> PdfChatAnswer:
        self._raise_if_cancelled(cancellation_token)
        normalized_question = _normalize_question(question)
        route_result = self.route_question(
            question=normalized_question,
            session_id=None,
            user_id="legacy",
            file_ids=file_ids,
            user_role=user_role,
            request_id=request_id,
            cancellation_token=cancellation_token,
        )
        return self.answer_routed_question(
            session_id=route_result.session_id,
            user_id="legacy",
            question=normalized_question,
            route_result=route_result,
            enable_deep_thinking=enable_deep_thinking,
            user_role=user_role,
            persist_turn=True,
            request_id=request_id,
            cancellation_token=cancellation_token,
        )

    def answer_session_question(
        self,
        *,
        session_id: str,
        user_id: str,
        question: str,
        file_ids: list[str] | None,
        enable_deep_thinking: bool = False,
        user_role: UserRole,
        request_id: str | None = None,
        cancellation_token: ChatCancellationToken | None = None,
    ) -> PdfChatAnswer:
        with self._session_operation_lock(session_id):
            self._raise_if_cancelled(cancellation_token)
            session = self.get_session(session_id, user_id=user_id)
            if session is None:
                raise AssetNotFoundError("PDF chat session was not found")
            normalized_question = _normalize_question(question)
            request_fingerprint = self._request_fingerprint(
                session_id=session.session_id,
                user_id=user_id,
                question=normalized_question,
                file_ids=file_ids,
                enable_deep_thinking=enable_deep_thinking,
            )
            existing_answer = self._claim_request(
                session=session,
                request_id=request_id,
                request_fingerprint=request_fingerprint,
            )
            if existing_answer is not None:
                return existing_answer
            try:
                route_result = self._route_question_locked(
                    question=normalized_question,
                    session=session,
                    file_ids=file_ids,
                    user_role=user_role,
                    request_id=request_id,
                    cancellation_token=cancellation_token,
                )
                return self._answer_routed_question_locked(
                    question=normalized_question,
                    session=session,
                    route_result=route_result,
                    enable_deep_thinking=enable_deep_thinking,
                    user_role=user_role,
                    persist_turn=True,
                    request_id=request_id,
                    request_fingerprint=request_fingerprint,
                    cancellation_token=cancellation_token,
                )
            except Exception:
                self._release_request(
                    session_id=session.session_id,
                    request_id=request_id,
                    request_fingerprint=request_fingerprint,
                )
                raise

    def route_question(
        self,
        *,
        question: str,
        session_id: str | None,
        user_id: str,
        file_ids: list[str] | None,
        user_role: UserRole,
        request_id: str | None = None,
        cancellation_token: ChatCancellationToken | None = None,
    ) -> PdfChatRouteResult:
        self._raise_if_cancelled(cancellation_token)
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
                    request_id=request_id,
                    cancellation_token=cancellation_token,
                )
        session = self.create_session_for_user(user_id)
        return self._route_question_locked(
            question=normalized_question,
            session=session,
            file_ids=file_ids,
            user_role=user_role,
            request_id=request_id,
            cancellation_token=cancellation_token,
        )

    def answer_routed_question(
        self,
        *,
        session_id: str,
        user_id: str,
        question: str,
        route_result: PdfChatRouteResult,
        enable_deep_thinking: bool = False,
        user_role: UserRole,
        persist_turn: bool = True,
        request_id: str | None = None,
        cancellation_token: ChatCancellationToken | None = None,
    ) -> PdfChatAnswer:
        with self._session_operation_lock(session_id):
            self._raise_if_cancelled(cancellation_token)
            session = self.get_session(session_id, user_id=user_id)
            if session is None:
                raise AssetNotFoundError("PDF chat session was not found")
            normalized_question = _normalize_question(question)
            request_fingerprint = self._request_fingerprint(
                session_id=session.session_id,
                user_id=user_id,
                question=normalized_question,
                file_ids=route_result.context_file_ids,
                selected_file_ids=[
                    document.file_id
                    for document in route_result.selected_documents
                ],
                enable_deep_thinking=enable_deep_thinking,
            )
            existing_answer = (
                self._claim_request(
                    session=session,
                    request_id=request_id,
                    request_fingerprint=request_fingerprint,
                )
                if persist_turn
                else None
            )
            if existing_answer is not None:
                return existing_answer
            try:
                if route_result.session_revision != session.conversation_revision:
                    raise ChatSessionRevisionConflict(session.session_id)
                return self._answer_routed_question_locked(
                    question=normalized_question,
                    session=session,
                    route_result=route_result,
                    enable_deep_thinking=enable_deep_thinking,
                    user_role=user_role,
                    persist_turn=persist_turn,
                    request_id=request_id,
                    request_fingerprint=(
                        request_fingerprint if persist_turn else None
                    ),
                    cancellation_token=cancellation_token,
                )
            except Exception:
                if persist_turn:
                    self._release_request(
                        session_id=session.session_id,
                        request_id=request_id,
                        request_fingerprint=request_fingerprint,
                    )
                raise

    def answer_selected_question(
        self,
        *,
        session_id: str,
        user_id: str,
        question: str,
        selected_file_ids: list[str],
        file_ids: list[str] | None,
        expected_session_revision: int,
        enable_deep_thinking: bool = False,
        user_role: UserRole,
        request_id: str | None = None,
        cancellation_token: ChatCancellationToken | None = None,
    ) -> PdfChatAnswer:
        with self._session_operation_lock(session_id):
            self._raise_if_cancelled(cancellation_token)
            session = self.get_session(session_id, user_id=user_id)
            if session is None:
                raise AssetNotFoundError("PDF chat session was not found")
            normalized_question = _normalize_question(question)
            request_fingerprint = self._request_fingerprint(
                session_id=session.session_id,
                user_id=user_id,
                question=normalized_question,
                file_ids=file_ids,
                selected_file_ids=selected_file_ids,
                enable_deep_thinking=enable_deep_thinking,
            )
            existing_answer = self._claim_request(
                session=session,
                request_id=request_id,
                request_fingerprint=request_fingerprint,
            )
            if existing_answer is not None:
                return existing_answer
            try:
                if expected_session_revision != session.conversation_revision:
                    raise ChatSessionRevisionConflict(session.session_id)
                route_result = self._plan_selected_file_route(
                    question=normalized_question,
                    session=session,
                    selected_file_ids=selected_file_ids,
                    file_ids=file_ids,
                    expected_session_revision=expected_session_revision,
                    user_role=user_role,
                    request_id=request_id,
                )
                return self._answer_routed_question_locked(
                    question=normalized_question,
                    session=session,
                    route_result=route_result,
                    enable_deep_thinking=enable_deep_thinking,
                    user_role=user_role,
                    persist_turn=True,
                    request_id=request_id,
                    request_fingerprint=request_fingerprint,
                    cancellation_token=cancellation_token,
                )
            except Exception:
                self._release_request(
                    session_id=session.session_id,
                    request_id=request_id,
                    request_fingerprint=request_fingerprint,
                )
                raise

    def _route_question_locked(
        self,
        *,
        question: str,
        session: ChatSession,
        file_ids: list[str] | None,
        user_role: UserRole,
        request_id: str | None,
        cancellation_token: ChatCancellationToken | None,
    ) -> PdfChatRouteResult:
        self._raise_if_cancelled(cancellation_token)
        resolved_scope = self._scope_resolver.resolve(
            selected_node_ids=file_ids,
            user_role=user_role,
        )
        candidate_file_ids = resolved_scope.candidate_file_ids
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
            scope_file_ids=candidate_file_ids,
            has_explicit_scope=resolved_scope.has_explicit_scope,
        )
        if not candidate_file_ids:
            selected_documents = []
        elif len(candidate_file_ids) == 1:
            file_id = candidate_file_ids[0]
            selected_documents = [
                SelectedDocument(
                    file_id=file_id,
                    version_id=file_id,
                    reason="only PDF candidate in the current scope",
                    confidence=1.0,
                )
            ]
        else:
            model_selection = pdf_model_selection(
                self._sessions.list_pdf_model_settings(),
                "router",
            )
            summaries = self._routing_catalog.build(
                candidate_file_ids=candidate_file_ids,
                user_role=user_role,
            )
            selected_documents = self._llm_client.route_pdf_documents(
                question=question,
                summaries=summaries,
                max_documents=len(summaries),
                user_questions=[turn.question for turn in existing_turns] + [question],
                attached_documents=[
                    attached_pdf_to_routing_document(document)
                    for document in attached_before
                ],
                previous_turns=existing_turns,
                model=model_selection.model,
                provider=model_selection.provider,
                cancellation_checker=self._cancellation_checker(cancellation_token),
            )
            self._raise_if_cancelled(cancellation_token)
        selected_documents = self._filter_accessible_selected_documents(
            selected_documents,
            user_role=user_role,
            allowed_file_ids=candidate_file_ids,
            enforce_final_limit=False,
        )
        if len(selected_documents) > self._policy.max_routed_documents:
            if self._document_ranking is None:
                raise PdfRankingIncomplete(
                    "more than four routed PDFs require vector ranking, but it is unavailable"
                )
            selected_documents = list(
                self._document_ranking.select(
                    question=question,
                    router_documents=selected_documents,
                    cancellation_checker=self._cancellation_checker(cancellation_token),
                ).documents
            )
        self._raise_if_cancelled(cancellation_token)
        newly_attached, planned_attachments = self._plan_new_documents(
            session_id=session.session_id,
            selected_documents=selected_documents,
            attached_documents=attached_before,
            user_role=user_role,
        )
        attached_after = [*attached_before, *planned_attachments]
        created_at = utc_now_iso()
        self._raise_if_cancelled(cancellation_token)
        logger.info(
            "pdf chat route planned session_id=%s request_id=%s "
            "scope_mode=%s candidate_count=%s selected_count=%s revision=%s",
            session.session_id,
            request_id,
            resolved_scope.scope.mode.value,
            len(candidate_file_ids),
            len(selected_documents),
            session.conversation_revision,
        )
        return PdfChatRouteResult(
            session_id=session.session_id,
            question=question,
            selected_documents=selected_documents,
            newly_attached_documents=newly_attached,
            attached_documents=attached_after,
            created_at=created_at,
            request_id=request_id,
            context_file_ids=resolved_scope.scope.selected_node_ids,
            session_revision=session.conversation_revision,
        )

    def _answer_routed_question_locked(
        self,
        *,
        question: str,
        session: ChatSession,
        route_result: PdfChatRouteResult,
        enable_deep_thinking: bool,
        user_role: UserRole,
        persist_turn: bool,
        request_id: str | None,
        request_fingerprint: str | None,
        cancellation_token: ChatCancellationToken | None,
    ) -> PdfChatAnswer:
        self._raise_if_cancelled(cancellation_token)
        existing_turns = self._filter_accessible_turns(
            self._sessions.list_turns(
                session.session_id,
                workspace=PDF_CHAT_WORKSPACE,
            ),
            user_role=user_role,
        )
        attached_documents = self._filter_accessible_attached_documents(
            route_result.attached_documents,
            user_role=user_role,
        )
        documents = route_result.selected_documents
        documents = self._filter_accessible_selected_documents(
            documents,
            user_role=user_role,
        )
        model_selection = pdf_model_selection(
            self._sessions.list_pdf_model_settings(),
            "chat",
        )
        (
            draft_answer,
            documents,
            context_allocation,
            visibility_changed,
        ) = self._answer_with_current_access(
            question=question,
            documents=documents,
            previous_turns=existing_turns,
            user_role=user_role,
            model_selection=model_selection,
            enable_deep_thinking=enable_deep_thinking,
            cancellation_token=cancellation_token,
        )
        self._raise_if_cancelled(cancellation_token)
        grounding_chunks = context_allocation.chunks
        attached_documents = self._filter_accessible_attached_documents(
            attached_documents,
            user_role=user_role,
        )
        selected_file_ids = {document.file_id for document in documents}
        newly_attached_documents = [
            document
            for document in route_result.newly_attached_documents
            if document.file_id in selected_file_ids
        ]
        logger.info(
            "pdf chat context allocated session_id=%s request_id=%s "
            "document_count=%s chunk_count=%s token_count=%s "
            "character_count=%s truncated=%s",
            session.session_id,
            request_id,
            len(context_allocation.document_chunk_counts),
            len(grounding_chunks),
            context_allocation.used_tokens,
            context_allocation.used_characters,
            context_allocation.truncated,
        )
        context_warnings = (
            [
                "The selected PDF context exceeded the answer budget and was "
                "deterministically truncated across documents."
            ]
            if context_allocation.truncated
            else []
        )
        if visibility_changed:
            context_warnings.append(
                "The available PDF evidence changed while this answer was being "
                "prepared. Send the question again to use the current file visibility."
            )
        if draft_answer is None or not grounding_chunks:
            answer = insufficient_evidence_answer(
                session_id=session.session_id,
                question=question,
                selected_documents=documents,
                newly_attached_documents=newly_attached_documents,
                attached_documents=attached_documents,
                warnings=context_warnings,
                request_id=request_id,
            )
        else:
            answer = build_pdf_answer(
                session_id=session.session_id,
                question=question,
                draft_answer=draft_answer,
                grounding_chunks=grounding_chunks,
                selected_documents=documents,
                newly_attached_documents=newly_attached_documents,
                attached_documents=attached_documents,
                warnings=context_warnings,
                request_id=request_id,
            )
        if persist_turn:
            self._raise_if_cancelled(cancellation_token)
            turn = chat_turn_from_pdf_answer(answer)
            newly_attached_file_ids = {
                document.file_id
                for document in answer.newly_attached_documents
            }
            committed_turn = self._sessions.commit_pdf_chat_turn(
                session_id=session.session_id,
                user_id=session.user_id,
                expected_conversation_revision=route_result.session_revision,
                context_file_ids=route_result.context_file_ids,
                attached_documents=[
                    document
                    for document in answer.attached_documents
                    if document.file_id in newly_attached_file_ids
                ],
                turn=turn,
                title_if_new=self._normalize_session_title(question),
                request_fingerprint=request_fingerprint,
            )
            logger.info(
                "pdf chat turn committed session_id=%s request_id=%s "
                "turn_id=%s expected_revision=%s",
                session.session_id,
                request_id,
                committed_turn.turn_id,
                route_result.session_revision,
            )
            return pdf_answer_from_chat_turn(committed_turn)
        return answer

    def _request_fingerprint(
        self,
        *,
        session_id: str,
        user_id: str,
        question: str,
        file_ids: list[str] | None,
        selected_file_ids: list[str] | None = None,
        enable_deep_thinking: bool,
    ) -> str:
        payload = {
            "workspace": PDF_CHAT_WORKSPACE,
            "session_id": session_id,
            "user_id": user_id,
            "question": question,
            "file_ids": sorted(
                {
                    file_id.strip()
                    for file_id in file_ids or []
                    if file_id.strip()
                }
            ),
            "selected_file_ids": sorted(
                {
                    file_id.strip()
                    for file_id in selected_file_ids or []
                    if file_id.strip()
                }
            ),
            "enable_deep_thinking": enable_deep_thinking,
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

    def _claim_request(
        self,
        *,
        session: ChatSession,
        request_id: str | None,
        request_fingerprint: str,
    ) -> PdfChatAnswer | None:
        if request_id is None:
            return None
        claimed_at = datetime.now(UTC)
        existing_turn = self._sessions.claim_pdf_chat_request(
            session_id=session.session_id,
            user_id=session.user_id,
            request_id=request_id,
            request_fingerprint=request_fingerprint,
            claimed_at=claimed_at.isoformat(),
            lease_expires_at=(claimed_at + timedelta(minutes=10)).isoformat(),
        )
        if existing_turn is None:
            return None
        return pdf_answer_from_chat_turn(existing_turn)

    def _plan_selected_file_route(
        self,
        *,
        question: str,
        session: ChatSession,
        selected_file_ids: list[str],
        file_ids: list[str] | None,
        expected_session_revision: int,
        user_role: UserRole,
        request_id: str | None,
    ) -> PdfChatRouteResult:
        resolved_scope = self._scope_resolver.resolve(
            selected_node_ids=file_ids,
            user_role=user_role,
        )
        selected_documents = self._filter_accessible_selected_documents(
            [
                SelectedDocument(
                    file_id=file_id,
                    version_id=file_id,
                    reason="selected by the route plan",
                )
                for file_id in selected_file_ids
            ],
            user_role=user_role,
            allowed_file_ids=resolved_scope.candidate_file_ids,
        )
        attached_before = self._filter_accessible_attached_documents(
            self._sessions.list_pdf_attached_documents(session.session_id),
            user_role=user_role,
        )
        attached_before = self._filter_attached_documents_by_scope(
            attached_before,
            scope_file_ids=resolved_scope.candidate_file_ids,
            has_explicit_scope=resolved_scope.has_explicit_scope,
        )
        newly_attached, planned_attachments = self._plan_new_documents(
            session_id=session.session_id,
            selected_documents=selected_documents,
            attached_documents=attached_before,
            user_role=user_role,
        )
        return PdfChatRouteResult(
            session_id=session.session_id,
            question=question,
            selected_documents=selected_documents,
            newly_attached_documents=newly_attached,
            attached_documents=[*attached_before, *planned_attachments],
            created_at=utc_now_iso(),
            request_id=request_id,
            context_file_ids=resolved_scope.scope.selected_node_ids,
            session_revision=expected_session_revision,
        )

    def _release_request(
        self,
        *,
        session_id: str,
        request_id: str | None,
        request_fingerprint: str,
    ) -> None:
        if request_id is None:
            return
        self._sessions.release_pdf_chat_request(
            session_id=session_id,
            request_id=request_id,
            request_fingerprint=request_fingerprint,
        )

    def _answer_with_current_access(
        self,
        *,
        question: str,
        documents: list[SelectedDocument],
        previous_turns: list[ChatTurn],
        user_role: UserRole,
        model_selection: PdfModelSelection,
        enable_deep_thinking: bool,
        cancellation_token: ChatCancellationToken | None,
    ) -> tuple[
        DraftChatAnswer | None,
        list[SelectedDocument],
        PdfContextAllocation,
        bool,
    ]:
        current_documents = self._filter_accessible_selected_documents(
            documents,
            user_role=user_role,
        )
        allocation = self._context_assembler.assemble(
            documents=current_documents,
            user_role=user_role,
        )
        if not allocation.chunks:
            return None, current_documents, allocation, False

        draft_answer = self._generate_pdf_draft_answer(
            question=question,
            allocation=allocation,
            previous_turns=previous_turns,
            model_selection=model_selection,
            enable_deep_thinking=enable_deep_thinking,
            cancellation_token=cancellation_token,
        )
        refreshed_documents = self._filter_accessible_selected_documents(
            current_documents,
            user_role=user_role,
        )
        if self._document_keys(refreshed_documents) == self._document_keys(
            current_documents
        ):
            return draft_answer, current_documents, allocation, False

        refreshed_allocation = self._context_assembler.assemble(
            documents=refreshed_documents,
            user_role=user_role,
        )
        if not refreshed_allocation.chunks:
            return None, refreshed_documents, refreshed_allocation, True

        refreshed_answer = self._generate_pdf_draft_answer(
            question=question,
            allocation=refreshed_allocation,
            previous_turns=previous_turns,
            model_selection=model_selection,
            enable_deep_thinking=enable_deep_thinking,
            cancellation_token=cancellation_token,
        )
        final_documents = self._filter_accessible_selected_documents(
            refreshed_documents,
            user_role=user_role,
        )
        if self._document_keys(final_documents) != self._document_keys(
            refreshed_documents
        ):
            return None, [], refreshed_allocation, True
        return refreshed_answer, refreshed_documents, refreshed_allocation, False

    def _generate_pdf_draft_answer(
        self,
        *,
        question: str,
        allocation: PdfContextAllocation,
        previous_turns: list[ChatTurn],
        model_selection: PdfModelSelection,
        enable_deep_thinking: bool,
        cancellation_token: ChatCancellationToken | None,
    ) -> DraftChatAnswer:
        self._raise_if_cancelled(cancellation_token)
        draft_answer = self._llm_client.answer_with_pdf_chunks(
            question,
            [
                chunk_payload(
                    item,
                    max_characters=(
                        None
                        if self._policy.full_document_context
                        else self._policy.max_single_chunk_characters
                    ),
                )
                for item in allocation.chunks
            ],
            previous_turns=previous_turns,
            model=model_selection.model,
            provider=model_selection.provider,
            enable_deep_thinking=enable_deep_thinking,
            cancellation_checker=self._cancellation_checker(cancellation_token),
        )
        self._raise_if_cancelled(cancellation_token)
        return draft_answer

    @staticmethod
    def _document_keys(
        documents: list[SelectedDocument],
    ) -> set[tuple[str, str]]:
        return {(document.file_id, document.version_id) for document in documents}

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
                    *turn.attached_documents,
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
        allowed_file_ids: list[str] | None = None,
        enforce_final_limit: bool = True,
    ) -> list[SelectedDocument]:
        filtered: list[SelectedDocument] = []
        seen: set[str] = set()
        allowed = set(allowed_file_ids) if allowed_file_ids is not None else None
        requested_file_ids = [
            document.file_id.strip()
            for document in documents
            if document.file_id.strip()
        ]
        accessible_file_ids = {
            file.file_id
            for file in self._sessions.list_pdf_files_by_ids(requested_file_ids)
            if is_visible_ready_pdf(file, user_role)
        }
        for document in documents:
            file_id = document.file_id.strip()
            if not file_id or file_id in seen:
                continue
            if allowed is not None and file_id not in allowed:
                continue
            if file_id not in accessible_file_ids:
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
        if not enforce_final_limit:
            return filtered
        return filtered[: self._policy.max_routed_documents]

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

    def _plan_new_documents(
        self,
        *,
        session_id: str,
        selected_documents: list[SelectedDocument],
        attached_documents: list[PdfAttachedDocument],
        user_role: UserRole,
    ) -> tuple[list[SelectedDocument], list[PdfAttachedDocument]]:
        attached_file_ids = {document.file_id for document in attached_documents}
        selected_file_ids = [
            document.file_id
            for document in selected_documents
            if document.file_id not in attached_file_ids
        ]
        accessible_file_ids = {
            file.file_id
            for file in self._sessions.list_pdf_files_by_ids(selected_file_ids)
            if is_visible_ready_pdf(file, user_role)
        }
        chunks_by_file_id = self._sessions.list_pdf_document_chunks_by_file_ids(
            list(accessible_file_ids)
        )
        newly_attached: list[SelectedDocument] = []
        planned_attachments: list[PdfAttachedDocument] = []
        for document in selected_documents:
            if document.file_id in attached_file_ids:
                continue
            chunks = chunks_by_file_id.get(document.file_id, [])
            planned_attachment = PdfAttachedDocument(
                session_id=session_id,
                file_id=document.file_id,
                attached_at=utc_now_iso(),
                chunk_count=len(chunks),
                context_hash=_document_context_hash(document.file_id, chunks),
            )
            if document.file_id in accessible_file_ids:
                newly_attached.append(document)
                planned_attachments.append(planned_attachment)
        return newly_attached, planned_attachments

    def _can_use_file(self, file_id: str, *, user_role: UserRole) -> bool:
        file = self._sessions.get_pdf_file(file_id)
        return file is not None and is_visible_ready_pdf(file, user_role)

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

    @contextmanager
    def _session_operation_locks(
        self,
        session_ids: list[str],
    ) -> Iterator[None]:
        with ExitStack() as stack:
            for session_id in sorted(set(session_ids)):
                stack.enter_context(self._session_operation_lock(session_id))
            yield

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

    @staticmethod
    def _cancellation_checker(
        cancellation_token: ChatCancellationToken | None,
    ):
        if cancellation_token is None:
            return None
        return cancellation_token.raise_if_cancelled

    @staticmethod
    def _raise_if_cancelled(
        cancellation_token: ChatCancellationToken | None,
    ) -> None:
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()


def _normalize_question(question: str) -> str:
    normalized = " ".join(question.split())
    if not normalized:
        raise UploadValidationError("PDF chat question is required")
    return normalized


def _document_context_hash(file_id: str, chunks: list[PdfDocumentChunk]) -> str:
    import hashlib

    digest = hashlib.sha256()
    digest.update(file_id.encode("utf-8"))
    for chunk in chunks:
        digest.update(chunk.chunk_id.encode("utf-8"))
        digest.update(chunk.content_hash.encode("utf-8"))
    return digest.hexdigest()
