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
    token_version: int


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def verify_password_and_update(password: str, password_hash: str) -> tuple[bool, str | None]:
    """Verify a password and return an upgraded hash when policy changed."""
    return password_hasher.verify_and_update(password, password_hash)


def create_access_token(
    *,
    user_id: uuid.UUID,
    role: str,
    token_version: int = 0,
    settings: Settings,
    now: datetime | None = None,
) -> tuple[str, int]:
    issued_at = now or datetime.now(UTC)
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    expires_at = issued_at + ttl
    payload = {
        "sub": str(user_id),
        "role": role,
        "ver": token_version,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm="HS256",
        headers={"kid": settings.jwt_active_kid},
    )
    return token, int(ttl.total_seconds())


def decode_access_token(token: str, settings: Settings) -> AccessTokenClaims:
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if kid is None:
            key = (
                settings.jwt_legacy_verification_secret.get_secret_value()
                if settings.jwt_legacy_verification_secret is not None
                else settings.jwt_secret
            )
        else:
            key = settings.jwt_verification_key_map.get(str(kid))
            if key is None:
                raise AuthenticationError()
        payload = jwt.decode(
            token,
            key,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={
                "require": [
                    "sub",
                    "role",
                    "iss",
                    "aud",
                    "iat",
                    "nbf",
                    "exp",
                    "jti",
                    "ver",
                ]
            },
        )
        if payload.get("type") != "access":
            raise AuthenticationError()
        token_version = int(payload["ver"])
        if token_version < 0:
            raise AuthenticationError()
        return AccessTokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            role=str(payload["role"]),
            token_version=token_version,
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise AuthenticationError() from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
