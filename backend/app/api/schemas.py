from pydantic import BaseModel, Field

from app.api.schema_models.common import (  # noqa: F401
    ChatSessionListResponse,
    ChatSessionResponse,
    PinChatSessionRequest,
    RenameChatSessionRequest,
)
from app.api.schema_models.pdf import (  # noqa: F401
    CreatePdfSummaryTasksRequest,
    CreatePdfSummaryTasksResponse,
    CreatePdfUploadTasksResponse,
    DeletePdfFileResponse,
    GeneratePdfSummaryResponse,
    ListPdfDocumentChunksResponse,
    ListPdfFilesResponse,
    ListPdfModelSettingsResponse,
    ListPdfParserProfilesResponse,
    ListPdfSummaryTasksResponse,
    ListPdfUploadBatchesResponse,
    ListPdfUploadTasksResponse,
    PdfAttachedDocumentResponse,
    PdfChatAnswerBlockResponse,
    PdfChatAnswerRequest,
    PdfChatAnswerResponse,
    PdfChatRequest,
    PdfChatRouteRequest,
    PdfChatRouteResponse,
    PdfChatTurnListResponse,
    PdfChatTurnResponse,
    PdfChunkSearchMatchResponse,
    PdfCitationResponse,
    PdfDocumentChunkResponse,
    PdfDocumentDetailResponse,
    PdfDocumentSummaryResponse,
    PdfFileResponse,
    PdfModelSettingResponse,
    PdfParseArtifactResponse,
    PdfParsePageResponse,
    PdfParseReportResponse,
    PdfParserProfileResponse,
    PdfParserStatusResponse,
    PdfPreviewBlockResponse,
    PdfSchemaItemResponse,
    PdfSelectedDocumentResponse,
    PdfSummaryTaskResponse,
    PdfUploadBatchDetailResponse,
    PdfUploadBatchResponse,
    PdfUploadTaskResponse,
    RenamePdfFileRequest,
    SearchPdfChunksRequest,
    SearchPdfChunksResponse,
    SetPdfFileVisibilityRequest,
    UpdatePdfModelSettingRequest,
    UpdatePdfParserProfileRequest,
)


class ErrorResponse(BaseModel):
    detail: str


class UserResponse(BaseModel):
    user_id: str
    email: str
    role: str
    created_at: str
    last_login_at: str | None = None


class AuthResponse(BaseModel):
    user: UserResponse
    access_token: str
    token_type: str = "bearer"
    expires_at: str


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=255)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)


class PasswordResetResponse(BaseModel):
    email: str
    reset_token: str | None = None
    expires_at: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=12, max_length=255)
    new_password: str = Field(min_length=8, max_length=255)


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str] = Field(default_factory=dict)


class WorkspaceUploadConfigResponse(BaseModel):
    max_bytes: int
    supported_extensions: list[str] = Field(default_factory=list)


class WorkspaceConfigResponse(BaseModel):
    upload: WorkspaceUploadConfigResponse


class CheckFileNameRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)


class CheckFileNameResponse(BaseModel):
    display_name: str
    exists: bool
    file_id: str | None = None
    active_version_id: str | None = None


class RenameExcelFileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)


class SetExcelFileVisibilityRequest(BaseModel):
    visible_to_members: bool


class ExcelFileResponse(BaseModel):
    file_id: str
    display_name: str
    active_version_id: str | None = None
    created_at: str
    updated_at: str
    visible_to_members: bool = True


class ExcelFileVersionResponse(BaseModel):
    version_id: str
    file_id: str
    original_filename: str
    file_hash: str
    status: str
    error_message: str | None = None
    created_at: str
    activated_at: str | None = None


class ExcelSheetResponse(BaseModel):
    sheet_id: str
    version_id: str
    sheet_index: int
    sheet_code: str
    sheet_name: str
    row_count: int
    column_count: int
    created_at: str


class ExcelArtifactResponse(BaseModel):
    artifact_id: str
    version_id: str
    artifact_type: str
    path: str
    created_at: str


class SheetProfileResponse(BaseModel):
    sheet_id: str
    sheet_code: str
    sheet_name: str
    row_count: int
    column_count: int
    candidate_header: list[str] = Field(default_factory=list)
    sample_rows: list[list[str]] = Field(default_factory=list)


