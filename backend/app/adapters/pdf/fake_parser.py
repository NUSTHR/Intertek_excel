from app.ports.pdf_parser import ParsedPdfBlock, ParsedPdfChunk, ParsedPdfDocument


class FakePdfParser:
    def parse(self, *, filename: str, content: bytes) -> ParsedPdfDocument:
        decoded = content[:4000].decode("utf-8", errors="ignore").strip()
        fallback_text = (
            f"{filename} was ingested through the PDF knowledge pipeline. "
            "Replace FakePdfParser with the MinerU adapter for production parsing."
        )
        text = decoded or fallback_text
        page_count = max(1, min(12, content.count(b"/Page") or len(content) // 1200 or 1))
        chunk_count = max(1, min(256, len(text) // 180 + 1))
        preview_blocks = [
            ParsedPdfBlock(
                page_label="Page 1",
                title="Parsed Overview",
                content=text[:420],
            ),
            ParsedPdfBlock(
                page_label="Index",
                title="Knowledge Index",
                content=(
                    "The backend generated searchable PDF chunks and metadata "
                    "for chat grounding."
                ),
            ),
        ]
        return ParsedPdfDocument(
            page_count=page_count,
            chunk_count=chunk_count,
            preview_blocks=preview_blocks,
            chunks=[
                ParsedPdfChunk(
                    text=block.content,
                    page_label=block.page_label,
                    title=block.title,
                    metadata={"source": "fake_parser"},
                )
                for block in preview_blocks
            ],
            schema={
                "Pages": str(page_count),
                "Indexed Chunks": str(chunk_count),
                "Parser": "FakePdfParser",
                "Primary Language": "Unknown",
            },
            tags=["#pdf", "#knowledge_base", "#indexed"],
        )
