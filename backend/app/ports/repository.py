from typing import Protocol

from app.domain.models import (
    AttachedDocument,
    AuthSession,
    ChatSession,
    ChatTurn,
    DocumentSummary,
    ExcelArtifact,
    ExcelFile,
    ExcelFilePurgeJob,
    ExcelFileVersion,
    ExcelFileVisibility,
    ExcelRowMapping,
    ExcelRowSearchEntry,
    ExcelRowSearchMatch,
    ExcelSheet,
    ExcelUploadTask,
    ExcelVersionStatus,
    LlmPreference,
    PasswordResetToken,
    PdfAttachedDocument,
    PdfDocumentChunk,
    PdfDocumentDetail,
    PdfDocumentSummary,
    PdfFile,
    PdfFileCleanupJob,
    PdfFileStatus,
    PdfFileVisibility,
    PdfModelSetting,
    PdfParseArtifact,
    PdfParsePage,
    PdfParseReport,
    PdfProcessingStatus,
    PdfSummaryTask,
    PdfUploadBatch,
    PdfUploadRecord,
    PdfUploadTask,
    PdfUploadTaskStage,
    PdfVectorIndex,
    PdfVectorIndexTask,
    UserAccount,
)


class ExcelAssetRepository(Protocol):
    def initialize(self) -> None:
        ...

    def create_file(self, file: ExcelFile) -> None:
        ...

    def get_file(self, file_id: str) -> ExcelFile | None:
        ...

    def get_file_including_deleted(self, file_id: str) -> ExcelFile | None:
        ...

    def find_file_by_display_name(self, display_name: str) -> ExcelFile | None:
        ...

    def list_files(self) -> list[ExcelFile]:
        ...

    def list_archived_files(self) -> list[ExcelFile]:
        ...

    def update_file_display_name(
        self,
        file_id: str,
        display_name: str,
        updated_at: str,
    ) -> ExcelFile | None:
        ...

    def update_file_visibility(
        self,
        file_id: str,
        visibility: ExcelFileVisibility,
        updated_at: str,
    ) -> ExcelFile | None:
        ...

    def archive_file(
        self,
        *,
        file_id: str,
        archived_at: str,
        purge_after: str,
    ) -> bool:
        ...

    def restore_archived_file(
        self,
        *,
        file_id: str,
        display_name: str,
        restored_at: str,
    ) -> ExcelFile | None:
        ...

    def request_excel_file_purge(
        self,
        *,
        file_id: str,
        requested_by: str,
        requested_at: str,
        allow_before_retention: bool,
    ) -> ExcelFilePurgeJob | None:
        ...

    def list_pending_excel_file_purge_jobs(
        self,
        *,
        available_at: str,
    ) -> list[ExcelFilePurgeJob]:
        ...

    def get_excel_file_purge_job(self, job_id: str) -> ExcelFilePurgeJob | None:
        ...

    def claim_excel_file_purge_job(
        self,
        *,
        job_id: str,
        worker_id: str,
        claim_token: str,
        claimed_at: str,
        lease_expires_at: str,
    ) -> ExcelFilePurgeJob | None:
        ...

    def complete_excel_file_purge_job(
        self,
        *,
        job_id: str,
        worker_id: str,
        claim_token: str,
        completed_at: str,
    ) -> ExcelFilePurgeJob | None:
        ...

    def fail_excel_file_purge_job(
        self,
        *,
        job_id: str,
        worker_id: str,
        claim_token: str,
        error_message: str,
        failed_at: str,
    ) -> ExcelFilePurgeJob | None:
        ...

    def create_version(self, version: ExcelFileVersion) -> None:
        ...

    def get_version(self, version_id: str) -> ExcelFileVersion | None:
        ...

    def list_versions(self, file_id: str) -> list[ExcelFileVersion]:
        ...

    def update_version_status(
        self,
        version_id: str,
        status: ExcelVersionStatus,
        error_message: str | None = None,
    ) -> None:
        ...

    def cleanup_failed_version_materialization(self, version_id: str) -> bool:
        ...

    def activate_version(self, file_id: str, version_id: str, activated_at: str) -> bool:
        ...

    def activate_version_for_upload_task(
        self,
        *,
        file_id: str,
        version_id: str,
        task_id: str,
        worker_id: str,
        claim_token: str,
        activated_at: str,
        task_result: dict[str, object],
    ) -> bool:
        ...

    def create_sheet(self, sheet: ExcelSheet) -> None:
        ...

    def get_sheet(self, sheet_id: str) -> ExcelSheet | None:
        ...

    def list_sheets(self, version_id: str) -> list[ExcelSheet]:
        ...

    def create_artifact(self, artifact: ExcelArtifact) -> None:
        ...

    def list_artifacts(self, version_id: str) -> list[ExcelArtifact]:
        ...

    def create_row_mappings(self, mappings: list[ExcelRowMapping]) -> None:
        ...

    def get_row_mapping(
        self,
        sheet_id: str,
        row_id: str,
    ) -> ExcelRowMapping | None:
        ...

    def list_row_mappings_for_sheet(self, sheet_id: str) -> list[ExcelRowMapping]:
        ...

    def list_row_mappings_for_sheet_page(
        self,
        sheet_id: str,
        offset: int,
        limit: int,
    ) -> list[ExcelRowMapping]:
        ...

    def replace_row_search_entries(
        self,
        version_id: str,
        entries: list[ExcelRowSearchEntry],
    ) -> None:
        ...

    def has_row_search_entries(self, version_id: str) -> bool:
        ...

    def search_row_index(
        self,
        *,
        version_id: str,
        query: str,
        sheet_id: str | None = None,
        limit: int | None = None,
    ) -> list[ExcelRowSearchMatch]:
        ...


