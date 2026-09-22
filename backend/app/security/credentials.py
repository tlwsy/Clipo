# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings
from app.db.base import utcnow
from app.errors import ClipoError

password_hasher = PasswordHasher()
dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def signing_key(settings: Settings) -> bytes:
    return hmac.digest(settings.secret_key.get_secret_value().encode(), b"clipo:jwt:v1", "sha256")


def create_access_token(user_id: int, settings: Settings) -> str:
    now = utcnow()
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(seconds=settings.access_token_ttl_seconds),
            "iss": "clipo",
            "aud": "clipo-api",
            "type": "access",
            "jti": secrets.token_hex(16),
        },
        signing_key(settings),
        algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> int:
    try:
        payload = jwt.decode(
            token,
            signing_key(settings),
            algorithms=["HS256"],
            issuer="clipo",
            audience="clipo-api",
            options={"require": ["sub", "exp", "iat", "type"]},
        )
        if payload["type"] != "access":
            raise ValueError("invalid token type")
        return int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise ClipoError(401, "invalid_token", "登录已过期，请重新登录") from exc


def cipher(settings: Settings) -> Fernet:
    key = hmac.digest(settings.secret_key.get_secret_value().encode(), b"clipo:fields:v1", "sha256")
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(value: str, settings: Settings) -> str:
    return cipher(settings).encrypt(value.encode()).decode()


def decrypt_secret(value: str, settings: Settings) -> str:
    try:
        return cipher(settings).decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ClipoError(
            409, "secret_unavailable", "密钥已变更，请在设置中重新填写 API Key"
        ) from exc
