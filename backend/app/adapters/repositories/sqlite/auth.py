import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.domain.models import (
    AuthSession,
    PasswordResetToken,
    UserAccount,
    UserRole,
)


class SQLiteAuthRepository:
    """Persistence boundary for users, sessions, resets, and login throttling."""

    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect

    def create_user(self, user: UserAccount) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_accounts
                  (
                    user_id, email, password_hash, role, is_active,
                    created_at, updated_at, last_login_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.user_id,
                    user.email,
                    user.password_hash,
                    user.role.value,
                    1 if user.is_active else 0,
                    user.created_at,
                    user.updated_at,
                    user.last_login_at,
                ),
            )

    def create_user_with_session_if_email_available(
        self,
        user: UserAccount,
        session: AuthSession,
    ) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO user_accounts
                  (
                    user_id, email, password_hash, role, is_active,
                    created_at, updated_at, last_login_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO NOTHING
                RETURNING user_id
                """,
                (
                    user.user_id,
                    user.email,
                    user.password_hash,
                    user.role.value,
                    1 if user.is_active else 0,
                    user.created_at,
                    user.updated_at,
                    user.last_login_at,
                ),
            )
            if cursor.fetchone() is None:
                return False
            connection.execute(
                """
                INSERT INTO auth_sessions
                  (
                    session_id, user_id, session_token_hash,
                    created_at, expires_at, revoked_at
                  )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.user_id,
                    session.session_token_hash,
                    session.created_at,
                    session.expires_at,
                    session.revoked_at,
                ),
            )
        return True

    def get_user(self, user_id: str) -> UserAccount | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM user_accounts WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return _to_user(row)

    def get_user_by_email(self, email: str) -> UserAccount | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM user_accounts WHERE email = ?",
                (email,),
            ).fetchone()
        return _to_user(row)

    def ensure_builtin_admin(self, user: UserAccount) -> UserAccount:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_accounts
                  (
                    user_id, email, password_hash, role, is_active,
                    created_at, updated_at, last_login_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO NOTHING
                """,
                (
                    user.user_id,
                    user.email,
                    user.password_hash,
                    user.role.value,
                    1 if user.is_active else 0,
                    user.created_at,
                    user.updated_at,
                    user.last_login_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM user_accounts WHERE email = ?",
                (user.email,),
            ).fetchone()
        resolved = _to_user(row)
        if resolved is None:
            raise RuntimeError("failed to ensure built-in administrator")
        return resolved

    def synchronize_builtin_admin(
        self,
        *,
        user_id: str,
        password_hash: str,
        updated_at: str,
    ) -> UserAccount | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE user_accounts
                SET password_hash = ?, is_active = 1, updated_at = ?
                WHERE user_id = ? AND role = ?
                """,
                (password_hash, updated_at, user_id, UserRole.ADMIN.value),
            )
            if cursor.rowcount != 1:
                return None
            connection.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (updated_at, user_id),
            )
            connection.execute(
                """
                UPDATE password_reset_tokens
                SET used_at = ?
                WHERE user_id = ? AND used_at IS NULL
                """,
                (updated_at, user_id),
            )
            row = connection.execute(
                "SELECT * FROM user_accounts WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return _to_user(row)

    def update_user_password(
        self,
        user_id: str,
        password_hash: str,
        updated_at: str,
    ) -> UserAccount | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE user_accounts
                SET password_hash = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (password_hash, updated_at, user_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM user_accounts WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return _to_user(row)

    def record_user_login(self, user_id: str, last_login_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE user_accounts
                SET last_login_at = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (last_login_at, last_login_at, user_id),
            )

    def create_auth_session(self, session: AuthSession) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO auth_sessions
                  (
                    session_id, user_id, session_token_hash,
                    created_at, expires_at, revoked_at
                  )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.user_id,
                    session.session_token_hash,
                    session.created_at,
                    session.expires_at,
                    session.revoked_at,
                ),
            )

    def get_auth_session_by_token_hash(
        self,
        token_hash: str,
    ) -> tuple[AuthSession, UserAccount] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                  auth_sessions.session_id AS auth_session_id,
                  auth_sessions.user_id AS auth_user_id,
                  auth_sessions.session_token_hash,
                  auth_sessions.created_at AS auth_created_at,
                  auth_sessions.expires_at,
                  auth_sessions.revoked_at,
                  user_accounts.user_id,
                  user_accounts.email,
                  user_accounts.password_hash,
                  user_accounts.role,
                  user_accounts.is_active,
                  user_accounts.created_at AS user_created_at,
                  user_accounts.updated_at AS user_updated_at,
                  user_accounts.last_login_at
                FROM auth_sessions
                JOIN user_accounts ON user_accounts.user_id = auth_sessions.user_id
                WHERE auth_sessions.session_token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return _to_auth_session(row), _to_joined_user(row)

    def revoke_auth_session(self, token_hash: str, revoked_at: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE session_token_hash = ? AND revoked_at IS NULL
                """,
                (revoked_at, token_hash),
            )
        return cursor.rowcount > 0

    def create_password_reset_token(self, token: PasswordResetToken) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO password_reset_tokens
                  (reset_token_id, user_id, token_hash, created_at, expires_at, used_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    token.reset_token_id,
                    token.user_id,
                    token.token_hash,
                    token.created_at,
                    token.expires_at,
                    token.used_at,
                ),
            )

    def consume_password_reset_token(
        self,
        *,
        token_hash: str,
        password_hash: str,
        used_at: str,
        protected_email: str,
    ) -> UserAccount | None:
        with self._connect() as connection:
            # The connection uses an IMMEDIATE transaction. The conditional update is
            # the consume fence: concurrent callers cannot both claim the same token.
            cursor = connection.execute(
                """
                UPDATE password_reset_tokens
                SET used_at = ?
                WHERE token_hash = ?
                  AND used_at IS NULL
                  AND expires_at > ?
                  AND EXISTS (
                    SELECT 1
                    FROM user_accounts
                    WHERE user_accounts.user_id = password_reset_tokens.user_id
                      AND user_accounts.is_active = 1
                      AND user_accounts.email <> ?
                  )
                """,
                (used_at, token_hash, used_at, protected_email),
            )
            if cursor.rowcount != 1:
                return None
            reset_row = connection.execute(
                """
                SELECT user_id
                FROM password_reset_tokens
                WHERE token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if reset_row is None:
                raise RuntimeError("consumed password reset token disappeared")
            user_id = str(reset_row["user_id"])
            updated = connection.execute(
                """
                UPDATE user_accounts
                SET password_hash = ?, updated_at = ?
                WHERE user_id = ? AND is_active = 1
                """,
                (password_hash, used_at, user_id),
            )
            if updated.rowcount != 1:
                raise RuntimeError("password reset user became unavailable")
            connection.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (used_at, user_id),
            )
            row = connection.execute(
                """
                SELECT *
                FROM user_accounts
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        return _to_user(row)

    def get_login_rate_limit_retry_after(
        self,
        email: str,
        now: str,
    ) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT blocked_until
                FROM auth_login_attempts
                WHERE email = ?
                """,
                (email,),
            ).fetchone()
        if row is None:
            return None
        return _retry_after_seconds(row["blocked_until"], now)

    def record_login_rate_limit_failure(
        self,
        email: str,
        *,
        now: str,
        max_failed_attempts: int,
        window_seconds: int,
    ) -> int | None:
        bounded_max_attempts = max(1, max_failed_attempts)
        bounded_window_seconds = max(1, window_seconds)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT failures, first_failure_at, blocked_until
                FROM auth_login_attempts
                WHERE email = ?
                """,
                (email,),
            ).fetchone()

            if row is None or _iso_seconds_between(row["first_failure_at"], now) > (
                bounded_window_seconds
            ):
                failures = 1
                first_failure_at = now
                blocked_until = now
            else:
                failures = int(row["failures"]) + 1
                first_failure_at = str(row["first_failure_at"])
                blocked_until = str(row["blocked_until"])

            if failures >= bounded_max_attempts:
                blocked_until = _add_seconds(first_failure_at, bounded_window_seconds)

            connection.execute(
                """
                INSERT INTO auth_login_attempts
                  (email, failures, first_failure_at, blocked_until)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                  failures = excluded.failures,
                  first_failure_at = excluded.first_failure_at,
                  blocked_until = excluded.blocked_until
                """,
                (email, failures, first_failure_at, blocked_until),
            )
        return _retry_after_seconds(blocked_until, now)

    def clear_login_rate_limit(self, email: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM auth_login_attempts WHERE email = ?",
                (email,),
            )


def _to_user(row: sqlite3.Row | None) -> UserAccount | None:
    if row is None:
        return None
    return UserAccount(
        user_id=str(row["user_id"]),
        email=str(row["email"]),
        password_hash=str(row["password_hash"]),
        role=UserRole(str(row["role"])),
        is_active=bool(int(row["is_active"])),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        last_login_at=row["last_login_at"],
    )


def _to_joined_user(row: sqlite3.Row) -> UserAccount:
    return UserAccount(
        user_id=str(row["user_id"]),
        email=str(row["email"]),
        password_hash=str(row["password_hash"]),
        role=UserRole(str(row["role"])),
        is_active=bool(int(row["is_active"])),
        created_at=str(row["user_created_at"]),
        updated_at=str(row["user_updated_at"]),
        last_login_at=row["last_login_at"],
    )


def _to_auth_session(row: sqlite3.Row) -> AuthSession:
    return AuthSession(
        session_id=str(row["auth_session_id"]),
        user_id=str(row["auth_user_id"]),
        session_token_hash=str(row["session_token_hash"]),
        created_at=str(row["auth_created_at"]),
        expires_at=str(row["expires_at"]),
        revoked_at=row["revoked_at"],
    )


def _to_password_reset_token(row: sqlite3.Row) -> PasswordResetToken:
    return PasswordResetToken(
        reset_token_id=str(row["reset_token_id"]),
        user_id=str(row["reset_user_id"]),
        token_hash=str(row["token_hash"]),
        created_at=str(row["reset_created_at"]),
        expires_at=str(row["expires_at"]),
        used_at=row["used_at"],
    )


def _retry_after_seconds(blocked_until: str, now: str) -> int | None:
    remaining_seconds = _iso_seconds_between(now, blocked_until)
    if remaining_seconds <= 0:
        return None
    return max(1, int(remaining_seconds))


def _iso_seconds_between(start: str, end: str) -> float:
    return (_parse_iso_datetime(end) - _parse_iso_datetime(start)).total_seconds()


def _add_seconds(value: str, seconds: int) -> str:
    return (_parse_iso_datetime(value) + timedelta(seconds=seconds)).isoformat(
        timespec="seconds"
    )


def _parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
