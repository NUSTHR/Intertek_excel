from dataclasses import dataclass

from app.application.auth.rate_limit import AuthenticationRateLimiter
from app.core.auth import (
    expires_at_iso,
    hash_password,
    hash_token,
    is_expired,
    new_secret_token,
    normalize_email,
    verify_password,
)
from app.core.errors import (
    AuthenticationError,
    PasswordResetTokenError,
    RateLimitError,
    UserAlreadyExistsError,
)
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.domain.models import (
    AuthenticatedUser,
    AuthSession,
    PasswordResetToken,
    UserAccount,
    UserRole,
)
from app.ports.repository import AuthRepository

BUILTIN_ADMIN_EMAIL = "admin@qq.com"
BUILTIN_ADMIN_PASSWORD = "admin"


@dataclass(frozen=True)
class AuthResult:
    user: AuthenticatedUser
    access_token: str
    expires_at: str


@dataclass(frozen=True)
class PasswordResetRequestResult:
    email: str
    reset_token: str | None
    expires_at: str | None


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        *,
        session_ttl_hours: int,
        password_reset_ttl_minutes: int,
        password_hash_iterations: int,
        expose_reset_token: bool = True,
        login_rate_limiter: AuthenticationRateLimiter | None = None,
    ) -> None:
        self._repository = repository
        self._session_ttl_hours = session_ttl_hours
        self._password_reset_ttl_minutes = password_reset_ttl_minutes
        self._password_hash_iterations = password_hash_iterations
        self._expose_reset_token = expose_reset_token
        self._login_rate_limiter = login_rate_limiter

    def initialize(self) -> None:
        self._repository.initialize()
        self.ensure_admin_user()

    def ensure_admin_user(self) -> UserAccount:
        now = utc_now_iso()
        candidate = UserAccount(
            user_id=new_id("user"),
            email=BUILTIN_ADMIN_EMAIL,
            password_hash=self._hash_password(BUILTIN_ADMIN_PASSWORD),
            role=UserRole.ADMIN,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        existing = self._repository.ensure_builtin_admin(candidate)
        if existing.role != UserRole.ADMIN:
            raise RuntimeError("built-in administrator email belongs to a non-admin account")
        if existing.is_active and verify_password(
            BUILTIN_ADMIN_PASSWORD,
            existing.password_hash,
        ):
            return existing
        synchronized = self._repository.synchronize_builtin_admin(
            user_id=existing.user_id,
            password_hash=candidate.password_hash,
            updated_at=now,
        )
        if synchronized is None:
            raise RuntimeError("failed to synchronize built-in administrator")
        return synchronized

    def register(self, email: str, password: str) -> AuthResult:
        normalized_email = normalize_email(email)
        self._validate_email(normalized_email)
        self._validate_password(password)
        now = utc_now_iso()
        user = UserAccount(
            user_id=new_id("user"),
            email=normalized_email,
            password_hash=self._hash_password(password),
            role=UserRole.MEMBER,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        result, session = self._prepare_auth_result(user)
        if not self._repository.create_user_with_session_if_email_available(user, session):
            raise UserAlreadyExistsError("an account with this email already exists")
        return result

    def login(self, email: str, password: str) -> AuthResult:
        normalized_email = normalize_email(email)
        self._raise_if_login_limited(normalized_email)
        user = self._repository.get_user_by_email(normalized_email)
        if user is None or not user.is_active:
            self._record_login_failure(normalized_email)
            raise AuthenticationError("invalid email or password")
        if not verify_password(password, user.password_hash):
            self._record_login_failure(normalized_email)
            raise AuthenticationError("invalid email or password")
        now = utc_now_iso()
        self._repository.record_user_login(user.user_id, now)
        refreshed_user = self._repository.get_user(user.user_id) or user
        self._record_login_success(normalized_email)
        return self._create_auth_result(refreshed_user)

    def get_user_for_token(self, token: str) -> AuthenticatedUser:
        if not token.strip():
            raise AuthenticationError("authentication is required")
        result = self._repository.get_auth_session_by_token_hash(hash_token(token))
        if result is None:
            raise AuthenticationError("authentication is required")
        session, user = result
        if session.revoked_at is not None or is_expired(session.expires_at):
            raise AuthenticationError("session expired")
        if not user.is_active:
            raise AuthenticationError("account is disabled")
        return self._to_authenticated_user(user)

    def logout(self, token: str) -> None:
        if token.strip():
            self._repository.revoke_auth_session(hash_token(token), utc_now_iso())

    def request_password_reset(self, email: str) -> PasswordResetRequestResult:
        normalized_email = normalize_email(email)
        if normalized_email == BUILTIN_ADMIN_EMAIL:
            return PasswordResetRequestResult(
                email=normalized_email,
                reset_token=None,
                expires_at=None,
            )
        user = self._repository.get_user_by_email(normalized_email)
        if user is None or not user.is_active:
            return PasswordResetRequestResult(
                email=normalized_email,
                reset_token=None,
                expires_at=None,
            )

        token = new_secret_token()
        expires_at = expires_at_iso(minutes=self._password_reset_ttl_minutes)
        reset_token = PasswordResetToken(
            reset_token_id=new_id("reset"),
            user_id=user.user_id,
            token_hash=hash_token(token),
            created_at=utc_now_iso(),
            expires_at=expires_at,
        )
        self._repository.create_password_reset_token(reset_token)
        return PasswordResetRequestResult(
            email=normalized_email,
            reset_token=token if self._expose_reset_token else None,
            expires_at=expires_at,
        )

    def reset_password(self, token: str, new_password: str) -> AuthResult:
        self._validate_password(new_password)
        now = utc_now_iso()
        updated_user = self._repository.consume_password_reset_token(
            token_hash=hash_token(token),
            password_hash=self._hash_password(new_password),
            used_at=now,
            protected_email=BUILTIN_ADMIN_EMAIL,
        )
        if updated_user is None:
            raise PasswordResetTokenError("invalid or expired reset token")
        return self._create_auth_result(updated_user)

    def _create_auth_result(self, user: UserAccount) -> AuthResult:
        result, session = self._prepare_auth_result(user)
        self._repository.create_auth_session(session)
        return result

    def _prepare_auth_result(self, user: UserAccount) -> tuple[AuthResult, AuthSession]:
        token = new_secret_token()
        expires_at = expires_at_iso(hours=self._session_ttl_hours)
        session = AuthSession(
            session_id=new_id("authsession"),
            user_id=user.user_id,
            session_token_hash=hash_token(token),
            created_at=utc_now_iso(),
            expires_at=expires_at,
        )
        return (
            AuthResult(
                user=self._to_authenticated_user(user),
                access_token=token,
                expires_at=expires_at,
            ),
            session,
        )

    def _hash_password(self, password: str) -> str:
        return hash_password(password, iterations=self._password_hash_iterations)

    def _validate_email(self, email: str) -> None:
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            raise AuthenticationError("enter a valid email address")

    def _validate_password(self, password: str) -> None:
        if len(password) < 8:
            raise AuthenticationError("password must be at least 8 characters")

    def _raise_if_login_limited(self, email: str) -> None:
        if self._login_rate_limiter is None:
            return
        retry_after = self._login_rate_limiter.retry_after_seconds(email)
        if retry_after is not None:
            raise RateLimitError(
                "too many failed login attempts; try again later",
                retry_after_seconds=retry_after,
            )

    def _record_login_failure(self, email: str) -> None:
        if self._login_rate_limiter is None:
            return
        retry_after = self._login_rate_limiter.record_failure(email)
        if retry_after is not None:
            raise RateLimitError(
                "too many failed login attempts; try again later",
                retry_after_seconds=retry_after,
            )

    def _record_login_success(self, email: str) -> None:
        if self._login_rate_limiter is not None:
            self._login_rate_limiter.record_success(email)

    def _to_authenticated_user(self, user: UserAccount) -> AuthenticatedUser:
        return AuthenticatedUser(
            user_id=user.user_id,
            email=user.email,
            role=user.role,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )
