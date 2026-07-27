from pydantic import BaseModel, Field


class RenamePdfFileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)


class SetPdfFileVisibilityRequest(BaseModel):
    visible_to_members: bool


class PdfFileResponse(BaseModel):
    file_id: str
    parent_id: str | None = None
    kind: str
    display_name: str
    original_filename: str
    size_bytes: int
    status: str
    processing_status: str
    progress: int
    status_detail: str
    error_message: str | None = None
    page_count: int | None = None
    chunk_count: int | None = None
    quality_status: str | None = None
    coverage_ratio: float | None = None
    warning_count: int | None = None
    failed_page_count: int | None = None
    parser_backend: str | None = None
    created_at: str
    updated_at: str
    visible_to_members: bool = True


class ListPdfFilesResponse(BaseModel):
    files: list[PdfFileResponse] = Field(default_factory=list)


class PdfParserStatusResponse(BaseModel):
    backend: str
    available: bool
    command: str | None = None
    version: str | None = None
    detail: str


class PdfParserProfileResponse(BaseModel):
    id: str
    label: str
    kind: str
    backend: str
    available: bool
    command: str | None = None
    version: str | None = None
    detail: str
    description: str
    is_default: bool
    is_selected: bool


class ListPdfParserProfilesResponse(BaseModel):
    selected_profile_id: str
    profiles: list[PdfParserProfileResponse] = Field(default_factory=list)


class UpdatePdfParserProfileRequest(BaseModel):
    selected_profile_id: str = Field(min_length=1, max_length=80)


class PdfUploadTaskResponse(BaseModel):
    task_id: str
    file_id: str | None = None
    batch_id: str | None = None
    original_filename: str
    status: str
    stage: str
    progress: int
    detail: str
    error_message: str | None = None
    error_code: str | None = None
    parser_backend: str = "unknown"
    retry_count: int = 0
    result: dict[str, object] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    last_retry_at: str | None = None


class PdfUploadBatchResponse(BaseModel):
    batch_id: str
    source_name: str
    status: str
    total_files: int
    accepted_files: int
    skipped_files: int
    total_bytes: int
    progress: int
    detail: str
    error_message: str | None = None
    parser_backend: str
    result: dict[str, object] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    completed_at: str | None = None


class CreatePdfUploadTasksResponse(BaseModel):
    batch: PdfUploadBatchResponse | None = None
    tasks: list[PdfUploadTaskResponse] = Field(default_factory=list)


class ListPdfUploadTasksResponse(BaseModel):
    tasks: list[PdfUploadTaskResponse] = Field(default_factory=list)


class ListPdfUploadBatchesResponse(BaseModel):
    batches: list[PdfUploadBatchResponse] = Field(default_factory=list)


class PdfUploadBatchDetailResponse(BaseModel):
    batch: PdfUploadBatchResponse
    tasks: list[PdfUploadTaskResponse] = Field(default_factory=list)


class PdfSummaryTaskResponse(BaseModel):
    task_id: str
    file_id: str
    status: str
    progress: int
    detail: str
    error_message: str | None = None
    retry_count: int = 0
    result: dict[str, object] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    last_retry_at: str | None = None


class CreatePdfSummaryTasksRequest(BaseModel):
    file_ids: list[str] = Field(default_factory=list)
    parent_id: str | None = None
    include_descendants: bool = True
    force: bool = False


class CreatePdfSummaryTasksResponse(BaseModel):
    tasks: list[PdfSummaryTaskResponse] = Field(default_factory=list)


class ListPdfSummaryTasksResponse(BaseModel):
    tasks: list[PdfSummaryTaskResponse] = Field(default_factory=list)


class PdfDocumentSummaryResponse(BaseModel):
    file_id: str
    status: str
    content: str
    updated_at: str | None = None
    error_message: str | None = None
    document_title: str = ""
    document_type: str = "pdf_document"
    business_domain: str = "pdf knowledge"
    key_topics: list[str] = Field(default_factory=list)
    positive_routing_terms: list[str] = Field(default_factory=list)
    negative_routing_terms: list[str] = Field(default_factory=list)
    exact_identifiers: list[str] = Field(default_factory=list)
    suitable_questions: list[str] = Field(default_factory=list)
    unsuitable_questions: list[str] = Field(default_factory=list)
    routing_notes: str = ""


class PdfPreviewBlockResponse(BaseModel):
    block_id: str
    page_label: str
    title: str
    content: str


class PdfSchemaItemResponse(BaseModel):
    item_id: str
    label: str
    value: str


class PdfParsePageResponse(BaseModel):
    page_id: str
    page_number: int
    page_label: str
    status: str
    text_block_count: int
    table_block_count: int
    image_block_count: int
    char_count: int
    warning_message: str | None = None
    error_message: str | None = None


class PdfParseArtifactResponse(BaseModel):
    artifact_id: str
    artifact_type: str
    name: str
    path: str | None = None
    size_bytes: int
    content_hash: str | None = None
    created_at: str


