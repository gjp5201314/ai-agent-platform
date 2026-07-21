"""
================================================================================
  数据库引擎和会话管理（Database Engine & Session Manager）
================================================================================

本模块是后端数据层的核心基础设施，基于异步 SQLAlchemy 2.0 构建，
集成了 pgvector 向量扩展和 PostgreSQL 全文搜索能力。

================================================================================
  异步 SQLAlchemy 架构（Async SQLAlchemy Setup）
================================================================================

  核心组件：

  ┌──────────────────────────────────────────────────────────────┐
  │  engine（数据库引擎）                                          │
  │  ─────────────────────                                       │
  │  使用 create_async_engine() 创建，连接到 PostgreSQL 数据库。    │
  │                                                              │
  │  连接池参数：                                                  │
  │  - pool_size=10      → 常驻连接数（空闲时保持 10 个连接）      │
  │  - max_overflow=20   → 峰值超出时最多额外创建 20 个连接         │
  │  - pool_pre_ping=True → 每次使用前先测试连接有效性             │
  │    （避免因数据库重启/NAT 超时导致的断连错误）                   │
  │  - echo=True         → 调试模式下打印所有 SQL 语句（开发用）     │
  └──────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────┐
  │  async_session_factory（会话工厂）                              │
  │  ─────────────────────────────                               │
  │  使用 async_sessionmaker 创建异步会话工厂。                    │
  │                                                              │
  │  关键配置：                                                    │
  │  - expire_on_commit=False → 提交后不过期对象属性               │
  │    避免在 FastAPI 响应序列化时触发懒加载查询                     │
  └──────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────┐
  │  get_db()（FastAPI 依赖注入函数）                               │
  │  ───────────────────────────────                             │
  │  作为路由的依赖项使用，自动管理会话生命周期：                      │
  │                                                              │
  │  请求进入 → 创建会话 → 执行业务逻辑 → 提交/回滚 → 关闭会话      │
  │                                                              │
  │  用法：                                                       │
  │  @router.post("/upload")                                     │
  │  async def upload(db: AsyncSession = Depends(get_db)):        │
  │      ...                                                     │
  └──────────────────────────────────────────────────────────────┘

================================================================================
  pgvector 扩展与 CJK 全文搜索（pgvector & CJK Full-Text Search）
================================================================================

  本系统在 PostgreSQL 之上使用了两个强大的扩展：

  1. pgvector 向量扩展
  ─────────────────────
  SQL: CREATE EXTENSION IF NOT EXISTS vector

  功能：
  - 新增 vector(N) 数据类型（N 维浮点数向量，默认 1024 维）
  - 提供向量距离/相似度运算：cosine_distance, l2_distance, inner_product
  - 支持 HNSW（Hierarchical Navigable Small World）向量索引

  HNSW 索引参数：
  - m = 16          → 每层最大连接数（平衡精度与构建时间）
  - ef_construction = 200  → 构建时的搜索宽度（越大精度越高，构建越慢）
  - 操作符：vector_cosine_ops → 使用余弦距离
  - 复杂度：O(log N)，比 IVFFlat 的 O(sqrt(N)) 快一个数量级

  2. PostgreSQL 全文搜索（tsvector/tsquery）
  ─────────────────────────────────────────
  table: document_chunks.search_vector (tsvector 类型)

  功能：
  - tsvector 列：预处理的词素索引，存储每个词的规范化形式及位置
  - GIN 索引：倒排索引，加速 @@ 匹配操作符（包含查找）
  - ts_rank()：相关性评分函数（类 BM25 算法）

  中文支持方案（CJK 分词）：
  PostgreSQL 的 'simple' 配置是空白分隔的，无法自动识别中文词边界。
  解决方案：入库前在 Python 端进行 CJK 分词预处理
  （见 retriever.py 的 _cjk_tokenize 函数），
  在每个汉字间插入空格后写入 tsvector。

================================================================================
  数据库初始化流程（init_db）
================================================================================

  应用启动时自动执行（在 main.py 的 lifespan 事件中调用）：

  1. 创建 pgvector 扩展（CREATE EXTENSION IF NOT EXISTS vector）
  2. 创建所有 ORM 表（Base.metadata.create_all）
  3. 执行幂等模式迁移（按需添加新列，如 source, is_protected 等）
  4. 添加 tsvector 列到 document_chunks（如不存在）
  5. 创建 GIN 全文搜索索引（idx_document_chunks_search）
  6. 创建 HNSW 向量搜索索引（idx_document_chunks_embedding_hnsw）
  7. 对所有已有文档块执行 CJK 分词重建（_reindex_existing_chunks）

  所有 DDL 操作都是幂等的（使用 IF NOT EXISTS / IF NOT FOUND），
  可以安全地在每次启动时重复执行。
"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings
from app.core.logger import logger

# ============================================================
#  数据库引擎（Database Engine）
#  ─────────────────────────────
#  连接到 PostgreSQL，配置文件来自 settings.database_url
#  pgvector 扩展必须在任何使用向量的模型定义之前启用
#  ============================================================

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,    # 调试模式下打印 SQL（生产环境应关闭）
    pool_size=10,               # 连接池常驻连接数
    max_overflow=20,            # 超出 pool_size 时最多额外创建的连接数
    pool_pre_ping=True,         # 使用前预检连接有效性（防止断连错误）
)

# ============================================================
#  会话工厂（Session Factory）
#  ─────────────────────────────
#  expire_on_commit=False 确保提交后对象属性不过期，
#  避免在序列化阶段触发额外的懒加载查询
#  ============================================================

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """
    所有 ORM 模型的声明式基类。

    使用 SQLAlchemy 2.0 的声明式映射风格（DeclarativeBase）。
    所有模型类继承自此类后自动获得表映射能力。

    例如：
      class Document(Base):
          __tablename__ = "documents"
          id: Mapped[str]
          ...
    """
    pass


# ============================================================
#  会话依赖注入（FastAPI Dependency）
#  ─────────────────────────────────
#  作为路由函数的依赖项使用，自动管理会话生命周期：
#  创建 → 执行 → 提交（正常）/ 回滚（异常）→ 关闭
#  ============================================================

async def get_db() -> AsyncSession:
    """
    FastAPI 依赖项：提供异步数据库会话。

    生命周期：
    - 请求到达时创建新会话
    - 路由函数执行完成后自动提交
    - 出现异常时自动回滚
    - 无论成功或失败，最终都会关闭会话归还连接到池

    用法示例（在路由文件中）：
        @router.post("/upload")
        async def upload_document(
            file: UploadFile,
            db: AsyncSession = Depends(get_db),
        ):
            doc = await upload_and_index_document(file, db)
            return {"id": doc.id}

    Yields:
        AsyncSession: 异步数据库会话实例
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ============================================================
#  数据库初始化（Database Initialization）
#  ──────────────────────────────────────
#  在应用启动时调用，按顺序执行以下步骤：
#  ============================================================

