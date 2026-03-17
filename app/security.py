from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from passlib.context import CryptContext

# bcrypt backend appears unreliable in some Windows environments.
# PBKDF2 is slower but very portable and sufficient for internal use.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def new_session_token() -> str:
    # URL-safe random token; treated as bearer token in an HttpOnly cookie.
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(UTC)


def session_expiry(days: int = 14) -> datetime:
    return utcnow() + timedelta(days=days)
