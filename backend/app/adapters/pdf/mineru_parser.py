import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.ports.pdf_parser import (
    ParsedPdfBlock,
    ParsedPdfChunk,
    ParsedPdfDocument,
    PdfParserRuntimeStatus,
)

MAX_CHUNK_CHARACTERS = 1_600
TEXT_JSON_KEYS = {
    "content",
    "markdown",
    "md_content",
    "page_content",
    "paragraph",
    "text",
}


class MinerUPdfParser:
    def __init__(
        self,
        *,
        command: str = "mineru",
        timeout_seconds: float = 300.0,
    ) -> None:
        self._command = command
        self._timeout_seconds = max(1.0, timeout_seconds)

    def parse(self, *, filename: str, content: bytes) -> ParsedPdfDocument:
        with tempfile.TemporaryDirectory(prefix="mineru-pdf-") as temporary_dir:
            workspace = Path(temporary_dir)
            input_path = workspace / (Path(filename).name or "uploaded.pdf")
            output_dir = workspace / "output"
            input_path.write_bytes(content)
            output_dir.mkdir(parents=True, exist_ok=True)
            self._run_mineru(input_path=input_path, output_dir=output_dir)
            return self._read_output(filename=filename, output_dir=output_dir)

    def runtime_status(self) -> PdfParserRuntimeStatus:
        return check_mineru_runtime(command=self._command)

    def _run_mineru(self, *, input_path: Path, output_dir: Path) -> None:
        completed = subprocess.run(
            [
                self._command,
                "-p",
                str(input_path),
                "-o",
                str(output_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=self._timeout_seconds,
        )
        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(error or "MinerU parsing failed")

    def _read_output(self, *, filename: str, output_dir: Path) -> ParsedPdfDocument:
        markdown_files = sorted(output_dir.rglob("*.md"))
        json_files = sorted(output_dir.rglob("*.json"))
        markdown = "\n\n".join(
            path.read_text(encoding="utf-8", errors="ignore").strip()
            for path in markdown_files
        ).strip()
        metadata = self._read_metadata(json_files)
        json_text = _text_from_json_files(json_files)
        preview_text = markdown or json_text or f"{filename} was parsed by MinerU."
        page_count = _page_count_from_metadata(metadata)
        chunks = _chunks_from_text(preview_text)
        chunk_count = len(chunks)
        return ParsedPdfDocument(
            page_count=page_count,
            chunk_count=chunk_count,
            preview_blocks=_preview_blocks_from_text(preview_text),
            chunks=chunks,
            schema={
                "Pages": str(page_count),
                "Indexed Chunks": str(chunk_count),
                "Parser": "MinerU",
                "Output Files": str(len(markdown_files) + len(json_files)),
            },
            tags=["#pdf", "#knowledge_base", "#mineru"],
        )

    def _read_metadata(self, json_files: list[Path]) -> dict[str, object]:
        merged: dict[str, object] = {}
        for path in json_files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                merged.update(payload)
        return merged


def check_mineru_runtime(*, command: str = "mineru") -> PdfParserRuntimeStatus:
    resolved_command = shutil.which(command)
    if resolved_command is None:
        return PdfParserRuntimeStatus(
            backend="mineru",
            available=False,
            command=command,
            detail=f"MinerU command '{command}' was not found on PATH.",
        )
    try:
        completed = subprocess.run(
            [resolved_command, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return PdfParserRuntimeStatus(
            backend="mineru",
            available=True,
            command=resolved_command,
            detail=f"MinerU executable was found, but version probing failed: {exc}",
        )
    version = (completed.stdout.strip() or completed.stderr.strip()).splitlines()
    return PdfParserRuntimeStatus(
        backend="mineru",
        available=True,
        command=resolved_command,
        version=version[0][:160] if version else None,
        detail="MinerU executable is available.",
    )


def _preview_blocks_from_text(text: str) -> list[ParsedPdfBlock]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    if not paragraphs:
        return [
            ParsedPdfBlock(
                page_label="Page 1",
                title="Parsed Overview",
                content="MinerU completed parsing, but no text preview was produced.",
            )
        ]
    blocks: list[ParsedPdfBlock] = []
    for index, paragraph in enumerate(paragraphs[:3]):
        blocks.append(
            ParsedPdfBlock(
                page_label=f"Block {index + 1}",
                title=_title_from_paragraph(paragraph, index),
                content=paragraph[:600],
            )
        )
    return blocks


def _chunks_from_text(text: str) -> list[ParsedPdfChunk]:
    paragraphs = _paragraphs_from_text(text)
    if not paragraphs:
        return [
            ParsedPdfChunk(
                text="MinerU completed parsing, but no text chunks were produced.",
                page_label="Page 1",
                title="Parsed Output",
                metadata={"source": "mineru"},
            )
        ]
    chunk_texts: list[str] = []
    for paragraph in paragraphs:
        chunk_texts.extend(_split_long_paragraph(paragraph))
    return [
        ParsedPdfChunk(
            text=chunk_text,
            page_label=None,
            title=_title_from_paragraph(chunk_text, index),
            metadata={"source": "mineru"},
        )
        for index, chunk_text in enumerate(chunk_texts)
    ]


def _title_from_paragraph(paragraph: str, index: int) -> str:
    first_line = paragraph.splitlines()[0].lstrip("#").strip()
    return first_line[:80] or f"Parsed Block {index + 1}"


def _safe_positive_int(value: object, *, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(1, parsed)


def _page_count_from_metadata(metadata: dict[str, object]) -> int:
    for key in ("page_count", "total_pages", "pages", "page_num"):
        value = metadata.get(key)
        if isinstance(value, list):
            value = len(value)
        page_count = _safe_positive_int(value, fallback=0)
        if page_count > 0:
            return page_count
    return 1


def _text_from_json_files(json_files: list[Path]) -> str:
    fragments: list[str] = []
    for path in json_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        fragments.extend(_text_fragments_from_json(payload))
    return "\n\n".join(_dedupe_preserving_order(fragments)).strip()


def _text_fragments_from_json(payload: object, *, key: str | None = None) -> list[str]:
    if isinstance(payload, dict):
        fragments: list[str] = []
        for child_key, value in payload.items():
            fragments.extend(_text_fragments_from_json(value, key=str(child_key)))
        return fragments
    if isinstance(payload, list):
        fragments = []
        for value in payload:
            fragments.extend(_text_fragments_from_json(value, key=key))
        return fragments
    if isinstance(payload, str) and key in TEXT_JSON_KEYS:
        text = payload.strip()
        if len(text) >= 12:
            return [text]
    return []


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = " ".join(value.split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(value)
    return deduped


def _paragraphs_from_text(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return [part.strip() for part in normalized.split("\n\n") if part.strip()]


def _split_long_paragraph(paragraph: str) -> list[str]:
    if len(paragraph) <= MAX_CHUNK_CHARACTERS:
        return [paragraph]
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for sentence in _sentence_like_parts(paragraph):
        projected_length = current_length + len(sentence) + (1 if current else 0)
        if current and projected_length > MAX_CHUNK_CHARACTERS:
            chunks.append(" ".join(current).strip())
            current = []
            current_length = 0
        if len(sentence) > MAX_CHUNK_CHARACTERS:
            chunks.extend(_hard_split(sentence, MAX_CHUNK_CHARACTERS))
            continue
        current.append(sentence)
        current_length += len(sentence) + (1 if current_length else 0)
    if current:
        chunks.append(" ".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def _sentence_like_parts(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    for char in text:
        current.append(char)
        if char in ".!?。！？；;":
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts or [text.strip()]


def _hard_split(text: str, max_length: int) -> list[str]:
    return [
        text[index : index + max_length].strip()
        for index in range(0, len(text), max_length)
        if text[index : index + max_length].strip()
    ]