class ExcelUploadTaskRepository(Protocol):
    def create_upload_task(self, task: ExcelUploadTask) -> None:
        ...

    def get_upload_task(self, task_id: str) -> ExcelUploadTask | None:
        ...

    def claim_next_upload_task(
        self,
        *,
        worker_id: str,
        started_at: str,
        lease_expires_at: str,
    ) -> ExcelUploadTask | None:
        ...

    def heartbeat_upload_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        heartbeat_at: str,
        lease_expires_at: str,
    ) -> bool:
        ...

    def is_upload_task_claim_active(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        checked_at: str,
    ) -> bool:
        ...

    def complete_upload_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        result: dict[str, object],
        finished_at: str,
    ) -> ExcelUploadTask | None:
        ...

    def fail_upload_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        error_message: str,
        finished_at: str,
    ) -> ExcelUploadTask | None:
        ...

    def fail_stale_processing_upload_tasks(
        self,
        *,
        cutoff_started_at: str,
        failed_at: str,
    ) -> int:
        ...


class ChatCancellationRepository(Protocol):
    def record_chat_cancellation(
        self,
        *,
        request_id: str,
        cancelled_at: str,
        expires_at: str,
    ) -> None:
        ...

    def is_chat_request_cancelled(self, request_id: str, *, now_iso: str) -> bool:
        ...


class DocumentSummaryRepository(Protocol):
    def initialize(self) -> None:
        ...

    def save_summary(self, summary: DocumentSummary) -> None:
        ...

    def get_summary(self, version_id: str) -> DocumentSummary | None:
        ...

    def list_summaries(self) -> list[DocumentSummary]:
        ...


