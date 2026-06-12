from dataclasses import dataclass, field
from threading import Event, Lock
from time import monotonic


class ChatRequestCancelledError(Exception):
    """Raised when an in-flight chat request is cancelled by the user."""


@dataclass
class ChatCancellationToken:
    request_id: str
    _event: Event = field(default_factory=Event)

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise ChatRequestCancelledError(self.request_id)


class ChatCancellationRegistry:
    def __init__(
        self,
        *,
        pending_retention_seconds: float = 300.0,
        max_pending_cancellations: int = 512,
    ) -> None:
        self._tokens: dict[str, ChatCancellationToken] = {}
        self._pending_cancelled_at: dict[str, float] = {}
        self._pending_retention_seconds = pending_retention_seconds
        self._max_pending_cancellations = max_pending_cancellations
        self._lock = Lock()

    def register(self, request_id: str | None) -> ChatCancellationToken | None:
        if not request_id:
            return None
        token = ChatCancellationToken(request_id=request_id)
        with self._lock:
            self._cleanup_pending_locked()
            cancelled_before_registration = request_id in self._pending_cancelled_at
            self._pending_cancelled_at.pop(request_id, None)
            self._tokens[request_id] = token
        if cancelled_before_registration:
            token.cancel()
        return token

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            self._cleanup_pending_locked()
            token = self._tokens.get(request_id)
            if token is None:
                self._pending_cancelled_at[request_id] = monotonic()
                self._trim_pending_locked()
                return False
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
