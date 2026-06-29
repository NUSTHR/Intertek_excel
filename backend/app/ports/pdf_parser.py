from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ParsedPdfBlock:
    page_label: str
    title: str
    content: str


@dataclass(frozen=True)
class ParsedPdfChunk:
    text: str
    page_label: str | None = None
    title: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedPdfDocument:
    page_count: int
    chunk_count: int
    preview_blocks: list[ParsedPdfBlock] = field(default_factory=list)
    chunks: list[ParsedPdfChunk] = field(default_factory=list)
    schema: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PdfParserRuntimeStatus:
    backend: str
    available: bool
    command: str | None = None
    version: str | None = None
    detail: str = ""


class PdfParser(Protocol):
    def parse(self, *, filename: str, content: bytes) -> ParsedPdfDocument:
        ...
