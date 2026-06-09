from dataclasses import dataclass, field
from enum import StrEnum


class ExcelVersionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    ARCHIVED = "archived"


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
class ChatStageTiming:
    stage: str
    duration_seconds: float


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


@dataclass(frozen=True)
class DraftAnswerBlock:
    text: str
    evidence_row_ids: list[str]


@dataclass(frozen=True)
class DraftCitation:
    row_id: str
    quote: str


@dataclass(frozen=True)
class DraftChatAnswer:
    answer_blocks: list[DraftAnswerBlock]
    citations: list[DraftCitation]
    insufficient_evidence: bool
    follow_up_suggestions: list[str]


@dataclass(frozen=True)
class ExcelCitation:
    citation_id: str
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
    timings: list[ChatStageTiming]
    created_at: str


@dataclass(frozen=True)
class ChatRouteResult:
    session_id: str
    question: str
    selected_documents: list[SelectedDocument]
    newly_attached_documents: list[SelectedDocument]
    attached_documents: list[AttachedDocument]
    timings: list[ChatStageTiming]
    created_at: str
