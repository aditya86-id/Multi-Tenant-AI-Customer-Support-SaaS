import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

# tokenUrl is only used for OpenAPI docs' "Authorize" button; login itself
# lives at /api/v1/auth/login and takes JSON, not form data.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


class CurrentUser:
    """Lightweight identity extracted from a validated JWT + DB lookup."""

    def __init__(self, user: User):
        self.id: uuid.UUID = user.id
        self.tenant_id: uuid.UUID = user.tenant_id
        self.role: str = user.role
        self.email: str = user.email
        self.is_active: bool = user.is_active


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise credentials_exception

    try:
        user_id = uuid.UUID(payload.user_id)
        tenant_id = uuid.UUID(payload.tenant_id)
    except (ValueError, TypeError):
        raise credentials_exception

    # Re-fetch the user (rather than trusting the token blindly) so a
    # deactivated user or deleted tenant is rejected immediately, and we
    # always filter by tenant_id even though id alone would be unique --
    # this is the pattern every other tenant-scoped query in the app follows.
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exception

    return CurrentUser(user)


def require_role(*allowed_roles: str):
    """
    Dependency factory for simple RBAC, e.g.:
        Depends(require_role("admin"))
    Full role/permission hardening happens in phase 7 -- this covers the
    admin-vs-agent split needed from phase 1 onward.
    """

    async def _checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return _checker
