from hashlib import sha256

from app.core.ids import new_id
from app.domain.models import PdfDocumentChunk, PdfDocumentDetail
from app.ports.pdf_parser import ParsedPdfChunk
from app.ports.repository import PdfKnowledgeRepository


class PdfIndexingService:
    def __init__(
        self,
        *,
        repository: PdfKnowledgeRepository,
        max_chunk_characters: int = 12_000,
    ) -> None:
        if max_chunk_characters < 1:
            raise ValueError("PDF chunk character limit must be positive")
        self._repository = repository
        self._max_chunk_characters = max_chunk_characters

    def index_document(
        self,
        *,
        file_id: str,
        parsed_chunks: list[ParsedPdfChunk],
        detail: PdfDocumentDetail,
    ) -> list[PdfDocumentChunk]:
        chunks = self.build_document_chunks(
            file_id=file_id,
            parsed_chunks=parsed_chunks,
            detail=detail,
        )
        self._repository.replace_pdf_document_chunks(file_id, chunks)
        return chunks

    def build_document_chunks(
        self,
        *,
        file_id: str,
        parsed_chunks: list[ParsedPdfChunk],
        detail: PdfDocumentDetail,
    ) -> list[PdfDocumentChunk]:
        chunks = _chunks_from_parsed_chunks(
            file_id,
            parsed_chunks,
            max_chunk_characters=self._max_chunk_characters,
        )
        if not chunks:
            chunks = _chunks_from_preview_blocks(
                detail,
                max_chunk_characters=self._max_chunk_characters,
            )
        return chunks


def _chunks_from_parsed_chunks(
    file_id: str,
    parsed_chunks: list[ParsedPdfChunk],
    *,
    max_chunk_characters: int,
) -> list[PdfDocumentChunk]:
    chunks: list[PdfDocumentChunk] = []
    for chunk in parsed_chunks:
        text = _normalize_text(chunk.text)
        if not text:
            continue
        segments = _split_text(text, max_characters=max_chunk_characters)
        for segment_index, segment in enumerate(segments):
            chunks.append(
                _build_chunk(
                    file_id=file_id,
                    chunk_index=len(chunks),
                    text=segment,
                    page_label=chunk.page_label,
                    title=chunk.title,
                    metadata={
                        **chunk.metadata,
                        "segment_index": str(segment_index),
                        "segment_count": str(len(segments)),
                    },
                )
            )
    return chunks


def _chunks_from_preview_blocks(
    detail: PdfDocumentDetail,
    *,
    max_chunk_characters: int,
) -> list[PdfDocumentChunk]:
    chunks: list[PdfDocumentChunk] = []
    for block in detail.preview_blocks:
        text = _normalize_text(block.content)
        if not text:
            continue
        segments = _split_text(text, max_characters=max_chunk_characters)
        for segment_index, segment in enumerate(segments):
            chunks.append(
                _build_chunk(
                    file_id=detail.file_id,
                    chunk_index=len(chunks),
                    text=segment,
                    page_label=block.page_label,
                    title=block.title,
                    metadata={
                        "source": "preview_block",
                        "segment_index": str(segment_index),
                        "segment_count": str(len(segments)),
                    },
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


def _split_text(text: str, *, max_characters: int) -> list[str]:
    if len(text) <= max_characters:
        return [text]
    segments: list[str] = []
    remaining = text
    preferred_boundaries = ("\n", "。", "！", "？", ". ", "! ", "? ", "; ", " ")
    while len(remaining) > max_characters:
        minimum_boundary = max_characters // 2
        boundary = -1
        boundary_width = 0
        window = remaining[: max_characters + 1]
        for marker in preferred_boundaries:
            candidate = window.rfind(marker, minimum_boundary)
            if candidate > boundary:
                boundary = candidate
                boundary_width = len(marker)
        split_at = boundary + boundary_width if boundary >= minimum_boundary else max_characters
        segment = remaining[:split_at].strip()
        if not segment:
            split_at = max_characters
            segment = remaining[:split_at]
        segments.append(segment)
        remaining = remaining[split_at:].strip()
    if remaining:
        segments.append(remaining)
    return segments


def _estimate_token_count(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)