class WorkbookProfileResponse(BaseModel):
    file_id: str
    version_id: str
    original_filename: str
    file_hash: str
    sheets: list[SheetProfileResponse] = Field(default_factory=list)


class SheetSummaryResponse(BaseModel):
    sheet_id: str
    sheet_name: str
    summary: str
    important_columns: list[str] = Field(default_factory=list)
    likely_question_types: list[str] = Field(default_factory=list)
    header_terms: list[str] = Field(default_factory=list)
    sampled_identifiers: list[str] = Field(default_factory=list)


class SheetSummaryUpdateRequest(BaseModel):
    sheet_id: str = Field(min_length=1, max_length=120)
    sheet_name: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=6000)
    important_columns: list[str] = Field(default_factory=list)
    likely_question_types: list[str] = Field(default_factory=list)
    header_terms: list[str] = Field(default_factory=list)
    sampled_identifiers: list[str] = Field(default_factory=list)


class DocumentSummaryResponse(BaseModel):
    summary_id: str
    file_id: str
    version_id: str
    document_title: str = ""
    document_type: str = "unknown"
    summary_text: str
    business_domain: str
    coverage_scope: dict[str, list[str]] = Field(default_factory=dict)
    key_topics: list[str] = Field(default_factory=list)
    positive_routing_terms: list[str] = Field(default_factory=list)
    negative_routing_terms: list[str] = Field(default_factory=list)
    exact_identifiers: list[str] = Field(default_factory=list)
    suitable_questions: list[str] = Field(default_factory=list)
    unsuitable_questions: list[str] = Field(default_factory=list)
    sheet_summaries: list[SheetSummaryResponse] = Field(default_factory=list)
    routing_notes: str = ""
    created_at: str


class UpdateDocumentSummaryRequest(BaseModel):
    document_title: str | None = Field(default=None, min_length=1, max_length=255)
    summary_text: str | None = Field(default=None, min_length=1, max_length=20000)
    business_domain: str | None = Field(default=None, min_length=1, max_length=255)
    key_topics: list[str] | None = None
    positive_routing_terms: list[str] | None = None
    negative_routing_terms: list[str] | None = None
    exact_identifiers: list[str] | None = None
    suitable_questions: list[str] | None = None
    unsuitable_questions: list[str] | None = None
    sheet_summaries: list[SheetSummaryUpdateRequest] | None = None
    routing_notes: str | None = Field(default=None, max_length=6000)


class UploadExcelResponse(BaseModel):
    file: ExcelFileResponse
    version: ExcelFileVersionResponse
    sheets: list[ExcelSheetResponse] = Field(default_factory=list)
    profile: WorkbookProfileResponse


class CreateUploadTaskResponse(BaseModel):
    task_id: str
    status: str
    created_at: str
    updated_at: str


class UploadTaskResponse(BaseModel):
    task_id: str
    status: str
    original_filename: str
    replace_existing: bool
    error_message: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    result: UploadExcelResponse | None = None


class ListExcelFilesResponse(BaseModel):
    files: list[ExcelFileResponse] = Field(default_factory=list)


class ListExcelVersionsResponse(BaseModel):
    versions: list[ExcelFileVersionResponse] = Field(default_factory=list)


class ListExcelSheetsResponse(BaseModel):
    sheets: list[ExcelSheetResponse] = Field(default_factory=list)


class ListExcelArtifactsResponse(BaseModel):
    artifacts: list[ExcelArtifactResponse] = Field(default_factory=list)


class ActiveExcelFileResponse(BaseModel):
    file: ExcelFileResponse
    version: ExcelFileVersionResponse


class DeleteExcelFileResponse(BaseModel):
    file_id: str
    display_name: str
    deleted_versions: int
    deleted_sheets: int
    deleted_artifacts: int
    deleted_row_mappings: int
    deleted_summaries: int
    deleted_chat_session_documents: int


class SheetPreviewResponse(BaseModel):
    sheet: ExcelSheetResponse
    rows: list[list[str]]
    total_rows: int
    offset: int
    limit: int


class RowMappingResponse(BaseModel):
    row_id: str
    version_id: str
    sheet_id: str
    original_row_number: int
    raw_csv_row_number: int


class RowLookupResponse(BaseModel):
    sheet: ExcelSheetResponse
    mapping: RowMappingResponse
    row: list[str]


