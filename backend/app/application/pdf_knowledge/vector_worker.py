import logging
import threading
import time
import uuid

from app.application.operational.task_lease import TaskLeaseHeartbeat, task_lease_window
from app.application.operational.worker_status import (
    WorkerRuntimeStatus,
    WorkerRuntimeTracker,
)
from app.application.pdf_knowledge.vector_indexing import PdfVectorIndexingService
from app.core.errors import WorkspaceError
from app.domain.models import PdfVectorIndexTask
from app.ports.pdf_vector_index import PdfVectorIndexRepository

logger = logging.getLogger(__name__)


class PdfVectorIndexTaskWorker:
    def __init__(
        self,
        *,
        repository: PdfVectorIndexRepository,
        indexing: PdfVectorIndexingService,
        poll_interval_seconds: float = 1.0,
        lease_seconds: float = 900.0,
        max_attempts: int = 20,
        retry_max_seconds: int = 900,
        reconciliation_embedding_revision: str | None = None,
        reconciliation_embedding_dimension: int = 0,
        reconciliation_interval_seconds: float = 60.0,
        reconciliation_batch_size: int = 100,
    ) -> None:
        self._repository = repository
        self._indexing = indexing
        self._poll_interval_seconds = max(0.1, poll_interval_seconds)
        self._lease_seconds = max(5.0, lease_seconds)
        if max_attempts < 1:
            raise ValueError("vector worker max attempts must be positive")
        if retry_max_seconds < 1:
            raise ValueError("vector worker retry maximum must be positive")
        self._max_attempts = max_attempts
        self._retry_max_seconds = retry_max_seconds
        self._reconciliation_embedding_revision = (
            reconciliation_embedding_revision.strip()
            if reconciliation_embedding_revision
            else None
        )
        self._reconciliation_embedding_dimension = reconciliation_embedding_dimension
        self._reconciliation_interval_seconds = max(
            5.0, reconciliation_interval_seconds
        )
        self._reconciliation_batch_size = max(1, reconciliation_batch_size)
        self._next_reconciliation_at = 0.0
        self._worker_id = f"pdf-vector-worker-{uuid.uuid4()}"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._runtime = WorkerRuntimeTracker()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._runtime.mark_started()
        self._reconcile_if_due(force=True)
        self._thread = threading.Thread(
            target=self._run,
            name="pdf-vector-index-task-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.1, timeout_seconds))
            if not self._thread.is_alive():
                self._runtime.mark_stopped()

    def runtime_status(self) -> WorkerRuntimeStatus:
        return self._runtime.snapshot(
            running=self._thread is not None and self._thread.is_alive(),
        )

    def run_once(self) -> bool:
        started_at, lease_expires_at = task_lease_window(self._lease_seconds)
        task = self._repository.claim_next_pdf_vector_index_task(
            worker_id=self._worker_id,
            started_at=started_at,
            lease_expires_at=lease_expires_at,
            max_attempts=self._max_attempts,
        )
        if task is None:
            return False
        self._runtime.mark_task_started()
        succeeded = False
        try:
            succeeded = self._process_task(task)
        finally:
            self._runtime.mark_task_finished(succeeded=succeeded)
        return True

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                self._reconcile_if_due()
                self._runtime.mark_poll()
                try:
                    processed = self.run_once()
                except Exception:
                    self._runtime.mark_loop_failure()
                    logger.exception("PDF vector worker iteration failed")
                    processed = False
                if not processed:
                    self._stop_event.wait(self._poll_interval_seconds)
        finally:
            self._runtime.mark_stopped()

    def _reconcile_if_due(self, *, force: bool = False) -> None:
        revision = self._reconciliation_embedding_revision
        if revision is None:
            return
        current = time.monotonic()
        if not force and current < self._next_reconciliation_at:
            return
        self._next_reconciliation_at = current + self._reconciliation_interval_seconds
        try:
            queued_count = self._repository.reconcile_pdf_vector_index_queue(
                embedding_revision=revision,
                embedding_dimension=self._reconciliation_embedding_dimension,
                batch_size=self._reconciliation_batch_size,
                queued_at=_utc_now_iso(),
            )
            if queued_count:
                logger.info(
                    "reconciled missing or stale PDF vector projections",
                    extra={"queued_count": queued_count},
                )
        except Exception:
            self._runtime.mark_loop_failure()
            logger.exception("PDF vector projection reconciliation failed")

    def _process_task(self, task: PdfVectorIndexTask) -> bool:
        heartbeat = TaskLeaseHeartbeat(
            callback=lambda heartbeat_at, renewed_until: (
                self._repository.heartbeat_pdf_vector_index_task(
                    task_id=task.task_id,
                    worker_id=self._worker_id,
                    claim_token=task.claim_token or "",
                    heartbeat_at=heartbeat_at,
                    lease_expires_at=renewed_until,
                )
            ),
            lease_seconds=self._lease_seconds,
            task_id=task.task_id,
        )

        def fence_claim() -> None:
            if heartbeat.claim_lost:
                raise RuntimeError("PDF vector task claim was lost")
            heartbeat_at, renewed_until = task_lease_window(self._lease_seconds)
            if not self._repository.heartbeat_pdf_vector_index_task(
                task_id=task.task_id,
                worker_id=self._worker_id,
                claim_token=task.claim_token or "",
                heartbeat_at=heartbeat_at,
                lease_expires_at=renewed_until,
            ):
                raise RuntimeError("PDF vector task claim was lost")

        try:
            with heartbeat:
                completed = self._indexing.process_task(
                    task,
                    claim_fence=fence_claim,
                    cancellation_checker=lambda: _raise_if_claim_lost(heartbeat),
                )
            return completed is not None
        except Exception as exc:
            error_code, retryable = _vector_failure_metadata(exc)
            self._repository.fail_pdf_vector_index_task(
                task_id=task.task_id,
                worker_id=self._worker_id,
                claim_token=task.claim_token or "",
                error_message=_safe_vector_error_message(exc),
                error_code=error_code,
                retryable=retryable,
                failed_at=_utc_now_iso(),
                max_attempts=self._max_attempts,
                retry_max_seconds=self._retry_max_seconds,
                retry_after_seconds=getattr(exc, "retry_after_seconds", None),
            )
            return False


def _raise_if_claim_lost(heartbeat: TaskLeaseHeartbeat) -> None:
    if heartbeat.claim_lost:
        raise RuntimeError("PDF vector task claim was lost")


def _safe_vector_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    return (message or "PDF vector indexing failed.")[:1000]


def _vector_failure_metadata(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, WorkspaceError):
        return exc.code, exc.retryable
    if isinstance(exc, ValueError):
        return "PDF_VECTOR_INVALID_INPUT", False
    if isinstance(exc, (TimeoutError, ConnectionError, OSError, RuntimeError)):
        return "PDF_VECTOR_TRANSIENT_FAILURE", True
    return "PDF_VECTOR_UNEXPECTED_FAILURE", True


def _utc_now_iso() -> str:
    from app.core.time import utc_now_iso

    return utc_now_iso()
