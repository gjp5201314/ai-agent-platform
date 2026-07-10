"""FastAPI shared dependencies."""
from typing import Optional
from uuid import uuid4

from fastapi import Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import AgentConfig, Conversation
from app.core.redis_client import rate_limit


async def get_or_create_conversation(
    conversation_id: Optional[str],
    agent_id: Optional[str],
    db: AsyncSession,
) -> Conversation:
    """Get existing conversation or create a new one."""
    if conversation_id:
        result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv

    # Create new conversation
    conv = Conversation(
        id=str(uuid4()),
        title="New Conversation",
        agent_id=agent_id,
    )
    db.add(conv)
    await db.flush()
    return conv


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

    # Fallback: first agent
    result = await db.execute(select(AgentConfig).limit(1))
    return result.scalar_one_or_none()


async def verify_rate_limit(
    x_forwarded_for: Optional[str] = Header(None),
    x_real_ip: Optional[str] = Header(None),
):
    """Rate limit middleware dependency."""
    ip = x_real_ip or x_forwarded_for or "unknown"
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    allowed = await rate_limit(f"chat:{ip}", max_requests=30, window=60)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")
