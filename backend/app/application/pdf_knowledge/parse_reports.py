from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    PdfParseArtifact,
    PdfParsePage,
    PdfParsePageStatus,
    PdfParseQualityStatus,
    PdfParseReport,
    PdfProcessingStatus,
)
from app.ports.pdf_parser import ParsedPdfArtifact, ParsedPdfDocument, ParsedPdfPage


def build_parse_report(
    *,
    file_id: str,
    parsed: ParsedPdfDocument,
    indexed_chunk_count: int,
    parser_backend: str,
    parser_version: str | None,
) -> PdfParseReport:
    now = utc_now_iso()
    pages = _build_parse_pages(file_id=file_id, parsed_pages=parsed.pages, parsed=parsed)
    artifacts = _build_parse_artifacts(file_id=file_id, parsed_artifacts=parsed.artifacts)
    total_pages = max(1, parsed.page_count, len(pages))
    parsed_pages = sum(1 for page in pages if page.status == PdfParsePageStatus.PARSED)
    failed_pages = sum(1 for page in pages if page.status == PdfParsePageStatus.FAILED)
    empty_pages = sum(
        1
        for page in pages
        if page.status in {PdfParsePageStatus.EMPTY, PdfParsePageStatus.IMAGE_ONLY}
    )
    warnings = _bounded_warnings(parsed.warnings)
    quality_status = _normalize_quality_status(
        declared=parsed.quality_status,
        has_extracted_chunks=_has_extracted_chunks(parsed),
        failed_pages=failed_pages,
        empty_pages=empty_pages,
        warnings=warnings,
    )
    coverage_ratio = _coverage_ratio(
        total_pages=total_pages,
        parsed_pages=parsed_pages,
        failed_pages=failed_pages,
        empty_pages=empty_pages,
    )
    return PdfParseReport(
        file_id=file_id,
        parser_backend=parsed.parser_backend or parser_backend,
        parser_version=parsed.parser_version or parser_version,
        quality_status=quality_status,
        total_pages=total_pages,
        parsed_pages=parsed_pages,
        failed_pages=failed_pages,
        empty_pages=empty_pages,
        text_block_count=sum(page.text_block_count for page in pages),
        table_block_count=sum(page.table_block_count for page in pages),
        image_block_count=sum(page.image_block_count for page in pages),
        chunk_count=indexed_chunk_count,
        coverage_ratio=coverage_ratio,
        warning_count=len(warnings),
        error_count=failed_pages + (1 if quality_status == PdfParseQualityStatus.FAILED else 0),
        warnings=warnings,
        created_at=now,
        updated_at=now,
        artifacts=artifacts,
        pages=pages,
    )


def build_failed_parse_report(
    *,
    file_id: str,
    parser_backend: str,
    parser_version: str | None,
    error_message: str,
    failed_at: str,
) -> PdfParseReport:
    safe_message = _truncate_optional(error_message, 500) or "PDF parsing failed."
    page = PdfParsePage(
        page_id=new_id("pdfpage"),
        file_id=file_id,
        page_number=1,
        page_label="Page 1",
        status=PdfParsePageStatus.FAILED,
        text_block_count=0,
        table_block_count=0,
        image_block_count=0,
        char_count=0,
        error_message=safe_message,
    )
    return PdfParseReport(
        file_id=file_id,
        parser_backend=parser_backend,
        parser_version=parser_version,
        quality_status=PdfParseQualityStatus.FAILED,
        total_pages=1,
        parsed_pages=0,
        failed_pages=1,
        empty_pages=0,
        text_block_count=0,
        table_block_count=0,
        image_block_count=0,
        chunk_count=0,
        coverage_ratio=0.0,
        warning_count=1,
        error_count=1,
        warnings=[safe_message],
        started_at=None,
        finished_at=failed_at,
        created_at=failed_at,
        updated_at=failed_at,
        pages=[page],
    )


def copy_parsed_document(
    parsed: ParsedPdfDocument,
    *,
    warnings: list[str] | None = None,
    artifacts: list[ParsedPdfArtifact] | None = None,
    artifact_root: str | None = None,
) -> ParsedPdfDocument:
    return ParsedPdfDocument(
        page_count=parsed.page_count,
        chunk_count=parsed.chunk_count,
        preview_blocks=parsed.preview_blocks,
        chunks=parsed.chunks,
        schema=parsed.schema,
        tags=parsed.tags,
        pages=parsed.pages,
        warnings=warnings if warnings is not None else parsed.warnings,
        artifacts=artifacts if artifacts is not None else parsed.artifacts,
        artifact_root=artifact_root,
        parser_backend=parsed.parser_backend,
        parser_version=parsed.parser_version,
        quality_status=parsed.quality_status,
    )