class PdfParseReportResponse(BaseModel):
    file_id: str
    parser_backend: str
    parser_version: str | None = None
    quality_status: str
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
    warnings: list[str] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str
    updated_at: str
    pages: list[PdfParsePageResponse] = Field(default_factory=list)
    artifacts: list[PdfParseArtifactResponse] = Field(default_factory=list)


class PdfDocumentDetailResponse(BaseModel):
    file_id: str
    summary: PdfDocumentSummaryResponse
    preview_blocks: list[PdfPreviewBlockResponse] = Field(default_factory=list)
    schema_items: list[PdfSchemaItemResponse] = Field(
        default_factory=list,
        alias="schema",
    )
    tags: list[str] = Field(default_factory=list)
    parse_report: PdfParseReportResponse | None = None


class PdfDocumentChunkResponse(BaseModel):
    chunk_id: str
    chunk_index: int
    text: str
    page_label: str | None = None
    title: str
    token_count: int
    content_hash: str
    metadata: dict[str, str] = Field(default_factory=dict)


class ListPdfDocumentChunksResponse(BaseModel):
    chunks: list[PdfDocumentChunkResponse] = Field(default_factory=list)


class SearchPdfChunksRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    file_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=12, ge=1, le=50)


class PdfChunkSearchMatchResponse(BaseModel):
    file: PdfFileResponse
    chunk: PdfDocumentChunkResponse
    score: float
    excerpt: str
    matched_terms: list[str] = Field(default_factory=list)


class SearchPdfChunksResponse(BaseModel):
    query: str
    matches: list[PdfChunkSearchMatchResponse] = Field(default_factory=list)
    total_matches: int
    limit: int


class PdfChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    file_ids: list[str] = Field(default_factory=list)
    retrieval_limit: int = Field(default=8, ge=1, le=20)
    enable_deep_thinking: bool = False


class PdfChatRouteRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    file_ids: list[str] = Field(default_factory=list)


class PdfChatAnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    selected_file_ids: list[str] = Field(default_factory=list)
    enable_deep_thinking: bool = False


class PdfSelectedDocumentResponse(BaseModel):
    file_id: str
    version_id: str
    reason: str
    confidence: float | None = None


class PdfAttachedDocumentResponse(BaseModel):
    file_id: str
    attached_at: str
    chunk_count: int
    context_hash: str
    status: str


class PdfChatRouteResponse(BaseModel):
    session_id: str
    question: str
    selected_documents: list[PdfSelectedDocumentResponse] = Field(default_factory=list)
    newly_attached_documents: list[PdfSelectedDocumentResponse] = Field(default_factory=list)
    attached_documents: list[PdfAttachedDocumentResponse] = Field(default_factory=list)
    created_at: str


class PdfChatAnswerBlockResponse(BaseModel):
    text: str
    citation_ids: list[str] = Field(default_factory=list)
    reasoning: str = ""


class PdfCitationResponse(BaseModel):
    citation_id: str
    evidence_id: str
    file_id: str
    file_name: str
    chunk_id: str
    chunk_index: int
    page_label: str | None = None
    title: str
    quote: str


class PdfChatAnswerResponse(BaseModel):
    session_id: str | None = None
    question: str
    answer_blocks: list[PdfChatAnswerBlockResponse] = Field(default_factory=list)
    citations: list[PdfCitationResponse] = Field(default_factory=list)
    retrieval_matches: list[PdfChunkSearchMatchResponse] = Field(default_factory=list)
    selected_documents: list[PdfSelectedDocumentResponse] = Field(default_factory=list)
    newly_attached_documents: list[PdfSelectedDocumentResponse] = Field(default_factory=list)
    attached_documents: list[PdfAttachedDocumentResponse] = Field(default_factory=list)
    insufficient_evidence: bool = False
    follow_up_suggestions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str


class PdfChatTurnResponse(BaseModel):
    turn_id: str
    session_id: str
    question: str
    answer: PdfChatAnswerResponse
    created_at: str


class PdfChatTurnListResponse(BaseModel):
    turns: list[PdfChatTurnResponse] = Field(default_factory=list)


class GeneratePdfSummaryResponse(BaseModel):
    summary: PdfDocumentSummaryResponse


class UpdatePdfModelSettingRequest(BaseModel):
    selected_provider: str = Field(min_length=1, max_length=80)
    selected_model: str = Field(min_length=1, max_length=160)


class PdfModelSettingResponse(BaseModel):
    id: str
    label: str
    providers: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    selected_provider: str
    selected_model: str


class ListPdfModelSettingsResponse(BaseModel):
    settings: list[PdfModelSettingResponse] = Field(default_factory=list)


class DeletePdfFileResponse(BaseModel):
    file_id: str
    display_name: str
    deleted_files: int
    deleted_chunks: int
    deleted_summaries: int
    deleted_preview_blocks: int
    deleted_schema_items: int
    deleted_parse_reports: int
    deleted_parse_pages: int
    deleted_parse_artifacts: int
