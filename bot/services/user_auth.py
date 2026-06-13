"""Web account credentials (email + password) for standalone web login."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
MIN_PASSWORD_LEN = 8
PBKDF2_ITERATIONS = 600_000


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email(email: str) -> bool:
    normalized = normalize_email(email)
    return bool(normalized) and len(normalized) <= 255 and EMAIL_RE.fullmatch(normalized)


def validate_password(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LEN:
        return "password_too_short"
    if len(password) > 128:
        return "password_too_long"
    return None


def validate_password_message(error_key: str | None, locale: str) -> str | None:
    if not error_key:
        return None
    from bot.i18n.api_messages import api_msg

    if error_key == "password_too_short":
        return api_msg(locale, error_key, min=MIN_PASSWORD_LEN)
    return api_msg(locale, error_key)


def hash_user_password(password: str, pepper: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt + pepper.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return f"{PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_user_password(password: str, stored: str, pepper: str) -> bool:
    try:
        iterations_str, salt_hex, digest_hex = stored.split("$", 2)
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False

    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt + pepper.encode("utf-8"),
        iterations,
    )
    return hmac.compare_digest(dk, expected)
