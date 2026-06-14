import sqlite3
from datetime import UTC, datetime, timedelta

from app.adapters.repositories.sqlite.policies import SQLiteMaintenancePolicy


class SQLiteOperationalMaintenance:
    def __init__(self, policy: SQLiteMaintenancePolicy) -> None:
        self._policy = policy

    def cleanup_expired_operational_records(
        self,
        connection: sqlite3.Connection,
        *,
        now_iso: str,
    ) -> dict[str, int]:
        deleted_auth_sessions = 0
        deleted_password_reset_tokens = 0
        deleted_chat_cancellations = 0
        deleted_login_attempts = 0
        if self._table_exists(connection, "auth_sessions"):
            cutoff = self._retention_cutoff_iso(
                now_iso,
                self._policy.auth_session_retention_days,
            )
            cursor = connection.execute(
                """
                DELETE FROM auth_sessions
                WHERE expires_at < ?
                   OR (revoked_at IS NOT NULL AND revoked_at < ?)
                """,
                (cutoff, cutoff),
            )
            deleted_auth_sessions = max(0, cursor.rowcount)
        if self._table_exists(connection, "password_reset_tokens"):
            cutoff = self._retention_cutoff_iso(
                now_iso,
                self._policy.password_reset_token_retention_days,
            )
            cursor = connection.execute(
                """
                DELETE FROM password_reset_tokens
                WHERE expires_at < ?
                   OR (used_at IS NOT NULL AND used_at < ?)
                """,
                (cutoff, cutoff),
            )
            deleted_password_reset_tokens = max(0, cursor.rowcount)
        if self._table_exists(connection, "chat_request_cancellations"):
            cursor = connection.execute(
                """
                DELETE FROM chat_request_cancellations
                WHERE expires_at < ?
                """,
                (now_iso,),
            )
            deleted_chat_cancellations = max(0, cursor.rowcount)
        if self._table_exists(connection, "auth_login_attempts"):
            cutoff = self._retention_cutoff_iso(
                now_iso,
                self._policy.login_attempt_retention_days,
            )
            cursor = connection.execute(
                """
                DELETE FROM auth_login_attempts
                WHERE blocked_until < ?
                  AND first_failure_at < ?
                """,
                (now_iso, cutoff),
            )
            deleted_login_attempts = max(0, cursor.rowcount)
        return {
            "auth_sessions": deleted_auth_sessions,
            "password_reset_tokens": deleted_password_reset_tokens,
            "chat_request_cancellations": deleted_chat_cancellations,
            "auth_login_attempts": deleted_login_attempts,
        }

    def _table_exists(self, connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    def _retention_cutoff_iso(self, now_iso: str, retention_days: int) -> str:
        now = datetime.fromisoformat(now_iso)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        cutoff = now.astimezone(UTC) - timedelta(days=max(0, retention_days))
        return cutoff.isoformat(timespec="seconds")
