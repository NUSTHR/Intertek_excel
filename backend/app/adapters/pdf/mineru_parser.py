import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

from app.domain.models import PdfParsePageStatus, PdfParseQualityStatus
from app.ports.pdf_parser import (
    ParsedPdfArtifact,
    ParsedPdfBlock,
    ParsedPdfChunk,
    ParsedPdfDocument,
    ParsedPdfPage,
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
        cli_backend: str = "pipeline",
        extra_args: tuple[str, ...] = (),
    ) -> None:
        self._command = command
        self._timeout_seconds = max(1.0, timeout_seconds)
        self._cli_backend = cli_backend.strip()
        self._extra_args = tuple(arg.strip() for arg in extra_args if arg.strip())

    def parse(self, *, filename: str, content: bytes) -> ParsedPdfDocument:
        with tempfile.TemporaryDirectory(prefix="mineru-pdf-") as temporary_dir:
            workspace = Path(temporary_dir)
            input_path = workspace / (Path(filename).name or "uploaded.pdf")
            output_dir = workspace / "output"
            input_path.write_bytes(content)
            output_dir.mkdir(parents=True, exist_ok=True)
            self._run_mineru(input_path=input_path, output_dir=output_dir)
            parsed = self._read_output(filename=filename, output_dir=output_dir)
            artifact_root = _copy_artifacts_to_handoff_dir(output_dir) if parsed.artifacts else None
            return replace(parsed, artifact_root=artifact_root)

    def runtime_status(self) -> PdfParserRuntimeStatus:
        return check_mineru_runtime(command=self._command)

    def _run_mineru(self, *, input_path: Path, output_dir: Path) -> None:
        command = [
            self._command,
            "-p",
            str(input_path),
            "-o",
            str(output_dir),
        ]
        if self._cli_backend:
            command.extend(["-b", self._cli_backend])
        command.extend(self._extra_args)
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self._timeout_seconds,
        )
        if completed.returncode != 0:
            error = _mineru_error_summary(completed.stderr, completed.stdout)
            raise RuntimeError(error or "MinerU parsing failed")

    def _read_output(self, *, filename: str, output_dir: Path) -> ParsedPdfDocument:
        return read_mineru_output(
            filename=filename,
            output_dir=output_dir,
            parser_name="MinerU",
            parser_backend="mineru",
        )

    def _read_metadata(self, json_files: list[Path]) -> tuple[dict[str, object], list[str]]:
        merged: dict[str, object] = {}
        warnings: list[str] = []
        for path in json_files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except OSError as exc:
                warnings.append(f"Unable to read MinerU JSON output {path.name}: {exc}")
                continue
            except json.JSONDecodeError as exc:
                warnings.append(f"Unable to decode MinerU JSON output {path.name}: {exc.msg}")
                continue
            if isinstance(payload, dict):
                merged.update(payload)
        return merged, warnings


def read_mineru_output(
    *,
    filename: str,
    output_dir: Path,
    parser_name: str = "MinerU",
    parser_backend: str = "mineru",
    parser_version: str | None = None,
    extra_warnings: list[str] | None = None,
) -> ParsedPdfDocument:
    markdown_files = sorted(output_dir.rglob("*.md"))
    json_files = sorted(output_dir.rglob("*.json"))
    markdown = "\n\n".join(
        path.read_text(encoding="utf-8", errors="ignore").strip()
        for path in markdown_files
    ).strip()
    metadata, metadata_warnings = _read_metadata(json_files)
    json_text, json_warnings = _text_from_json_files(json_files)
    preview_text = markdown or json_text or f"{filename} was parsed by MinerU."
    page_count = _page_count_from_metadata(metadata)
    chunks = _chunks_from_text(preview_text)
    chunk_count = len(chunks)
    warnings = [
        *(extra_warnings or []),
        *metadata_warnings,
        *json_warnings,
        *_output_warnings(
            markdown_files=markdown_files,
            json_files=json_files,
            markdown=markdown,
            json_text=json_text,
        ),
    ]
    pages = _pages_from_parsed_text(
        page_count=page_count,
        text=markdown or json_text,
        warnings=warnings,
    )
    quality_status = _quality_status_for_output(
        chunks=chunks,
        pages=pages,
        warnings=warnings,
    )
    return ParsedPdfDocument(
        page_count=page_count,
        chunk_count=chunk_count,
        preview_blocks=_preview_blocks_from_text(preview_text),
        chunks=chunks,
        schema={
            "Pages": str(page_count),
            "Indexed Chunks": str(chunk_count),
            "Parser": parser_name,
            "Output Files": str(len(markdown_files) + len(json_files)),
        },
        tags=["#pdf", "#knowledge_base", "#mineru"],
        pages=pages,
        warnings=warnings,
        artifacts=_artifact_manifest(output_dir),
        artifact_root=output_dir.as_posix(),
        parser_backend=parser_backend,
        parser_version=parser_version,
        quality_status=quality_status,
    )


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
            timeout=30,
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


