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
from app.core.logger import logger

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
    Initialize database: create extensions, tables, and full-text search indexes.
    Call this on application startup.
    """
    from sqlalchemy import text
    from app.models import Conversation, Message, Document, DocumentChunk, AgentConfig  # noqa

    async with engine.begin() as conn:
        # pgvector extension for vector columns
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # Run table creation first
        await conn.run_sync(Base.metadata.create_all)

        # ---- Schema migrations: new columns (idempotent) ----
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'documents' AND column_name = 'source'
                ) THEN
                    ALTER TABLE documents ADD COLUMN source VARCHAR(20) DEFAULT 'user';
                END IF;
            END $$;
        """))
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'agent_configs' AND column_name = 'is_protected'
                ) THEN
                    ALTER TABLE agent_configs ADD COLUMN is_protected BOOLEAN DEFAULT FALSE;
                END IF;
            END $$;
        """))
        # Add tsvector column (idempotent)
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'document_chunks' AND column_name = 'search_vector'
                ) THEN
                    ALTER TABLE document_chunks
                    ADD COLUMN search_vector tsvector;
                END IF;
            END $$;
        """))

        # Create GIN index for fast full-text search (idempotent)
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_search
            ON document_chunks USING GIN (search_vector);
        """))

        # ---- HNSW vector index for fast ANN (cosine distance) ----
        # HNSW provides orders-of-magnitude faster search than IVFFlat
        # for high-dimensional vectors, scales with log(N).
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_hnsw
            ON document_chunks USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 200);
        """))

    # ---- Re-index existing chunks with CJK tokenization ----
    await _reindex_existing_chunks()


async def _reindex_existing_chunks():
    """
    Re-populate search_vector for all existing chunks using CJK-aware
    tokenization (Python-side, avoids PL/pgSQL escaping issues).
    """
    from sqlalchemy import text, select
    from app.models import DocumentChunk
    from app.rag.retriever import _cjk_tokenize

    async with async_session_factory() as session:
        result = await session.execute(select(DocumentChunk.id, DocumentChunk.content))
        rows = result.fetchall()

        if not rows:
            return

        for chunk_id, content in rows:
            tokenized = _cjk_tokenize(content)
            await session.execute(
                text("UPDATE document_chunks SET search_vector = to_tsvector('simple', :content) WHERE id = :id"),
                {"content": tokenized, "id": chunk_id},
            )

        await session.commit()
        logger.info(f"Reindexed {len(rows)} document chunks for hybrid keyword search")
