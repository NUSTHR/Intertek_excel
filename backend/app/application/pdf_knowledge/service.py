from pathlib import Path

from app.application.llm_preferences.service import WorkspaceLlmPreferenceService
from app.application.pdf_knowledge.indexing import PdfIndexingService
from app.application.pdf_knowledge.library_service import PdfLibraryService
from app.application.pdf_knowledge.models import DeletePdfFileResult
from app.application.pdf_knowledge.parser_profiles import PdfParserProfileRegistry
from app.application.pdf_knowledge.parsing_service import PdfParsingService
from app.application.pdf_knowledge.settings_service import PdfModelSettingsService
from app.application.pdf_knowledge.summary_service import PdfSummaryService
from app.application.pdf_knowledge.upload_service import (
    PdfUploadBatchCreationResult,
    PdfUploadService,
)
from app.application.pdf_knowledge.uploads import (
    PdfUploadCandidate,
    PdfUploadRecordBuilder,
)
from app.domain.models import (
    PdfDocumentChunk,
    PdfDocumentDetail,
    PdfDocumentSummary,
    PdfFile,
    PdfModelSetting,
    PdfSummaryTask,
    PdfUploadBatch,
    PdfUploadTask,
    UserRole,
)
from app.ports.llm_client import LlmClient
from app.ports.pdf_parser import (
    PdfParser,
    PdfParserProfile,
    PdfParserRuntimeStatus,
)
from app.ports.repository import PdfKnowledgeRepository


