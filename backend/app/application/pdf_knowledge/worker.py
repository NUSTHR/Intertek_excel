import logging
import shutil
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.application.pdf_knowledge.service import PdfKnowledgeService
from app.core.errors import ExcelWorkspaceError, UploadValidationError
from app.core.time import utc_now_iso
from app.domain.models import PdfUploadTask
from app.ports.repository import PdfKnowledgeRepository

logger = logging.getLogger(__name__)


class PdfUploadTaskWorker:
    def __init__(
        self,
        *,
        repository: PdfKnowledgeRepository,
        pdf_knowledge: PdfKnowledgeService,
        storage_root: Path | None = None,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self._repository = repository
        self._pdf_knowledge = pdf_knowledge
        self._storage_root = storage_root.expanduser().resolve() if storage_root else None
        self._staging_root = (
            (self._storage_root / "pdf-knowledge" / "upload-tasks").resolve()
            if self._storage_root
            else None
        )
        self._poll_interval_seconds = max(0.1, poll_interval_seconds)
        self._worker_id = f"pdf-worker-{uuid.uuid4()}"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="pdf-upload-task-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.1, timeout_seconds))

    def run_once(self) -> bool:
        task = self._repository.claim_next_pdf_upload_task(
            worker_id=self._worker_id,
            started_at=utc_now_iso(),
        )
        if task is None:
            return False
        self._process_task(task)
        return True

    def mark_stale_processing_tasks_failed(self, *, max_processing_age_minutes: int) -> int:
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=max(1, max_processing_age_minutes))
        return self._repository.fail_stale_processing_pdf_upload_tasks(
            cutoff_started_at=cutoff.isoformat(timespec="seconds"),
            failed_at=now.isoformat(timespec="seconds"),
        )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = self.run_once()
            except Exception:
                logger.exception("PDF upload task worker iteration failed")
                processed = False
            if not processed:
                self._stop_event.wait(self._poll_interval_seconds)

    def _process_task(self, task: PdfUploadTask) -> None:
        try:
            staging_path = self._validated_staging_path(task)
            content = staging_path.read_bytes()
            self._pdf_knowledge.parse_and_index_task(task, content)
            self._delete_staging_tree(task)
        except Exception as exc:
            failure_recorded = False
            try:
                self._pdf_knowledge.fail_task(
                    task,
                    _safe_task_error_message(exc),
                    error_code=_error_code_for_exception(exc),
                )
                failure_recorded = True
            finally:
                if failure_recorded:
                    self._delete_staging_tree(task)

    def _delete_staging_tree(self, task: PdfUploadTask) -> None:
        try:
            _delete_pdf_staging_path(
                self._staging_path(task),
                task.task_id,
                staging_root=self._staging_root,
            )
        except Exception:
            logger.warning(
                "Failed to clean PDF upload task staging files",
                extra={"task_id": task.task_id},
                exc_info=True,
            )

    def _validated_staging_path(self, task: PdfUploadTask) -> Path:
        staging_path = self._staging_path(task)
        if self._staging_root is None:
            return staging_path
        expected_task_dir = (self._staging_root / task.task_id).resolve()
        if not staging_path.is_relative_to(expected_task_dir) or staging_path == expected_task_dir:
            raise ExcelWorkspaceError("PDF upload task staging path is invalid")
        return staging_path

    def _staging_path(self, task: PdfUploadTask) -> Path:
        path = Path(task.staging_path).expanduser()
        if path.is_absolute():
            return path.resolve()
        if ".." in path.parts:
            raise ExcelWorkspaceError("PDF upload task staging path is invalid")
        if self._storage_root is None:
            return path.resolve()
        return (self._storage_root / path).resolve()


def _delete_pdf_staging_path(
    staging_path: Path,
    task_id: str,
    *,
    staging_root: Path | None = None,
) -> None:
    task_path = staging_path.expanduser().resolve()
    task_dir = task_path.parent
    if staging_root is not None:
        expected_task_dir = (staging_root / task_id).resolve()
        if not task_path.is_relative_to(expected_task_dir):
            raise ExcelWorkspaceError(
                "refusing to delete PDF upload staging path outside task directory"
            )
        shutil.rmtree(expected_task_dir, ignore_errors=True)
        return
    if task_dir.name != task_id:
        raise ExcelWorkspaceError(
            "refusing to delete PDF upload staging path outside task directory"
        )
    shutil.rmtree(task_dir, ignore_errors=True)


def _safe_task_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return "PDF parsing failed."
    return message[:500]


def _error_code_for_exception(exc: Exception) -> str:
    if isinstance(exc, UploadValidationError):
        return "upload_validation_failed"
    if isinstance(exc, ExcelWorkspaceError):
        return "task_processing_failed"
    if isinstance(exc, TimeoutError):
        return "parser_timeout"
    if isinstance(exc, OSError):
        return "staging_io_failed"
    return "parser_failed"
