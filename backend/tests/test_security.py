import uuid
from datetime import datetime, timedelta, timezone

import pytest
from jose import JWTError, jwt

from app.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.enums import UserRole


def test_hash_password_roundtrip():
    hashed = hash_password("CorrectHorse123!")
    assert verify_password("CorrectHorse123!", hashed) is True


def test_hash_password_rejects_wrong_password():
    hashed = hash_password("CorrectHorse123!")
    assert verify_password("WrongPassword456", hashed) is False


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, UserRole.CLIENT)
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "client"
    assert payload["type"] == "access"


def test_access_token_tampered_signature_rejected():
    token = create_access_token(uuid.uuid4(), UserRole.CLIENT)
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(JWTError):
        decode_access_token(tampered)


def test_access_token_expired_rejected():
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid.uuid4()),
        "role": "client",
        "type": "access",
        "iat": now - timedelta(minutes=30),
        "exp": now - timedelta(minutes=15),
    }
    expired_token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    with pytest.raises(JWTError):
        decode_access_token(expired_token)


def test_access_token_wrong_type_claim_rejected():
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid.uuid4()),
        "role": "client",
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    bad_type_token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    with pytest.raises(JWTError):
        decode_access_token(bad_type_token)


def test_hash_refresh_token_is_deterministic():
    token = "some-opaque-refresh-token-value"
    assert hash_refresh_token(token) == hash_refresh_token(token)


def test_hash_refresh_token_differs_for_different_input():
    assert hash_refresh_token("token-a") != hash_refresh_token("token-b")