def processing_outcome_for_report(
    report: PdfParseReport,
) -> tuple[PdfProcessingStatus, str]:
    if report.quality_status == PdfParseQualityStatus.FAILED:
        return PdfProcessingStatus.FAILED, "PDF parsing failed. Review the parse quality report."
    if report.quality_status == PdfParseQualityStatus.PARTIAL:
        return (
            PdfProcessingStatus.PARTIAL,
            "PDF parsed with incomplete coverage. Review warnings before using it for chat.",
        )
    if report.quality_status == PdfParseQualityStatus.WARNING:
        return (
            PdfProcessingStatus.PARTIAL,
            "PDF parsed with warnings. Review the parse quality report.",
        )
    return PdfProcessingStatus.READY, "Ready for PDF-grounded chat."


def _build_parse_pages(
    *,
    file_id: str,
    parsed_pages: list[ParsedPdfPage],
    parsed: ParsedPdfDocument,
) -> list[PdfParsePage]:
    if parsed_pages:
        return [
            PdfParsePage(
                page_id=new_id("pdfpage"),
                file_id=file_id,
                page_number=max(1, page.page_number),
                page_label=page.page_label or f"Page {max(1, page.page_number)}",
                status=page.status,
                text_block_count=max(0, page.text_block_count),
                table_block_count=max(0, page.table_block_count),
                image_block_count=max(0, page.image_block_count),
                char_count=max(0, page.char_count),
                warning_message=_truncate_optional(page.warning_message, 500),
                error_message=_truncate_optional(page.error_message, 500),
            )
            for page in parsed_pages
        ]
    page_count = max(1, parsed.page_count)
    has_text = _has_extracted_chunks(parsed)
    aggregate_warning = (
        "Parser output did not include page-level mapping; "
        "aggregate text was attached to the first page."
    )
    return [
        PdfParsePage(
            page_id=new_id("pdfpage"),
            file_id=file_id,
            page_number=page_number,
            page_label=f"Page {page_number}",
            status=(
                PdfParsePageStatus.PARSED
                if has_text and page_number == 1
                else PdfParsePageStatus.SKIPPED
            ),
            text_block_count=len(parsed.chunks) if has_text and page_number == 1 else 0,
            table_block_count=0,
            image_block_count=0,
            char_count=(
                sum(len(chunk.text) for chunk in parsed.chunks)
                if has_text and page_number == 1
                else 0
            ),
            warning_message=(
                aggregate_warning if has_text and page_number == 1 else None
            ),
        )
        for page_number in range(1, page_count + 1)
    ]


def _build_parse_artifacts(
    *,
    file_id: str,
    parsed_artifacts: list[ParsedPdfArtifact],
) -> list[PdfParseArtifact]:
    now = utc_now_iso()
    return [
        PdfParseArtifact(
            artifact_id=new_id("pdfartifact"),
            file_id=file_id,
            artifact_type=artifact.artifact_type[:80] or "file",
            name=artifact.name[:255] or "artifact",
            path=artifact.path,
            size_bytes=max(0, artifact.size_bytes),
            content_hash=artifact.content_hash,
            created_at=now,
        )
        for artifact in parsed_artifacts[:200]
    ]


def _normalize_quality_status(
    *,
    declared: PdfParseQualityStatus,
    has_extracted_chunks: bool,
    failed_pages: int,
    empty_pages: int,
    warnings: list[str],
) -> PdfParseQualityStatus:
    if not has_extracted_chunks:
        return PdfParseQualityStatus.FAILED
    if declared == PdfParseQualityStatus.FAILED:
        return PdfParseQualityStatus.FAILED
    if declared == PdfParseQualityStatus.PARTIAL or failed_pages > 0 or empty_pages > 0:
        return PdfParseQualityStatus.PARTIAL
    if declared == PdfParseQualityStatus.WARNING or warnings:
        return PdfParseQualityStatus.WARNING
    if declared == PdfParseQualityStatus.GOOD:
        return PdfParseQualityStatus.GOOD
    return PdfParseQualityStatus.GOOD


def _has_extracted_chunks(parsed: ParsedPdfDocument) -> bool:
    return any(
        chunk.text.strip()
        and chunk.text.strip() != "MinerU completed parsing, but no text chunks were produced."
        for chunk in parsed.chunks
    )


def _coverage_ratio(
    *,
    total_pages: int,
    parsed_pages: int,
    failed_pages: int,
    empty_pages: int,
) -> float:
    if total_pages <= 0:
        return 0.0
    usable_pages = max(0, parsed_pages - failed_pages - empty_pages)
    return round(min(1.0, max(0.0, usable_pages / total_pages)), 4)


def _bounded_warnings(warnings: list[str]) -> list[str]:
    bounded: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        normalized = " ".join(str(warning).split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        bounded.append(normalized[:500])
        if len(bounded) >= 50:
            break
    return bounded


def _truncate_optional(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized[:max_length] if normalized else None