def _read_metadata(json_files: list[Path]) -> tuple[dict[str, object], list[str]]:
    merged: dict[str, object] = {}
    warnings: list[str] = []
    for path in json_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            warnings.append(f"Unable to read MinerU JSON output {path.name}: {exc}")
            continue
        except json.JSONDecodeError as exc:
            warnings.append(f"Unable to decode MinerU JSON output {path.name}: {exc.msg}")
            continue
        if isinstance(payload, dict):
            merged.update(payload)
    return merged, warnings


def _mineru_error_summary(stderr: str, stdout: str) -> str:
    text = "\n".join(part.strip() for part in (stderr, stdout) if part.strip())
    if not text:
        return ""
    for pattern in (
        r"ModuleNotFoundError:\s*(.+)",
        r"ImportError:\s*(.+)",
        r"Error:\s*(.+)",
    ):
        matches = re.findall(pattern, text)
        if matches:
            return f"MinerU parsing failed: {matches[-1].strip()}"[:500]
    for line in reversed(text.splitlines()):
        normalized = " ".join(line.split())
        if normalized:
            return f"MinerU parsing failed: {normalized}"[:500]
    return "MinerU parsing failed."


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


def _text_from_json_files(json_files: list[Path]) -> tuple[str, list[str]]:
    fragments: list[str] = []
    warnings: list[str] = []
    for path in json_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            warnings.append(f"Unable to read MinerU JSON text output {path.name}: {exc}")
            continue
        except json.JSONDecodeError as exc:
            warnings.append(f"Unable to decode MinerU JSON text output {path.name}: {exc.msg}")
            continue
        fragments.extend(_text_fragments_from_json(payload))
    return "\n\n".join(_dedupe_preserving_order(fragments)).strip(), warnings


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


def _output_warnings(
    *,
    markdown_files: list[Path],
    json_files: list[Path],
    markdown: str,
    json_text: str,
) -> list[str]:
    warnings: list[str] = []
    if not markdown_files:
        warnings.append("MinerU did not produce Markdown output; JSON text fallback was used.")
    if not json_files:
        warnings.append("MinerU did not produce JSON output metadata.")
    if not markdown and not json_text:
        warnings.append("MinerU completed but no extractable text was found.")
    return warnings


def _pages_from_parsed_text(
    *,
    page_count: int,
    text: str,
    warnings: list[str],
) -> list[ParsedPdfPage]:
    bounded_page_count = max(1, page_count)
    if not text.strip():
        return [
            ParsedPdfPage(
                page_number=page_number,
                page_label=f"Page {page_number}",
                status=PdfParsePageStatus.EMPTY,
                warning_message="No extractable text was produced for this page.",
            )
            for page_number in range(1, bounded_page_count + 1)
        ]
    paragraphs = _paragraphs_from_text(text)
    first_page_warning = (
        "MinerU output did not include reliable page-level text mapping; "
        "counts are derived from aggregate output."
    )
    if warnings:
        first_page_warning = f"{first_page_warning} Review parser warnings."
    return [
        ParsedPdfPage(
            page_number=page_number,
            page_label=f"Page {page_number}",
            status=PdfParsePageStatus.PARSED if page_number == 1 else PdfParsePageStatus.SKIPPED,
            text_block_count=len(paragraphs) if page_number == 1 else 0,
            char_count=len(text) if page_number == 1 else 0,
            warning_message=first_page_warning if page_number == 1 else None,
        )
        for page_number in range(1, bounded_page_count + 1)
    ]


def _quality_status_for_output(
    *,
    chunks: list[ParsedPdfChunk],
    pages: list[ParsedPdfPage],
    warnings: list[str],
) -> PdfParseQualityStatus:
    if not chunks or all(not chunk.text.strip() for chunk in chunks):
        return PdfParseQualityStatus.FAILED
    if any(page.status == PdfParsePageStatus.FAILED for page in pages):
        return PdfParseQualityStatus.PARTIAL
    if any(page.status == PdfParsePageStatus.EMPTY for page in pages):
        return PdfParseQualityStatus.PARTIAL
    if warnings:
        return PdfParseQualityStatus.WARNING
    return PdfParseQualityStatus.GOOD


def _artifact_manifest(output_dir: Path) -> list[ParsedPdfArtifact]:
    artifacts: list[ParsedPdfArtifact] = []
    for path in sorted(item for item in output_dir.rglob("*") if item.is_file()):
        try:
            content = path.read_bytes()
        except OSError:
            content = b""
        artifacts.append(
            ParsedPdfArtifact(
                artifact_type=path.suffix.lower().lstrip(".") or "file",
                name=path.name,
                path=path.relative_to(output_dir).as_posix(),
                size_bytes=len(content),
                content_hash=hashlib.sha256(content).hexdigest() if content else None,
            )
        )
    return artifacts


def _copy_artifacts_to_handoff_dir(output_dir: Path) -> str:
    handoff_root = Path(tempfile.mkdtemp(prefix="mineru-pdf-artifacts-"))
    shutil.copytree(output_dir, handoff_root, dirs_exist_ok=True)
    return handoff_root.as_posix()
