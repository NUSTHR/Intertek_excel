from dataclasses import dataclass, field
from typing import Protocol

from app.domain.models import PdfParsePageStatus, PdfParseQualityStatus


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
class ParsedPdfPage:
    page_number: int
    page_label: str
    status: PdfParsePageStatus
    text_block_count: int = 0
    table_block_count: int = 0
    image_block_count: int = 0
    char_count: int = 0
    warning_message: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ParsedPdfArtifact:
    artifact_type: str
    name: str
    path: str | None = None
    size_bytes: int = 0
    content_hash: str | None = None


@dataclass(frozen=True)
class ParsedPdfDocument:
    page_count: int
    chunk_count: int
    preview_blocks: list[ParsedPdfBlock] = field(default_factory=list)
    chunks: list[ParsedPdfChunk] = field(default_factory=list)
    schema: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    pages: list[ParsedPdfPage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: list[ParsedPdfArtifact] = field(default_factory=list)
    artifact_root: str | None = None
    parser_backend: str | None = None
    parser_version: str | None = None
    quality_status: PdfParseQualityStatus = PdfParseQualityStatus.UNKNOWN


@dataclass(frozen=True)
class PdfParserRuntimeStatus:
    backend: str
    available: bool
    command: str | None = None
    version: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class PdfParserProfile:
    profile_id: str
    label: str
    kind: str
    status: PdfParserRuntimeStatus
    description: str = ""
    is_default: bool = False
    is_selected: bool = False


class PdfParser(Protocol):
    def parse(self, *, filename: str, content: bytes) -> ParsedPdfDocument:
        ...
