import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings
from app.core.errors import AuthenticationError

password_hasher = PasswordHash.recommended()


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    role: str


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def create_access_token(
    *, user_id: uuid.UUID, role: str, settings: Settings, now: datetime | None = None
) -> tuple[str, int]:
    issued_at = now or datetime.now(UTC)
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    expires_at = issued_at + ttl
    payload = {
        "sub": str(user_id),
        "role": role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, int(ttl.total_seconds())


def decode_access_token(token: str, settings: Settings) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "role", "iss", "aud", "iat", "nbf", "exp", "jti"]},
        )
        if payload.get("type") != "access":
            raise AuthenticationError()
        return AccessTokenClaims(user_id=uuid.UUID(payload["sub"]), role=str(payload["role"]))
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise AuthenticationError() from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
