from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    *, subject: str, tenant_id: str, role: str, expires_delta: timedelta | None = None
) -> str:
    """
    Encodes tenant_id and role directly into the JWT so every downstream
    request can enforce tenant scoping without an extra DB round trip.
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "tenant_id": tenant_id,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


class TokenPayload:
    def __init__(self, sub: str, tenant_id: str, role: str):
        self.user_id = sub
        self.tenant_id = tenant_id
        self.role = role


def decode_access_token(token: str) -> TokenPayload:
    """
    Raises jose.JWTError on any failure (expired, bad signature, malformed).
    Callers are expected to catch this and turn it into a 401.
    """
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    sub = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    role = payload.get("role")
    if not sub or not tenant_id or not role:
        raise JWTError("Token payload missing required claims")
    return TokenPayload(sub=sub, tenant_id=tenant_id, role=role)
