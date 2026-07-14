"""Health check endpoints — POST only, no params exposed in URL."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.core.redis_client import get_redis
from app.core.memory import get_memory_status
from app.schemas import HealthCheck

router = APIRouter()


@router.post("/health", response_model=HealthCheck)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Check service health (POST — no sensitive data in URL)."""
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

    # Mem0 long-term memory status
    memory_status = get_memory_status()

    # Overall status: ok only if all critical services are ok
    overall = "ok"
    if db_status != "ok" or redis_status != "ok":
        overall = "degraded"

    return HealthCheck(
        status=overall,
        database=db_status,
        redis=redis_status,
        memory=memory_status,
        llm_provider=settings.llm_provider,
    )
