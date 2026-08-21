import logging
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
from app.core.content_fingerprint import ordered_content_fingerprint
from app.core.errors import UploadValidationError
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    PdfDocumentChunk,
    PdfDocumentDetail,
    PdfDocumentSummary,
    PdfParseReport,
    PdfPreviewBlock,
    PdfProcessingStatus,
    PdfSchemaItem,
    PdfUploadBatch,
    PdfUploadTask,
    PdfUploadTaskStage,
    PdfUploadTaskStatus,
    PdfVectorIndex,
    PdfVectorIndexStatus,
    PdfVectorIndexTask,
    PdfVectorIndexTaskAction,
    PdfVectorIndexTaskStatus,
)
from app.ports.pdf_parser import ParsedPdfArtifact, ParsedPdfDocument
from app.ports.repository import PdfKnowledgeRepository

logger = logging.getLogger(__name__)


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
        vector_embedding_revision: str | None = None,
        vector_embedding_dimension: int = 4096,
    ) -> None:
        self._repository = repository
        self._files_root = (
            storage_root.expanduser().resolve() / "pdf-knowledge" / "files"
        ).resolve()
        self._upload_records = upload_records
        self._parser_profiles = parser_profiles
        self._indexing = indexing
        self._refresh_batch = refresh_batch
        self._vector_embedding_revision = (
            vector_embedding_revision.strip() if vector_embedding_revision else None
        )
        if vector_embedding_dimension < 1:
            raise ValueError("vector embedding dimension must be positive")
        self._vector_embedding_dimension = vector_embedding_dimension

    def process_task(self, task: PdfUploadTask, content: bytes) -> PdfUploadTask:
        if task.file_id is None:
            raise UploadValidationError("PDF upload task is missing a file reference")
        worker_id, claim_token = self._task_claim(task)
        now = utc_now_iso()
        self._update_file_processing(
            task=task,
            file_id=task.file_id,
            processing_status=PdfProcessingStatus.PARSING,
            progress=25,
            status_detail="MinerU parsing started.",
            updated_at=now,
        )
        if self._repository.update_pdf_upload_task_progress(
            task_id=task.task_id,
            worker_id=worker_id,
            claim_token=claim_token,
            progress=25,
            detail="MinerU parsing started.",
            updated_at=now,
            stage=PdfUploadTaskStage.PARSING,
        ) is None:
            raise UploadValidationError("PDF upload task claim is no longer active")
        self._refresh_batch_safely(task.batch_id)
        parsing_at = utc_now_iso()
        self._update_file_processing(
            task=task,
            file_id=task.file_id,
            processing_status=PdfProcessingStatus.PARSING,
            progress=55,
            status_detail="MinerU is extracting document structure.",
            updated_at=parsing_at,
        )
        if self._repository.update_pdf_upload_task_progress(
            task_id=task.task_id,
            worker_id=worker_id,
            claim_token=claim_token,
            progress=55,
            detail="MinerU is extracting document structure.",
            updated_at=parsing_at,
            stage=PdfUploadTaskStage.PARSING,
        ) is None:
            raise UploadValidationError("PDF upload task claim is no longer active")
        self._refresh_batch_safely(task.batch_id)
        detail, chunks, parse_report = self._build_parse_result(
            task=task,
            file_id=task.file_id,
            filename=task.original_filename,
            content=content,
            parser_profile_id=task.parser_backend,
        )
        indexed_at = utc_now_iso()
        self._update_file_processing(
            task=task,
            file_id=task.file_id,
            processing_status=PdfProcessingStatus.INDEXING,
            progress=90,
            status_detail="Building knowledge chunks and chat index.",
            updated_at=indexed_at,
        )
        if self._repository.update_pdf_upload_task_progress(
            task_id=task.task_id,
            worker_id=worker_id,
            claim_token=claim_token,
            progress=90,
            detail="Building knowledge chunks and chat index.",
            updated_at=indexed_at,
            stage=PdfUploadTaskStage.INDEXING,
        ) is None:
            raise UploadValidationError("PDF upload task claim is no longer active")
        self._refresh_batch_safely(task.batch_id)
        final_status, final_detail = processing_outcome_for_report(parse_report)
        ready_at = utc_now_iso()
        vector_index, vector_index_task = self._build_vector_index_publication(
            task=task,
            chunks=chunks,
            queued_at=ready_at,
        )
        completed_task = self._repository.publish_pdf_parse_result(
            task_id=task.task_id,
            worker_id=worker_id,
            claim_token=claim_token,
            detail=detail,
            chunks=chunks,
            report=parse_report,
            processing_status=final_status,
            status_detail=final_detail,
            error_message=(
                "; ".join(parse_report.warnings[:2])
                if final_status == PdfProcessingStatus.FAILED
                else None
            ),
            result={
                "file_id": task.file_id,
                "quality_status": parse_report.quality_status.value,
                "coverage_ratio": parse_report.coverage_ratio,
                "warning_count": parse_report.warning_count,
                "failed_page_count": parse_report.failed_pages,
            },
            published_at=ready_at,
            vector_index=vector_index,
            vector_index_task=vector_index_task,
        )
        if completed_task is None:
            self._delete_task_artifact_tree(task)
            completed_task = self._repository.get_pdf_upload_task(task.task_id) or task
        else:
            self._cleanup_unreferenced_terminal_task_artifacts_safely(task.file_id)
        self._refresh_batch_safely(completed_task.batch_id)
        return completed_task

    def _build_vector_index_publication(
        self,
        *,
        task: PdfUploadTask,
        chunks: list[PdfDocumentChunk],
        queued_at: str,
    ) -> tuple[PdfVectorIndex | None, PdfVectorIndexTask | None]:
        revision = self._vector_embedding_revision
        if revision is None:
            return None, None
        if task.file_id is None:
            raise UploadValidationError("PDF upload task is missing a file reference")
        source_fingerprint = ordered_content_fingerprint(
            [chunk.content_hash for chunk in chunks]
        )
        index = PdfVectorIndex(
            file_id=task.file_id,
            source_fingerprint=source_fingerprint,
            embedding_revision=revision,
            embedding_dimension=self._vector_embedding_dimension,
            status=PdfVectorIndexStatus.PENDING,
            expected_chunk_count=len(chunks),
            indexed_chunk_count=0,
            created_at=queued_at,
            updated_at=queued_at,
        )
        index_task = PdfVectorIndexTask(
            task_id=new_id("pdfvector"),
            file_id=task.file_id,
            action=PdfVectorIndexTaskAction.INDEX,
            source_fingerprint=source_fingerprint,
            embedding_revision=revision,
            status=PdfVectorIndexTaskStatus.PENDING,
            attempt_count=0,
            created_at=queued_at,
            updated_at=queued_at,
        )
        return index, index_task

    def fail_task(
        self,
        task: PdfUploadTask,
        error_message: str,
        *,
        error_code: str | None = None,
        failed_at: str | None = None,
    ) -> PdfUploadTask:
        failed_at = failed_at or utc_now_iso()
        worker_id, claim_token = self._task_claim(task)
        report: PdfParseReport | None = None
        if task.file_id is not None:
            parser_status = self._parser_profiles.status_for(task.parser_backend)
            report = build_failed_parse_report(
                file_id=task.file_id,
                parser_backend=parser_status.backend,
                parser_version=parser_status.version,
                error_message=error_message,
                failed_at=failed_at,
            )
        try:
            failed_task = self._repository.fail_pdf_parse_result(
                task_id=task.task_id,
                worker_id=worker_id,
                claim_token=claim_token,
                report=report,
                error_message=error_message,
                failed_at=failed_at,
                error_code=error_code,
            )
        except Exception:
            current_task = self._repository.get_pdf_upload_task(task.task_id)
            if (
                current_task is None
                or current_task.status != PdfUploadTaskStatus.READY
            ):
                self._delete_task_artifact_tree(task)
            raise
        if failed_task is not None:
            self._delete_task_artifact_tree(task)
        else:
            failed_task = self._repository.get_pdf_upload_task(task.task_id) or task
            if failed_task.status != PdfUploadTaskStatus.READY:
                self._delete_task_artifact_tree(task)
        self._refresh_batch_safely(failed_task.batch_id)
        return failed_task

    def _update_file_processing(
        self,
        *,
        task: PdfUploadTask,
        file_id: str,
        processing_status: PdfProcessingStatus,
        progress: int,
        status_detail: str,
        updated_at: str,
        error_message: str | None = None,
        page_count: int | None = None,
        chunk_count: int | None = None,
    ) -> None:
        worker_id, claim_token = self._task_claim(task)
        updated = self._repository.update_pdf_file_processing(
            file_id=file_id,
            processing_status=processing_status,
            progress=progress,
            status_detail=status_detail,
            updated_at=updated_at,
            error_message=error_message,
            page_count=page_count,
            chunk_count=chunk_count,
            task_id=task.task_id,
            worker_id=worker_id,
            claim_token=claim_token,
        )
        if updated is None:
            raise UploadValidationError("PDF upload task claim is no longer active")

    @staticmethod
    def _task_claim(task: PdfUploadTask) -> tuple[str, str]:
        if not task.worker_id or not task.claim_token:
            raise UploadValidationError("PDF upload task claim is incomplete")
        return task.worker_id, task.claim_token

    def fail_stale_tasks(
        self,
        *,
        cutoff_started_at: str,
        failed_at: str,
    ) -> int:
        stale_tasks = self._repository.list_stale_processing_pdf_upload_tasks(
            cutoff_started_at=cutoff_started_at
        )
        failed_count = self._repository.fail_stale_processing_pdf_upload_tasks(
            cutoff_started_at=cutoff_started_at,
            failed_at=failed_at,
        )
        for task in stale_tasks:
            persisted = self._repository.get_pdf_upload_task(task.task_id)
            if (
                persisted is None
                or persisted.error_code != "stale_processing_task"
                or task.file_id is None
            ):
                continue
            parser_status = self._parser_profiles.status_for(task.parser_backend)
            report = build_failed_parse_report(
                file_id=task.file_id,
                parser_backend=parser_status.backend,
                parser_version=parser_status.version,
                error_message=(
                    "PDF processing was interrupted. Please upload the document again."
                ),
                failed_at=failed_at,
            )
            self._repository.save_pdf_parse_report(report)
            self._repository.replace_pdf_parse_pages(task.file_id, report.pages)
            self._repository.replace_pdf_parse_artifacts(task.file_id, report.artifacts)
            self._delete_task_artifact_tree(persisted)
            self._refresh_batch_safely(task.batch_id)
        return failed_count

    def _refresh_batch_safely(self, batch_id: str | None) -> None:
        if not batch_id:
            return
        try:
            self._refresh_batch(batch_id)
        except Exception:
            logger.warning(
                "Failed to refresh PDF upload batch projection",
                extra={"batch_id": batch_id},
                exc_info=True,
            )

    def _build_parse_result(
        self,
        *,
        task: PdfUploadTask,
        file_id: str,
        filename: str,
        content: bytes,
        parser_profile_id: str | None = None,
    ) -> tuple[PdfDocumentDetail, list[PdfDocumentChunk], PdfParseReport]:
        parser = self._parser_profiles.parser_for(parser_profile_id)
        parser_status = self._parser_profiles.status_for(parser_profile_id)
        parsed = parser.parse(filename=filename, content=content)
        if not self._repository.is_pdf_upload_task_claim_active(
            task_id=task.task_id,
            worker_id=task.worker_id or "",
            claim_token=task.claim_token or "",
            checked_at=utc_now_iso(),
        ):
            raise UploadValidationError("PDF upload task claim is no longer active")
        parsed = self._archive_artifacts(
            file_id=file_id,
            task_id=task.task_id,
            claim_token=task.claim_token or "",
            parsed=parsed,
        )
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
        chunks = self._indexing.build_document_chunks(
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
        return detail, chunks, report

    def _archive_artifacts(
        self,
        *,
        file_id: str,
        task_id: str,
        claim_token: str,
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
            archive_root = (
                self._files_root
                / file_id
                / "task-artifacts"
                / task_id
                / claim_token
            ).resolve()
            if not archive_root.is_relative_to(self._files_root):
                raise UploadValidationError("PDF artifact archive path is invalid")
            if not claim_token or archive_root.name != claim_token:
                raise UploadValidationError("PDF artifact claim path is invalid")
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

    def _delete_task_artifact_tree(self, task: PdfUploadTask) -> None:
        if task.file_id is None or not task.claim_token:
            return
        target = (
            self._files_root
            / task.file_id
            / "task-artifacts"
            / task.task_id
            / task.claim_token
        ).resolve()
        expected_parent = (
            self._files_root / task.file_id / "task-artifacts" / task.task_id
        ).resolve()
        if target.parent == expected_parent and target.name == task.claim_token:
            shutil.rmtree(target, ignore_errors=True)

    def _cleanup_unreferenced_terminal_task_artifacts(self, file_id: str) -> int:
        task_artifacts_root = (
            self._files_root / file_id / "task-artifacts"
        ).resolve()
        expected_file_root = (self._files_root / file_id).resolve()
        if (
            task_artifacts_root.parent != expected_file_root
            or not task_artifacts_root.is_dir()
            or task_artifacts_root.is_symlink()
        ):
            return 0
        referenced_paths: list[Path] = []
        for artifact in self._repository.list_pdf_parse_artifacts(file_id):
            if not artifact.path:
                continue
            try:
                referenced_paths.append(
                    self._upload_records.stored_file_path(artifact.path)
                )
            except UploadValidationError:
                logger.warning(
                    "Ignoring unsafe PDF parse artifact reference during cleanup",
                    extra={"file_id": file_id, "artifact_id": artifact.artifact_id},
                )
        deleted = 0
        for task_root in task_artifacts_root.iterdir():
            if not task_root.is_dir() or task_root.is_symlink():
                continue
            task = self._repository.get_pdf_upload_task(task_root.name)
            if (
                task is None
                or task.file_id != file_id
                or task.status
                in {PdfUploadTaskStatus.QUEUED, PdfUploadTaskStatus.PROCESSING}
            ):
                continue
            for claim_root in task_root.iterdir():
                resolved_claim_root = claim_root.resolve()
                if (
                    not claim_root.is_dir()
                    or claim_root.is_symlink()
                    or resolved_claim_root.parent != task_root.resolve()
                ):
                    continue
                if any(
                    path == resolved_claim_root or path.is_relative_to(resolved_claim_root)
                    for path in referenced_paths
                ):
                    continue
                shutil.rmtree(resolved_claim_root)
                deleted += 1
            try:
                task_root.rmdir()
            except OSError:
                pass
        try:
            task_artifacts_root.rmdir()
        except OSError:
            pass
        return deleted

    def _cleanup_unreferenced_terminal_task_artifacts_safely(self, file_id: str) -> None:
        try:
            self._cleanup_unreferenced_terminal_task_artifacts(file_id)
        except Exception:
            logger.warning(
                "Failed to clean unreferenced PDF task artifacts",
                extra={"file_id": file_id},
                exc_info=True,
            )
