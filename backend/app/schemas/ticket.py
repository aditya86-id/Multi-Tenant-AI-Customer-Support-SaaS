import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class TicketUpdateRequest(BaseModel):
    """All fields optional -- only the ones the caller sends get updated."""

    status: str | None = Field(default=None, pattern="^(open|in_progress|resolved|closed)$")
    priority: str | None = Field(default=None, pattern="^(low|normal|high|urgent)$")
    assigned_to: uuid.UUID | None = None
