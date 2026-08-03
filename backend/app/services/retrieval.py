import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk

DEFAULT_TOP_K = 5


async def retrieve_relevant_chunks(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int = DEFAULT_TOP_K,
) -> list[tuple[Chunk, float]]:
    """
    Returns the top_k chunks -- scoped to tenant_id, never a global search
    -- most similar to query_embedding, each paired with a cosine
    similarity score (1 - cosine distance, so higher = more similar).
    Phase 4's escalation decision consumes this similarity score directly.
    """
    distance = Chunk.embedding.cosine_distance(query_embedding)
    result = await db.execute(
        select(Chunk, distance.label("distance"))
        .where(Chunk.tenant_id == tenant_id)
        .order_by(distance)
        .limit(top_k)
    )
    return [(chunk, 1 - dist) for chunk, dist in result.all()]
