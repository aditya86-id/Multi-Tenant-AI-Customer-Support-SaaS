import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class QueryRequest(BaseModel):
    tenant_slug: str
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    end_user_identifier: str | None = None


class SourceRef(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    snippet: str


class QueryResponse(BaseModel):
    conversation_id: uuid.UUID
    answer: str
    confidence: float
    sources: list[SourceRef]


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    confidence: float | None
    created_at: datetime
