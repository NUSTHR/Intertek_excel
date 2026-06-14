from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Event, Lock
from time import monotonic

from app.core.time import utc_now_iso
from app.ports.repository import ChatCancellationRepository


class ChatRequestCancelledError(Exception):
    """Raised when an in-flight chat request is cancelled by the user."""


@dataclass
class ChatCancellationToken:
    request_id: str
    repository: ChatCancellationRepository | None = None
    _event: Event = field(default_factory=Event)

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        if self._event.is_set():
            return True
        if self.repository is None:
            return False
        return self.repository.is_chat_request_cancelled(
            self.request_id,
            now_iso=utc_now_iso(),
        )

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise ChatRequestCancelledError(self.request_id)


class ChatCancellationRegistry:
    def __init__(
        self,
        *,
        pending_retention_seconds: float = 300.0,
        max_pending_cancellations: int = 512,
        repository: ChatCancellationRepository | None = None,
    ) -> None:
        self._tokens: dict[str, ChatCancellationToken] = {}
        self._pending_cancelled_at: dict[str, float] = {}
        self._pending_retention_seconds = pending_retention_seconds
        self._max_pending_cancellations = max_pending_cancellations
        self._repository = repository
        self._lock = Lock()

    def register(self, request_id: str | None) -> ChatCancellationToken | None:
        if not request_id:
            return None
        token = ChatCancellationToken(request_id=request_id, repository=self._repository)
        with self._lock:
            self._cleanup_pending_locked()
            cancelled_before_registration = (
                request_id in self._pending_cancelled_at
                or self._shared_request_is_cancelled(request_id)
            )
            self._pending_cancelled_at.pop(request_id, None)
            self._tokens[request_id] = token
        if cancelled_before_registration:
            token.cancel()
        return token

    def cancel(self, request_id: str) -> bool:
        shared_cancellation_recorded = self._record_shared_cancellation(request_id)
        with self._lock:
            self._cleanup_pending_locked()
            token = self._tokens.get(request_id)
            if token is None:
                self._pending_cancelled_at[request_id] = monotonic()
                self._trim_pending_locked()
                return shared_cancellation_recorded
        token.cancel()
        return True

    def unregister(self, request_id: str | None) -> None:
        if not request_id:
            return
        with self._lock:
            self._tokens.pop(request_id, None)

    def _cleanup_pending_locked(self) -> None:
        cutoff = monotonic() - self._pending_retention_seconds
        expired_ids = [
            request_id
            for request_id, cancelled_at in self._pending_cancelled_at.items()
            if cancelled_at < cutoff
        ]
        for request_id in expired_ids:
            self._pending_cancelled_at.pop(request_id, None)

    def _trim_pending_locked(self) -> None:
        if len(self._pending_cancelled_at) <= self._max_pending_cancellations:
            return
        request_ids = sorted(
            self._pending_cancelled_at,
            key=lambda request_id: self._pending_cancelled_at[request_id],
        )
        for request_id in request_ids[: -self._max_pending_cancellations]:
            self._pending_cancelled_at.pop(request_id, None)

    def _shared_request_is_cancelled(self, request_id: str) -> bool:
        if self._repository is None:
            return False
        return self._repository.is_chat_request_cancelled(
            request_id,
            now_iso=utc_now_iso(),
        )

    def _record_shared_cancellation(self, request_id: str) -> bool:
        if self._repository is None:
            return False
        cancelled_at = datetime.now(UTC)
        expires_at = cancelled_at + timedelta(seconds=self._pending_retention_seconds)
        self._repository.record_chat_cancellation(
            request_id=request_id,
            cancelled_at=cancelled_at.isoformat(timespec="seconds"),
            expires_at=expires_at.isoformat(timespec="seconds"),
        )
        return True
