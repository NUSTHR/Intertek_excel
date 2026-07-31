import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock, RLock

from app.application.chat.access_control import ChatAccessController
from app.application.chat.cancellation import (
    ChatCancellationToken,
    ChatRequestCancelledError,
)
from app.application.chat.citations import CitationVerifier
from app.application.chat.policy import ChatServicePolicy
from app.application.document_summaries.service import DocumentSummaryService
from app.application.excel_assets.access import FileAccessContext
from app.application.excel_assets.service import ExcelAssetService
from app.application.llm_preferences.service import WorkspaceLlmPreferenceService
from app.core.errors import AssetNotFoundError, ChatSessionRevisionConflict
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    AttachedDocument,
    ChatAnswer,
    ChatAnswerBlock,
    ChatRouteResult,
    ChatSession,
    ChatTurn,
    ChatWorkspace,
    DraftAnswerBlock,
    DraftChatAnswer,
    ExcelCitation,
    ExcelSheet,
    LlmPreference,
    SelectedDocument,
    UserRole,
)
from app.ports.chat_workflow import ChatWorkflow, ChatWorkflowRequest
from app.ports.llm_client import LlmClient
from app.ports.repository import ChatSessionRepository


@dataclass
class _SessionOperationLock:
    lock: RLock = field(default_factory=RLock)
    users: int = 0
    discard_when_idle: bool = False


