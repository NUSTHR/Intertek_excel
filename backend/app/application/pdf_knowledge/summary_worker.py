import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta

from app.application.pdf_knowledge.service import PdfKnowledgeService
from app.core.time import utc_now_iso
from app.domain.models import PdfSummaryTask
from app.ports.repository import PdfKnowledgeRepository

logger = logging.getLogger(__name__)


class PdfSummaryTaskWorker:
    def __init__(
        self,
        *,
        repository: PdfKnowledgeRepository,
        pdf_knowledge: PdfKnowledgeService,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self._repository = repository
        self._pdf_knowledge = pdf_knowledge
        self._poll_interval_seconds = max(0.1, poll_interval_seconds)
        self._worker_id = f"pdf-summary-worker-{uuid.uuid4()}"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="pdf-summary-task-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.1, timeout_seconds))

    def run_once(self) -> bool:
        task = self._repository.claim_next_pdf_summary_task(
            worker_id=self._worker_id,
            started_at=utc_now_iso(),
        )
        if task is None:
            return False
        self._process_task(task)
        return True

    def mark_stale_running_tasks_failed(self, *, max_running_age_minutes: int) -> int:
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=max(1, max_running_age_minutes))
        return self._pdf_knowledge.fail_stale_running_summary_tasks(
            cutoff_started_at=cutoff.isoformat(timespec="seconds"),
            failed_at=now.isoformat(timespec="seconds"),
        )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = self.run_once()
            except Exception:
                logger.exception("PDF summary task worker iteration failed")
                processed = False
            if not processed:
                self._stop_event.wait(self._poll_interval_seconds)

    def _process_task(self, task: PdfSummaryTask) -> None:
        try:
            self._pdf_knowledge.process_summary_task(task)
        except Exception as exc:
            self._pdf_knowledge.fail_summary_task(task, _safe_summary_error_message(exc))


def _safe_summary_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return "PDF summary generation failed."
    return message[:500]
