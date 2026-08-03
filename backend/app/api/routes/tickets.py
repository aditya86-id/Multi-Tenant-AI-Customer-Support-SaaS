import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.ticket import Ticket
from app.schemas.ticket import TicketResponse

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