class ChatSessionRepository(Protocol):
    def initialize(self) -> None:
        ...

    def create_session(self, session: ChatSession) -> None:
        ...

    def list_sessions(self, *, workspace: str = "excel") -> list[ChatSession]:
        ...

    def get_session(
        self,
        session_id: str,
        *,
        workspace: str = "excel",
    ) -> ChatSession | None:
        ...

    def touch_session(self, session_id: str, updated_at: str) -> None:
        ...

    def set_session_context_file_ids(
        self,
        session_id: str,
        file_ids: list[str],
        updated_at: str,
        *,
        workspace: str = "excel",
    ) -> ChatSession | None:
        ...

    def rename_session(
        self,
        session_id: str,
        title: str,
        updated_at: str,
        *,
        workspace: str = "excel",
        expected_revision: int | None = None,
    ) -> ChatSession | None:
        ...

    def set_session_pinned(
        self,
        session_id: str,
        pinned_at: str | None,
        updated_at: str,
        *,
        workspace: str = "excel",
        expected_revision: int | None = None,
    ) -> ChatSession | None:
        ...

    def delete_session(
        self,
        session_id: str,
        *,
        workspace: str = "excel",
        expected_revision: int | None = None,
    ) -> bool:
        ...

    def batch_set_sessions_pinned(
        self,
        session_revisions: dict[str, int],
        pinned_at: str | None,
        updated_at: str,
        *,
        workspace: str = "excel",
    ) -> list[ChatSession]:
        ...

    def batch_delete_sessions(
        self,
        session_revisions: dict[str, int],
        *,
        workspace: str = "excel",
    ) -> list[str]:
        ...

    def attach_document(self, document: AttachedDocument) -> bool:
        ...

    def detach_documents(self, session_id: str, version_ids: list[str]) -> None:
        ...

    def list_attached_documents(self, session_id: str) -> list[AttachedDocument]:
        ...

    def create_turn(self, turn: ChatTurn) -> None:
        ...

    def get_turn_by_request_id(
        self,
        session_id: str,
        request_id: str,
        *,
        workspace: str = "excel",
    ) -> ChatTurn | None:
        ...

    def claim_excel_chat_request(
        self,
        *,
        session_id: str,
        user_id: str,
        request_id: str,
        request_fingerprint: str,
        claimed_at: str,
        lease_expires_at: str,
    ) -> ChatTurn | None:
        ...

    def release_excel_chat_request(
        self,
        *,
        session_id: str,
        request_id: str,
        request_fingerprint: str,
    ) -> None:
        ...

    def commit_excel_chat_turn(
        self,
        *,
        session_id: str,
        user_id: str,
        expected_conversation_revision: int,
        attached_documents: list[AttachedDocument],
        turn: ChatTurn,
        request_fingerprint: str | None,
    ) -> ChatTurn:
        ...

    def delete_turn(self, session_id: str, turn_id: str) -> None:
        ...

    def list_turns(
        self,
        session_id: str,
        *,
        workspace: str = "excel",
    ) -> list[ChatTurn]:
        ...

    def get_session_with_turns(
        self,
        session_id: str,
        *,
        workspace: str = "excel",
        user_id: str | None = None,
    ) -> tuple[ChatSession, list[ChatTurn]] | None:
        ...


class PdfChatRepository(ChatSessionRepository, Protocol):
    def get_pdf_vector_index(self, file_id: str) -> PdfVectorIndex | None:
        ...

    def get_pdf_file(self, file_id: str) -> PdfFile | None:
        ...

    def list_pdf_files(self) -> list[PdfFile]:
        ...

    def list_pdf_files_by_ids(self, file_ids: list[str]) -> list[PdfFile]:
        ...

    def list_pdf_document_chunks(self, file_id: str) -> list[PdfDocumentChunk]:
        ...

    def get_pdf_document_chunk(
        self,
        file_id: str,
        chunk_id: str,
    ) -> PdfDocumentChunk | None:
        ...

    def list_pdf_document_chunks_by_file_ids(
        self,
        file_ids: list[str],
    ) -> dict[str, list[PdfDocumentChunk]]:
        ...

    def list_pdf_document_summaries(self) -> list[PdfDocumentSummary]:
        ...

    def list_pdf_model_settings(self) -> list[PdfModelSetting]:
        ...

    def attach_pdf_document(self, document: PdfAttachedDocument) -> bool:
        ...

    def detach_pdf_documents(self, session_id: str, file_ids: list[str]) -> None:
        ...

    def list_pdf_attached_documents(self, session_id: str) -> list[PdfAttachedDocument]:
        ...

    def claim_pdf_chat_request(
        self,
        *,
        session_id: str,
        user_id: str,
        request_id: str,
        request_fingerprint: str,
        claimed_at: str,
        lease_expires_at: str,
    ) -> ChatTurn | None:
        ...

    def release_pdf_chat_request(
        self,
        *,
        session_id: str,
        request_id: str,
        request_fingerprint: str,
    ) -> None:
        ...

    def commit_pdf_chat_turn(
        self,
        *,
        session_id: str,
        user_id: str,
        expected_conversation_revision: int,
        context_file_ids: list[str],
        attached_documents: list[PdfAttachedDocument],
        turn: ChatTurn,
        title_if_new: str | None,
        request_fingerprint: str | None,
    ) -> ChatTurn:
        ...


