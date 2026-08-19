import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

HeartbeatCallback = Callable[[str, str], bool]


def task_lease_window(lease_seconds: float) -> tuple[str, str]:
    now = datetime.now(UTC)
    lease_duration = max(5.0, lease_seconds)
    return (
        now.isoformat(timespec="seconds"),
        (now + timedelta(seconds=lease_duration)).isoformat(timespec="seconds"),
    )


class TaskLeaseHeartbeat:
    """Renews a claimed task lease without extending an expired or revoked claim."""

    def __init__(
        self,
        *,
        callback: HeartbeatCallback,
        lease_seconds: float,
        task_id: str,
    ) -> None:
        self._callback = callback
        self._lease_seconds = max(5.0, lease_seconds)
        self._interval_seconds = max(1.0, min(30.0, self._lease_seconds / 3))
        self._task_id = task_id
        self._stop_event = threading.Event()
        self._claim_lost = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def claim_lost(self) -> bool:
        return self._claim_lost.is_set()

    def __enter__(self) -> "TaskLeaseHeartbeat":
        self._thread = threading.Thread(
            target=self._run,
            name=f"task-lease-heartbeat-{self._task_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval_seconds + 1.0))

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            heartbeat_at, lease_expires_at = task_lease_window(self._lease_seconds)
            try:
                renewed = self._callback(heartbeat_at, lease_expires_at)
            except Exception:
                logger.warning(
                    "Task lease heartbeat failed",
                    extra={"task_id": self._task_id},
                    exc_info=True,
                )
                continue
            if not renewed:
                self._claim_lost.set()
                self._stop_event.set()