class SheetRowResponse(BaseModel):
    mapping: RowMappingResponse
    row: list[str]


class SheetRowsResponse(BaseModel):
    sheet: ExcelSheetResponse
    rows: list[SheetRowResponse]
    total_rows: int
    offset: int
    limit: int


class SheetSearchMatchResponse(BaseModel):
    sheet: ExcelSheetResponse
    mapping: RowMappingResponse
    row: list[str]
    matched_columns: list[int]


class SheetSearchResponse(BaseModel):
    sheet: ExcelSheetResponse
    query: str
    matches: list[SheetSearchMatchResponse]
    total_matches: int
    limit: int


class WorkbookSearchResponse(BaseModel):
    version_id: str
    query: str
    matches: list[SheetSearchMatchResponse]
    total_matches: int
    limit: int


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    enable_deep_thinking: bool = False
    request_id: str | None = Field(default=None, min_length=8, max_length=120)


class ChatAnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    selected_version_ids: list[str] = Field(default_factory=list)
    enable_deep_thinking: bool = False
    request_id: str | None = Field(default=None, min_length=8, max_length=120)


class ChatRouteRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class CancelChatRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=120)


class CancelChatResponse(BaseModel):
    request_id: str
    cancelled: bool


class AttachedDocumentResponse(BaseModel):
    file_id: str
    version_id: str
    attached_at: str
    row_count: int
    context_hash: str
    status: str


class SelectedDocumentResponse(BaseModel):
    file_id: str
    version_id: str
    reason: str
    confidence: float | None = None


class ExcelCitationResponse(BaseModel):
    citation_id: str
    evidence_id: str
    file_id: str
    version_id: str
    sheet_id: str
    sheet_name: str
    row_id: str
    row: list[str]
    quote: str = ""


class ChatAnswerBlockResponse(BaseModel):
    text: str
    citation_ids: list[str] = Field(default_factory=list)
    reasoning: str = ""


class ChatAnswerResponse(BaseModel):
    session_id: str
    question: str
    answer_blocks: list[ChatAnswerBlockResponse] = Field(default_factory=list)
    selected_documents: list[SelectedDocumentResponse] = Field(default_factory=list)
    newly_attached_documents: list[SelectedDocumentResponse] = Field(default_factory=list)
    attached_documents: list[AttachedDocumentResponse] = Field(default_factory=list)
    citations: list[ExcelCitationResponse] = Field(default_factory=list)
    insufficient_evidence: bool = False
    follow_up_suggestions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str


class ChatTurnResponse(BaseModel):
    turn_id: str
    session_id: str
    question: str
    answer: ChatAnswerResponse
    created_at: str


class ChatTurnListResponse(BaseModel):
    turns: list[ChatTurnResponse] = Field(default_factory=list)


class ChatRouteResponse(BaseModel):
    session_id: str
    question: str
    selected_documents: list[SelectedDocumentResponse] = Field(default_factory=list)
    newly_attached_documents: list[SelectedDocumentResponse] = Field(default_factory=list)
    attached_documents: list[AttachedDocumentResponse] = Field(default_factory=list)
    created_at: str


class LlmModelDefaultsResponse(BaseModel):
    summary_provider: str
    summary_model: str
    router_provider: str
    router_model: str
    answer_provider: str
    answer_model: str


class LlmProviderOptionResponse(BaseModel):
    provider: str
    label: str
    models: list[str] = Field(default_factory=list)
    deep_thinking_models: list[str] = Field(default_factory=list)


class LlmModelOptionsResponse(BaseModel):
    models: list[str] = Field(default_factory=list)
    providers: list[LlmProviderOptionResponse] = Field(default_factory=list)
    defaults: LlmModelDefaultsResponse


class LlmPreferenceRequest(BaseModel):
    summary_provider: str = Field(min_length=1, max_length=80)
    summary_model: str = Field(min_length=1, max_length=160)
    router_provider: str = Field(min_length=1, max_length=80)
    router_model: str = Field(min_length=1, max_length=160)
    answer_provider: str = Field(min_length=1, max_length=80)
    answer_model: str = Field(min_length=1, max_length=160)


class LlmPreferenceResponse(LlmPreferenceRequest):
    scope: str
    created_at: str
    updated_at: str
