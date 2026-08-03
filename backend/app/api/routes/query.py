from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.message import Message
from app.models.tenant import Tenant
from app.models.ticket import Ticket
from app.schemas.conversation import QueryRequest, QueryResponse, SourceRef
from app.services.embeddings import EmbeddingError, embed_query
from app.services.llm import AnswerGenerationError, generate_answer_and_maybe_escalate
from app.services.retrieval import DEFAULT_TOP_K, retrieve_relevant_chunks

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse)
async def query(payload: QueryRequest, db: AsyncSession = Depends(get_db)) -> QueryResponse:
    """
    Public, widget-facing endpoint: an end customer's message in, a grounded
    answer with citations out. Scoped entirely by tenant_slug -- there is no
    JWT here since this is called by anonymous site visitors, so tenant_slug
    (not a raw tenant_id) is the only thing the caller can supply, exactly
    like the login endpoint.
    """
    tenant_result = await db.execute(select(Tenant).where(Tenant.slug == payload.tenant_slug))
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None or not tenant.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown tenant")

    if payload.conversation_id is not None:
        conv_result = await db.execute(
            select(Conversation).where(
                Conversation.id == payload.conversation_id, Conversation.tenant_id == tenant.id
            )
        )
        conversation = conv_result.scalar_one_or_none()
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
            )
    else:
        conversation = Conversation(
            tenant_id=tenant.id, end_user_identifier=payload.end_user_identifier
        )
        db.add(conversation)
        await db.flush()

    db.add(
        Message(
            tenant_id=tenant.id,
            conversation_id=conversation.id,
            role="user",
            content=payload.message,
        )
    )

    try:
        query_embedding = embed_query(payload.message)
    except EmbeddingError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    scored_chunks = await retrieve_relevant_chunks(
        db, tenant_id=tenant.id, query_embedding=query_embedding, top_k=DEFAULT_TOP_K
    )
    confidence = scored_chunks[0][1] if scored_chunks else 0.0

    try:
        result = generate_answer_and_maybe_escalate(
            payload.message, scored_chunks, retrieval_confidence=confidence
        )
    except AnswerGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    answer = result.answer
    ticket_id = None

    if result.escalated:
        ticket = Ticket(
            tenant_id=tenant.id,
            conversation_id=conversation.id,
            subject=result.ticket_subject or "Customer support request",
            summary=result.ticket_summary,
            priority=result.ticket_priority,
            escalation_reason=result.escalation_reason,
            status="open",
        )
        db.add(ticket)
        conversation.status = "escalated"
        await db.flush()
        ticket_id = ticket.id

    retrieved_chunk_ids = [chunk.id for chunk, _score in scored_chunks]
    db.add(
        Message(
            tenant_id=tenant.id,
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            retrieved_chunk_ids=retrieved_chunk_ids,
            confidence=confidence,
        )
    )
    await db.commit()

    # Need filenames for source refs -- fetch the parent documents in one query
    # rather than N+1-ing it per chunk.
    document_ids = {chunk.document_id for chunk, _ in scored_chunks}
    documents_by_id = {}
    if document_ids:
        doc_result = await db.execute(select(Document).where(Document.id.in_(document_ids)))
        documents_by_id = {doc.id: doc for doc in doc_result.scalars().all()}

    sources = [
        SourceRef(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            filename=documents_by_id[chunk.document_id].filename
            if chunk.document_id in documents_by_id
            else "unknown",
            snippet=chunk.content[:280],
        )
        for chunk, _score in scored_chunks
    ]

    return QueryResponse(
        conversation_id=conversation.id,
        answer=answer,
        confidence=confidence,
        sources=sources,
        escalated=result.escalated,
        ticket_id=ticket_id,
    )
