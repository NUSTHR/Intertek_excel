import logging
import os
import shutil
import tempfile
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.application.excel_assets.models import UploadExcelResult
from app.application.excel_assets.service import ExcelAssetService
from app.core.errors import AssetNotFoundError, ExcelWorkspaceError
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import ExcelUploadTask, ExcelUploadTaskStatus
from app.ports.repository import ExcelUploadTaskRepository

logger = logging.getLogger(__name__)


class UploadTaskService:
    def __init__(
        self,
        *,
        repository: ExcelUploadTaskRepository,
        storage_root: Path,
    ) -> None:
        self._repository = repository
        self._staging_root = (storage_root / "upload-tasks").resolve()

    def create_task(
        self,
        *,
        user_id: str,
        original_filename: str,
        content: bytes,
        replace_existing: bool,
    ) -> ExcelUploadTask:
        now = utc_now_iso()
        task_id = new_id("upload")
        staging_path = self._write_staging_file(task_id, original_filename, content)
        task = ExcelUploadTask(
            task_id=task_id,
            user_id=user_id,
            original_filename=original_filename,
            staging_path=str(staging_path),
            replace_existing=replace_existing,
            status=ExcelUploadTaskStatus.QUEUED,
            error_message=None,
            result={},
            created_at=now,
            updated_at=now,
        )
        try:
            self._repository.create_upload_task(task)
        except Exception:
            try:
                _delete_staging_path(staging_path, task_id)
            except Exception:
                logger.warning(
                    "Failed to clean staging files after upload task creation failed",
                    extra={"task_id": task_id},
                    exc_info=True,
                )
            raise
        return task

    def get_task(self, task_id: str, *, user_id: str) -> ExcelUploadTask:
        task = self._repository.get_upload_task(task_id)
        if task is None or task.user_id != user_id:
            raise AssetNotFoundError("upload task was not found")
        return task

    def mark_stale_processing_tasks_failed(self, *, max_processing_age_minutes: int) -> int:
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=max(1, max_processing_age_minutes))
        return self._repository.fail_stale_processing_upload_tasks(
            cutoff_started_at=cutoff.isoformat(timespec="seconds"),
            failed_at=now.isoformat(timespec="seconds"),
        )

    def _write_staging_file(
        self,
        task_id: str,
        original_filename: str,
        content: bytes,
    ) -> Path:
        filename = Path(original_filename).name or "workbook"
        task_dir = self._staging_root / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        staging_path = (task_dir / filename).resolve()
        if not staging_path.is_relative_to(task_dir.resolve()):
            raise ExcelWorkspaceError("upload staging path is invalid")
        self._write_bytes_atomic(staging_path, content)
        return staging_path

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


class UploadTaskWorker:
    def __init__(
        self,
        *,
        repository: ExcelUploadTaskRepository,
        excel_assets: ExcelAssetService,
        storage_root: Path | None = None,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self._repository = repository
        self._excel_assets = excel_assets
        self._staging_root = (storage_root / "upload-tasks").resolve() if storage_root else None
        self._poll_interval_seconds = max(0.1, poll_interval_seconds)
        self._worker_id = f"worker-{uuid.uuid4()}"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="excel-upload-task-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.1, timeout_seconds))

    def run_once(self) -> bool:
        task = self._repository.claim_next_upload_task(
            worker_id=self._worker_id,
            started_at=utc_now_iso(),
        )
        if task is None:
            return False
        self._process_task(task)
        return True

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = self.run_once()
            except Exception:
                logger.exception("Upload task worker iteration failed")
                processed = False
            if not processed:
                self._stop_event.wait(self._poll_interval_seconds)

    def _process_task(self, task: ExcelUploadTask) -> None:
        try:
            staging_path = self._validated_staging_path(task)
            content = staging_path.read_bytes()
            result = self._excel_assets.upload_workbook(
                original_filename=task.original_filename,
                content=content,
                replace_existing=task.replace_existing,
            )
            self._repository.complete_upload_task(
                task_id=task.task_id,
                result=_upload_result_payload(result),
                finished_at=utc_now_iso(),
            )
            self._delete_staging_tree(task)
        except Exception as exc:
            failure_recorded = False
            try:
                self._repository.fail_upload_task(
                    task_id=task.task_id,
                    error_message=str(exc),
                    finished_at=utc_now_iso(),
                )
                failure_recorded = True
            finally:
                if failure_recorded:
                    self._delete_staging_tree(task)

    def _delete_staging_tree(self, task: ExcelUploadTask) -> None:
        try:
            _delete_staging_path(
                Path(task.staging_path),
                task.task_id,
                staging_root=self._staging_root,
            )
        except Exception:
            logger.warning(
                "Failed to clean upload task staging files",
                extra={"task_id": task.task_id},
                exc_info=True,
            )

    def _validated_staging_path(self, task: ExcelUploadTask) -> Path:
        staging_path = Path(task.staging_path).expanduser().resolve()
        if self._staging_root is None:
            return staging_path
        expected_task_dir = (self._staging_root / task.task_id).resolve()
        if not staging_path.is_relative_to(expected_task_dir) or staging_path == expected_task_dir:
            raise ExcelWorkspaceError("upload task staging path is invalid")
        return staging_path


def _upload_result_payload(result: UploadExcelResult) -> dict[str, object]:
    return {
        "file_id": result.file.file_id,
        "version_id": result.version.version_id,
    }


def _delete_staging_path(
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
                "refusing to delete upload staging path outside task directory"
            )
        shutil.rmtree(expected_task_dir, ignore_errors=True)
        return
    if task_dir.name != task_id:
        raise ExcelWorkspaceError("refusing to delete upload staging path outside task directory")
    shutil.rmtree(task_dir, ignore_errors=True)
