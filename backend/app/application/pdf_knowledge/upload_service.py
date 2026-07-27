from dataclasses import dataclass

from app.application.pdf_knowledge.batch_status import (
    is_terminal_batch_status,
    upload_batch_rollup,
)
from app.application.pdf_knowledge.library_service import PdfLibraryService
from app.application.pdf_knowledge.parser_profiles import PdfParserProfileRegistry
from app.application.pdf_knowledge.summary_service import PdfSummaryService
from app.application.pdf_knowledge.uploads import (
    PdfUploadCandidate,
    PdfUploadRecordBuilder,
    first_skipped_upload_reason,
    source_name_for_upload_batch,
    upload_batch_queued_detail,
)
from app.core.errors import AssetNotFoundError, UploadValidationError
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    PdfFileKind,
    PdfProcessingStatus,
    PdfUploadBatch,
    PdfUploadBatchStatus,
    PdfUploadTask,
    PdfUploadTaskStage,
    PdfUploadTaskStatus,
    UserRole,
)
from app.ports.repository import PdfKnowledgeRepository


@dataclass(frozen=True)
class PdfUploadBatchCreationResult:
    batch: PdfUploadBatch
    tasks: list[PdfUploadTask]


class PdfUploadService:
    """Owns PDF upload, reparse, retry, cancellation, and batch lifecycle."""

    def __init__(
        self,
        *,
        repository: PdfKnowledgeRepository,
        upload_records: PdfUploadRecordBuilder,
        parser_profiles: PdfParserProfileRegistry,
        library: PdfLibraryService,
        summaries: PdfSummaryService,
    ) -> None:
        self._repository = repository
        self._upload_records = upload_records
        self._parser_profiles = parser_profiles
        self._library = library
        self._summaries = summaries

    def create_task(
        self,
        *,
        user_id: str,
        original_filename: str,
        content: bytes,
        relative_path: str | None = None,
    ) -> PdfUploadTask:
        now = utc_now_iso()
        file, task = self._upload_records.build_upload_records(
            user_id=user_id,
            original_filename=original_filename,
            content=content,
            relative_path=relative_path,
            created_at=now,
            batch_id=None,
            parser_backend=self._parser_profiles.selected_profile_id,
        )
        self._repository.create_pdf_file(file)
        self._repository.create_pdf_upload_task(task)
        return task

    def create_batch(
        self,
        *,
        user_id: str,
        candidates: list[PdfUploadCandidate],
        source_name: str | None = None,
    ) -> PdfUploadBatchCreationResult:
        if not candidates:
            raise UploadValidationError("no supported PDF knowledge files were found")
        now = utc_now_iso()
        inspection = self._upload_records.inspect_candidates(candidates)
        accepted = inspection.accepted
        if not accepted:
            first_skip_reason = first_skipped_upload_reason(inspection.skipped)
            if first_skip_reason:
                raise UploadValidationError(first_skip_reason)
            raise UploadValidationError("no supported PDF knowledge files were found")
        batch_id = new_id("pdfbatch")
        skipped_count = len(inspection.skipped)
        batch = PdfUploadBatch(
            batch_id=batch_id,
            user_id=user_id,
            source_name=source_name_for_upload_batch(accepted, source_name),
            status=PdfUploadBatchStatus.QUEUED,
            total_files=len(candidates),
            accepted_files=len(accepted),
            skipped_files=skipped_count,
            total_bytes=sum(len(candidate.content) for candidate in accepted),
            progress=5,
            detail=upload_batch_queued_detail(len(accepted), skipped_count),
            parser_backend=self._parser_profiles.selected_profile_id,
            created_at=now,
            updated_at=now,
            result={
                "accepted_files": len(accepted),
                "skipped_files": skipped_count,
                "skipped_files_detail": inspection.skipped,
            },
        )
        records = [
            self._upload_records.build_upload_records(
                user_id=user_id,
                original_filename=candidate.original_filename,
                content=candidate.content,
                relative_path=candidate.relative_path or candidate.original_filename,
                created_at=now,
                batch_id=batch_id,
                parser_backend=self._parser_profiles.selected_profile_id,
            )
            for candidate in accepted
        ]
        self._repository.create_pdf_upload_batch(batch)
        for file, task in records:
            self._repository.create_pdf_file(file)
            self._repository.create_pdf_upload_task(task)
        return PdfUploadBatchCreationResult(
            batch=batch,
            tasks=[task for _file, task in records],
        )

    def get_task(self, task_id: str, *, user_id: str) -> PdfUploadTask:
        task = self._repository.get_pdf_upload_task(task_id)
        if task is None or task.user_id != user_id:
            raise AssetNotFoundError("PDF upload task was not found")
        return task

    def list_tasks(self, *, user_id: str) -> list[PdfUploadTask]:
        return self._repository.list_pdf_upload_tasks(user_id)

    def list_batches(self, *, user_id: str) -> list[PdfUploadBatch]:
        return [
            self.refresh_batch(batch.batch_id)
            for batch in self._repository.list_pdf_upload_batches(user_id)
        ]

    def get_batch(self, batch_id: str, *, user_id: str) -> PdfUploadBatch:
        batch = self._repository.get_pdf_upload_batch(batch_id)
        if batch is None or batch.user_id != user_id:
            raise AssetNotFoundError("PDF upload batch was not found")
        return self.refresh_batch(batch.batch_id)

    def list_batch_tasks(
        self,
        batch_id: str,
        *,
        user_id: str,
    ) -> list[PdfUploadTask]:
        batch = self.get_batch(batch_id, user_id=user_id)
        return self._repository.list_pdf_upload_tasks_by_batch(batch.batch_id)

    def create_reparse_task(
        self,
        *,
        file_id: str,
        user_id: str,
        user_role: UserRole,
    ) -> PdfUploadTask:
        file = self._library.get_file(file_id, user_role=user_role)
        if file.kind != PdfFileKind.PDF or not file.storage_path:
            raise UploadValidationError("only stored PDF documents can be reparsed")
        content = self._upload_records.stored_file_path(file.storage_path).read_bytes()
        now = utc_now_iso()
        task_id = new_id("pdfupload")
        staging_path = self._upload_records.write_staging_file(
            task_id,
            file.original_filename,
            content,
        )
        self._summaries.mark_stale(file, updated_at=now)
        task = PdfUploadTask(
            task_id=task_id,
            user_id=user_id,
            file_id=file.file_id,
            original_filename=file.original_filename,
            staging_path=self._upload_records.storage_reference(staging_path),
            status=PdfUploadTaskStatus.QUEUED,
            progress=5,
            detail="Queued for MinerU reparse.",
            error_message=None,
            result={"operation": "reparse"},
            created_at=now,
            updated_at=now,
            stage=PdfUploadTaskStage.QUEUED,
            parser_backend=self._parser_profiles.selected_profile_id,
            retry_count=0,
        )
        self._repository.update_pdf_file_processing(
            file_id=file.file_id,
            processing_status=PdfProcessingStatus.QUEUED,
            progress=5,
            status_detail="Queued for MinerU reparse.",
            updated_at=now,
            error_message=None,
        )
        self._repository.create_pdf_upload_task(task)
        return task

    def cancel_task(self, task_id: str, *, user_id: str) -> PdfUploadTask:
        task = self.get_task(task_id, user_id=user_id)
        if task.status != PdfUploadTaskStatus.QUEUED:
            raise UploadValidationError("only queued PDF upload tasks can be cancelled")
        cancelled_at = utc_now_iso()
        if task.file_id is not None:
            self._repository.update_pdf_file_processing(
                file_id=task.file_id,
                processing_status=PdfProcessingStatus.CANCELLED,
                progress=100,
                status_detail="PDF parsing was cancelled before it started.",
                updated_at=cancelled_at,
                error_message=None,
            )
        cancelled = self._repository.cancel_pdf_upload_task(
            task_id=task.task_id,
            cancelled_at=cancelled_at,
            detail="PDF parsing was cancelled before it started.",
        ) or task
        if cancelled.batch_id:
            self.refresh_batch(cancelled.batch_id)
        return cancelled

    def retry_task(self, task_id: str, *, user_id: str) -> PdfUploadTask:
        task = self.get_task(task_id, user_id=user_id)
        if task.status not in {
            PdfUploadTaskStatus.FAILED,
            PdfUploadTaskStatus.CANCELLED,
        }:
            raise UploadValidationError(
                "only failed or cancelled PDF upload tasks can be retried"
            )
        if task.file_id is None:
            raise UploadValidationError("PDF upload task is missing a file reference")
        file = self._repository.get_pdf_file(task.file_id)
        if file is None or file.user_id != user_id or not file.storage_path:
            raise AssetNotFoundError("PDF source file was not found")
        content = self._upload_records.stored_file_path(file.storage_path).read_bytes()
        now = utc_now_iso()
        retry_task_id = new_id("pdfupload")
        staging_path = self._upload_records.write_staging_file(
            retry_task_id,
            file.original_filename,
            content,
        )
        retry_task = PdfUploadTask(
            task_id=retry_task_id,
            user_id=user_id,
            file_id=file.file_id,
            original_filename=file.original_filename,
            staging_path=self._upload_records.storage_reference(staging_path),
            status=PdfUploadTaskStatus.QUEUED,
            progress=5,
            detail="Queued for MinerU retry.",
            error_message=None,
            result={"operation": "retry", "previous_task_id": task.task_id},
            created_at=now,
            updated_at=now,
            stage=PdfUploadTaskStage.QUEUED,
            parser_backend=self._parser_profiles.selected_profile_id,
            retry_count=task.retry_count + 1,
            last_retry_at=now,
            batch_id=task.batch_id,
        )
        self._repository.update_pdf_file_processing(
            file_id=file.file_id,
            processing_status=PdfProcessingStatus.QUEUED,
            progress=5,
            status_detail="Queued for MinerU retry.",
            updated_at=now,
            error_message=None,
        )
        self._repository.create_pdf_upload_task(retry_task)
        if retry_task.batch_id:
            self.refresh_batch(retry_task.batch_id)
        return retry_task

    def cancel_batch(self, batch_id: str, *, user_id: str) -> PdfUploadBatch:
        batch = self.get_batch(batch_id, user_id=user_id)
        for task in self._repository.list_pdf_upload_tasks_by_batch(batch.batch_id):
            if task.status == PdfUploadTaskStatus.QUEUED:
                self.cancel_task(task.task_id, user_id=user_id)
        return self.refresh_batch(batch.batch_id)

    def retry_batch(
        self,
        batch_id: str,
        *,
        user_id: str,
    ) -> PdfUploadBatchCreationResult:
        batch = self.get_batch(batch_id, user_id=user_id)
        retry_tasks = [
            self.retry_task(task.task_id, user_id=user_id)
            for task in self._repository.list_pdf_upload_tasks_by_batch(batch.batch_id)
            if task.status
            in {PdfUploadTaskStatus.FAILED, PdfUploadTaskStatus.CANCELLED}
        ]
        if not retry_tasks:
            raise UploadValidationError(
                "upload batch has no failed or cancelled tasks to retry"
            )
        return PdfUploadBatchCreationResult(
            batch=self.refresh_batch(batch.batch_id),
            tasks=retry_tasks,
        )

    def refresh_batch(self, batch_id: str) -> PdfUploadBatch:
        batch = self._repository.get_pdf_upload_batch(batch_id)
        if batch is None:
            raise AssetNotFoundError("PDF upload batch was not found")
        tasks = self._repository.list_pdf_upload_tasks_by_batch(batch.batch_id)
        status, progress, detail, error_message, result = upload_batch_rollup(batch, tasks)
        now = utc_now_iso()
        return self._repository.update_pdf_upload_batch_status(
            batch_id=batch.batch_id,
            status=status,
            progress=progress,
            detail=detail,
            updated_at=now,
            completed_at=now if is_terminal_batch_status(status) else None,
            error_message=error_message,
            result=result,
        ) or batch

    def is_supported_filename(self, filename: str) -> bool:
        return self._upload_records.is_supported_filename(filename)