async def init_db():
    """
    初始化数据库：创建扩展、表、索引和全文搜索基础设施。

    执行顺序：
    1. 启用 pgvector 向量扩展
    2. 创建所有 ORM 映射的表（Base.metadata.create_all）
    3. 执行幂等模式迁移（安全地添加缺失的列）
    4. 创建全文搜索 GIN 索引
    5. 创建向量搜索 HNSW 索引
    6. 对已有数据执行 CJK 分词重建

    所有 DDL 操作使用 IF NOT EXISTS / IF NOT FOUND 保证幂等性，
    可在每次启动时安全重复执行。

    在 main.py 的应用生命周期事件中调用：
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            await init_db()
            yield
    """
    from sqlalchemy import text
    # 导入模型以确保它们注册到 Base.metadata
    from app.models import Conversation, Message, Document, DocumentChunk, AgentConfig  # noqa

    async with engine.begin() as conn:
        # ── 步骤 1：启用 pgvector 扩展 ──
        # vector 类型用于存储文本嵌入向量（默认 1024 维）
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # ── 步骤 2：创建所有表 ──
        # Base.metadata.create_all 会根据模型定义自动建表
        # 已存在的表不会重复创建
        await conn.run_sync(Base.metadata.create_all)

        # ── 步骤 3：幂等模式迁移（按需添加新列）──
        # 使用 PL/pgSQL 的 DO 块检查列是否存在，不存在则添加
        # 这种方式避免了使用 Alembic 迁移工具的复杂性

        # Document.source：区分用户知识库和管理员知识库
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

        # AgentConfig.is_protected：标记 Agent 是否为受保护的内置 Agent
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

        # AgentConfig.allow_delegation：是否允许 Agent 委托任务给其他 Agent
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

        # ── 步骤 4：添加 tsvector 列 ──
        # search_vector 列用于存储全文搜索的词素索引
        # PostgreSQL tsvector 类型：存储规范化词素 + 位置信息
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

        # ── 步骤 5：GIN 全文搜索索引 ──
        # GIN（Generalized Inverted Index）是倒排索引，
        # 用于加速 tsvector 的 @@ 包含查找操作
        # 专为 ts_rank 相关性排序优化
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_search
            ON document_chunks USING GIN (search_vector);
        """))

        # ── 步骤 6：HNSW 向量搜索索引 ──
        # HNSW（Hierarchical Navigable Small World）是当前最高效的
        # 高维向量近似最近邻（ANN）搜索算法之一
        #
        # 参数说明：
        #   m = 16              每层节点的最大连接数（16 是平衡值）
        #   ef_construction = 200  构建搜索图时的探索宽度
        #   vector_cosine_ops   使用余弦距离作为相似度度量
        #
        # 性能特点：
        #   搜索复杂度 O(log N)，比 IVFFlat 的 O(sqrt(N)) 快一个数量级
        #   搜索精度约 99%（相比暴力搜索的轻微损失）
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_hnsw
            ON document_chunks USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 200);
        """))

    # ── 步骤 7：CJK 分词重建已有的文档块索引 ──
    await _reindex_existing_chunks()


# ============================================================
#  已有数据重新索引（Re-index Existing Chunks）
#  ──────────────────────────────────────────
#  使用 CJK 分词重新填充所有已存在文档块的 search_vector 列。
#  在 Python 端处理（而非 PL/pgSQL）以避免字符串转义问题。
#  ============================================================

async def _reindex_existing_chunks():
    """
    使用 CJK 感知分词重新填充所有已有文档块的 search_vector。

    为什么在 Python 端处理：
    - PL/pgSQL 中处理中文需要复杂的转义和编码处理
    - Python 的 retriever._cjk_tokenize() 已经实现完整的 CJK 分词逻辑
    - 在 Python 端逐块更新，逻辑清晰且易于调试

    执行流程：
    1. 查询所有文档块的 id 和 content
    2. 对每条 content 执行 CJK 分词
    3. 用 to_tsvector('simple', tokenized_content) 更新 search_vector
    4. 提交事务

    注意：此函数仅在 init_db() 中调用，用于修复已有数据或升级后的索引重建。
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
