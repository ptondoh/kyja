import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import settings
from app.models.enums import UserRole

BCRYPT_ROUNDS = 12
ACCESS_TOKEN_TYPE = "access"

REFRESH_COOKIE_NAME = "refresh_token"
CSRF_COOKIE_NAME = "csrf_refresh_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
# "/auth" (pas seulement "/auth/refresh") : le cookie doit aussi être visible par
# /auth/logout pour que le logout puisse lire et révoquer le refresh token — un
# scope limité à /auth/refresh ne serait jamais envoyé sur /auth/logout.
REFRESH_COOKIE_PATH = "/auth"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: uuid.UUID, role: UserRole) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Lève jose.JWTError (signature invalide, expiré, malformé...) à charge de l'appelant."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise JWTError("Invalid token type")
    return payload


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    """SHA-256 simple (pas bcrypt) : l'entrée a déjà ~512 bits d'entropie CSPRNG,
    et il faut un hash déterministe pour un lookup indexé WHERE token_hash = :h."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)
