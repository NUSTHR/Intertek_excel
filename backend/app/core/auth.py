from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

PASSWORD_HASH_SCHEME = "pbkdf2_sha256"


def hash_password(password: str, *, iterations: int) -> str:
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return f"{PASSWORD_HASH_SCHEME}${iterations}${salt}${derived.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations_text, salt, expected_hex = password_hash.split("$", 3)
        iterations = int(iterations_text)
    except (ValueError, TypeError):
        return False
    if scheme != PASSWORD_HASH_SCHEME:
        return False
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return hmac.compare_digest(derived.hex(), expected_hex)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def new_secret_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def expires_at_iso(*, hours: int = 0, minutes: int = 0) -> str:
    return (
        datetime.now(UTC) + timedelta(hours=hours, minutes=minutes)
    ).isoformat(timespec="seconds")


def is_expired(iso_value: str) -> bool:
    try:
        return datetime.fromisoformat(iso_value) <= datetime.now(UTC)
    except ValueError:
        return True
