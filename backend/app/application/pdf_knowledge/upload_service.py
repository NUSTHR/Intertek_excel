from dataclasses import dataclass

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
from app.core.errors import (
    ActiveUploadTaskConflictError,
    AssetNotFoundError,
    UploadValidationError,
)
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    PdfFileKind,
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
        parent_id: str | None = None,
    ) -> PdfUploadTask:
        now = utc_now_iso()
        target_parent_id = self._validate_target_parent(
            user_id=user_id,
            parent_id=parent_id,
        )
        record = self._upload_records.build_upload_records(
            user_id=user_id,
            original_filename=original_filename,
            content=content,
            relative_path=relative_path,
            parent_id=target_parent_id,
            created_at=now,
            batch_id=None,
            parser_backend=self._parser_profiles.selected_profile_id,
        )
        try:
            self._repository.create_pdf_upload(record)
        except Exception:
            self._upload_records.delete_upload_record(record)
            raise
        return record.task

    def create_batch(
        self,
        *,
        user_id: str,
        candidates: list[PdfUploadCandidate],
        source_name: str | None = None,
        parent_id: str | None = None,
    ) -> PdfUploadBatchCreationResult:
        if not candidates:
            raise UploadValidationError("no supported PDF knowledge files were found")
        now = utc_now_iso()
        target_parent_id = self._validate_target_parent(
            user_id=user_id,
            parent_id=parent_id,
        )
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
        records = []
        try:
            for candidate in accepted:
                records.append(
                    self._upload_records.build_upload_records(
                        user_id=user_id,
                        original_filename=candidate.original_filename,
                        content=candidate.content,
                        relative_path=candidate.relative_path or candidate.original_filename,
                        parent_id=target_parent_id,
                        created_at=now,
                        batch_id=batch_id,
                        parser_backend=self._parser_profiles.selected_profile_id,
                    )
                )
            self._repository.create_pdf_upload_batch_records(batch, records)
        except Exception:
            for record in records:
                self._upload_records.delete_upload_record(record)
            raise
        return PdfUploadBatchCreationResult(
            batch=batch,
            tasks=[record.task for record in records],
        )

    def _validate_target_parent(
        self,
        *,
        user_id: str,
        parent_id: str | None,
    ) -> str | None:
        normalized_parent_id = (parent_id or "").strip()
        if not normalized_parent_id:
            return None
        parent = self._repository.get_pdf_file(normalized_parent_id)
        if (
            parent is None
            or parent.user_id != user_id
            or parent.kind != PdfFileKind.FOLDER
        ):
            raise UploadValidationError("target PDF folder was not found")
        return parent.file_id

    def get_task(self, task_id: str, *, user_id: str) -> PdfUploadTask:
        task = self._repository.get_pdf_upload_task(task_id)
        if task is None or task.user_id != user_id:
            raise AssetNotFoundError("PDF upload task was not found")
        return task

    def list_tasks(self, *, user_id: str) -> list[PdfUploadTask]:
        return self._repository.list_pdf_upload_tasks(user_id)

    def list_batches(self, *, user_id: str) -> list[PdfUploadBatch]:
        return self._repository.list_pdf_upload_batches(user_id)

    def get_batch(self, batch_id: str, *, user_id: str) -> PdfUploadBatch:
        batch = self._repository.get_pdf_upload_batch(batch_id)
        if batch is None or batch.user_id != user_id:
            raise AssetNotFoundError("PDF upload batch was not found")
        return batch

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
        self._ensure_no_active_file_task(file.file_id)
        content = self._upload_records.stored_file_path(file.storage_path).read_bytes()
        now = utc_now_iso()
        task_id = new_id("pdfupload")
        staging_path = self._upload_records.write_staging_file(
            task_id,
            file.original_filename,
            content,
        )
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
        try:
            self._repository.queue_pdf_upload_task_for_existing_file(
                task,
                status_detail="Queued for MinerU reparse.",
                mark_summary_stale=True,
            )
        except Exception:
            self._upload_records.delete_staging_task(task.task_id)
            raise
        return task

    def cancel_task(self, task_id: str, *, user_id: str) -> PdfUploadTask:
        task = self.get_task(task_id, user_id=user_id)
        if task.status != PdfUploadTaskStatus.QUEUED:
            raise UploadValidationError("only queued PDF upload tasks can be cancelled")
        cancelled_at = utc_now_iso()
        cancelled = self._repository.cancel_pdf_upload_task(
            task_id=task.task_id,
            cancelled_at=cancelled_at,
            detail="PDF parsing was cancelled before it started.",
        )
        if cancelled is None:
            raise UploadValidationError("PDF upload task is no longer queued")
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
        self._ensure_no_active_file_task(file.file_id)
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
        try:
            self._repository.queue_pdf_upload_task_for_existing_file(
                retry_task,
                status_detail="Queued for MinerU retry.",
                mark_summary_stale=False,
            )
        except Exception:
            self._upload_records.delete_staging_task(retry_task.task_id)
            raise
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
        batch = self._repository.recompute_pdf_upload_batch(
            batch_id=batch_id,
            updated_at=utc_now_iso(),
        )
        if batch is None:
            raise AssetNotFoundError("PDF upload batch was not found")
        return batch

    def is_supported_filename(self, filename: str) -> bool:
        return self._upload_records.is_supported_filename(filename)

    def _ensure_no_active_file_task(self, file_id: str) -> None:
        active_task = self._repository.get_active_pdf_upload_task_for_file(file_id)
        if active_task is not None:
            raise ActiveUploadTaskConflictError(
                file_id=file_id,
                task_id=active_task.task_id,
            )