class AuthRepository(Protocol):
    def initialize(self) -> None:
        ...

    def create_user(self, user: UserAccount) -> None:
        ...

    def create_user_with_session_if_email_available(
        self,
        user: UserAccount,
        session: AuthSession,
    ) -> bool:
        """Atomically create a user and its initial session.

        Return ``False`` only when the normalized email already exists. Any
        other integrity or persistence failure must propagate so callers do not
        misreport infrastructure failures as an ordinary registration conflict.
        """
        ...

    def get_user(self, user_id: str) -> UserAccount | None:
        ...

    def get_user_by_email(self, email: str) -> UserAccount | None:
        ...

    def ensure_builtin_admin(self, user: UserAccount) -> UserAccount:
        ...

    def synchronize_builtin_admin(
        self,
        *,
        user_id: str,
        password_hash: str,
        updated_at: str,
    ) -> UserAccount | None:
        ...

    def update_user_password(
        self,
        user_id: str,
        password_hash: str,
        updated_at: str,
    ) -> UserAccount | None:
        ...

    def record_user_login(self, user_id: str, last_login_at: str) -> None:
        ...

    def create_auth_session(self, session: AuthSession) -> None:
        ...

    def get_auth_session_by_token_hash(
        self,
        token_hash: str,
    ) -> tuple[AuthSession, UserAccount] | None:
        ...

    def revoke_auth_session(self, token_hash: str, revoked_at: str) -> bool:
        ...

    def create_password_reset_token(self, token: PasswordResetToken) -> None:
        ...

    def consume_password_reset_token(
        self,
        *,
        token_hash: str,
        password_hash: str,
        used_at: str,
        protected_email: str,
    ) -> UserAccount | None:
        ...

    def get_login_rate_limit_retry_after(
        self,
        email: str,
        now: str,
    ) -> int | None:
        ...

    def record_login_rate_limit_failure(
        self,
        email: str,
        *,
        now: str,
        max_failed_attempts: int,
        window_seconds: int,
    ) -> int | None:
        ...

    def clear_login_rate_limit(self, email: str) -> None:
        ...


class LlmPreferenceRepository(Protocol):
    def get_llm_preference(self, scope: str) -> LlmPreference | None:
        ...

    def save_llm_preference(self, preference: LlmPreference) -> LlmPreference:
        ...


