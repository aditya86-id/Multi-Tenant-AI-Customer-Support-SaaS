import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID | None
    assigned_to: uuid.UUID | None
    subject: str
    summary: str | None
    status: str
    priority: str
    escalation_reason: str | None
    created_at: datetime
    updated_at: datetime
