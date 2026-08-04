import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user, require_role
from app.db.session import get_db
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.ticket import TicketResponse, TicketUpdateRequest

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketResponse])
async def list_tickets(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Ticket]:
    """
    Lists tickets for the current tenant only -- this is how a support
    agent (or this demo) verifies that agentic escalation actually created
    a ticket, without needing direct DB access.
    """
    result = await db.execute(
        select(Ticket)
        .where(Ticket.tenant_id == current_user.tenant_id)
        .order_by(Ticket.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Ticket:
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.tenant_id == current_user.tenant_id)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: uuid.UUID,
    payload: TicketUpdateRequest,
    current_user: CurrentUser = Depends(require_role("admin", "agent")),
    db: AsyncSession = Depends(get_db),
) -> Ticket:
    """
    Staff-only (admin or agent) ticket update -- status, priority, and/or
    assignment. Only fields actually sent in the request are changed.
    """
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.tenant_id == current_user.tenant_id)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    if payload.assigned_to is not None:
        # Never let a ticket be assigned to a user outside this tenant --
        # even though assigned_to is just a UUID, this closes the one place
        # a cross-tenant reference could otherwise sneak in.
        user_result = await db.execute(
            select(User).where(
                User.id == payload.assigned_to, User.tenant_id == current_user.tenant_id
            )
        )
        if user_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="assigned_to must be a user in this tenant",
            )
        ticket.assigned_to = payload.assigned_to

    if payload.status is not None:
        ticket.status = payload.status
    if payload.priority is not None:
        ticket.priority = payload.priority

    await db.commit()
    await db.refresh(ticket)
    return ticket
