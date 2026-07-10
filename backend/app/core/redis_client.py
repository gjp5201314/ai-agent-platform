"""Redis client for session state, rate limiting, and caching."""
from typing import Optional, Any
import json

import redis.asyncio as redis

from app.config import settings

# Connection pool — created lazily
_redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """Get or create the Redis connection."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
        )
    return _redis_client


async def close_redis():
    """Close Redis connection on shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


# ---- Helper functions ----

async def cache_set(key: str, value: Any, ttl: int = 3600) -> bool:
    """Set a cache key with TTL (seconds)."""
    r = await get_redis()
    return await r.set(key, json.dumps(value, default=str), ex=ttl)


async def cache_get(key: str) -> Any:
    """Get a cached value, or None."""
    r = await get_redis()
    data = await r.get(key)
    return json.loads(data) if data else None


async def cache_delete(key: str) -> bool:
    r = await get_redis()
    return await r.delete(key) > 0


async def rate_limit(identifier: str, max_requests: int = 20, window: int = 60) -> bool:
    """
    Simple sliding window rate limiter.
    Returns True if request is allowed, False if rate-limited.
    """
    r = await get_redis()
    key = f"rate_limit:{identifier}"
    current = await r.incr(key)
    if current == 1:
        await r.expire(key, window)
    return current <= max_requests
