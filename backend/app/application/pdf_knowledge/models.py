from dataclasses import dataclass

from app.domain.models import PdfAttachedDocument, PdfDocumentChunk, PdfFile, SelectedDocument


@dataclass(frozen=True)
class PdfChunkSearchMatch:
    file: PdfFile
    chunk: PdfDocumentChunk
    score: float
    excerpt: str
    matched_terms: list[str]


@dataclass(frozen=True)
class PdfChunkSearchResult:
    query: str
    matches: list[PdfChunkSearchMatch]
    total_matches: int
    limit: int


@dataclass(frozen=True)
class PdfCitation:
    citation_id: str
    evidence_id: str
    file_id: str
    file_name: str
    chunk_id: str
    chunk_index: int
    page_label: str | None
    title: str
    quote: str


@dataclass(frozen=True)
class PdfAnswerBlock:
    text: str
    citation_ids: list[str]
    reasoning: str = ""


@dataclass(frozen=True)
class PdfChatAnswer:
    session_id: str | None
    question: str
    answer_blocks: list[PdfAnswerBlock]
    citations: list[PdfCitation]
    retrieval_matches: list[PdfChunkSearchMatch]
    selected_documents: list[SelectedDocument]
    newly_attached_documents: list[SelectedDocument]
    attached_documents: list[PdfAttachedDocument]
    insufficient_evidence: bool
    follow_up_suggestions: list[str]
    warnings: list[str]
    created_at: str


@dataclass(frozen=True)
class DeletePdfFileResult:
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
