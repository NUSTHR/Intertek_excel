import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.core.errors import UploadValidationError
from app.core.ids import new_id
from app.domain.models import (
    PdfFile,
    PdfFileKind,
    PdfFileStatus,
    PdfFileVisibility,
    PdfProcessingStatus,
    PdfUploadRecord,
    PdfUploadTask,
    PdfUploadTaskStage,
    PdfUploadTaskStatus,
)

SUPPORTED_EXTENSIONS = {".pdf"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class PdfUploadCandidate:
    original_filename: str
    content: bytes
    relative_path: str | None = None


@dataclass(frozen=True)
class PdfUploadCandidateInspection:
    accepted: list[PdfUploadCandidate]
    skipped: list[dict[str, object]]


class PdfUploadRecordBuilder:
    def __init__(
        self,
        *,
        storage_root: Path,
    ) -> None:
        self._storage_root = storage_root.expanduser().resolve()
        self._files_root = (self._storage_root / "pdf-knowledge" / "files").resolve()
        self._staging_root = (self._storage_root / "pdf-knowledge" / "upload-tasks").resolve()

    @property
    def files_root(self) -> Path:
        return self._files_root

    def build_upload_records(
        self,
        *,
        user_id: str,
        original_filename: str,
        content: bytes,
        relative_path: str | None,
        parent_id: str | None,
        created_at: str,
        batch_id: str | None,
        parser_backend: str,
    ) -> PdfUploadRecord:
        self.validate_upload(original_filename, content)
        file_id = new_id("pdf")
        task_id = new_id("pdfupload")
        sanitized_path = self._sanitize_relative_path(relative_path or original_filename)
        try:
            staging_path = self.write_staging_file(task_id, original_filename, content)
            storage_path = self._store_original_file(file_id, original_filename, content)
        except Exception:
            self._delete_managed_tree(self._staging_root, task_id)
            self._delete_managed_tree(self._files_root, file_id)
            raise
        file = PdfFile(
            file_id=file_id,
            user_id=user_id,
            parent_id=parent_id,
            display_name=sanitized_path.name,
            original_filename=Path(original_filename).name,
            kind=PdfFileKind.PDF,
            size_bytes=len(content),
            storage_path=self.storage_reference(storage_path),
            status=PdfFileStatus.ACTIVE,
            visibility=PdfFileVisibility.VISIBLE,
            processing_status=PdfProcessingStatus.QUEUED,
            progress=5,
            status_detail="Queued for MinerU parsing.",
            error_message=None,
            page_count=None,
            chunk_count=None,
            created_at=created_at,
            updated_at=created_at,
        )
        task = PdfUploadTask(
            task_id=task_id,
            user_id=user_id,
            file_id=file_id,
            original_filename=Path(original_filename).name,
            staging_path=self.storage_reference(staging_path),
            status=PdfUploadTaskStatus.QUEUED,
            progress=5,
            detail="Queued for MinerU parsing.",
            error_message=None,
            result={},
            created_at=created_at,
            updated_at=created_at,
            stage=PdfUploadTaskStage.QUEUED,
            parser_backend=parser_backend,
            batch_id=batch_id,
        )
        return PdfUploadRecord(
            file=file,
            task=task,
            folder_names=tuple(sanitized_path.parts[:-1]),
        )

    def validate_upload(self, filename: str, content: bytes) -> None:
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

    def inspect_candidates(
        self,
        candidates: list[PdfUploadCandidate],
    ) -> PdfUploadCandidateInspection:
        accepted: list[PdfUploadCandidate] = []
        skipped: list[dict[str, object]] = []
        for candidate in candidates:
            try:
                self.validate_upload(candidate.original_filename, candidate.content)
            except UploadValidationError as error:
                skipped.append(skipped_upload_detail(candidate, str(error)))
                continue
            accepted.append(candidate)
        return PdfUploadCandidateInspection(accepted=accepted, skipped=skipped)

    def write_staging_file(self, task_id: str, filename: str, content: bytes) -> Path:
        task_dir = (self._staging_root / task_id).resolve()
        task_dir.mkdir(parents=True, exist_ok=True)
        path = (task_dir / (Path(filename).name or "uploaded.pdf")).resolve()
        if not path.is_relative_to(task_dir):
            raise UploadValidationError("upload staging path is invalid")
        self._write_bytes_atomic(path, content)
        return path

    def delete_staging_task(self, task_id: str) -> None:
        self._delete_managed_tree(self._staging_root, task_id)

    def delete_upload_record(self, record: PdfUploadRecord) -> None:
        self._delete_managed_tree(self._staging_root, record.task.task_id)
        self._delete_managed_tree(self._files_root, record.file.file_id)

    def stored_file_path(self, storage_path: str) -> Path:
        path = Path(storage_path).expanduser()
        if path.is_absolute():
            resolved_path = path.resolve()
        else:
            if ".." in path.parts:
                raise UploadValidationError("PDF storage path is invalid")
            resolved_path = (self._storage_root / path).resolve()
        if not resolved_path.is_relative_to(self._storage_root):
            raise UploadValidationError("PDF storage path is invalid")
        return resolved_path

    def storage_reference(self, path: Path) -> str:
        resolved_path = path.expanduser().resolve()
        if not resolved_path.is_relative_to(self._storage_root):
            raise UploadValidationError("PDF storage path is invalid")
        return resolved_path.relative_to(self._storage_root).as_posix()

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

    def _delete_managed_tree(self, root: Path, child_id: str) -> None:
        target = (root / child_id).resolve()
        if target.parent != root or target.name != child_id or target.is_symlink():
            raise UploadValidationError("managed upload path is invalid")
        shutil.rmtree(target, ignore_errors=True)


def source_name_for_upload_batch(
    candidates: list[PdfUploadCandidate],
    source_name: str | None,
) -> str:
    normalized = (source_name or "").strip()
    if normalized:
        return normalized[:255]
    paths = [
        PurePosixPath((candidate.relative_path or candidate.original_filename).replace("\\", "/"))
        for candidate in candidates
    ]
    first_parent = next((path.parts[0] for path in paths if len(path.parts) > 1), "")
    if first_parent:
        return first_parent[:255]
    if len(candidates) == 1:
        return Path(candidates[0].original_filename).name[:255]
    return f"{len(candidates)} uploaded documents"


def upload_batch_queued_detail(accepted_count: int, skipped_count: int) -> str:
    document_label = "document" if accepted_count == 1 else "documents"
    if skipped_count == 0:
        return f"Queued {accepted_count} {document_label}."
    skipped_label = "file" if skipped_count == 1 else "files"
    return f"Queued {accepted_count} {document_label}; skipped {skipped_count} {skipped_label}."


def skipped_upload_detail(
    candidate: PdfUploadCandidate,
    reason: str,
) -> dict[str, object]:
    return {
        "filename": Path(candidate.original_filename).name or candidate.original_filename,
        "relative_path": candidate.relative_path or candidate.original_filename,
        "size_bytes": len(candidate.content),
        "reason": reason,
    }


def first_skipped_upload_reason(skipped: list[dict[str, object]]) -> str | None:
    if not skipped:
        return None
    reason = skipped[0].get("reason")
    return reason if isinstance(reason, str) and reason.strip() else None
