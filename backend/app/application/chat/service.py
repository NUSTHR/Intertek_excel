import hashlib
import logging
from time import perf_counter

from app.application.document_summaries.service import DocumentSummaryService
from app.application.excel_assets.service import ExcelAssetService
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    AttachedDocument,
    ChatAnswer,
    ChatAnswerBlock,
    ChatRouteResult,
    ChatSession,
    ChatStageTiming,
    ChatTurn,
    ExcelCitation,
    ExcelSheet,
    SelectedDocument,
)
from app.ports.chat_workflow import ChatWorkflow, ChatWorkflowRequest
from app.ports.llm_client import LlmClient
from app.ports.repository import ChatSessionRepository

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        excel_assets: ExcelAssetService,
        summaries: DocumentSummaryService,
        llm_client: LlmClient,
        sessions: ChatSessionRepository,
        max_documents: int = 3,
        page_size: int = 5000,
        workflow: ChatWorkflow | None = None,
    ) -> None:
        self._excel_assets = excel_assets
        self._summaries = summaries
        self._llm_client = llm_client
        self._sessions = sessions
        self._max_documents = max_documents
        self._page_size = page_size
        self._workflow = workflow

    def create_session(self) -> ChatSession:
        now = utc_now_iso()
        session = ChatSession(
            session_id=new_id("session"),
            created_at=now,
            updated_at=now,
        )
        self._sessions.create_session(session)
        return session

    def get_session(self, session_id: str) -> ChatSession | None:
        return self._sessions.get_session(session_id)

    def list_sessions(self) -> list[ChatSession]:
        return self._sessions.list_sessions()

    def rename_session(self, session_id: str, title: str) -> ChatSession | None:
        normalized_title = self._normalize_session_title(title)
        return self._sessions.rename_session(
            session_id=session_id,
            title=normalized_title,
            updated_at=utc_now_iso(),
        )

    def set_session_pinned(self, session_id: str, pinned: bool) -> ChatSession | None:
        now = utc_now_iso()
        return self._sessions.set_session_pinned(
            session_id=session_id,
            pinned_at=now if pinned else None,
            updated_at=now,
        )

    def delete_session(self, session_id: str) -> bool:
        return self._sessions.delete_session(session_id)

    def answer_question(
        self,
        question: str,
        session_id: str | None = None,
        *,
        router_model: str | None = None,
        router_provider: str | None = None,
        answer_model: str | None = None,
        answer_provider: str | None = None,
    ) -> ChatAnswer:
        if self._workflow is not None:
            return self._workflow.answer_question(
                ChatWorkflowRequest(
                    question=question,
                    session_id=session_id,
                    router_model=router_model,
                    router_provider=router_provider,
                    answer_model=answer_model,
                    answer_provider=answer_provider,
                ),
                actions=self,
            )
        route_result = self.route_question(
            question,
            session_id=session_id,
            router_model=router_model,
            router_provider=router_provider,
        )
        return self.answer_routed_question(
            question=question,
            session_id=route_result.session_id,
            route_result=route_result,
            answer_model=answer_model,
            answer_provider=answer_provider,
        )

    def route_question(
        self,
        question: str,
        session_id: str | None = None,
        *,
        router_model: str | None = None,
        router_provider: str | None = None,
    ) -> ChatRouteResult:
        total_timer = StageTimer()
        session = self._get_or_create_session(session_id)
        existing_turns = self._sessions.list_turns(session.session_id)
        attached_before = self._sessions.list_attached_documents(session.session_id)
        summaries = self._summaries.list_active_summaries()
        with total_timer.measure("route_model"):
            selected_documents = self._llm_client.route_documents(
                question=question,
                summaries=summaries,
                max_documents=self._max_documents,
                user_questions=[turn.question for turn in existing_turns] + [question],
                attached_documents=attached_before,
                previous_turns=existing_turns,
                model=router_model,
                provider=router_provider,
            )

        with total_timer.measure("attach_documents"):
            newly_attached = self._attach_new_documents(
                session_id=session.session_id,
                selected_documents=selected_documents,
                attached_documents=attached_before,
            )
        attached_after = self._sessions.list_attached_documents(session.session_id)
        created_at = utc_now_iso()
        self._sessions.touch_session(session.session_id, created_at)
        timings = [*total_timer.timings(), total_timer.total("route_total")]
        self._log_timings(
            session_id=session.session_id,
            question=question,
            timings=timings,
            selected_count=len(selected_documents),
            newly_attached_count=len(newly_attached),
        )
        return ChatRouteResult(
            session_id=session.session_id,
            question=question,
            selected_documents=selected_documents,
            newly_attached_documents=newly_attached,
            attached_documents=attached_after,
            timings=timings,
            created_at=created_at,
        )

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
        total_timer = StageTimer()
        session = self._get_or_create_session(session_id)
        existing_turns = self._sessions.list_turns(session.session_id)
        attached_documents = self._sessions.list_attached_documents(session.session_id)
        documents_for_answer = self._resolve_documents_for_answer(
            attached_documents=attached_documents,
            route_result=route_result,
            selected_version_ids=selected_version_ids,
        )
        with total_timer.measure("load_rows"):
            rows, citation_index = self._load_rows_for_documents(documents_for_answer)
        with total_timer.measure("answer_model"):
            draft_answer = self._llm_client.answer_with_rows(
                question=question,
                documents=documents_for_answer,
                rows=rows,
                previous_turns=existing_turns,
                model=answer_model,
                provider=answer_provider,
            )
        cited_row_ids = [
            row_id
            for block in draft_answer.answer_blocks
            for row_id in block.evidence_row_ids
        ]
        with total_timer.measure("verify_citations"):
            citations, row_id_to_citation_id, warnings = self._build_verified_citations(
                draft_answer.citations,
                cited_row_ids,
                citation_index,
            )
        answer_blocks = [
            ChatAnswerBlock(
                text=block.text,
                citation_ids=[
                    citation_id
                    for row_id in block.evidence_row_ids
                    if (citation_id := row_id_to_citation_id.get(row_id)) is not None
                ],
            )
            for block in draft_answer.answer_blocks
        ]
        created_at = utc_now_iso()
        answer_timings = [*total_timer.timings(), total_timer.total("answer_total")]
        timings = [*(route_result.timings if route_result else []), *answer_timings]
        timings.append(
            ChatStageTiming(
                stage="chat_total",
                duration_seconds=self._chat_total(timings),
            )
        )
        selected_documents = documents_for_answer
        newly_attached_documents = (
            route_result.newly_attached_documents if route_result is not None else []
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
            timings=timings,
            created_at=created_at,
        )
        self._sessions.create_turn(
            ChatTurn(
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
            )
        )
        self._sessions.touch_session(session.session_id, created_at)
        self._log_timings(
            session_id=session.session_id,
            question=question,
            timings=timings,
            selected_count=len(attached_documents),
            newly_attached_count=0,
        )
        return answer

    def _resolve_documents_for_answer(
        self,
        *,
        attached_documents: list[AttachedDocument],
        route_result: ChatRouteResult | None,
        selected_version_ids: list[str] | None,
    ) -> list[SelectedDocument]:
        if route_result is not None:
            return route_result.selected_documents or self._attached_to_selected_documents(
                attached_documents
            )
        if selected_version_ids:
            selected_version_id_set = set(selected_version_ids)
            return [
                document
                for document in self._attached_to_selected_documents(attached_documents)
                if document.version_id in selected_version_id_set
            ]
        return self._attached_to_selected_documents(attached_documents)

    def _get_or_create_session(self, session_id: str | None) -> ChatSession:
        if session_id is None:
            return self.create_session()
        session = self._sessions.get_session(session_id)
        if session is not None:
            return session
        now = utc_now_iso()
        session = ChatSession(
            session_id=session_id,
            created_at=now,
            updated_at=now,
        )
        self._sessions.create_session(session)
        return session

    def _normalize_session_title(self, title: str) -> str:
        normalized = " ".join(title.split())
        return normalized[:120] if normalized else "New chat"

    def _attach_new_documents(
        self,
        session_id: str,
        selected_documents: list[SelectedDocument],
        attached_documents: list[AttachedDocument],
    ) -> list[SelectedDocument]:
        attached_version_ids = {document.version_id for document in attached_documents}
        newly_attached: list[SelectedDocument] = []
        for document in selected_documents:
            if document.version_id in attached_version_ids:
                continue
            sheets = self._excel_assets.list_sheets(document.version_id)
            attached = AttachedDocument(
                session_id=session_id,
                file_id=document.file_id,
                version_id=document.version_id,
                attached_at=utc_now_iso(),
                row_count=sum(sheet.row_count for sheet in sheets),
                context_hash=self._document_context_hash(document.version_id, sheets),
            )
            self._sessions.attach_document(attached)
            newly_attached.append(document)
        return newly_attached

    def _load_rows_for_attached_documents(
        self,
        attached_documents: list[AttachedDocument],
    ) -> tuple[list[dict], dict[str, ExcelCitation]]:
        return self._load_rows_for_documents(
            self._attached_to_selected_documents(attached_documents)
        )

    def _load_rows_for_documents(
        self,
        documents: list[SelectedDocument],
    ) -> tuple[list[dict], dict[str, ExcelCitation]]:
        rows: list[dict] = []
        citation_index: dict[str, ExcelCitation] = {}
        for document in documents:
            for sheet in self._excel_assets.list_sheets(document.version_id):
                offset = 0
                while True:
                    result = self._excel_assets.list_sheet_rows(
                        sheet_id=sheet.sheet_id,
                        offset=offset,
                        limit=self._page_size,
                    )
                    for row_response in result.rows:
                        if not row_response:
                            continue
                        row_id = row_response[0]
                        rows.append(
                            {
                                "file_id": document.file_id,
                                "version_id": document.version_id,
                                "sheet_id": sheet.sheet_id,
                                "sheet_name": sheet.sheet_name,
                                "row_id": row_id,
                                "cells": row_response,
                            }
                        )
                        citation_index[row_id] = ExcelCitation(
                            citation_id="",
                            file_id=document.file_id,
                            version_id=document.version_id,
                            sheet_id=sheet.sheet_id,
                            sheet_name=sheet.sheet_name,
                            row_id=row_id,
                            row=row_response,
                        )
                    offset += len(result.rows)
                    if offset >= result.total_rows or not result.rows:
                        break
        return rows, citation_index

    def _build_verified_citations(
        self,
        draft_citations: list,
        evidence_row_ids: list[str],
        citation_index: dict[str, ExcelCitation],
    ) -> tuple[list[ExcelCitation], dict[str, str], list[str]]:
        citations: list[ExcelCitation] = []
        row_id_to_citation_id: dict[str, str] = {}
        warnings: list[str] = []
        quotes_by_row_id = {draft.row_id: draft.quote for draft in draft_citations}
        for row_id in [*quotes_by_row_id, *evidence_row_ids]:
            source = citation_index.get(row_id)
            if source is None:
                warnings.append(f"ignored invalid citation row_id: {row_id}")
                continue
            if row_id in row_id_to_citation_id:
                continue
            citation_id = f"C{len(citations) + 1}"
            row_id_to_citation_id[row_id] = citation_id
            citations.append(
                ExcelCitation(
                    citation_id=citation_id,
                    file_id=source.file_id,
                    version_id=source.version_id,
                    sheet_id=source.sheet_id,
                    sheet_name=source.sheet_name,
                    row_id=source.row_id,
                    row=source.row,
                    quote=quotes_by_row_id.get(row_id, ""),
                )
            )
        return citations, row_id_to_citation_id, warnings

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

    def _chat_total(self, timings: list[ChatStageTiming]) -> float:
        answer_total = next(
            (
                timing.duration_seconds
                for timing in timings
                if timing.stage == "answer_total"
            ),
            0.0,
        )
        route_total = next(
            (
                timing.duration_seconds
                for timing in timings
                if timing.stage == "route_total"
            ),
            0.0,
        )
        return route_total + answer_total

    def _log_timings(
        self,
        session_id: str,
        question: str,
        timings: list[ChatStageTiming],
        selected_count: int,
        newly_attached_count: int,
    ) -> None:
        logger.info(
            "chat timing session_id=%s selected=%s newly_attached=%s timings=%s question=%r",
            session_id,
            selected_count,
            newly_attached_count,
            {
                timing.stage: round(timing.duration_seconds, 3)
                for timing in timings
            },
            question[:160],
        )


class StageTimer:
    def __init__(self) -> None:
        self._started_at = perf_counter()
        self._timings: list[ChatStageTiming] = []

    def measure(self, stage: str) -> "StageMeasurement":
        return StageMeasurement(stage=stage, timer=self)

    def add(self, stage: str, duration_seconds: float) -> None:
        self._timings.append(
            ChatStageTiming(stage=stage, duration_seconds=duration_seconds)
        )

    def timings(self) -> list[ChatStageTiming]:
        return list(self._timings)

    def total(self, stage: str) -> ChatStageTiming:
        return ChatStageTiming(
            stage=stage,
            duration_seconds=perf_counter() - self._started_at,
        )


class StageMeasurement:
    def __init__(self, stage: str, timer: StageTimer) -> None:
        self._stage = stage
        self._timer = timer
        self._started_at = 0.0

    def __enter__(self) -> None:
        self._started_at = perf_counter()

    def __exit__(self, *_exc: object) -> None:
        self._timer.add(self._stage, perf_counter() - self._started_at)
