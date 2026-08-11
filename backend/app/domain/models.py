from dataclasses import dataclass, field
from enum import StrEnum


class ExcelVersionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    ARCHIVED = "archived"


class ExcelFileStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class ExcelFileVisibility(StrEnum):
    VISIBLE = "visible"
    HIDDEN = "hidden"


class ExcelArtifactType(StrEnum):
    ORIGINAL = "original"
    RAW_CSV = "raw_csv"
    PROFILE = "profile"
    ROW_MAPPING = "row_mapping"


class ExcelUploadTaskStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class PdfFileStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class PdfFileVisibility(StrEnum):
    VISIBLE = "visible"
    HIDDEN = "hidden"


class PdfFileKind(StrEnum):
    FOLDER = "folder"
    PDF = "pdf"
    CSV = "csv"
    XLSX = "xlsx"


class PdfProcessingStatus(StrEnum):
    UPLOADING = "uploading"
    QUEUED = "queued"
    PARSING = "parsing"
    INDEXING = "indexing"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PdfUploadTaskStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PdfSummaryTaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class PdfUploadTaskStage(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    PARSING = "parsing"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PdfUploadBatchStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChatWorkspace(StrEnum):
    EXCEL = "excel"
    PDF = "pdf"


class PdfParseQualityStatus(StrEnum):
    UNKNOWN = "unknown"
    GOOD = "good"
    WARNING = "warning"
    PARTIAL = "partial"
    FAILED = "failed"


class PdfParsePageStatus(StrEnum):
    PARSED = "parsed"
    EMPTY = "empty"
    IMAGE_ONLY = "image_only"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ExcelFile:
    file_id: str
    display_name: str
    active_version_id: str | None
    created_at: str
    updated_at: str
    status: ExcelFileStatus = ExcelFileStatus.ACTIVE
    deleted_at: str | None = None
    visibility: ExcelFileVisibility = ExcelFileVisibility.VISIBLE


@dataclass(frozen=True)
class ExcelFileVersion:
    version_id: str
    file_id: str
    original_filename: str
    file_hash: str
    status: ExcelVersionStatus
    error_message: str | None
    created_at: str
    activated_at: str | None


@dataclass(frozen=True)
class ExcelSheet:
    sheet_id: str
    version_id: str
    sheet_index: int
    sheet_code: str
    sheet_name: str
    row_count: int
    column_count: int
    raw_csv_path: str
    created_at: str


@dataclass(frozen=True)
class ExcelArtifact:
    artifact_id: str
    version_id: str
    artifact_type: ExcelArtifactType
    path: str
    created_at: str


@dataclass(frozen=True)
class ExcelRowMapping:
    mapping_id: str
    version_id: str
    sheet_id: str
    row_id: str
    original_row_number: int
    raw_csv_row_number: int
    created_at: str


@dataclass(frozen=True)
class ExcelRowSearchEntry:
    mapping_id: str
    version_id: str
    sheet_id: str
    row_id: str
    original_row_number: int
    raw_csv_row_number: int
    created_at: str
    row: list[str]


@dataclass(frozen=True)
class ExcelRowSearchMatch:
    mapping_id: str
    version_id: str
    sheet_id: str
    row_id: str
    original_row_number: int
    raw_csv_row_number: int
    created_at: str
    row: list[str]


@dataclass(frozen=True)
class ExcelUploadTask:
    task_id: str
    user_id: str
    original_filename: str
    staging_path: str
    replace_existing: bool
    status: ExcelUploadTaskStatus
    error_message: str | None
    result: dict[str, object]
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    worker_id: str | None = None


@dataclass(frozen=True)
class PdfFile:
    file_id: str
    user_id: str
    parent_id: str | None
    display_name: str
    original_filename: str
    kind: PdfFileKind
    size_bytes: int
    storage_path: str | None
    status: PdfFileStatus
    visibility: PdfFileVisibility
    processing_status: PdfProcessingStatus
    progress: int
    status_detail: str
    error_message: str | None
    page_count: int | None
    chunk_count: int | None
    created_at: str
    updated_at: str
    deleted_at: str | None = None
    quality_status: PdfParseQualityStatus | None = None
    coverage_ratio: float | None = None
    warning_count: int | None = None
    failed_page_count: int | None = None
    parser_backend: str | None = None
    content_fingerprint: str = ""


@dataclass(frozen=True)
class PdfUploadBatch:
    batch_id: str
    user_id: str
    source_name: str
    status: PdfUploadBatchStatus
    total_files: int
    accepted_files: int
    skipped_files: int
    total_bytes: int
    progress: int
    detail: str
    parser_backend: str
    created_at: str
    updated_at: str
    completed_at: str | None = None
    error_message: str | None = None
    result: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PdfUploadTask:
    task_id: str
    user_id: str
    file_id: str | None
    original_filename: str
    staging_path: str
    status: PdfUploadTaskStatus
    progress: int
    detail: str
    error_message: str | None
    result: dict[str, object]
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    worker_id: str | None = None
    stage: PdfUploadTaskStage = PdfUploadTaskStage.QUEUED
    parser_backend: str = "unknown"
    error_code: str | None = None
    retry_count: int = 0
    last_retry_at: str | None = None
    batch_id: str | None = None


@dataclass(frozen=True)
class PdfSummaryTask:
    task_id: str
    user_id: str
    file_id: str
    status: PdfSummaryTaskStatus
    progress: int
    detail: str
    error_message: str | None
    result: dict[str, object]
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    worker_id: str | None = None
    retry_count: int = 0
    last_retry_at: str | None = None
    source_fingerprint: str = ""
    state_revision: int = 0
    claim_token: str | None = None
    claimed_at: str | None = None
    attempt: int = 1
    parent_task_id: str | None = None


@dataclass(frozen=True)
class PdfDocumentSummary:
    file_id: str
    status: str
    content: str
    updated_at: str | None = None
    error_message: str | None = None
    document_title: str = ""
    document_type: str = "pdf_document"
    business_domain: str = "pdf knowledge"
    key_topics: list[str] = field(default_factory=list)
    positive_routing_terms: list[str] = field(default_factory=list)
    negative_routing_terms: list[str] = field(default_factory=list)
    exact_identifiers: list[str] = field(default_factory=list)
    suitable_questions: list[str] = field(default_factory=list)
    unsuitable_questions: list[str] = field(default_factory=list)
    routing_notes: str = ""
    source_fingerprint: str = ""
    source_updated_at: str | None = None
    provider: str = ""
    model: str = ""
    prompt_version: str = "pdf-summary-v1"
    generation_task_id: str | None = None
    generated_by_user_id: str | None = None
    revision: int = 0
    created_at: str | None = None


@dataclass(frozen=True)
class PdfFileCleanupJob:
    job_id: str
    file_id: str
    relative_path: str
    status: str
    attempt_count: int
    error_message: str | None
    created_at: str
    updated_at: str
    completed_at: str | None = None


@dataclass(frozen=True)
class PdfPreviewBlock:
    block_id: str
    file_id: str
    page_label: str
    title: str
    content: str
    block_index: int


@dataclass(frozen=True)
class PdfSchemaItem:
    item_id: str
    file_id: str
    label: str
    value: str
    item_index: int


@dataclass(frozen=True)
class PdfDocumentChunk:
    chunk_id: str
    file_id: str
    chunk_index: int
    text: str
    page_label: str | None
    title: str
    token_count: int
    content_hash: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PdfParsePage:
    page_id: str
    file_id: str
    page_number: int
    page_label: str
    status: PdfParsePageStatus
    text_block_count: int
    table_block_count: int
    image_block_count: int
    char_count: int
    warning_message: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class PdfParseArtifact:
    artifact_id: str
    file_id: str
    artifact_type: str
    name: str
    path: str | None
    size_bytes: int
    content_hash: str | None
    created_at: str


@dataclass(frozen=True)
class PdfParseReport:
    file_id: str
    parser_backend: str
    quality_status: PdfParseQualityStatus
    total_pages: int
    parsed_pages: int
    failed_pages: int
    empty_pages: int
    text_block_count: int
    table_block_count: int
    image_block_count: int
    chunk_count: int
    coverage_ratio: float
    warning_count: int
    error_count: int
    warnings: list[str]
    created_at: str
    updated_at: str
    parser_version: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    artifacts: list[PdfParseArtifact] = field(default_factory=list)
    pages: list[PdfParsePage] = field(default_factory=list)


@dataclass(frozen=True)
class PdfDocumentDetail:
    file_id: str
    summary: PdfDocumentSummary
    preview_blocks: list[PdfPreviewBlock]
    schema: list[PdfSchemaItem]
    tags: list[str]
    parse_report: PdfParseReport | None = None


@dataclass(frozen=True)
class PdfModelSetting:
    setting_id: str
    label: str
    providers: list[str]
    models: list[str]
    selected_provider: str
    selected_model: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SheetProfile:
    sheet_id: str
    sheet_code: str
    sheet_name: str
    row_count: int
    column_count: int
    sample_rows: list[list[str]]
    candidate_header: list[str]
    profile_rows: list[list[str]] = field(default_factory=list)


@dataclass(frozen=True)
class WorkbookProfile:
    file_id: str
    version_id: str
    original_filename: str
    file_hash: str
    sheets: list[SheetProfile]


@dataclass(frozen=True)
class SheetSummary:
    sheet_id: str
    sheet_name: str
    summary: str
    important_columns: list[str]
    likely_question_types: list[str]
    header_terms: list[str] = field(default_factory=list)
    sampled_identifiers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DocumentSummary:
    summary_id: str
    file_id: str
    version_id: str
    summary_text: str
    business_domain: str
    key_topics: list[str]
    suitable_questions: list[str]
    unsuitable_questions: list[str]
    sheet_summaries: list[SheetSummary]
    created_at: str
    document_title: str = ""
    document_type: str = "unknown"
    coverage_scope: dict[str, list[str]] = field(default_factory=dict)
    positive_routing_terms: list[str] = field(default_factory=list)
    negative_routing_terms: list[str] = field(default_factory=list)
    exact_identifiers: list[str] = field(default_factory=list)
    routing_notes: str = ""


@dataclass(frozen=True)
class ChatSession:
    session_id: str
    user_id: str
    created_at: str
    updated_at: str
    title: str = "New chat"
    pinned_at: str | None = None
    status: str = "active"
    workspace: ChatWorkspace = ChatWorkspace.EXCEL
    context_file_ids: list[str] = field(default_factory=list)
    revision: int = 0
    conversation_revision: int = 0


@dataclass(frozen=True)
class AttachedDocument:
    session_id: str
    file_id: str
    version_id: str
    attached_at: str
    row_count: int
    context_hash: str
    status: str = "attached"


@dataclass(frozen=True)
class SelectedDocument:
    file_id: str
    version_id: str
    reason: str
    confidence: float | None = None


@dataclass(frozen=True)
class PdfAttachedDocument:
    session_id: str
    file_id: str
    attached_at: str
    chunk_count: int
    context_hash: str
    status: str = "attached"


@dataclass(frozen=True)
class PdfChatRouteResult:
    session_id: str
    question: str
    selected_documents: list[SelectedDocument]
    newly_attached_documents: list[SelectedDocument]
    attached_documents: list[PdfAttachedDocument]
    created_at: str
    request_id: str | None = None
    context_file_ids: list[str] = field(default_factory=list)
    session_revision: int = 0


@dataclass(frozen=True)
class ChatTurn:
    turn_id: str
    session_id: str
    question: str
    answer_text: str
    citation_ids: list[str]
    selected_documents: list[SelectedDocument]
    created_at: str
    answer_blocks: list["ChatAnswerBlock"] = field(default_factory=list)
    newly_attached_documents: list[SelectedDocument] = field(default_factory=list)
    attached_documents: list[AttachedDocument] = field(default_factory=list)
    citations: list["ExcelCitation"] = field(default_factory=list)
    insufficient_evidence: bool = False
    follow_up_suggestions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    request_id: str | None = None


@dataclass(frozen=True)
class DraftAnswerBlock:
    text: str
    evidence_ids: list[str]
    reasoning: str = ""


@dataclass(frozen=True)
class DraftCitation:
    evidence_id: str = ""
    quote: str = ""
    version_id: str = ""
    sheet_id: str = ""
    row_id: str = ""


@dataclass(frozen=True)
class DraftChatAnswer:
    answer_blocks: list[DraftAnswerBlock]
    citations: list[DraftCitation]
    insufficient_evidence: bool
    follow_up_suggestions: list[str]


@dataclass(frozen=True)
class ExcelCitation:
    citation_id: str
    evidence_id: str
    file_id: str
    version_id: str
    sheet_id: str
    sheet_name: str
    row_id: str
    row: list[str]
    quote: str = ""


@dataclass(frozen=True)
class ChatAnswerBlock:
    text: str
    citation_ids: list[str]
    reasoning: str = ""


@dataclass(frozen=True)
class ChatAnswer:
    session_id: str
    question: str
    answer_blocks: list[ChatAnswerBlock]
    selected_documents: list[SelectedDocument]
    newly_attached_documents: list[SelectedDocument]
    attached_documents: list[AttachedDocument]
    citations: list[ExcelCitation]
    insufficient_evidence: bool
    follow_up_suggestions: list[str]
    warnings: list[str]
    created_at: str


@dataclass(frozen=True)
class ChatRouteResult:
    session_id: str
    question: str
    selected_documents: list[SelectedDocument]
    newly_attached_documents: list[SelectedDocument]
    attached_documents: list[AttachedDocument]
    created_at: str
    request_id: str | None = None
    session_revision: int = 0


@dataclass(frozen=True)
class LlmPreference:
    scope: str
    summary_provider: str
    summary_model: str
    router_provider: str
    router_model: str
    answer_provider: str
    answer_model: str
    created_at: str
    updated_at: str


class UserRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


@dataclass(frozen=True)
class UserAccount:
    user_id: str
    email: str
    password_hash: str
    role: UserRole
    is_active: bool
    created_at: str
    updated_at: str
    last_login_at: str | None = None


@dataclass(frozen=True)
class AuthSession:
    session_id: str
    user_id: str
    session_token_hash: str
    created_at: str
    expires_at: str
    revoked_at: str | None = None


@dataclass(frozen=True)
class PasswordResetToken:
    reset_token_id: str
    user_id: str
    token_hash: str
    created_at: str
    expires_at: str
    used_at: str | None = None


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    email: str
    role: UserRole
    created_at: str
    last_login_at: str | None = None
