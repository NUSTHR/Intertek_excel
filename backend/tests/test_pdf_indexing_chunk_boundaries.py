from app.application.pdf_knowledge.indexing import PdfIndexingService
from app.domain.models import PdfDocumentDetail, PdfDocumentSummary
from app.ports.pdf_parser import ParsedPdfChunk


def test_pdf_indexing_splits_oversized_source_without_losing_words() -> None:
    service = PdfIndexingService(
        repository=object(),  # type: ignore[arg-type]
        max_chunk_characters=12,
    )
    original = "alpha beta gamma delta epsilon zeta"

    chunks = service.build_document_chunks(
        file_id="file-1",
        parsed_chunks=[
            ParsedPdfChunk(
                text=original,
                page_label="1",
                title="Requirements",
                metadata={"source": "parser"},
            )
        ],
        detail=PdfDocumentDetail(
            file_id="file-1",
            summary=PdfDocumentSummary(file_id="file-1", status="ready", content=""),
            preview_blocks=[],
            schema=[],
            tags=[],
        ),
    )

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 12 for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert " ".join(chunk.text for chunk in chunks).split() == original.split()
    assert all(chunk.metadata["segment_count"] == str(len(chunks)) for chunk in chunks)
