from hashlib import sha256

from app.core.ids import new_id
from app.domain.models import PdfDocumentChunk, PdfDocumentDetail
from app.ports.pdf_parser import ParsedPdfChunk
from app.ports.repository import PdfKnowledgeRepository


class PdfIndexingService:
    def __init__(self, *, repository: PdfKnowledgeRepository) -> None:
        self._repository = repository

    def index_document(
        self,
        *,
        file_id: str,
        parsed_chunks: list[ParsedPdfChunk],
        detail: PdfDocumentDetail,
    ) -> list[PdfDocumentChunk]:
        chunks = _chunks_from_parsed_chunks(file_id, parsed_chunks)
        if not chunks:
            chunks = _chunks_from_preview_blocks(detail)
        self._repository.replace_pdf_document_chunks(file_id, chunks)
        return chunks


def _chunks_from_parsed_chunks(
    file_id: str,
    parsed_chunks: list[ParsedPdfChunk],
) -> list[PdfDocumentChunk]:
    chunks: list[PdfDocumentChunk] = []
    for chunk in parsed_chunks:
        text = _normalize_text(chunk.text)
        if not text:
            continue
        chunks.append(
            _build_chunk(
                file_id=file_id,
                chunk_index=len(chunks),
                text=text,
                page_label=chunk.page_label,
                title=chunk.title,
                metadata=chunk.metadata,
            )
        )
    return chunks


def _chunks_from_preview_blocks(detail: PdfDocumentDetail) -> list[PdfDocumentChunk]:
    chunks: list[PdfDocumentChunk] = []
    for block in detail.preview_blocks:
        text = _normalize_text(block.content)
        if not text:
            continue
        chunks.append(
            _build_chunk(
                file_id=detail.file_id,
                chunk_index=len(chunks),
                text=text,
                page_label=block.page_label,
                title=block.title,
                metadata={"source": "preview_block"},
            )
        )
    if chunks:
        return chunks
    return [
        _build_chunk(
            file_id=detail.file_id,
            chunk_index=0,
            text="No parseable text was produced for this PDF.",
            page_label=None,
            title="Empty Parse Result",
            metadata={"source": "fallback"},
        )
    ]


def _build_chunk(
    *,
    file_id: str,
    chunk_index: int,
    text: str,
    page_label: str | None,
    title: str,
    metadata: dict[str, str],
) -> PdfDocumentChunk:
    return PdfDocumentChunk(
        chunk_id=new_id("pdfchunk"),
        file_id=file_id,
        chunk_index=chunk_index,
        text=text,
        page_label=page_label,
        title=title.strip() or f"Chunk {chunk_index + 1}",
        token_count=_estimate_token_count(text),
        content_hash=sha256(text.encode("utf-8")).hexdigest(),
        metadata={
            str(key): str(value)
            for key, value in metadata.items()
            if str(key).strip()
        },
    )


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _estimate_token_count(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)
