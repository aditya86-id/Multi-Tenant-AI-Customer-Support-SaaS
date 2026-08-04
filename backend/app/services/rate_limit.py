import time

import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()

_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Rate limit exceeded, retry after {retry_after_seconds}s")


async def enforce_tenant_rate_limit(
    tenant_id: str, limit: int | None = None, window_seconds: int = 60
) -> None:
    """
    Fixed-window rate limit keyed per tenant_id -- never global -- so one
    tenant's traffic (or a misbehaving/abusive client) can never eat into
    another tenant's quota. Backed by Redis rather than an in-memory
    counter so the limit holds even if the API runs as multiple instances.
    """
    limit = limit if limit is not None else settings.rate_limit_per_minute
    client = _get_redis()
    window = int(time.time()) // window_seconds
    key = f"ratelimit:{tenant_id}:{window}"

    count = await client.incr(key)
    if count == 1:
        await client.expire(key, window_seconds)

    if count > limit:
        ttl = await client.ttl(key)
        raise RateLimitExceeded(retry_after_seconds=max(ttl, 1))
