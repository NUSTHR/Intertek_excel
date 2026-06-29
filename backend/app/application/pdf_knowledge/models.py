from dataclasses import dataclass

from app.domain.models import PdfDocumentChunk, PdfFile


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
    question: str
    answer_blocks: list[PdfAnswerBlock]
    citations: list[PdfCitation]
    retrieval_matches: list[PdfChunkSearchMatch]
    insufficient_evidence: bool
    follow_up_suggestions: list[str]
    warnings: list[str]
    created_at: str
