"""
数据库引擎和会话管理（异步SQLAlchemy + pgvector）
"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings
from app.core.logger import logger

# 启用pgvector扩展 - 必须在任何模型使用它之前创建
# 我们在初始化脚本/迁移中处理CREATE EXTENSION

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
    """所有ORM模型的声明基类"""
    pass


async def get_db() -> AsyncSession:
    """FastAPI依赖：提供异步数据库会话"""
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
    初始化数据库：创建扩展、表和全文搜索索引
    在应用启动时调用
    """
    from sqlalchemy import text
    from app.models import Conversation, Message, Document, DocumentChunk, AgentConfig  # noqa

    async with engine.begin() as conn:
        # pgvector扩展，用于向量列
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # 先运行表创建
        await conn.run_sync(Base.metadata.create_all)

        # ---- 模式迁移：新列（幂等）----
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
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'agent_configs' AND column_name = 'allow_delegation'
                ) THEN
                    ALTER TABLE agent_configs ADD COLUMN allow_delegation BOOLEAN DEFAULT TRUE;
                END IF;
            END $$;
        """))
        # 添加tsvector列（幂等）
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

        # 创建GIN索引用于快速全文搜索（幂等）
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_search
            ON document_chunks USING GIN (search_vector);
        """))

        # ---- HNSW向量索引用于快速ANN（余弦距离）----
        # HNSW比IVFFlat在高维向量上提供数量级的更快搜索
        # 复杂度为log(N)
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_hnsw
            ON document_chunks USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 200);
        """))

    # ---- 使用CJK分词重新索引现有块 ----
    await _reindex_existing_chunks()


async def _reindex_existing_chunks():
    """
    使用CJK感知分词重新填充所有现有块的search_vector
    （Python端，避免PL/pgSQL转义问题）
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
        logger.info(f"已为 {len(rows)} 个文档块重新建立混合关键词搜索索引")