class ChatService:
    def __init__(
        self,
        excel_assets: ExcelAssetService,
        summaries: DocumentSummaryService,
        llm_client: LlmClient,
        sessions: ChatSessionRepository,
        llm_preferences: WorkspaceLlmPreferenceService,
        max_routed_documents: int = 3,
        row_page_size: int = 5000,
        max_answer_rows: int = 20_000,
        policy: ChatServicePolicy | None = None,
        workflow: ChatWorkflow | None = None,
    ) -> None:
        self._policy = policy or ChatServicePolicy(
            max_routed_documents=max_routed_documents,
            row_page_size=row_page_size,
            max_answer_rows=max_answer_rows,
        )
        self._excel_assets = excel_assets
        self._summaries = summaries
        self._llm_client = llm_client
        self._sessions = sessions
        self._llm_preferences = llm_preferences
        self._workflow = workflow
        self._workspace = ChatWorkspace.EXCEL.value
        self._citation_verifier = CitationVerifier()
        self._access_controller = ChatAccessController(excel_assets)
        self._session_locks: dict[str, _SessionOperationLock] = {}
        self._session_locks_guard = Lock()

    def create_session(self) -> ChatSession:
        return self.create_session_for_user("legacy")

    def create_session_for_user(self, user_id: str) -> ChatSession:
        now = utc_now_iso()
        session = ChatSession(
            session_id=new_id("session"),
            user_id=user_id,
            created_at=now,
            updated_at=now,
            workspace=ChatWorkspace.EXCEL,
        )
        self._sessions.create_session(session)
        return session

    def get_session(self, session_id: str, user_id: str | None = None) -> ChatSession | None:
        session = self._sessions.get_session(session_id, workspace=self._workspace)
        if user_id is not None and session is not None and session.user_id != user_id:
            return None
        return session

    def list_sessions(self, user_id: str | None = None) -> list[ChatSession]:
        sessions = self._sessions.list_sessions(workspace=self._workspace)
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
            normalized_title = self._normalize_session_title(title)
            return self._sessions.rename_session(
                session_id=session_id,
                title=normalized_title,
                updated_at=utc_now_iso(),
                workspace=self._workspace,
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
                workspace=self._workspace,
            )

    def delete_session(self, session_id: str, user_id: str | None = None) -> bool:
        with self._session_operation_lock(session_id):
            if self.get_session(session_id, user_id=user_id) is None:
                return False
            deleted = self._sessions.delete_session(session_id, workspace=self._workspace)
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
        return self._sessions.list_turns(session_id, workspace=self._workspace)

    def answer_question(
        self,
        question: str,
        session_id: str | None = None,
        user_id: str = "legacy",
        *,
        enable_deep_thinking: bool = False,
        cancellation_token: ChatCancellationToken | None = None,
        user_role: UserRole = UserRole.MEMBER,
        request_id: str | None = None,
    ) -> ChatAnswer:
        resolved_session_id = session_id
        if resolved_session_id is None:
            resolved_session_id = self.create_session_for_user(user_id).session_id
        with self._session_operation_lock(resolved_session_id):
            return self._answer_question_locked(
                question,
                session_id=resolved_session_id,
                user_id=user_id,
                enable_deep_thinking=enable_deep_thinking,
                cancellation_token=cancellation_token,
                user_role=user_role,
                request_id=request_id,
            )

    def _answer_question_locked(
        self,
        question: str,
        session_id: str | None = None,
        user_id: str = "legacy",
        *,
        enable_deep_thinking: bool = False,
        cancellation_token: ChatCancellationToken | None = None,
        user_role: UserRole = UserRole.MEMBER,
        request_id: str | None = None,
    ) -> ChatAnswer:
        if session_id is None:
            raise AssetNotFoundError("chat session was not found")
        session = self._require_session(session_id, user_id=user_id)
        request_fingerprint = self._request_fingerprint(
            session_id=session.session_id,
            user_id=user_id,
            question=question,
            enable_deep_thinking=enable_deep_thinking,
        )
        existing_answer = self._claim_request(
            session=session,
            request_id=request_id,
            request_fingerprint=request_fingerprint,
        )
        if existing_answer is not None:
            return existing_answer
        preference = self._llm_preferences.get_preference()
        access = FileAccessContext(user_id=user_id, role=user_role)
        try:
            self._raise_if_cancelled(cancellation_token)
            if self._workflow is not None:
                return self._workflow.answer_question(
                    ChatWorkflowRequest(
                        question=question,
                        session_id=session.session_id,
                        user_id=user_id,
                        enable_deep_thinking=enable_deep_thinking,
                        llm_preference=preference,
                        cancellation_token=cancellation_token,
                        file_access=access,
                        request_id=request_id,
                    ),
                    actions=self,
                )
            route_result = self.route_question(
                question,
                session_id=session.session_id,
                user_id=user_id,
                llm_preference=preference,
                cancellation_token=cancellation_token,
                file_access=access,
                request_id=request_id,
            )
            return self.answer_routed_question(
                question=question,
                session_id=route_result.session_id,
                user_id=user_id,
                route_result=route_result,
                enable_deep_thinking=enable_deep_thinking,
                llm_preference=preference,
                cancellation_token=cancellation_token,
                file_access=access,
                request_id=request_id,
            )
        except Exception:
            self._release_request(
                session_id=session.session_id,
                request_id=request_id,
                request_fingerprint=request_fingerprint,
            )
            raise

    def answer_selected_question(
        self,
        *,
        question: str,
        session_id: str,
        user_id: str,
        selected_version_ids: list[str],
        expected_session_revision: int | None = None,
        enable_deep_thinking: bool = False,
        cancellation_token: ChatCancellationToken | None = None,
        user_role: UserRole = UserRole.MEMBER,
        request_id: str | None = None,
    ) -> ChatAnswer:
        with self._session_operation_lock(session_id):
            session = self._require_session(session_id, user_id=user_id)
            request_fingerprint = self._request_fingerprint(
                session_id=session.session_id,
                user_id=user_id,
                question=question,
                enable_deep_thinking=enable_deep_thinking,
                selected_version_ids=selected_version_ids,
            )
            existing_answer = self._claim_request(
                session=session,
                request_id=request_id,
                request_fingerprint=request_fingerprint,
            )
            if existing_answer is not None:
                return existing_answer
            access = FileAccessContext(user_id=user_id, role=user_role)
            try:
                route_result = self._plan_selected_version_route(
                    question=question,
                    session=session,
                    selected_version_ids=selected_version_ids,
                    access=access,
                    request_id=request_id,
                    expected_session_revision=expected_session_revision,
                )
                return self._answer_routed_question_locked(
                    question=question,
                    session_id=session.session_id,
                    user_id=user_id,
                    route_result=route_result,
                    selected_version_ids=selected_version_ids,
                    enable_deep_thinking=enable_deep_thinking,
                    cancellation_token=cancellation_token,
                    file_access=access,
                    request_id=request_id,
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
        question: str,
        session_id: str | None = None,
        user_id: str = "legacy",
        *,
        llm_preference: LlmPreference | None = None,
        cancellation_token: ChatCancellationToken | None = None,
        file_access: FileAccessContext | None = None,
        request_id: str | None = None,
    ) -> ChatRouteResult:
        if session_id is not None:
            with self._session_operation_lock(session_id):
                return self._route_question_locked(
                    question,
                    session_id=session_id,
                    user_id=user_id,
                    llm_preference=llm_preference,
                    cancellation_token=cancellation_token,
                    file_access=file_access,
                    request_id=request_id,
                )
        return self._route_question_locked(
            question,
            session_id=session_id,
            user_id=user_id,
            llm_preference=llm_preference,
            cancellation_token=cancellation_token,
            file_access=file_access,
            request_id=request_id,
        )

    def _route_question_locked(
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
        preference = llm_preference or self._llm_preferences.get_preference()
        self._raise_if_cancelled(cancellation_token)
        if session_id is None:
            raise AssetNotFoundError("chat session was not found")
        session = self._require_session(session_id, user_id=user_id)
        existing_turns = self._filter_accessible_turn_context(
            self._sessions.list_turns(session.session_id),
            access=file_access,
        )
        attached_before = self._filter_accessible_attached_documents(
            self._sessions.list_attached_documents(session.session_id),
            access=file_access,
        )
        summaries = self._summaries.list_active_summaries(access=file_access)
        self._raise_if_cancelled(cancellation_token)
        selected_documents = self._llm_client.route_documents(
            question=question,
            summaries=summaries,
            max_documents=self._policy.max_routed_documents,
            user_questions=[turn.question for turn in existing_turns] + [question],
            attached_documents=attached_before,
            previous_turns=existing_turns,
            model=preference.router_model,
            provider=preference.router_provider,
            cancellation_checker=self._cancellation_checker(cancellation_token),
        )
        selected_documents = self._filter_accessible_selected_documents(
            selected_documents,
            access=file_access,
        )
        self._raise_if_cancelled(cancellation_token)

        newly_attached, planned_attachments = self._plan_new_documents(
            session_id=session.session_id,
            selected_documents=selected_documents,
            attached_documents=attached_before,
            access=file_access,
        )
        self._raise_if_cancelled(cancellation_token)
        attached_after = [*attached_before, *planned_attachments]
        created_at = utc_now_iso()
        return ChatRouteResult(
            session_id=session.session_id,
            question=question,
            selected_documents=selected_documents,
            newly_attached_documents=newly_attached,
            attached_documents=attached_after,
            created_at=created_at,
            request_id=request_id,
            session_revision=session.conversation_revision,
        )

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
        with self._session_operation_lock(session_id):
            return self._answer_routed_question_locked(
                question,
                session_id=session_id,
                user_id=user_id,
                route_result=route_result,
                selected_version_ids=selected_version_ids,
                enable_deep_thinking=enable_deep_thinking,
                llm_preference=llm_preference,
                cancellation_token=cancellation_token,
                file_access=file_access,
                request_id=request_id,
            )

    def _answer_routed_question_locked(
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
        preference = llm_preference or self._llm_preferences.get_preference()
        session = self._require_session(session_id, user_id=user_id)
        try:
            self._raise_if_cancelled(cancellation_token)
            existing_turns = self._filter_accessible_turn_context(
                self._sessions.list_turns(session.session_id),
                access=file_access,
            )
            attached_documents = (
                route_result.attached_documents
                if route_result is not None
                else self._filter_accessible_attached_documents(
                    self._sessions.list_attached_documents(session.session_id),
                    access=file_access,
                )
            )
            documents_for_answer = self._resolve_documents_for_answer(
                attached_documents=attached_documents,
                route_result=route_result,
                selected_version_ids=selected_version_ids,
            )
            documents_for_answer = self._filter_accessible_selected_documents(
                documents_for_answer,
                access=file_access,
            )
            (
                draft_answer,
                documents_for_answer,
                rows,
                citation_index,
                rows_truncated,
            ) = self._answer_with_current_access(
                question=question,
                initial_documents=documents_for_answer,
                previous_turns=existing_turns,
                preference=preference,
                enable_deep_thinking=enable_deep_thinking,
                cancellation_token=cancellation_token,
                access=file_access,
            )
            self._raise_if_cancelled(cancellation_token)
            current_document_keys = self._document_keys(
                self._filter_accessible_selected_documents(
                    documents_for_answer,
                    access=file_access,
                )
            )
            if current_document_keys != self._document_keys(documents_for_answer):
                draft_answer = self._visibility_changed_draft_answer(question)
                documents_for_answer = []
                citation_index = {}
                rows_truncated = False
            cited_evidence_ids = [
                evidence_id
                for block in draft_answer.answer_blocks
                for evidence_id in block.evidence_ids
            ]
            citations, evidence_id_to_citation_id, citation_warnings = (
                self._build_verified_citations(
                    draft_answer.citations,
                    cited_evidence_ids,
                    citation_index,
                )
            )
            warnings = [
                *self._row_limit_warnings(rows_truncated),
                *citation_warnings,
            ]
            answer_blocks = [
                ChatAnswerBlock(
                    text=block.text,
                    citation_ids=[
                        citation_id
                        for evidence_id in block.evidence_ids
                        if (
                            citation_id := evidence_id_to_citation_id.get(evidence_id)
                        )
                        is not None
                    ],
                    reasoning=block.reasoning,
                )
                for block in draft_answer.answer_blocks
            ]
            created_at = utc_now_iso()
            selected_documents = documents_for_answer
            newly_attached_documents = self._filter_accessible_selected_documents(
                route_result.newly_attached_documents if route_result is not None else [],
                access=file_access,
            )
            answer = ChatAnswer(
                session_id=session.session_id,
                question=question,
                answer_blocks=answer_blocks,
                selected_documents=selected_documents,
                newly_attached_documents=newly_attached_documents,
                attached_documents=attached_documents,
                citations=citations,
                insufficient_evidence=draft_answer.insufficient_evidence,
                follow_up_suggestions=draft_answer.follow_up_suggestions,
                warnings=warnings,
                created_at=created_at,
            )
            self._raise_if_cancelled(cancellation_token)
            turn = ChatTurn(
                turn_id=new_id("turn"),
                session_id=session.session_id,
                question=question,
                answer_text="\n".join(block.text for block in answer_blocks),
                citation_ids=[
                    citation_id
                    for block in answer_blocks
                    for citation_id in block.citation_ids
                ],
                selected_documents=selected_documents,
                created_at=created_at,
                answer_blocks=answer_blocks,
                newly_attached_documents=newly_attached_documents,
                attached_documents=attached_documents,
                citations=citations,
                insufficient_evidence=answer.insufficient_evidence,
                follow_up_suggestions=answer.follow_up_suggestions,
                warnings=answer.warnings,
                request_id=request_id,
            )
            self._raise_if_cancelled(cancellation_token)
            newly_attached_version_ids = {
                document.version_id for document in newly_attached_documents
            }
            committed_turn = self._sessions.commit_excel_chat_turn(
                session_id=session.session_id,
                user_id=user_id,
                expected_conversation_revision=(
                    route_result.session_revision
                    if route_result is not None
                    else session.conversation_revision
                ),
                attached_documents=[
                    document
                    for document in attached_documents
                    if document.version_id in newly_attached_version_ids
                ],
                turn=turn,
                request_fingerprint=(
                    self._request_fingerprint(
                        session_id=session.session_id,
                        user_id=user_id,
                        question=question,
                        enable_deep_thinking=enable_deep_thinking,
                        selected_version_ids=selected_version_ids,
                    )
                    if request_id
                    else None
                ),
            )
            return self._answer_from_turn(committed_turn)
        except ChatRequestCancelledError:
            raise

    def _cancellation_checker(
        self,
        cancellation_token: ChatCancellationToken | None,
    ):
        if cancellation_token is None:
            return None
        return cancellation_token.raise_if_cancelled

    def _raise_if_cancelled(
        self,
        cancellation_token: ChatCancellationToken | None,
    ) -> None:
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()

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
                if entry.users <= 0 and entry.discard_when_idle:
                    self._session_locks.pop(session_id, None)

    def _discard_session_operation_lock(self, session_id: str) -> None:
        with self._session_locks_guard:
            entry = self._session_locks.get(session_id)
            if entry is None:
                return
            if entry.users <= 0:
                self._session_locks.pop(session_id, None)
            else:
                entry.discard_when_idle = True

    def _filter_accessible_attached_documents(
        self,
        documents: list[AttachedDocument],
        *,
        access: FileAccessContext | None,
    ) -> list[AttachedDocument]:
        return self._access_controller.filter_attached_documents(
            documents,
            access=access,
        )

    def _filter_accessible_selected_documents(
        self,
        documents: list[SelectedDocument],
        *,
        access: FileAccessContext | None,
    ) -> list[SelectedDocument]:
        return self._access_controller.filter_selected_documents(
            documents,
            access=access,
        )

    def _filter_accessible_turn_context(
        self,
        turns: list[ChatTurn],
        *,
        access: FileAccessContext | None,
    ) -> list[ChatTurn]:
        return self._access_controller.filter_turn_context(turns, access=access)

    def _answer_with_current_access(
        self,
        *,
        question: str,
        initial_documents: list[SelectedDocument],
        previous_turns: list[ChatTurn],
        preference: LlmPreference,
        enable_deep_thinking: bool,
        cancellation_token: ChatCancellationToken | None,
        access: FileAccessContext | None,
    ) -> tuple[
        DraftChatAnswer,
        list[SelectedDocument],
        list[dict],
        dict[str, ExcelCitation],
        bool,
    ]:
        documents, rows, citation_index, rows_truncated = self._current_answer_inputs(
            initial_documents,
            access=access,
            cancellation_token=cancellation_token,
        )
        self._raise_if_cancelled(cancellation_token)
        if not documents:
            return (
                self._insufficient_evidence_draft_answer(question),
                documents,
                rows,
                citation_index,
                rows_truncated,
            )

        draft_answer = self._llm_client.answer_with_rows(
            question=question,
            documents=documents,
            rows=rows,
            previous_turns=previous_turns,
            model=preference.answer_model,
            provider=preference.answer_provider,
            enable_deep_thinking=enable_deep_thinking,
            cancellation_checker=self._cancellation_checker(cancellation_token),
        )
        self._raise_if_cancelled(cancellation_token)

        refreshed_documents = self._filter_accessible_selected_documents(
            documents,
            access=access,
        )
        if self._document_keys(refreshed_documents) == self._document_keys(documents):
            return draft_answer, documents, rows, citation_index, rows_truncated

        documents, rows, citation_index, rows_truncated = self._current_answer_inputs(
            refreshed_documents,
            access=access,
            cancellation_token=cancellation_token,
        )
        if not documents:
            return (
                self._insufficient_evidence_draft_answer(question),
                documents,
                rows,
                citation_index,
                rows_truncated,
            )

        draft_answer = self._llm_client.answer_with_rows(
            question=question,
            documents=documents,
            rows=rows,
            previous_turns=previous_turns,
            model=preference.answer_model,
            provider=preference.answer_provider,
            enable_deep_thinking=enable_deep_thinking,
            cancellation_checker=self._cancellation_checker(cancellation_token),
        )
        self._raise_if_cancelled(cancellation_token)

        final_documents = self._filter_accessible_selected_documents(
            documents,
            access=access,
        )
        if self._document_keys(final_documents) != self._document_keys(documents):
            return (
                self._visibility_changed_draft_answer(question),
                [],
                [],
                {},
                False,
            )
        return draft_answer, documents, rows, citation_index, rows_truncated

    def _current_answer_inputs(
        self,
        documents: list[SelectedDocument],
        *,
        access: FileAccessContext | None,
        cancellation_token: ChatCancellationToken | None = None,
    ) -> tuple[list[SelectedDocument], list[dict], dict[str, ExcelCitation], bool]:
        current_documents = self._filter_accessible_selected_documents(
            documents,
            access=access,
        )
        rows, citation_index, rows_truncated = self._load_rows_for_documents(
            current_documents,
            access=access,
            cancellation_token=cancellation_token,
        )
        current_documents = self._filter_accessible_selected_documents(
            current_documents,
            access=access,
        )
        allowed_version_ids = {document.version_id for document in current_documents}
        return (
            current_documents,
            [row for row in rows if row.get("version_id") in allowed_version_ids],
            {
                evidence_id: citation
                for evidence_id, citation in citation_index.items()
                if citation.version_id in allowed_version_ids
            },
            rows_truncated,
        )

    def _insufficient_evidence_draft_answer(self, question: str) -> DraftChatAnswer:
        _ = question
        return DraftChatAnswer(
            answer_blocks=[
                DraftAnswerBlock(
                    text="No visible workspace evidence is available for this question.",
                    evidence_ids=[],
                )
            ],
            citations=[],
            insufficient_evidence=True,
            follow_up_suggestions=[],
        )

    def _visibility_changed_draft_answer(self, question: str) -> DraftChatAnswer:
        _ = question
        return DraftChatAnswer(
            answer_blocks=[
                DraftAnswerBlock(
                    text=(
                        "The available workspace evidence changed while this answer was "
                        "being prepared. Send the question again to use the current file "
                        "visibility."
                    ),
                    evidence_ids=[],
                )
            ],
            citations=[],
            insufficient_evidence=True,
            follow_up_suggestions=[],
        )

    def _document_keys(self, documents: list[SelectedDocument]) -> set[tuple[str, str]]:
        return {(document.file_id, document.version_id) for document in documents}

    def _resolve_documents_for_answer(
        self,
        *,
        attached_documents: list[AttachedDocument],
        route_result: ChatRouteResult | None,
        selected_version_ids: list[str] | None,
    ) -> list[SelectedDocument]:
        if route_result is not None:
            if route_result.selected_documents:
                return route_result.selected_documents
            return self._attached_to_selected_documents(attached_documents)
        if selected_version_ids:
            selected_version_id_set = set(selected_version_ids)
            return [
                document
                for document in self._attached_to_selected_documents(attached_documents)
                if document.version_id in selected_version_id_set
            ]
        return self._attached_to_selected_documents(attached_documents)

    def _require_session(self, session_id: str, *, user_id: str) -> ChatSession:
        session = self._sessions.get_session(session_id, workspace=self._workspace)
        if session is not None and session.user_id == user_id:
            return session
        raise AssetNotFoundError("chat session was not found")

    def _request_fingerprint(
        self,
        *,
        session_id: str,
        user_id: str,
        question: str,
        enable_deep_thinking: bool,
        selected_version_ids: list[str] | None = None,
    ) -> str:
        payload = {
            "workspace": self._workspace,
            "session_id": session_id,
            "user_id": user_id,
            "question": question,
            "enable_deep_thinking": enable_deep_thinking,
            "selected_version_ids": sorted(set(selected_version_ids or [])),
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
    ) -> ChatAnswer | None:
        if request_id is None:
            return None
        claimed_at = datetime.now(UTC)
        existing_turn = self._sessions.claim_excel_chat_request(
            session_id=session.session_id,
            user_id=session.user_id,
            request_id=request_id,
            request_fingerprint=request_fingerprint,
            claimed_at=claimed_at.isoformat(),
            lease_expires_at=(claimed_at + timedelta(minutes=10)).isoformat(),
        )
        if existing_turn is None:
            return None
        return self._answer_from_turn(existing_turn)

    def _release_request(
        self,
        *,
        session_id: str,
        request_id: str | None,
        request_fingerprint: str,
    ) -> None:
        if request_id is None:
            return
        self._sessions.release_excel_chat_request(
            session_id=session_id,
            request_id=request_id,
            request_fingerprint=request_fingerprint,
        )

    def _answer_from_turn(self, turn: ChatTurn) -> ChatAnswer:
        return ChatAnswer(
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
            created_at=turn.created_at,
        )

    def _plan_selected_version_route(
        self,
        *,
        question: str,
        session: ChatSession,
        selected_version_ids: list[str],
        access: FileAccessContext,
        request_id: str | None,
        expected_session_revision: int | None,
    ) -> ChatRouteResult:
        if (
            expected_session_revision is not None
            and expected_session_revision != session.conversation_revision
        ):
            raise ChatSessionRevisionConflict(session.session_id)
        summaries_by_version_id = {
            summary.version_id: summary
            for summary in self._summaries.list_active_summaries(access=access)
        }
        selected_documents: list[SelectedDocument] = []
        seen_version_ids: set[str] = set()
        for version_id in selected_version_ids:
            if version_id in seen_version_ids:
                continue
            seen_version_ids.add(version_id)
            summary = summaries_by_version_id.get(version_id)
            if summary is None:
                continue
            selected_documents.append(
                SelectedDocument(
                    file_id=summary.file_id,
                    version_id=summary.version_id,
                    reason="selected by the route plan",
                )
            )
        attached_before = self._filter_accessible_attached_documents(
            self._sessions.list_attached_documents(session.session_id),
            access=access,
        )
        newly_attached, planned_attachments = self._plan_new_documents(
            session_id=session.session_id,
            selected_documents=selected_documents,
            attached_documents=attached_before,
            access=access,
        )
        return ChatRouteResult(
            session_id=session.session_id,
            question=question,
            selected_documents=selected_documents,
            newly_attached_documents=newly_attached,
            attached_documents=[*attached_before, *planned_attachments],
            created_at=utc_now_iso(),
            request_id=request_id,
            session_revision=(
                session.conversation_revision
                if expected_session_revision is None
                else expected_session_revision
            ),
        )

    def _normalize_session_title(self, title: str) -> str:
        normalized = " ".join(title.split())
        return normalized[:120] if normalized else "New chat"

    def _plan_new_documents(
        self,
        session_id: str,
        selected_documents: list[SelectedDocument],
        attached_documents: list[AttachedDocument],
        *,
        access: FileAccessContext | None,
    ) -> tuple[list[SelectedDocument], list[AttachedDocument]]:
        attached_version_ids = {document.version_id for document in attached_documents}
        newly_attached: list[SelectedDocument] = []
        planned_attachments: list[AttachedDocument] = []
        for document in selected_documents:
            if document.version_id in attached_version_ids:
                continue
            try:
                sheets = self._excel_assets.list_sheets(
                    document.version_id,
                    access=access,
                )
            except AssetNotFoundError:
                continue
            attached = AttachedDocument(
                session_id=session_id,
                file_id=document.file_id,
                version_id=document.version_id,
                attached_at=utc_now_iso(),
                row_count=sum(sheet.row_count for sheet in sheets),
                context_hash=self._document_context_hash(document.version_id, sheets),
            )
            newly_attached.append(document)
            planned_attachments.append(attached)
        return newly_attached, planned_attachments

    def _load_rows_for_attached_documents(
        self,
        attached_documents: list[AttachedDocument],
        *,
        access: FileAccessContext | None = None,
    ) -> tuple[list[dict], dict[str, ExcelCitation], bool]:
        return self._load_rows_for_documents(
            self._attached_to_selected_documents(attached_documents),
            access=access,
        )

    def _load_rows_for_documents(
        self,
        documents: list[SelectedDocument],
        *,
        access: FileAccessContext | None = None,
        cancellation_token: ChatCancellationToken | None = None,
    ) -> tuple[list[dict], dict[str, ExcelCitation], bool]:
        rows: list[dict] = []
        citation_index: dict[str, ExcelCitation] = {}
        rows_truncated = False
        for document in documents:
            self._raise_if_cancelled(cancellation_token)
            try:
                sheets = self._excel_assets.list_sheets(
                    document.version_id,
                    access=access,
                )
            except AssetNotFoundError:
                try:
                    sheets = self._excel_assets.list_sheets_for_legacy_chat_context(
                        document.version_id
                    )
                except AssetNotFoundError:
                    continue
            for sheet in sheets:
                self._raise_if_cancelled(cancellation_token)
                offset = 0
                while True:
                    self._raise_if_cancelled(cancellation_token)
                    try:
                        result = self._excel_assets.list_sheet_rows(
                            sheet_id=sheet.sheet_id,
                            offset=offset,
                            limit=self._policy.row_page_size,
                            access=access,
                        )
                    except AssetNotFoundError:
                        try:
                            result = (
                                self._excel_assets
                                .list_sheet_rows_for_legacy_chat_context(
                                    sheet_id=sheet.sheet_id,
                                    offset=offset,
                                    limit=self._policy.row_page_size,
                                )
                            )
                        except AssetNotFoundError:
                            break
                    for row_response in result.rows:
                        self._raise_if_cancelled(cancellation_token)
                        if (
                            self._policy.effective_max_answer_rows is not None
                            and len(rows) >= self._policy.effective_max_answer_rows
                        ):
                            rows_truncated = True
                            break
                        if not row_response:
                            continue
                        row_id = row_response[0]
                        evidence_id = self._citation_verifier.evidence_id(
                            version_id=document.version_id,
                            sheet_id=sheet.sheet_id,
                            row_id=row_id,
                        )
                        rows.append(
                            {
                                "evidence_id": evidence_id,
                                "file_id": document.file_id,
                                "version_id": document.version_id,
                                "sheet_id": sheet.sheet_id,
                                "sheet_name": sheet.sheet_name,
                                "row_id": row_id,
                                "cells": row_response,
                            }
                        )
                        citation_index[evidence_id] = ExcelCitation(
                            citation_id="",
                            evidence_id=evidence_id,
                            file_id=document.file_id,
                            version_id=document.version_id,
                            sheet_id=sheet.sheet_id,
                            sheet_name=sheet.sheet_name,
                            row_id=row_id,
                            row=row_response,
                        )
                    offset += len(result.rows)
                    if rows_truncated:
                        return rows, citation_index, rows_truncated
                    if offset >= result.total_rows or not result.rows:
                        break
        return rows, citation_index, rows_truncated

    def _row_limit_warnings(self, rows_truncated: bool) -> list[str]:
        if not rows_truncated or self._policy.effective_max_answer_rows is None:
            return []
        return [
            (
                f"Only the first {self._policy.effective_max_answer_rows} row(s) were inspected "
                "to keep the answer request within the long-running safety limit."
            )
        ]

    def _build_verified_citations(
        self,
        draft_citations: list,
        evidence_ids: list[str],
        citation_index: dict[str, ExcelCitation],
    ) -> tuple[list[ExcelCitation], dict[str, str], list[str]]:
        result = self._citation_verifier.build_verified_citations(
            draft_citations,
            evidence_ids,
            citation_index,
        )
        return result.citations, result.evidence_id_to_citation_id, result.warnings

    def _attached_to_selected_documents(
        self,
        attached_documents: list[AttachedDocument],
    ) -> list[SelectedDocument]:
        return [
            SelectedDocument(
                file_id=document.file_id,
                version_id=document.version_id,
                reason="already attached to chat session",
            )
            for document in attached_documents
        ]

    def _document_context_hash(self, version_id: str, sheets: list[ExcelSheet]) -> str:
        digest = hashlib.sha256()
        digest.update(version_id.encode())
        for sheet in sheets:
            digest.update(sheet.sheet_id.encode())
            digest.update(sheet.sheet_name.encode())
            digest.update(str(sheet.row_count).encode())
            digest.update(str(sheet.column_count).encode())
        return digest.hexdigest()
