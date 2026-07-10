"""
Database engine and session management (async SQLAlchemy + pgvector).
"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Enable pgvector extension - must be created before any model uses it
# We handle CREATE EXTENSION in the init script / migration

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields an async DB session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """
    Initialize database: create pgvector extension and all tables.
    Call this on application startup.
    """
    from sqlalchemy import text
    from app.models import Conversation, Message, Document, DocumentChunk, AgentConfig  # noqa

    async with engine.begin() as conn:
        # pgvector extension is required for vector columns
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