class PdfKnowledgeService:
    """Compatibility facade for PDF knowledge application use cases."""

    def __init__(
        self,
        *,
        repository: PdfKnowledgeRepository,
        storage_root: Path,
        parser: PdfParser,
        parser_status: PdfParserRuntimeStatus | None = None,
        parser_profiles: dict[str, PdfParser] | None = None,
        parser_profile_statuses: dict[str, PdfParserRuntimeStatus] | None = None,
        parser_profile_descriptors: list[PdfParserProfile] | None = None,
        default_parser_profile_id: str | None = None,
        indexing: PdfIndexingService | None = None,
        vector_embedding_revision: str | None = None,
        vector_embedding_dimension: int = 4096,
        pdf_chunk_max_characters: int = 12_000,
        llm_client: LlmClient | None = None,
        llm_preferences: WorkspaceLlmPreferenceService | None = None,
    ) -> None:
        resolved_storage_root = storage_root.expanduser().resolve()
        library = PdfLibraryService(
            repository=repository,
            storage_root=resolved_storage_root,
        )
        model_settings = PdfModelSettingsService(repository=repository)
        summaries = PdfSummaryService(
            repository=repository,
            library=library,
            model_settings=model_settings,
            llm_client=llm_client,
            llm_preferences=llm_preferences,
        )
        upload_records = PdfUploadRecordBuilder(
            storage_root=resolved_storage_root,
        )
        parser_registry = PdfParserProfileRegistry(
            parser=parser,
            parser_status=parser_status,
            parser_profiles=parser_profiles,
            parser_profile_statuses=parser_profile_statuses,
            parser_profile_descriptors=parser_profile_descriptors,
            default_parser_profile_id=default_parser_profile_id,
        )
        uploads = PdfUploadService(
            repository=repository,
            upload_records=upload_records,
            parser_profiles=parser_registry,
            library=library,
            summaries=summaries,
        )
        parsing = PdfParsingService(
            repository=repository,
            storage_root=resolved_storage_root,
            upload_records=upload_records,
            parser_profiles=parser_registry,
            indexing=indexing
            or PdfIndexingService(
                repository=repository,
                max_chunk_characters=pdf_chunk_max_characters,
            ),
            refresh_batch=uploads.refresh_batch,
            vector_embedding_revision=vector_embedding_revision,
            vector_embedding_dimension=vector_embedding_dimension,
        )

        self._library = library
        self._model_settings = model_settings
        self._summaries = summaries
        self._parser_profiles = parser_registry
        self._uploads = uploads
        self._parsing = parsing
        library.retry_pending_file_cleanups()

    def list_files(self, *, user_role: UserRole) -> list[PdfFile]:
        return self._library.list_files(user_role=user_role)

    def get_parser_status(self) -> PdfParserRuntimeStatus:
        return self._parser_profiles.selected_status()

    def list_parser_profiles(self) -> list[PdfParserProfile]:
        return self._parser_profiles.list_profiles()

    def select_parser_profile(self, profile_id: str) -> list[PdfParserProfile]:
        return self._parser_profiles.select(profile_id)

    def get_file(self, file_id: str, *, user_role: UserRole) -> PdfFile:
        return self._library.get_file(file_id, user_role=user_role)

    def rename_file(
        self,
        file_id: str,
        display_name: str,
        *,
        user_role: UserRole,
    ) -> PdfFile:
        return self._library.rename_file(
            file_id,
            display_name,
            user_role=user_role,
        )

    def set_file_visibility(
        self,
        file_id: str,
        visible_to_members: bool,
        *,
        user_role: UserRole,
    ) -> PdfFile:
        return self._library.set_file_visibility(
            file_id,
            visible_to_members,
            user_role=user_role,
        )

    def delete_file(
        self,
        file_id: str,
        *,
        confirm_delete: bool = False,
        user_role: UserRole,
    ) -> DeletePdfFileResult:
        return self._library.delete_file(
            file_id,
            confirm_delete=confirm_delete,
            user_role=user_role,
        )

    def create_upload_task(
        self,
        *,
        user_id: str,
        original_filename: str,
        content: bytes,
        relative_path: str | None = None,
        parent_id: str | None = None,
    ) -> PdfUploadTask:
        return self._uploads.create_task(
            user_id=user_id,
            original_filename=original_filename,
            content=content,
            relative_path=relative_path,
            parent_id=parent_id,
        )

    def create_upload_batch(
        self,
        *,
        user_id: str,
        candidates: list[PdfUploadCandidate],
        source_name: str | None = None,
        parent_id: str | None = None,
    ) -> PdfUploadBatchCreationResult:
        return self._uploads.create_batch(
            user_id=user_id,
            candidates=candidates,
            source_name=source_name,
            parent_id=parent_id,
        )

    def get_upload_task(self, task_id: str, *, user_id: str) -> PdfUploadTask:
        return self._uploads.get_task(task_id, user_id=user_id)

    def list_upload_tasks(self, *, user_id: str) -> list[PdfUploadTask]:
        return self._uploads.list_tasks(user_id=user_id)

    def create_summary_tasks(
        self,
        *,
        user_id: str,
        user_role: UserRole,
        file_ids: list[str] | None = None,
        parent_id: str | None = None,
        include_descendants: bool = True,
        force: bool = False,
    ) -> list[PdfSummaryTask]:
        return self._summaries.create_tasks(
            user_id=user_id,
            user_role=user_role,
            file_ids=file_ids,
            parent_id=parent_id,
            include_descendants=include_descendants,
            force=force,
        )

    def list_summary_tasks(self, *, user_id: str) -> list[PdfSummaryTask]:
        return self._summaries.list_tasks(user_id=user_id)

    def get_summary_task(self, task_id: str, *, user_id: str) -> PdfSummaryTask:
        return self._summaries.get_task(task_id, user_id=user_id)

    def cancel_summary_task(self, task_id: str, *, user_id: str) -> PdfSummaryTask:
        return self._summaries.cancel_task(task_id, user_id=user_id)

    def retry_summary_task(self, task_id: str, *, user_id: str) -> PdfSummaryTask:
        return self._summaries.retry_task(task_id, user_id=user_id)

    def process_summary_task(self, task: PdfSummaryTask) -> PdfSummaryTask:
        return self._summaries.process_task(task)

    def fail_summary_task(
        self,
        task: PdfSummaryTask,
        error_message: str,
    ) -> PdfSummaryTask:
        return self._summaries.fail_task(task, error_message)

    def fail_stale_running_summary_tasks(
        self,
        *,
        cutoff_started_at: str,
        failed_at: str,
    ) -> int:
        return self._summaries.fail_stale_running_tasks(
            cutoff_started_at=cutoff_started_at,
            failed_at=failed_at,
        )

    def list_upload_batches(self, *, user_id: str) -> list[PdfUploadBatch]:
        return self._uploads.list_batches(user_id=user_id)

    def get_upload_batch(self, batch_id: str, *, user_id: str) -> PdfUploadBatch:
        return self._uploads.get_batch(batch_id, user_id=user_id)

    def list_upload_batch_tasks(
        self,
        batch_id: str,
        *,
        user_id: str,
    ) -> list[PdfUploadTask]:
        return self._uploads.list_batch_tasks(batch_id, user_id=user_id)

    def create_reparse_task(
        self,
        *,
        file_id: str,
        user_id: str,
        user_role: UserRole,
    ) -> PdfUploadTask:
        return self._uploads.create_reparse_task(
            file_id=file_id,
            user_id=user_id,
            user_role=user_role,
        )

    def cancel_upload_task(self, task_id: str, *, user_id: str) -> PdfUploadTask:
        return self._uploads.cancel_task(task_id, user_id=user_id)

    def retry_upload_task(self, task_id: str, *, user_id: str) -> PdfUploadTask:
        return self._uploads.retry_task(task_id, user_id=user_id)

    def cancel_upload_batch(self, batch_id: str, *, user_id: str) -> PdfUploadBatch:
        return self._uploads.cancel_batch(batch_id, user_id=user_id)

    def retry_upload_batch(
        self,
        batch_id: str,
        *,
        user_id: str,
    ) -> PdfUploadBatchCreationResult:
        return self._uploads.retry_batch(batch_id, user_id=user_id)

    def parse_and_index_task(self, task: PdfUploadTask, content: bytes) -> PdfUploadTask:
        return self._parsing.process_task(task, content)

    def fail_task(
        self,
        task: PdfUploadTask,
        error_message: str,
        *,
        error_code: str | None = None,
        failed_at: str | None = None,
    ) -> PdfUploadTask:
        return self._parsing.fail_task(
            task,
            error_message,
            error_code=error_code,
            failed_at=failed_at,
        )

    def ensure_deleted_file_cleanup(self, file_id: str) -> bool:
        return self._library.ensure_deleted_file_cleanup(file_id)

    def fail_stale_processing_tasks(
        self,
        *,
        cutoff_started_at: str,
        failed_at: str,
    ) -> int:
        return self._parsing.fail_stale_tasks(
            cutoff_started_at=cutoff_started_at,
            failed_at=failed_at,
        )

    def get_document_detail(
        self,
        file_id: str,
        *,
        user_role: UserRole,
    ) -> PdfDocumentDetail:
        return self._library.get_document_detail(file_id, user_role=user_role)

    def list_document_chunks(
        self,
        file_id: str,
        *,
        user_role: UserRole,
    ) -> list[PdfDocumentChunk]:
        return self._library.list_document_chunks(file_id, user_role=user_role)

    def get_document_chunk(
        self,
        file_id: str,
        chunk_id: str,
        *,
        user_role: UserRole,
    ) -> PdfDocumentChunk:
        return self._library.get_document_chunk(
            file_id,
            chunk_id,
            user_role=user_role,
        )

    def generate_summary(
        self,
        file_id: str,
        *,
        user_role: UserRole,
    ) -> PdfDocumentSummary:
        return self._summaries.generate(file_id, user_role=user_role)

    def list_model_settings(self) -> list[PdfModelSetting]:
        return self._model_settings.list_settings()

    def update_model_setting(
        self,
        *,
        setting_id: str,
        selected_provider: str,
        selected_model: str,
    ) -> list[PdfModelSetting]:
        return self._model_settings.update_setting(
            setting_id=setting_id,
            selected_provider=selected_provider,
            selected_model=selected_model,
        )

    def is_supported_filename(self, filename: str) -> bool:
        return self._uploads.is_supported_filename(filename)
