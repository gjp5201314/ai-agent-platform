"""Health check endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.core.redis_client import get_redis
from app.schemas import HealthCheck

router = APIRouter()


@router.get("/health", response_model=HealthCheck)
@router.get("/", response_model=HealthCheck)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Check service health: database, redis, LLM config."""
    db_status = "unknown"
    redis_status = "unknown"

    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    try:
        redis = await get_redis()
        await redis.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"

    return HealthCheck(
        status="ok" if db_status == "ok" and redis_status == "ok" else "degraded",
        database=db_status,
        redis=redis_status,
        llm_provider=settings.llm_provider,
    )
