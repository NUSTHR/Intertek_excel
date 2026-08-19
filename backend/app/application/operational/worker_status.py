from dataclasses import dataclass
from threading import Lock

from app.core.time import utc_now_iso


@dataclass(frozen=True)
class WorkerRuntimeStatus:
    running: bool
    state: str
    started_at: str | None
    last_poll_at: str | None
    last_success_at: str | None
    last_failure_at: str | None
    current_task_started_at: str | None
    consecutive_loop_failures: int


class WorkerRuntimeTracker:
    """Thread-safe operational telemetry for an in-process task worker."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._state = "stopped"
        self._started_at: str | None = None
        self._last_poll_at: str | None = None
        self._last_success_at: str | None = None
        self._last_failure_at: str | None = None
        self._current_task_started_at: str | None = None
        self._consecutive_loop_failures = 0

    def mark_started(self) -> None:
        now = utc_now_iso()
        with self._lock:
            self._state = "idle"
            self._started_at = now
            self._last_poll_at = now
            self._current_task_started_at = None
            self._consecutive_loop_failures = 0

    def mark_poll(self) -> None:
        with self._lock:
            self._last_poll_at = utc_now_iso()
            if self._state != "busy":
                self._state = "idle"

    def mark_task_started(self) -> None:
        with self._lock:
            self._state = "busy"
            self._current_task_started_at = utc_now_iso()

    def mark_task_finished(self, *, succeeded: bool) -> None:
        now = utc_now_iso()
        with self._lock:
            self._state = "idle"
            if succeeded:
                self._last_success_at = now
            else:
                self._last_failure_at = now
            self._last_poll_at = now
            self._current_task_started_at = None
            self._consecutive_loop_failures = 0

    def mark_loop_failure(self) -> None:
        with self._lock:
            self._state = "failed"
            self._last_failure_at = utc_now_iso()
            self._current_task_started_at = None
            self._consecutive_loop_failures += 1

    def mark_stopped(self) -> None:
        with self._lock:
            self._state = "stopped"
            self._current_task_started_at = None

    def snapshot(self, *, running: bool) -> WorkerRuntimeStatus:
        with self._lock:
            state = self._state
            if not running and state != "stopped":
                state = "dead"
            return WorkerRuntimeStatus(
                running=running,
                state=state,
                started_at=self._started_at,
                last_poll_at=self._last_poll_at,
                last_success_at=self._last_success_at,
                last_failure_at=self._last_failure_at,
                current_task_started_at=self._current_task_started_at,
                consecutive_loop_failures=self._consecutive_loop_failures,
            )
