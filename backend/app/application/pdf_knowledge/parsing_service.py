import shutil
from collections.abc import Callable
from pathlib import Path

from app.application.pdf_knowledge.indexing import PdfIndexingService
from app.application.pdf_knowledge.parse_reports import (
    build_failed_parse_report,
    build_parse_report,
    copy_parsed_document,
    processing_outcome_for_report,
)
from app.application.pdf_knowledge.parser_profiles import PdfParserProfileRegistry
from app.application.pdf_knowledge.uploads import PdfUploadRecordBuilder
from app.core.errors import UploadValidationError
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    PdfDocumentDetail,
    PdfDocumentSummary,
    PdfParseReport,
    PdfPreviewBlock,
    PdfProcessingStatus,
    PdfSchemaItem,
    PdfUploadBatch,
    PdfUploadTask,
    PdfUploadTaskStage,
)
from app.ports.pdf_parser import ParsedPdfArtifact, ParsedPdfDocument
from app.ports.repository import PdfKnowledgeRepository


class PdfParsingService:
    """Executes PDF parsing, indexing, diagnostics, and failure recovery."""

    def __init__(
        self,
        *,
        repository: PdfKnowledgeRepository,
        storage_root: Path,
        upload_records: PdfUploadRecordBuilder,
        parser_profiles: PdfParserProfileRegistry,
        indexing: PdfIndexingService,
        refresh_batch: Callable[[str], PdfUploadBatch],
    ) -> None:
        self._repository = repository
        self._files_root = (
            storage_root.expanduser().resolve() / "pdf-knowledge" / "files"
        ).resolve()
        self._upload_records = upload_records
        self._parser_profiles = parser_profiles
        self._indexing = indexing
        self._refresh_batch = refresh_batch

    def process_task(self, task: PdfUploadTask, content: bytes) -> PdfUploadTask:
        if task.file_id is None:
            raise UploadValidationError("PDF upload task is missing a file reference")
        now = utc_now_iso()
        self._repository.update_pdf_file_processing(
            file_id=task.file_id,
            processing_status=PdfProcessingStatus.PARSING,
            progress=25,
            status_detail="MinerU parsing started.",
            updated_at=now,
        )
        self._repository.update_pdf_upload_task_progress(
            task_id=task.task_id,
            progress=25,
            detail="MinerU parsing started.",
            updated_at=now,
            stage=PdfUploadTaskStage.PARSING,
        )
        parsing_at = utc_now_iso()
        self._repository.update_pdf_file_processing(
            file_id=task.file_id,
            processing_status=PdfProcessingStatus.PARSING,
            progress=55,
            status_detail="MinerU is extracting document structure.",
            updated_at=parsing_at,
        )
        self._repository.update_pdf_upload_task_progress(
            task_id=task.task_id,
            progress=55,
            detail="MinerU is extracting document structure.",
            updated_at=parsing_at,
            stage=PdfUploadTaskStage.PARSING,
        )
        page_count, chunk_count, parse_report = self._parse_and_index(
            file_id=task.file_id,
            filename=task.original_filename,
            content=content,
            parser_profile_id=task.parser_backend,
        )
        indexed_at = utc_now_iso()
        self._repository.update_pdf_file_processing(
            file_id=task.file_id,
            processing_status=PdfProcessingStatus.INDEXING,
            progress=90,
            status_detail="Building knowledge chunks and chat index.",
            updated_at=indexed_at,
        )
        self._repository.update_pdf_upload_task_progress(
            task_id=task.task_id,
            progress=90,
            detail="Building knowledge chunks and chat index.",
            updated_at=indexed_at,
            stage=PdfUploadTaskStage.INDEXING,
        )
        final_status, final_detail = processing_outcome_for_report(parse_report)
        ready_at = utc_now_iso()
        self._repository.update_pdf_file_processing(
            file_id=task.file_id,
            processing_status=final_status,
            progress=100,
            status_detail=final_detail,
            updated_at=ready_at,
            page_count=page_count,
            chunk_count=chunk_count,
            error_message=(
                "; ".join(parse_report.warnings[:2])
                if final_status == PdfProcessingStatus.FAILED
                else None
            ),
        )
        completed_task = self._repository.complete_pdf_upload_task(
            task_id=task.task_id,
            result={
                "file_id": task.file_id,
                "quality_status": parse_report.quality_status.value,
                "coverage_ratio": parse_report.coverage_ratio,
                "warning_count": parse_report.warning_count,
                "failed_page_count": parse_report.failed_pages,
            },
            detail=final_detail,
            finished_at=ready_at,
        ) or task
        if completed_task.batch_id:
            self._refresh_batch(completed_task.batch_id)
        return completed_task

    def fail_task(
        self,
        task: PdfUploadTask,
        error_message: str,
        *,
        error_code: str | None = None,
        failed_at: str | None = None,
    ) -> PdfUploadTask:
        failed_at = failed_at or utc_now_iso()
        if task.file_id is not None:
            parser_status = self._parser_profiles.status_for(task.parser_backend)
            report = build_failed_parse_report(
                file_id=task.file_id,
                parser_backend=parser_status.backend,
                parser_version=parser_status.version,
                error_message=error_message,
                failed_at=failed_at,
            )
            self._repository.save_pdf_parse_report(report)
            self._repository.replace_pdf_parse_pages(task.file_id, report.pages)
            self._repository.replace_pdf_parse_artifacts(task.file_id, report.artifacts)
            self._repository.update_pdf_file_processing(
                file_id=task.file_id,
                processing_status=PdfProcessingStatus.FAILED,
                progress=100,
                status_detail="PDF parsing failed.",
                updated_at=failed_at,
                error_message=error_message,
            )
        failed_task = self._repository.fail_pdf_upload_task(
            task_id=task.task_id,
            error_message=error_message,
            failed_at=failed_at,
            error_code=error_code,
        ) or task
        if failed_task.batch_id:
            self._refresh_batch(failed_task.batch_id)
        return failed_task

    def fail_stale_tasks(
        self,
        *,
        cutoff_started_at: str,
        failed_at: str,
    ) -> int:
        stale_tasks = self._repository.list_stale_processing_pdf_upload_tasks(
            cutoff_started_at=cutoff_started_at
        )
        for task in stale_tasks:
            self.fail_task(
                task,
                "PDF processing was interrupted. Please upload the document again.",
                error_code="stale_processing_task",
                failed_at=failed_at,
            )
        return len(stale_tasks)

    def _parse_and_index(
        self,
        *,
        file_id: str,
        filename: str,
        content: bytes,
        parser_profile_id: str | None = None,
    ) -> tuple[int, int, PdfParseReport]:
        parser = self._parser_profiles.parser_for(parser_profile_id)
        parser_status = self._parser_profiles.status_for(parser_profile_id)
        parsed = parser.parse(filename=filename, content=content)
        parsed = self._archive_artifacts(file_id=file_id, parsed=parsed)
        detail = PdfDocumentDetail(
            file_id=file_id,
            summary=PdfDocumentSummary(file_id=file_id, status="empty", content=""),
            preview_blocks=[
                PdfPreviewBlock(
                    block_id=new_id("pdfblock"),
                    file_id=file_id,
                    page_label=block.page_label,
                    title=block.title,
                    content=block.content,
                    block_index=index,
                )
                for index, block in enumerate(parsed.preview_blocks)
            ],
            schema=[
                PdfSchemaItem(
                    item_id=new_id("pdfschema"),
                    file_id=file_id,
                    label=label,
                    value=value,
                    item_index=index,
                )
                for index, (label, value) in enumerate(parsed.schema.items())
            ],
            tags=parsed.tags,
        )
        self._repository.save_pdf_document_detail(detail)
        chunks = self._indexing.index_document(
            file_id=file_id,
            parsed_chunks=parsed.chunks,
            detail=detail,
        )
        report = build_parse_report(
            file_id=file_id,
            parsed=parsed,
            indexed_chunk_count=len(chunks),
            parser_backend=parser_status.backend,
            parser_version=parser_status.version,
        )
        self._repository.save_pdf_parse_report(report)
        self._repository.replace_pdf_parse_pages(file_id, report.pages)
        self._repository.replace_pdf_parse_artifacts(file_id, report.artifacts)
        return parsed.page_count, len(chunks), report

    def _archive_artifacts(
        self,
        *,
        file_id: str,
        parsed: ParsedPdfDocument,
    ) -> ParsedPdfDocument:
        if not parsed.artifact_root or not parsed.artifacts:
            return parsed
        source_root = Path(parsed.artifact_root).expanduser().resolve()
        try:
            if not source_root.exists() or not source_root.is_dir():
                warnings = [
                    *parsed.warnings,
                    "Parser artifact root was not available for archival.",
                ]
                return copy_parsed_document(
                    parsed,
                    warnings=warnings,
                    artifact_root=parsed.artifact_root,
                )
            archive_root = (self._files_root / file_id / "artifacts").resolve()
            if not archive_root.is_relative_to(self._files_root):
                raise UploadValidationError("PDF artifact archive path is invalid")
            if archive_root.exists():
                shutil.rmtree(archive_root)
            archive_root.mkdir(parents=True, exist_ok=True)
            archived_artifacts: list[ParsedPdfArtifact] = []
            warnings = list(parsed.warnings)
            for artifact in parsed.artifacts[:200]:
                if not artifact.path:
                    archived_artifacts.append(artifact)
                    continue
                source_path = (source_root / artifact.path).resolve()
                if not source_path.is_relative_to(source_root) or not source_path.is_file():
                    warnings.append(
                        f"Parser artifact '{artifact.name}' was not available for archival."
                    )
                    archived_artifacts.append(artifact)
                    continue
                destination_path = (archive_root / artifact.path).resolve()
                if not destination_path.is_relative_to(archive_root):
                    warnings.append(
                        f"Parser artifact '{artifact.name}' had an unsafe relative path."
                    )
                    archived_artifacts.append(artifact)
                    continue
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, destination_path)
                archived_artifacts.append(
                    ParsedPdfArtifact(
                        artifact_type=artifact.artifact_type,
                        name=artifact.name,
                        path=self._upload_records.storage_reference(destination_path),
                        size_bytes=artifact.size_bytes,
                        content_hash=artifact.content_hash,
                    )
                )
            return copy_parsed_document(
                parsed,
                warnings=warnings,
                artifacts=archived_artifacts,
                artifact_root=None,
            )
        finally:
            shutil.rmtree(source_root, ignore_errors=True)
