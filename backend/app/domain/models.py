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
