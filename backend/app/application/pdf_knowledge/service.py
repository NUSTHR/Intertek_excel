import os
import tempfile
from pathlib import Path, PurePosixPath

from app.application.pdf_knowledge.indexing import PdfIndexingService
from app.application.pdf_knowledge.models import PdfChunkSearchResult
from app.application.pdf_knowledge.retrieval import PdfRetrievalService
from app.core.errors import AssetNotFoundError, UploadValidationError
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    PdfDocumentChunk,
    PdfDocumentDetail,
    PdfDocumentSummary,
    PdfFile,
    PdfFileKind,
    PdfFileStatus,
    PdfFileVisibility,
    PdfModelSetting,
    PdfPreviewBlock,
    PdfProcessingStatus,
    PdfSchemaItem,
    PdfUploadTask,
    PdfUploadTaskStage,
    PdfUploadTaskStatus,
    UserRole,
)
from app.ports.pdf_parser import PdfParser, PdfParserRuntimeStatus
from app.ports.repository import PdfKnowledgeRepository

DEFAULT_PDF_MODEL_SETTINGS = (
    ("summary", "Summary Engine"),
    ("router", "Router Engine"),
    ("chat", "Chat Engine"),
)
DEFAULT_PROVIDERS = ["SiliconFlow", "DeepSeek"]
DEFAULT_MODELS = ["deepseek-v3", "gpt-4o"]
SUPPORTED_EXTENSIONS = {".pdf", ".csv", ".xlsx", ".xls"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MODEL_SETTING_ORDER = {
    setting_id: index
    for index, (setting_id, _label) in enumerate(DEFAULT_PDF_MODEL_SETTINGS)
}


class PdfKnowledgeService:
    def __init__(
        self,
        *,
        repository: PdfKnowledgeRepository,
        storage_root: Path,
        parser: PdfParser,
        parser_status: PdfParserRuntimeStatus | None = None,
        indexing: PdfIndexingService | None = None,
        retrieval: PdfRetrievalService | None = None,
    ) -> None:
        self._repository = repository
        self._storage_root = storage_root.expanduser().resolve()
        self._files_root = (self._storage_root / "pdf-knowledge" / "files").resolve()
        self._staging_root = (self._storage_root / "pdf-knowledge" / "upload-tasks").resolve()
        self._parser = parser
        self._parser_status = parser_status or PdfParserRuntimeStatus(
            backend=parser.__class__.__name__,
            available=True,
            detail="PDF parser instance is configured.",
        )
        self._indexing = indexing or PdfIndexingService(repository=repository)
        self._retrieval = retrieval or PdfRetrievalService(repository=repository)

    def list_files(self, *, user_role: UserRole) -> list[PdfFile]:
        files = self._repository.list_pdf_files()
        if user_role == UserRole.ADMIN:
            return files
        return [
            file
            for file in files
            if file.visibility == PdfFileVisibility.VISIBLE
        ]

    def get_parser_status(self) -> PdfParserRuntimeStatus:
        return self._parser_status

    def get_file(self, file_id: str, *, user_role: UserRole) -> PdfFile:
        file = self._repository.get_pdf_file(file_id)
        if file is None or (
            user_role != UserRole.ADMIN and file.visibility != PdfFileVisibility.VISIBLE
        ):
            raise AssetNotFoundError("PDF file was not found")
        return file

    def create_upload_task(
        self,
        *,
        user_id: str,
        original_filename: str,
        content: bytes,
        relative_path: str | None = None,
    ) -> PdfUploadTask:
        self._validate_upload(original_filename, content)
        now = utc_now_iso()
        file_id = new_id("pdf")
        task_id = new_id("pdfupload")
        sanitized_path = self._sanitize_relative_path(relative_path or original_filename)
        parent_id = self._ensure_folder_hierarchy(
            user_id=user_id,
            path_parts=sanitized_path.parts[:-1],
            created_at=now,
        )
        staging_path = self._write_staging_file(task_id, original_filename, content)
        storage_path = self._store_original_file(file_id, original_filename, content)
        file = PdfFile(
            file_id=file_id,
            user_id=user_id,
            parent_id=parent_id,
            display_name=sanitized_path.name,
            original_filename=Path(original_filename).name,
            kind=self._kind_from_filename(original_filename),
            size_bytes=len(content),
            storage_path=self._storage_reference(storage_path),
            status=PdfFileStatus.ACTIVE,
            visibility=PdfFileVisibility.VISIBLE,
            processing_status=PdfProcessingStatus.QUEUED,
            progress=5,
            status_detail="Queued for MinerU parsing.",
            error_message=None,
            page_count=None,
            chunk_count=None,
            created_at=now,
            updated_at=now,
        )
        task = PdfUploadTask(
            task_id=task_id,
            user_id=user_id,
            file_id=file_id,
            original_filename=Path(original_filename).name,
            staging_path=self._storage_reference(staging_path),
            status=PdfUploadTaskStatus.QUEUED,
            progress=5,
            detail="Queued for MinerU parsing.",
            error_message=None,
            result={},
            created_at=now,
            updated_at=now,
            stage=PdfUploadTaskStage.QUEUED,
            parser_backend=self._parser_status.backend,
        )
        self._repository.create_pdf_file(file)
        self._repository.create_pdf_upload_task(task)
        return task

    def get_upload_task(self, task_id: str, *, user_id: str) -> PdfUploadTask:
        task = self._repository.get_pdf_upload_task(task_id)
        if task is None or task.user_id != user_id:
            raise AssetNotFoundError("PDF upload task was not found")
        return task

    def list_upload_tasks(self, *, user_id: str) -> list[PdfUploadTask]:
        return self._repository.list_pdf_upload_tasks(user_id)

    def parse_and_index_task(self, task: PdfUploadTask, content: bytes) -> PdfUploadTask:
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
        page_count, chunk_count = self._parse_and_index(
            file_id=task.file_id,
            filename=task.original_filename,
            content=content,
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
        ready_at = utc_now_iso()
        self._repository.update_pdf_file_processing(
            file_id=task.file_id,
            processing_status=PdfProcessingStatus.READY,
            progress=100,
            status_detail="Ready for PDF-grounded chat.",
            updated_at=ready_at,
            page_count=page_count,
            chunk_count=chunk_count,
        )
        return self._repository.complete_pdf_upload_task(
            task_id=task.task_id,
            result={"file_id": task.file_id},
            finished_at=ready_at,
        ) or task

    def fail_task(
        self,
        task: PdfUploadTask,
        error_message: str,
        *,
        error_code: str | None = None,
    ) -> PdfUploadTask:
        failed_at = utc_now_iso()
        if task.file_id is not None:
            self._repository.update_pdf_file_processing(
                file_id=task.file_id,
                processing_status=PdfProcessingStatus.FAILED,
                progress=100,
                status_detail="PDF parsing failed.",
                updated_at=failed_at,
                error_message=error_message,
            )
        return self._repository.fail_pdf_upload_task(
            task_id=task.task_id,
            error_message=error_message,
            failed_at=failed_at,
            error_code=error_code,
        ) or task

    def get_document_detail(self, file_id: str, *, user_role: UserRole) -> PdfDocumentDetail:
        file = self.get_file(file_id, user_role=user_role)
        detail = self._repository.get_pdf_document_detail(file.file_id)
        if detail is not None:
            return detail
        return PdfDocumentDetail(
            file_id=file.file_id,
            summary=PdfDocumentSummary(file_id=file.file_id, status="empty", content=""),
            preview_blocks=[],
            schema=[],
            tags=[],
        )

    def list_document_chunks(
        self,
        file_id: str,
        *,
        user_role: UserRole,
    ) -> list[PdfDocumentChunk]:
        file = self.get_file(file_id, user_role=user_role)
        return self._repository.list_pdf_document_chunks(file.file_id)

    def search_document_chunks(
        self,
        *,
        query: str,
        file_ids: list[str] | None,
        limit: int | None,
        user_role: UserRole,
    ) -> PdfChunkSearchResult:
        return self._retrieval.search_chunks(
            query=query,
            file_ids=file_ids,
            limit=limit,
            user_role=user_role,
        )

    def generate_summary(self, file_id: str, *, user_role: UserRole) -> PdfDocumentSummary:
        file = self.get_file(file_id, user_role=user_role)
        now = utc_now_iso()
        if file.processing_status != PdfProcessingStatus.READY:
            content = (
                "The source is still being prepared. Summary quality will improve "
                "after parsing and indexing finish."
            )
        else:
            content = (
                f"{file.display_name} is indexed and ready for PDF-grounded chat. "
                f"It contains {file.page_count or 'multiple'} pages and "
                f"{file.chunk_count or 'several'} searchable chunks."
            )
        summary = PdfDocumentSummary(
            file_id=file.file_id,
            status="ready",
            content=content,
            updated_at=now,
        )
        self._repository.save_pdf_document_summary(summary)
        return summary

    def list_model_settings(self) -> list[PdfModelSetting]:
        settings = self._repository.list_pdf_model_settings()
        if settings:
            return _sort_model_settings(settings)
        now = utc_now_iso()
        return [
            self._repository.save_pdf_model_setting(
                PdfModelSetting(
                    setting_id=setting_id,
                    label=label,
                    providers=list(DEFAULT_PROVIDERS),
                    models=list(DEFAULT_MODELS),
                    selected_provider=DEFAULT_PROVIDERS[0],
                    selected_model=DEFAULT_MODELS[0],
                    created_at=now,
                    updated_at=now,
                )
            )
            for setting_id, label in DEFAULT_PDF_MODEL_SETTINGS
        ]

    def update_model_setting(
        self,
        *,
        setting_id: str,
        selected_provider: str,
        selected_model: str,
    ) -> list[PdfModelSetting]:
        settings = {setting.setting_id: setting for setting in self.list_model_settings()}
        current = settings.get(setting_id)
        if current is None:
            raise AssetNotFoundError("PDF model setting was not found")
        self._repository.save_pdf_model_setting(
            PdfModelSetting(
                setting_id=current.setting_id,
                label=current.label,
                providers=current.providers,
                models=current.models,
                selected_provider=selected_provider,
                selected_model=selected_model,
                created_at=current.created_at,
                updated_at=utc_now_iso(),
            )
        )
        return self.list_model_settings()

    def _parse_and_index(self, *, file_id: str, filename: str, content: bytes) -> tuple[int, int]:
        parsed = self._parser.parse(filename=filename, content=content)
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
        return parsed.page_count, len(chunks)

    def _validate_upload(self, filename: str, content: bytes) -> None:
        if not filename.strip():
            raise UploadValidationError("filename is required")
        if len(content) == 0:
            raise UploadValidationError("uploaded file is empty")
        if len(content) > MAX_UPLOAD_BYTES:
            raise UploadValidationError("uploaded file exceeds the 50 MB limit")
        if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise UploadValidationError("unsupported PDF knowledge file type")

    def is_supported_filename(self, filename: str) -> bool:
        return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS

    def _kind_from_filename(self, filename: str) -> PdfFileKind:
        suffix = Path(filename).suffix.lower()
        if suffix == ".csv":
            return PdfFileKind.CSV
        if suffix in {".xlsx", ".xls"}:
            return PdfFileKind.XLSX
        return PdfFileKind.PDF

    def _ensure_folder_hierarchy(
        self,
        *,
        user_id: str,
        path_parts: tuple[str, ...],
        created_at: str,
    ) -> str | None:
        parent_id: str | None = None
        for part in path_parts:
            folder = self._find_folder_by_name(
                user_id=user_id,
                parent_id=parent_id,
                name=part,
            )
            if folder is None:
                folder_id = new_id("pdffolder")
                folder = PdfFile(
                    file_id=folder_id,
                    user_id=user_id,
                    parent_id=parent_id,
                    display_name=part,
                    original_filename=part,
                    kind=PdfFileKind.FOLDER,
                    size_bytes=0,
                    storage_path=None,
                    status=PdfFileStatus.ACTIVE,
                    visibility=PdfFileVisibility.VISIBLE,
                    processing_status=PdfProcessingStatus.READY,
                    progress=100,
                    status_detail="Folder indexed",
                    error_message=None,
                    page_count=None,
                    chunk_count=None,
                    created_at=created_at,
                    updated_at=created_at,
                )
                self._repository.create_pdf_file(folder)
            parent_id = folder.file_id
        return parent_id

    def _find_folder_by_name(
        self,
        *,
        user_id: str,
        parent_id: str | None,
        name: str,
    ) -> PdfFile | None:
        for file in self._repository.list_pdf_files():
            if (
                file.kind == PdfFileKind.FOLDER
                and file.user_id == user_id
                and file.parent_id == parent_id
                and file.display_name == name
            ):
                return file
        return None

    def _sanitize_relative_path(self, value: str) -> Path:
        normalized = value.replace("\\", "/")
        parts = tuple(
            part.strip()
            for part in PurePosixPath(normalized).parts
            if part.strip()
            and part.strip() not in {".", "..", "/"}
            and not part.strip().endswith(":")
        )
        if not parts:
            raise UploadValidationError("filename is required")
        return Path(*parts)

    def _write_staging_file(self, task_id: str, filename: str, content: bytes) -> Path:
        task_dir = (self._staging_root / task_id).resolve()
        task_dir.mkdir(parents=True, exist_ok=True)
        path = (task_dir / (Path(filename).name or "uploaded.pdf")).resolve()
        if not path.is_relative_to(task_dir):
            raise UploadValidationError("upload staging path is invalid")
        self._write_bytes_atomic(path, content)
        return path

    def _store_original_file(self, file_id: str, filename: str, content: bytes) -> Path:
        file_dir = (self._files_root / file_id).resolve()
        file_dir.mkdir(parents=True, exist_ok=True)
        path = (file_dir / (Path(filename).name or "uploaded.pdf")).resolve()
        if not path.is_relative_to(file_dir):
            raise UploadValidationError("PDF storage path is invalid")
        self._write_bytes_atomic(path, content)
        return path

    def _write_bytes_atomic(self, path: Path, content: bytes) -> None:
        temporary_file = tempfile.NamedTemporaryFile(
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_file.name)
        try:
            with temporary_file:
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            temporary_path.replace(path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    def _storage_reference(self, path: Path) -> str:
        resolved_path = path.expanduser().resolve()
        if not resolved_path.is_relative_to(self._storage_root):
            raise UploadValidationError("PDF storage path is invalid")
        return resolved_path.relative_to(self._storage_root).as_posix()


def _sort_model_settings(settings: list[PdfModelSetting]) -> list[PdfModelSetting]:
    return sorted(
        settings,
        key=lambda setting: (
            MODEL_SETTING_ORDER.get(setting.setting_id, len(MODEL_SETTING_ORDER)),
            setting.setting_id,
        ),
    )
