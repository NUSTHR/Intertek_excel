from dataclasses import replace

from app.application.llm_preferences.service import WorkspaceLlmPreferenceService
from app.application.pdf_knowledge.library_service import PdfLibraryService
from app.application.pdf_knowledge.model_settings import pdf_model_selection
from app.application.pdf_knowledge.settings_service import PdfModelSettingsService
from app.core.errors import AssetNotFoundError, UploadValidationError
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    PdfDocumentChunk,
    PdfDocumentSummary,
    PdfFile,
    PdfFileKind,
    PdfProcessingStatus,
    PdfSummaryTask,
    PdfSummaryTaskStatus,
    SheetProfile,
    UserRole,
    WorkbookProfile,
)
from app.ports.llm_client import LlmClient
from app.ports.repository import PdfKnowledgeRepository


class PdfSummarySourceChangedError(RuntimeError):
    """Raised when parsed PDF content changes while a summary is being generated."""


class PdfSummaryService:
    """Owns PDF summary generation and durable summary task lifecycle."""

    def __init__(
        self,
        *,
        repository: PdfKnowledgeRepository,
        library: PdfLibraryService,
        model_settings: PdfModelSettingsService,
        llm_client: LlmClient | None = None,
        llm_preferences: WorkspaceLlmPreferenceService | None = None,
    ) -> None:
        self._repository = repository
        self._library = library
        self._model_settings = model_settings
        self._llm_client = llm_client
        self._llm_preferences = llm_preferences

    def create_tasks(
        self,
        *,
        user_id: str,
        user_role: UserRole,
        file_ids: list[str] | None = None,
        parent_id: str | None = None,
        include_descendants: bool = True,
        force: bool = False,
    ) -> list[PdfSummaryTask]:
        files = self._task_candidate_files(
            file_ids=file_ids or [],
            parent_id=parent_id,
            include_descendants=include_descendants,
            user_role=user_role,
        )
        if not files:
            raise UploadValidationError("no PDF documents were available for summary")
        now = utc_now_iso()
        tasks: list[PdfSummaryTask] = []
        for file in files:
            active_task = self._repository.find_active_pdf_summary_task(file.file_id)
            if active_task is not None:
                tasks.append(active_task)
                continue
            task = self._new_task(
                file=file,
                user_id=user_id,
                created_at=now,
                force=force,
            )
            if task.result.get("reason") == "already_ready":
                tasks.append(task)
                continue
            tasks.append(self._repository.create_pdf_summary_task(task))
        return tasks

    def list_tasks(self, *, user_id: str) -> list[PdfSummaryTask]:
        return self._repository.list_pdf_summary_tasks(user_id)

    def get_task(self, task_id: str, *, user_id: str) -> PdfSummaryTask:
        task = self._repository.get_pdf_summary_task(task_id)
        if task is None or task.user_id != user_id:
            raise AssetNotFoundError("PDF summary task was not found")
        return task

    def cancel_task(self, task_id: str, *, user_id: str) -> PdfSummaryTask:
        task = self.get_task(task_id, user_id=user_id)
        if task.status != PdfSummaryTaskStatus.QUEUED:
            raise UploadValidationError("only queued PDF summary tasks can be cancelled")
        cancelled = self._repository.cancel_pdf_summary_task(
            task_id=task.task_id,
            cancelled_at=utc_now_iso(),
            detail="PDF summary generation was cancelled before it started.",
        )
        return cancelled or task

    def retry_task(self, task_id: str, *, user_id: str) -> PdfSummaryTask:
        task = self.get_task(task_id, user_id=user_id)
        if task.status not in {
            PdfSummaryTaskStatus.FAILED,
            PdfSummaryTaskStatus.SKIPPED,
            PdfSummaryTaskStatus.CANCELLED,
        }:
            raise UploadValidationError(
                "only failed, skipped, or cancelled PDF summary tasks can be retried"
            )
        file = self._repository.get_pdf_file(task.file_id)
        if file is None:
            raise AssetNotFoundError("PDF source file was not found")
        retried = self._repository.retry_pdf_summary_task(
            task_id=task.task_id,
            retried_at=utc_now_iso(),
        )
        return retried or task

    def process_task(self, task: PdfSummaryTask) -> PdfSummaryTask:
        worker_id, claim_token = self._task_claim(task)
        file = self._repository.get_pdf_file(task.file_id)
        now = utc_now_iso()
        if file is None:
            return self._repository.skip_pdf_summary_task(
                task_id=task.task_id,
                worker_id=worker_id,
                claim_token=claim_token,
                detail="PDF source file is no longer available.",
                result={"reason": "file_not_available"},
                skipped_at=now,
            ) or task
        if file.kind != PdfFileKind.PDF:
            return self._repository.skip_pdf_summary_task(
                task_id=task.task_id,
                worker_id=worker_id,
                claim_token=claim_token,
                detail="Skipped non-PDF item.",
                result={"reason": "not_pdf"},
                skipped_at=now,
            ) or task
        if file.processing_status != PdfProcessingStatus.READY:
            return self._repository.skip_pdf_summary_task(
                task_id=task.task_id,
                worker_id=worker_id,
                claim_token=claim_token,
                detail="Skipped because PDF parsing is not ready.",
                result={
                    "reason": "not_ready",
                    "processing_status": file.processing_status.value,
                },
                skipped_at=now,
            ) or task
        if file.content_fingerprint != task.source_fingerprint:
            return self._repository.skip_pdf_summary_task(
                task_id=task.task_id,
                worker_id=worker_id,
                claim_token=claim_token,
                detail="Skipped because the parsed PDF content changed.",
                result={"reason": "source_changed"},
                skipped_at=now,
            ) or task
        try:
            summary = self.generate(
                file.file_id,
                user_role=UserRole.ADMIN,
                generation_task=task,
            )
        except PdfSummarySourceChangedError:
            return self._repository.skip_pdf_summary_task(
                task_id=task.task_id,
                worker_id=worker_id,
                claim_token=claim_token,
                detail="Skipped because the parsed PDF content changed.",
                result={"reason": "source_changed"},
                skipped_at=utc_now_iso(),
            ) or task
        finished_at = utc_now_iso()
        return self._repository.complete_pdf_summary_task(
            task_id=task.task_id,
            worker_id=worker_id,
            claim_token=claim_token,
            result={
                "summary_status": summary.status,
                "summary_updated_at": summary.updated_at,
            },
            detail="PDF summary generated.",
            finished_at=finished_at,
        ) or task

    def fail_task(
        self,
        task: PdfSummaryTask,
        error_message: str,
    ) -> PdfSummaryTask:
        worker_id, claim_token = self._task_claim(task)
        return self._repository.fail_pdf_summary_task(
            task_id=task.task_id,
            worker_id=worker_id,
            claim_token=claim_token,
            error_message=error_message[:500],
            failed_at=utc_now_iso(),
        ) or task

    def fail_stale_running_tasks(
        self,
        *,
        cutoff_started_at: str,
        failed_at: str,
    ) -> int:
        return self._repository.fail_stale_running_pdf_summary_tasks(
            cutoff_started_at=cutoff_started_at,
            failed_at=failed_at,
        )

    def generate(
        self,
        file_id: str,
        *,
        user_role: UserRole,
        generation_task: PdfSummaryTask | None = None,
    ) -> PdfDocumentSummary:
        file = self._library.get_file(file_id, user_role=user_role)
        now = utc_now_iso()
        if file.kind != PdfFileKind.PDF:
            raise UploadValidationError("PDF summary can only be generated for PDF files")
        if file.processing_status != PdfProcessingStatus.READY:
            content = (
                "The source is still being prepared. Summary quality will improve "
                "after parsing and indexing finish."
            )
            summary = PdfDocumentSummary(
                file_id=file.file_id,
                status="pending",
                content=content,
                updated_at=now,
                document_title=file.display_name,
                source_fingerprint=file.content_fingerprint,
                source_updated_at=file.updated_at,
                generation_task_id=(generation_task.task_id if generation_task else None),
                generated_by_user_id=(generation_task.user_id if generation_task else None),
                created_at=now,
            )
        elif self._llm_client is not None and self._llm_preferences is not None:
            chunks = self._repository.list_pdf_document_chunks(file.file_id)
            model_selection = pdf_model_selection(
                self._model_settings.list_settings(),
                "summary",
            )
            document_summary = self._llm_client.generate_document_summary(
                _summary_profile(file=file, chunks=chunks),
                model=model_selection.model,
                provider=model_selection.provider,
            )
            summary = PdfDocumentSummary(
                file_id=file.file_id,
                status="ready",
                content=document_summary.summary_text,
                updated_at=now,
                document_title=file.display_name,
                document_type=document_summary.document_type,
                business_domain=document_summary.business_domain,
                key_topics=document_summary.key_topics,
                positive_routing_terms=document_summary.positive_routing_terms,
                negative_routing_terms=document_summary.negative_routing_terms,
                exact_identifiers=document_summary.exact_identifiers,
                suitable_questions=document_summary.suitable_questions,
                unsuitable_questions=document_summary.unsuitable_questions,
                routing_notes=document_summary.routing_notes,
                source_fingerprint=file.content_fingerprint,
                source_updated_at=file.updated_at,
                provider=model_selection.provider,
                model=model_selection.model,
                generation_task_id=(generation_task.task_id if generation_task else None),
                generated_by_user_id=(generation_task.user_id if generation_task else None),
                created_at=now,
            )
        else:
            content = (
                f"{file.display_name} is indexed and ready for PDF-grounded chat. "
                f"It contains {file.page_count or 'multiple'} pages and "
                f"{file.chunk_count or 'several'} searchable chunks."
            )
            summary = PdfDocumentSummary(
                file_id=file.file_id,
                status="ready",
                content=content,
                updated_at=now,
                document_title=file.display_name,
                key_topics=[file.display_name, "PDF", "indexed document"],
                positive_routing_terms=[file.display_name, "PDF", "indexed document"],
                exact_identifiers=[file.display_name],
                suitable_questions=["Ask about content present in this PDF document."],
                unsuitable_questions=["Questions requiring information outside this PDF."],
                routing_notes="fallback PDF summary generated without LLM",
                source_fingerprint=file.content_fingerprint,
                source_updated_at=file.updated_at,
                provider="fallback",
                model="deterministic",
                generation_task_id=(generation_task.task_id if generation_task else None),
                generated_by_user_id=(generation_task.user_id if generation_task else None),
                created_at=now,
            )
        if not self._repository.save_pdf_document_summary(summary):
            raise PdfSummarySourceChangedError(
                "PDF content changed while its summary was being generated"
            )
        return summary

    def mark_stale(self, file: PdfFile, *, updated_at: str) -> None:
        detail = self._repository.get_pdf_document_detail(file.file_id)
        if detail is None or detail.summary.status in {"empty", "stale"}:
            return
        self._repository.save_pdf_document_summary(
            replace(
                detail.summary,
                status="stale",
                updated_at=updated_at,
                error_message="PDF content changed; regenerate the summary before routing.",
                source_fingerprint=file.content_fingerprint,
                source_updated_at=file.updated_at,
            )
        )

    def _task_claim(self, task: PdfSummaryTask) -> tuple[str, str]:
        if (
            task.status != PdfSummaryTaskStatus.RUNNING
            or not task.worker_id
            or not task.claim_token
        ):
            raise UploadValidationError("PDF summary task does not have an active worker claim")
        return task.worker_id, task.claim_token

    def _task_candidate_files(
        self,
        *,
        file_ids: list[str],
        parent_id: str | None,
        include_descendants: bool,
        user_role: UserRole,
    ) -> list[PdfFile]:
        all_files = self._library.list_files(user_role=user_role)
        files_by_id = {file.file_id: file for file in all_files}
        selected: list[PdfFile] = []
        if file_ids:
            for file_id in _dedupe_file_ids(file_ids):
                file = self._library.get_file(file_id, user_role=user_role)
                if file.kind == PdfFileKind.FOLDER and include_descendants:
                    selected.extend(
                        self._descendant_pdf_files(file.file_id, files_by_id=files_by_id)
                    )
                    continue
                selected.append(file)
        elif parent_id:
            parent = self._library.get_file(parent_id, user_role=user_role)
            if parent.kind != PdfFileKind.FOLDER:
                raise UploadValidationError("PDF summary parent scope must be a folder")
            selected.extend(
                self._descendant_pdf_files(parent.file_id, files_by_id=files_by_id)
            )
        else:
            selected.extend(all_files)
        deduped: list[PdfFile] = []
        seen: set[str] = set()
        for file in selected:
            if file.file_id in seen or file.kind != PdfFileKind.PDF:
                continue
            seen.add(file.file_id)
            deduped.append(file)
        return deduped

    def _descendant_pdf_files(
        self,
        parent_id: str,
        *,
        files_by_id: dict[str, PdfFile],
    ) -> list[PdfFile]:
        children_by_parent: dict[str | None, list[PdfFile]] = {}
        for file in files_by_id.values():
            children_by_parent.setdefault(file.parent_id, []).append(file)
        descendants: list[PdfFile] = []
        stack = list(children_by_parent.get(parent_id, []))
        while stack:
            file = stack.pop(0)
            if file.kind == PdfFileKind.PDF:
                descendants.append(file)
            elif file.kind == PdfFileKind.FOLDER:
                stack.extend(children_by_parent.get(file.file_id, []))
        return descendants

    def _new_task(
        self,
        *,
        file: PdfFile,
        user_id: str,
        created_at: str,
        force: bool,
    ) -> PdfSummaryTask:
        if file.processing_status != PdfProcessingStatus.READY:
            return PdfSummaryTask(
                task_id=new_id("pdfsummary"),
                user_id=user_id,
                file_id=file.file_id,
                status=PdfSummaryTaskStatus.SKIPPED,
                progress=100,
                detail="Skipped because PDF parsing is not ready.",
                error_message=None,
                result={
                    "reason": "not_ready",
                    "processing_status": file.processing_status.value,
                },
                created_at=created_at,
                updated_at=created_at,
                finished_at=created_at,
                source_fingerprint=file.content_fingerprint,
            )
        if not force and self._summary_is_current_ready(file):
            return PdfSummaryTask(
                task_id=new_id("pdfsummary"),
                user_id=user_id,
                file_id=file.file_id,
                status=PdfSummaryTaskStatus.SKIPPED,
                progress=100,
                detail="Skipped because the PDF summary is already ready.",
                error_message=None,
                result={"reason": "already_ready"},
                created_at=created_at,
                updated_at=created_at,
                finished_at=created_at,
                source_fingerprint=file.content_fingerprint,
            )
        return PdfSummaryTask(
            task_id=new_id("pdfsummary"),
            user_id=user_id,
            file_id=file.file_id,
            status=PdfSummaryTaskStatus.QUEUED,
            progress=5,
            detail="Queued for PDF summary generation.",
            error_message=None,
            result={},
            created_at=created_at,
            updated_at=created_at,
            source_fingerprint=file.content_fingerprint,
        )

    def _summary_is_current_ready(self, file: PdfFile) -> bool:
        detail = self._repository.get_pdf_document_detail(file.file_id)
        if detail is None or detail.summary.status != "ready":
            return False
        return detail.summary.source_fingerprint == file.content_fingerprint


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


def _summary_profile(
    *,
    file: PdfFile,
    chunks: list[PdfDocumentChunk],
) -> WorkbookProfile:
    rows = [
        [
            chunk.page_label or "",
            chunk.title,
            chunk.text[:2000],
        ]
        for chunk in chunks[:80]
    ]
    return WorkbookProfile(
        file_id=file.file_id,
        version_id=file.file_id,
        original_filename=file.display_name,
        file_hash=file.file_id,
        sheets=[
            SheetProfile(
                sheet_id=file.file_id,
                sheet_code="pdf",
                sheet_name=file.display_name,
                row_count=len(chunks),
                column_count=3,
                sample_rows=rows[:20],
                candidate_header=["page_label", "title", "text"],
                profile_rows=rows,
            )
        ],
    )
