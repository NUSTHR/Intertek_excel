from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str


class CheckFileNameRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)


class CheckFileNameResponse(BaseModel):
    display_name: str
    exists: bool
    file_id: str | None = None
    active_version_id: str | None = None


class ExcelFileResponse(BaseModel):
    file_id: str
    display_name: str
    active_version_id: str | None = None
    created_at: str
    updated_at: str


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


class DocumentSummaryResponse(BaseModel):
    summary_id: str
    file_id: str
    version_id: str
    summary_text: str
    business_domain: str
    key_topics: list[str] = Field(default_factory=list)
    suitable_questions: list[str] = Field(default_factory=list)
    unsuitable_questions: list[str] = Field(default_factory=list)
    sheet_summaries: list[SheetSummaryResponse] = Field(default_factory=list)
    created_at: str


class UploadExcelResponse(BaseModel):
    file: ExcelFileResponse
    version: ExcelFileVersionResponse
    sheets: list[ExcelSheetResponse] = Field(default_factory=list)
    profile: WorkbookProfileResponse


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


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    router_model: str | None = None
    answer_model: str | None = None


class ChatAnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    answer_model: str | None = None
    selected_version_ids: list[str] = Field(default_factory=list)


class ChatRouteRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    router_model: str | None = None


class GenerateDocumentSummaryRequest(BaseModel):
    model: str | None = None


class ChatSessionResponse(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    status: str


class AttachedDocumentResponse(BaseModel):
    file_id: str
    version_id: str
    attached_at: str
    row_count: int
    context_hash: str
    status: str


class ChatStageTimingResponse(BaseModel):
    stage: str
    duration_seconds: float


class SelectedDocumentResponse(BaseModel):
    file_id: str
    version_id: str
    reason: str
    confidence: float | None = None


class ExcelCitationResponse(BaseModel):
    citation_id: str
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
    timings: list[ChatStageTimingResponse] = Field(default_factory=list)
    created_at: str


class ChatRouteResponse(BaseModel):
    session_id: str
    question: str
    selected_documents: list[SelectedDocumentResponse] = Field(default_factory=list)
    newly_attached_documents: list[SelectedDocumentResponse] = Field(default_factory=list)
    attached_documents: list[AttachedDocumentResponse] = Field(default_factory=list)
    timings: list[ChatStageTimingResponse] = Field(default_factory=list)
    created_at: str


class LlmModelDefaultsResponse(BaseModel):
    summary_model: str
    router_model: str
    answer_model: str


class LlmModelOptionsResponse(BaseModel):
    models: list[str] = Field(default_factory=list)
    defaults: LlmModelDefaultsResponse
