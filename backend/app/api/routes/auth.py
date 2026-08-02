from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import LoginRequest, TenantSignupRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: TenantSignupRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """
    Creates a new tenant and its first admin user atomically. This is the
    only endpoint that creates a Tenant row -- everything after this is
    scoped to an existing tenant_id.
    """
    existing = await db.execute(select(Tenant).where(Tenant.slug == payload.tenant_slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant slug '{payload.tenant_slug}' is already taken",
        )

    tenant = Tenant(name=payload.tenant_name, slug=payload.tenant_slug)
    db.add(tenant)
    try:
        await db.flush()  # assigns tenant.id without committing yet
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant slug '{payload.tenant_slug}' is already taken",
        )

    admin_user = User(
        tenant_id=tenant.id,
        email=payload.admin_email,
        hashed_password=hash_password(payload.admin_password),
        full_name=payload.admin_full_name,
        role="admin",
    )
    db.add(admin_user)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create tenant/admin user -- likely a duplicate slug or email",
        )

    await db.refresh(admin_user)

    token = create_access_token(
        subject=str(admin_user.id), tenant_id=str(tenant.id), role=admin_user.role
    )
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """
    Login is always scoped by tenant_slug + email, since the same email can
    exist under different tenants. This prevents accidentally logging a
    user into the wrong tenant's data.
    """
    result = await db.execute(
        select(User, Tenant)
        .join(Tenant, Tenant.id == User.tenant_id)
        .where(Tenant.slug == payload.tenant_slug, User.email == payload.email)
    )
    row = result.first()

    generic_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid tenant, email, or password",
    )

    if row is None:
        raise generic_error

    user, tenant = row

    if not tenant.is_active or not user.is_active:
        raise generic_error

    if not verify_password(payload.password, user.hashed_password):
        raise generic_error

    token = create_access_token(subject=str(user.id), tenant_id=str(tenant.id), role=user.role)
    return TokenResponse(access_token=token)
