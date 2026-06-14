from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock

from app.core.time import utc_now_iso
from app.ports.repository import AuthRepository


@dataclass
class _AttemptWindow:
    failures: int
    first_failure_at: float
    blocked_until: float


class AuthenticationRateLimiter:
    def __init__(
        self,
        *,
        max_failed_attempts: int,
        window_seconds: int,
        repository: AuthRepository | None = None,
    ) -> None:
        self._max_failed_attempts = max(1, max_failed_attempts)
        self._window_seconds = max(1, window_seconds)
        self._repository = repository
        self._attempts: dict[str, _AttemptWindow] = {}
        self._lock = Lock()

    def retry_after_seconds(self, key: str) -> int | None:
        if self._repository is not None:
            return self._repository.get_login_rate_limit_retry_after(key, utc_now_iso())
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now)
            window = self._attempts.get(key)
            if window is None or window.blocked_until <= now:
                return None
            return max(1, int(window.blocked_until - now))

    def record_failure(self, key: str) -> int | None:
        if self._repository is not None:
            return self._repository.record_login_rate_limit_failure(
                key,
                now=utc_now_iso(),
                max_failed_attempts=self._max_failed_attempts,
                window_seconds=self._window_seconds,
            )
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now)
            window = self._attempts.get(key)
            if window is None:
                window = _AttemptWindow(
                    failures=0,
                    first_failure_at=now,
                    blocked_until=0.0,
                )
                self._attempts[key] = window
            if now - window.first_failure_at > self._window_seconds:
                window.failures = 0
                window.first_failure_at = now
                window.blocked_until = 0.0
            window.failures += 1
            if window.failures >= self._max_failed_attempts:
                window.blocked_until = max(
                    window.blocked_until,
                    window.first_failure_at + self._window_seconds,
                )
                return max(1, int(window.blocked_until - now))
        return None

    def record_success(self, key: str) -> None:
        if self._repository is not None:
            self._repository.clear_login_rate_limit(key)
            return
        with self._lock:
            self._attempts.pop(key, None)

    def _prune_locked(self, now: float) -> None:
        expired_keys = [
            key
            for key, window in self._attempts.items()
            if now - window.first_failure_at > self._window_seconds
            and window.blocked_until <= now
        ]
        for key in expired_keys:
            self._attempts.pop(key, None)
