"""FastAPI shared dependencies — security-first design."""
from typing import Optional

from fastapi import Depends, HTTPException, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import AgentConfig
from app.core.redis_client import rate_limit


async def get_client_ip(request: Request) -> str:
    """
    Extract real client IP from proxy headers.
    Validates header format to prevent injection attacks.
    """
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    x_real_ip = request.headers.get("X-Real-IP")

    ip = x_real_ip or (x_forwarded_for.split(",")[0].strip() if x_forwarded_for else None)
    if not ip:
        ip = request.client.host if request.client else "unknown"

    # Sanitize: reject obviously malformed IP strings
    ip = ip.strip()
    if len(ip) > 45:  # max IPv6 length
        ip = ip[:45]
    if "\n" in ip or "\r" in ip or "\0" in ip:
        raise HTTPException(status_code=400, detail="Invalid client IP header")

    return ip


async def get_default_agent(db: AsyncSession) -> Optional[AgentConfig]:
    """Get the default agent config, or the first available."""
    result = await db.execute(
        select(AgentConfig)
        .where(AgentConfig.is_default == True)
        .limit(1)
    )
    agent = result.scalar_one_or_none()
    if agent:
        return agent
    result = await db.execute(select(AgentConfig).limit(1))
    return result.scalar_one_or_none()


async def verify_rate_limit(
    request: Request,
    max_requests: int = 30,
    window: int = 60,
    key_prefix: str = "api",
):
    """
    Rate limit middleware dependency — applies to any endpoint.
    Uses sliding window counter per IP in Redis.

    Args:
        max_requests: max calls in the time window
        window: time window in seconds
        key_prefix: Redis key namespace (e.g. "chat", "rag", "agents")
    """
    ip = await get_client_ip(request)
    key = f"{key_prefix}:{ip}"
    allowed = await rate_limit(key, max_requests=max_requests, window=window)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")


# Convenience: stricter limits for write-heavy endpoints
async def verify_write_rate_limit(request: Request):
    """Rate limit for write operations (create/update/delete): 10 req / 60s."""
    await verify_rate_limit(request, max_requests=10, window=60, key_prefix="write")


# Convenience: moderate limits for read operations
async def verify_read_rate_limit(request: Request):
    """Rate limit for read operations (list/get): 60 req / 60s."""
    await verify_rate_limit(request, max_requests=60, window=60, key_prefix="read")