class PdfKnowledgeRepository(Protocol):
    def create_pdf_file(self, file: PdfFile) -> None:
        ...

    def create_pdf_upload(self, record: PdfUploadRecord) -> None:
        ...

    def get_pdf_file(self, file_id: str) -> PdfFile | None:
        ...

    def get_pdf_file_including_deleted(self, file_id: str) -> PdfFile | None:
        ...

    def find_pdf_file_by_parent_and_name(
        self,
        *,
        user_id: str,
        parent_id: str | None,
        display_name: str,
        status: PdfFileStatus = PdfFileStatus.ACTIVE,
    ) -> PdfFile | None:
        ...

    def get_pdf_folder_by_parent_and_name(
        self,
        *,
        user_id: str,
        parent_id: str | None,
        display_name: str,
    ) -> PdfFile | None:
        ...

    def get_or_create_pdf_folder(
        self,
        *,
        user_id: str,
        parent_id: str | None,
        display_name: str,
        created_at: str,
    ) -> PdfFile:
        ...

    def list_pdf_files(self) -> list[PdfFile]:
        ...

    def update_pdf_file_processing(
        self,
        *,
        file_id: str,
        processing_status: PdfProcessingStatus,
        progress: int,
        status_detail: str,
        updated_at: str,
        error_message: str | None = None,
        page_count: int | None = None,
        chunk_count: int | None = None,
        task_id: str | None = None,
        worker_id: str | None = None,
        claim_token: str | None = None,
    ) -> PdfFile | None:
        ...

    def update_pdf_file_visibility(
        self,
        file_id: str,
        visibility: PdfFileVisibility,
        updated_at: str,
    ) -> PdfFile | None:
        ...

    def rename_pdf_file_and_summary(
        self,
        file_id: str,
        display_name: str,
        updated_at: str,
    ) -> PdfFile | None:
        ...

    def delete_pdf_file_tree(self, file_id: str) -> dict[str, int]:
        ...

    def list_pending_pdf_file_cleanup_jobs(
        self,
        *,
        available_at: str,
    ) -> list[PdfFileCleanupJob]:
        ...

    def claim_pdf_file_cleanup_job(
        self,
        *,
        job_id: str,
        worker_id: str,
        claim_token: str,
        claimed_at: str,
        lease_expires_at: str,
    ) -> PdfFileCleanupJob | None:
        ...

    def ensure_pdf_file_cleanup_job(
        self,
        *,
        file_id: str,
        created_at: str,
    ) -> PdfFileCleanupJob | None:
        ...

    def complete_pdf_file_cleanup_job(
        self,
        *,
        job_id: str,
        worker_id: str,
        claim_token: str,
        completed_at: str,
    ) -> PdfFileCleanupJob | None:
        ...

    def fail_pdf_file_cleanup_job(
        self,
        *,
        job_id: str,
        worker_id: str,
        claim_token: str,
        error_message: str,
        failed_at: str,
    ) -> PdfFileCleanupJob | None:
        ...

    def create_pdf_upload_batch(self, batch: PdfUploadBatch) -> None:
        ...

    def create_pdf_upload_batch_records(
        self,
        batch: PdfUploadBatch,
        records: list[PdfUploadRecord],
    ) -> None:
        ...

    def get_pdf_upload_batch(self, batch_id: str) -> PdfUploadBatch | None:
        ...

    def list_pdf_upload_batches(self, user_id: str) -> list[PdfUploadBatch]:
        ...

    def recompute_pdf_upload_batch(
        self,
        *,
        batch_id: str,
        updated_at: str,
    ) -> PdfUploadBatch | None:
        ...

    def create_pdf_upload_task(self, task: PdfUploadTask) -> None:
        ...

    def queue_pdf_upload_task_for_existing_file(
        self,
        task: PdfUploadTask,
        *,
        status_detail: str,
        mark_summary_stale: bool,
    ) -> None:
        ...

    def get_pdf_upload_task(self, task_id: str) -> PdfUploadTask | None:
        ...

    def get_active_pdf_upload_task_for_file(self, file_id: str) -> PdfUploadTask | None:
        ...

    def list_pdf_upload_tasks(self, user_id: str) -> list[PdfUploadTask]:
        ...

    def list_pdf_upload_tasks_by_batch(self, batch_id: str) -> list[PdfUploadTask]:
        ...

    def claim_next_pdf_upload_task(
        self,
        *,
        worker_id: str,
        started_at: str,
        lease_expires_at: str,
    ) -> PdfUploadTask | None:
        ...

    def heartbeat_pdf_upload_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        heartbeat_at: str,
        lease_expires_at: str,
    ) -> bool:
        ...

    def is_pdf_upload_task_claim_active(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        checked_at: str,
    ) -> bool:
        ...

    def update_pdf_upload_task_progress(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        progress: int,
        detail: str,
        updated_at: str,
        stage: PdfUploadTaskStage | None = None,
    ) -> PdfUploadTask | None:
        ...

    def complete_pdf_upload_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        result: dict[str, object],
        detail: str,
        finished_at: str,
    ) -> PdfUploadTask | None:
        ...

    def publish_pdf_parse_result(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        detail: PdfDocumentDetail,
        chunks: list[PdfDocumentChunk],
        report: PdfParseReport,
        processing_status: PdfProcessingStatus,
        status_detail: str,
        error_message: str | None,
        result: dict[str, object],
        published_at: str,
        vector_index: PdfVectorIndex | None = None,
        vector_index_task: PdfVectorIndexTask | None = None,
    ) -> PdfUploadTask | None:
        ...

    def fail_pdf_parse_result(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        report: PdfParseReport | None,
        error_message: str,
        error_code: str | None,
        failed_at: str,
    ) -> PdfUploadTask | None:
        ...

    def fail_pdf_upload_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        error_message: str,
        failed_at: str,
        error_code: str | None = None,
    ) -> PdfUploadTask | None:
        ...

    def cancel_pdf_upload_task(
        self,
        *,
        task_id: str,
        cancelled_at: str,
        detail: str,
    ) -> PdfUploadTask | None:
        ...

    def list_stale_processing_pdf_upload_tasks(
        self,
        *,
        cutoff_started_at: str,
    ) -> list[PdfUploadTask]:
        ...

    def fail_stale_processing_pdf_upload_tasks(
        self,
        *,
        cutoff_started_at: str,
        failed_at: str,
    ) -> int:
        ...

    def create_pdf_summary_task(self, task: PdfSummaryTask) -> PdfSummaryTask:
        ...

    def get_pdf_summary_task(self, task_id: str) -> PdfSummaryTask | None:
        ...

    def find_active_pdf_summary_task(self, file_id: str) -> PdfSummaryTask | None:
        ...

    def list_pdf_summary_tasks(self, user_id: str) -> list[PdfSummaryTask]:
        ...

    def claim_next_pdf_summary_task(
        self,
        *,
        worker_id: str,
        started_at: str,
    ) -> PdfSummaryTask | None:
        ...

    def complete_pdf_summary_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        result: dict[str, object],
        detail: str,
        finished_at: str,
    ) -> PdfSummaryTask | None:
        ...

    def fail_pdf_summary_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        error_message: str,
        failed_at: str,
    ) -> PdfSummaryTask | None:
        ...

    def skip_pdf_summary_task(
        self,
        *,
        task_id: str,
        worker_id: str,
        claim_token: str,
        detail: str,
        result: dict[str, object],
        skipped_at: str,
    ) -> PdfSummaryTask | None:
        ...

    def cancel_pdf_summary_task(
        self,
        *,
        task_id: str,
        cancelled_at: str,
        detail: str,
    ) -> PdfSummaryTask | None:
        ...

    def retry_pdf_summary_task(
        self,
        *,
        task_id: str,
        retried_at: str,
    ) -> PdfSummaryTask | None:
        ...

    def fail_stale_running_pdf_summary_tasks(
        self,
        *,
        cutoff_started_at: str,
        failed_at: str,
    ) -> int:
        ...

    def save_pdf_document_detail(self, detail: PdfDocumentDetail) -> None:
        ...

    def get_pdf_document_detail(self, file_id: str) -> PdfDocumentDetail | None:
        ...

    def save_pdf_document_summary(self, summary: PdfDocumentSummary) -> bool:
        ...

    def list_pdf_document_summaries(self) -> list[PdfDocumentSummary]:
        ...

    def save_pdf_parse_report(self, report: PdfParseReport) -> None:
        ...

    def get_pdf_parse_report(self, file_id: str) -> PdfParseReport | None:
        ...

    def replace_pdf_parse_pages(
        self,
        file_id: str,
        pages: list[PdfParsePage],
    ) -> None:
        ...

    def list_pdf_parse_pages(self, file_id: str) -> list[PdfParsePage]:
        ...

    def replace_pdf_parse_artifacts(
        self,
        file_id: str,
        artifacts: list[PdfParseArtifact],
    ) -> None:
        ...

    def list_pdf_parse_artifacts(self, file_id: str) -> list[PdfParseArtifact]:
        ...

    def replace_pdf_document_chunks(
        self,
        file_id: str,
        chunks: list[PdfDocumentChunk],
    ) -> None:
        ...

    def list_pdf_document_chunks(self, file_id: str) -> list[PdfDocumentChunk]:
        ...

    def get_pdf_document_chunk(
        self,
        file_id: str,
        chunk_id: str,
    ) -> PdfDocumentChunk | None:
        ...

    def list_pdf_model_settings(self) -> list[PdfModelSetting]:
        ...

    def save_pdf_model_setting(self, setting: PdfModelSetting) -> PdfModelSetting:
        ...

    def attach_pdf_document(self, document: PdfAttachedDocument) -> bool:
        ...

    def detach_pdf_documents(self, session_id: str, file_ids: list[str]) -> None:
        ...

    def list_pdf_attached_documents(self, session_id: str) -> list[PdfAttachedDocument]:
        ...
