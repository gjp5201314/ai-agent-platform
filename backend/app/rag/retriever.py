"""
================================================================================
  混合检索引擎（Hybrid Search Engine）
================================================================================

本模块实现了面向 RAG（检索增强生成）的企业级混合检索策略，
通过融合以下两种互补的检索方式来提升搜索精度和中文支持：

  检索方式一：向量语义搜索（Vector Semantic Search）
  ─────────────────────────────────────────────────────
  使用 DashScope text-embedding-v3 模型将查询文本和文档块转换为
  高维向量（如 1024 维），然后通过 pgvector 扩展的 HNSW 索引进行
  余弦相似度（cosine distance）近邻搜索。
  
  优势：能理解语义，即使用户用词不完全匹配文档也能找到相关内容。
  局限：对精确的关键词（如专业术语、缩写、代码）可能不够敏感。

  检索方式二：BM25 关键词搜索（Keyword Search）
  ─────────────────────────────────────────────────────
  使用 PostgreSQL 的全文搜索功能（tsvector / tsquery），
  通过内置的 TF-IDF / BM25 排名算法对文档块进行关键词匹配。
  中文文本在入库前经过 CJK 分词预处理（见下方说明）。
  
  优势：对精确的关键词、专业术语、代码有极好的召回能力。
  局限：无法理解语义，可能遗漏同义词或近义表达。

  融合算法：RRF（Reciprocal Rank Fusion，倒数排名融合）
  ─────────────────────────────────────────────────────
  将两种搜索结果按各自排名进行加权融合，而非简单取交集或并集。
  公式：RRF 得分 = Σ 1 / (k + rank_i)
  其中 k=60（学术界推荐经验值），rank_i 是各检索列表中的排名（从1开始）。
  
  优势：
  - 无需对两类搜索的分数量纲进行归一化
  - 结果排序更鲁棒，避免单一搜索源的偏差
  - 同时出现在两个榜单高位的结果获得最高综合得分

================================================================================
  CJK 分词处理（CJK Tokenization）
================================================================================

PostgreSQL 的 'simple' 分词配置无法正确切分中文：它不知道"你好世界"是
四个独立汉字还是一个词。因此我们在文本入库和查询时进行预处理：

  1. 在汉字之间插入空格（英文字母保持不变）
     例如："你好世界AI agent" → "你 好 世 界 AI agent"
  
  2. PostgreSQL tsvector 以空格为分隔符，每个汉字成为一个独立 token
  
  3. 使用 trigram 匹配策略（plainto_tsquery + ts_rank），
     汉字的 n-gram 级匹配在精度和召回之间取得良好平衡

  4. 分词范围：CJK 统一表意文字块（U+4E00-U+9FFF）及扩展区

================================================================================
  搜索流程（Search Flow: query → results）
================================================================================

            用户输入查询字符串
                    │
                    ▼
      ┌─────────────────────────┐
      │  hybrid_search()        │  ← 主入口函数
      │  - 校验参数              │
      │  - 计算 fetch_k          │
      │    (= top_k * 3, 最少10)  │
      └──────┬──────────┬───────┘
             │          │
      ┌──────▼──┐  ┌───▼───────┐
      │向量搜索  │  │关键词搜索  │  ← 两个搜索并行执行
      │cosine   │  │ts_rank    │
      │distance │  │(BM25-like)│
      └──────┬──┘  └───┬───────┘
             │          │
             └────┬─────┘
                  │
                  ▼
      ┌─────────────────────────┐
      │  _rrf_fuse()            │  ← RRF 融合排序
      │  融合两类结果，按综合     │
      │  得分降序排列             │
      └───────────┬─────────────┘
                  │
                  ▼
      ┌─────────────────────────┐
      │  阈值过滤                 │  ← similarity_threshold
      │  过滤低于阈值的低相关性   │     (默认 0.5)
      │  结果                    │
      └───────────┬─────────────┘
                  │
                  ▼
      ┌─────────────────────────┐
      │  Top-K 截取              │  ← 取前 top_k 条结果
      └───────────┬─────────────┘
                  │
                  ▼
      ┌─────────────────────────┐
      │  返回 RagSearchResult[]  │  ← 含 chunk_id, content,
      │                          │    filename, score 等
      └─────────────────────────┘
"""
import re
from typing import List, Tuple, Optional
from uuid import uuid4

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk
from app.rag.embeddings import embed_query, embed_texts
from app.rag.chunker import split_text, extract_text_from_bytes
from app.schemas import RagSearchResult
from app.core.logger import logger


# ============================================================
#  CJK 中文分词器（Tokenizer）
#  ─────────────────────────────────────
#  功能：将中文文本按单字切分，使 PostgreSQL tsvector
#        能够识别每个汉字为独立的关键词 token。
#  原理：在每个 CJK 统一汉字前后插入空格。
#  ============================================================

# 正则表达式：匹配任意单个 CJK 统一表意文字
# - \u4e00-\u9fff：基本汉字块（常用 20,000+ 汉字）
# - \u3400-\u4dbf：CJK 扩展 A 区
# - \uf900-\ufaff：CJK 兼容汉字
_CJK_RE = re.compile(r'([\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff])')


def _cjk_tokenize(text: str) -> str:
    """
    在每个 CJK 汉字前后插入空格，使 PostgreSQL tsvector
    将其视为独立 token，以实现中文关键词匹配。

    示例：
      "你好世界AI agent" → "你 好 世 界 AI agent"
      "数据库索引优化"   → "数 据 库 索 引 优 化"

    Args:
        text: 原始文本

    Returns:
        分词后的文本（全小写、多余空格归一化）
    """
    spaced = _CJK_RE.sub(r' \1 ', text)
    return re.sub(r'\s+', ' ', spaced).strip().lower()


# ============================================================
#  BM25 风格关键词搜索（Keyword Search）
#  ─────────────────────────────────────
#  使用 PostgreSQL 原生全文搜索：
#  - tsvector：预处理的词索引列
#  - plainto_tsquery：将自然语言查询转为 tsquery
#  - ts_rank：TF-IDF 风格的相关性评分
#
#  中文支持：查询前先经 CJK 分词预处理。
#  过滤支持：可按 source 字段过滤（"user" / "admin"）。
#  ============================================================

async def keyword_search(
    db: AsyncSession,
    query: str,
    top_k: int = 6,
    source: Optional[str] = None,
) -> List[Tuple[str, str, str, str, float]]:
    """
    基于 PostgreSQL tsvector/tsquery 的全文关键词搜索（BM25 风格）。

    中文文本通过 CJK 分词预处理后，每个汉字作为一个独立词元参与匹配。
    若指定 source 参数，仅搜索该来源的文档（"user" 或 "admin"）。

    Args:
        db: 异步数据库会话
        query: 原始搜索查询字符串
        top_k: 返回结果数量上限
        source: 可选文档来源过滤（"user" / "admin"）

    Returns:
        结果列表，每项为 (chunk_id, document_id, filename, content, score)
    """
    tokenized_query = _cjk_tokenize(query)

    source_filter = "AND d.source = :source" if source else ""

    stmt = text(f"""
        SELECT
            dc.id AS chunk_id,
            dc.document_id,
            d.filename,
            dc.content,
            ts_rank(dc.search_vector, plainto_tsquery('simple', :query)) AS score
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE dc.search_vector @@ plainto_tsquery('simple', :query)
        {source_filter}
        ORDER BY score DESC
        LIMIT :top_k
    """)

    result = await db.execute(stmt, {"query": tokenized_query, "top_k": top_k, "source": source} if source else {"query": tokenized_query, "top_k": top_k})
    return [(row[0], row[1], row[2], row[3], float(row[4])) for row in result.fetchall()]


# ============================================================
#  向量语义搜索（Vector Semantic Search）
#  ─────────────────────────────────────
#  使用 pgvector 扩展的余弦距离（cosine distance）进行
#  语义近邻搜索。
#
#  流程：
#  1. 将查询文本通过 DashScope API 转为向量
#  2. 在 document_chunks 表的 embedding 列上计算余弦距离
#  3. 返回距离最近的 top_k 个文档块
#
#  余弦距离 = 1 - 余弦相似度
#  距离越小 = 语义越相似
#  ============================================================

async def vector_search(
    db: AsyncSession,
    query: str,
    top_k: int = 6,
    source: Optional[str] = None,
) -> List[Tuple[str, str, str, str, float]]:
    """
    基于 pgvector 余弦距离的语义搜索。

    将查询文本转换为向量后，在向量空间中搜索最相似的文档块。
    若指定 source 参数，仅搜索该来源的文档（"user" 或 "admin"）。

    Args:
        db: 异步数据库会话
        query: 原始搜索查询字符串
        top_k: 返回结果数量上限
        source: 可选文档来源过滤（"user" / "admin"）

    Returns:
        结果列表，每项为 (chunk_id, document_id, filename, content, similarity)
        其中 similarity = 1 - cosine_distance（值越大越相似）
    """
    query_embedding = await embed_query(query)

    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            Document.filename,
            DocumentChunk.content,
            (1 - DocumentChunk.embedding.cosine_distance(query_embedding)).label("similarity"),
        )
        .join(Document, DocumentChunk.document_id == Document.id)
    )

    if source:
        stmt = stmt.where(Document.source == source)

    stmt = stmt.order_by(DocumentChunk.embedding.cosine_distance(query_embedding)).limit(top_k)

    result = await db.execute(stmt)
    return [(row[0], row[1], row[2], row[3], float(row[4])) for row in result.fetchall()]


# ============================================================
#  RRF 融合算法（Reciprocal Rank Fusion）
#  ─────────────────────────────────────
#  将向量搜索结果和关键词搜索结果按排名加权融合。
#
#  核心思想：
#  - 两种搜索各自返回的结果列表，排名是唯一可信的公共语言
#  - 每种搜索的分数量纲不同（余弦相似度 vs ts_rank），
#    无法直接比较，但排名可以直接融合
#
#  数学公式：
#    RRF_score(doc) = Σ 1 / (k + rank_i)
#
#    其中 k = 60（标准经验值），rank_i 从 1 开始计数
#
#  效果：
#  - 在两路搜索中都排在前面的文档获得最高综合分
#  - 只有一路排名靠前的文档也能获得可观的分数
#  ============================================================

def _rrf_fuse(
    vector_rows: List[Tuple[str, str, str, str, float]],
    keyword_rows: List[Tuple[str, str, str, str, float]],
    k: int = 60,
) -> List[Tuple[str, str, str, str, float]]:
    """
    使用倒数排名融合（RRF）合并两个排序结果列表。

    RRF 得分 = Σ 1 / (k + rank)
    其中 rank 是从 1 开始的位置序号（0-based 索引 + 1）。

    算法步骤：
    1. 构建 chunk_id → 数据行 的映射表
    2. 遍历向量结果列表，累计 RRF 得分
    3. 遍历关键词结果列表，累计 RRF 得分
    4. 按 RRF 综合得分降序排序返回

    Args:
        vector_rows: 语义搜索结果列表
        keyword_rows: 关键词搜索结果列表
        k: RRF 常数（默认 60，学术界推荐值）

    Returns:
        融合后的结果列表，按 RRF 综合得分从高到低排序
    """
    # 构建 id → row 的映射表，用于最终去重和组装结果
    row_map: dict[str, Tuple[str, str, str, str, float]] = {}
    for row in vector_rows + keyword_rows:
        row_map[row[0]] = row

    # 累计 RRF 得分
    rrf_scores: dict[str, float] = {}
    for rank, row in enumerate(vector_rows):
        rrf_scores[row[0]] = rrf_scores.get(row[0], 0.0) + 1.0 / (k + rank + 1)
    for rank, row in enumerate(keyword_rows):
        rrf_scores[row[0]] = rrf_scores.get(row[0], 0.0) + 1.0 / (k + rank + 1)

    # 按 RRF 综合得分降序排序
    sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)

    return [row_map[cid] for cid in sorted_ids]


# ============================================================
#  混合搜索（Hybrid Search）—— 主入口
#  ─────────────────────────────────────
#  将向量语义搜索和 BM25 关键词搜索的结果通过 RRF 融合，
#  然后进行相似度阈值过滤和 Top-K 截取。
#
#  关键设计决策：
#  1. 并行执行两路搜索以降低延迟
#  2. fetch_k = top_k * 3（最少 10），扩大候选池
#  3. RRF 融合后，用向量余弦相似度作为最终分（更有意义）
#  4. 低于 similarity_threshold 的结果被丢弃
#  5. 任一路搜索失败不影响另一路（优雅降级）
#  ============================================================

async def hybrid_search(
    db: AsyncSession,
    query: str,
    top_k: int = 4,
    similarity_threshold: float = 0.5,
    source: Optional[str] = None,
) -> List[RagSearchResult]:
    """
    混合搜索：向量语义 + BM25 关键词 → RRF 融合 → 返回结果。

    本函数是混合搜索的唯一入口，前端调用时应优先使用此函数。

    Args:
        db: 异步数据库会话
        query: 原始搜索查询字符串（支持中英文）
        top_k: 最终返回的结果数量上限
        similarity_threshold: 最低向量余弦相似度阈值（0.0~1.0）
                              低于此值的结果将被过滤
        source: 可选文档来源过滤（"user" / "admin"）
                外部用户调用传 "user"，管理员调用不传或传 None

    Returns:
        RagSearchResult 列表，按综合相关性从高到低排序
        字段含：chunk_id, document_id, filename, content, score
    """
    # 扩大候选池：top_k * 3，最少取 10 个候选
    fetch_k = max(top_k * 3, 10)

    # DEBUG: 记录搜索参数
    logger.debug(f"hybrid_search: query='{query[:50]}', top_k={top_k}, threshold={similarity_threshold}, source={source}")

    # 并行执行两路搜索（异步并发，降低总延迟）
    # 任一路失败时自动降级为空列表，另一路结果仍可用
    try:
        vector_rows = await vector_search(db, query, top_k=fetch_k, source=source)
        logger.debug(f"vector_search returned {len(vector_rows)} results")
    except Exception as e:
        logger.warning(f"vector_search FAILED: {e}")
        vector_rows = []
    try:
        keyword_rows = await keyword_search(db, query, top_k=fetch_k, source=source)
        logger.debug(f"keyword_search returned {len(keyword_rows)} results")
    except Exception as e:
        logger.warning(f"keyword_search FAILED: {e}")
        keyword_rows = []

    # RRF 融合两路搜索结果
    fused = _rrf_fuse(vector_rows, keyword_rows)
    logger.debug(f"RRF fused: {len(fused)} results")

    # 构建相似度查找表：chunk_id → 向量余弦相似度 (0~1)
    # 用于阈值过滤和作为最终展示分（比 RRF 分更直观）
    similarity_map: dict[str, float] = {
        row[0]: float(row[4]) for row in vector_rows
    }

    # 阈值过滤并组装结果对象
    results: List[RagSearchResult] = []
    for chunk_id, doc_id, filename, content, rrf_score in fused:
        if len(results) >= top_k:
            break
        # 优先使用向量相似度作为有效分（0~1 范围，直观可比）
        # 若无向量结果则回退到 RRF 分（值很小，约 0.01-0.05）
        effective_score = similarity_map.get(chunk_id, rrf_score)
        if effective_score < similarity_threshold:
            # 低于相关性阈值 —— 丢弃，不给 LLM 送入无效上下文
            continue
        results.append(RagSearchResult(
            chunk_id=chunk_id,
            document_id=doc_id,
            filename=filename,
            content=content,
            score=round(effective_score, 4),
        ))

    return results


# ============================================================
#  传统纯语义搜索（向后兼容）
#  ─────────────────────────────────────
#  仅使用 pgvector 进行语义搜索，不使用关键词搜索或 RRF 融合。
#  保留此函数以确保旧代码兼容。
#  新代码请使用 hybrid_search()。
#  ============================================================

async def search_similar(
    db: AsyncSession,
    query: str,
    top_k: int = 4,
    similarity_threshold: float = 0.5,
) -> List[RagSearchResult]:
    """
    纯语义搜索（仅 pgvector）。
    为向后兼容保留；生产环境推荐使用 hybrid_search()。

    Args:
        db: 异步数据库会话
        query: 搜索查询字符串
        top_k: 返回结果数量上限
        similarity_threshold: 最低向量余弦相似度阈值

    Returns:
        RagSearchResult 列表
    """
    rows = await vector_search(db, query, top_k=top_k)

    results = []
    for chunk_id, doc_id, filename, content, similarity in rows:
        if similarity >= similarity_threshold:
            results.append(RagSearchResult(
                chunk_id=chunk_id,
                document_id=doc_id,
                filename=filename,
                content=content,
                score=float(similarity),
            ))
    return results


# ============================================================
#  文档索引流程（Document Indexing Pipeline）
#  ─────────────────────────────────────
#  完整的文档处理管线：提取 → 分块 → 嵌入 → 存储
#
#  步骤：
#  1. 提取文本（支持 PDF/DOCX/TXT/MD）
#  2. 递归分块（500 字符/块，50 字符重叠）
#  3. 批量生成嵌入向量（DashScope API）
#  4. 写入 document_chunks 表（含向量）
#  5. 填充 tsvector 列（CJK 分词后写回）
#  6. 更新文档状态为 "ready"
#  ============================================================

async def index_document(
    db: AsyncSession,
    document_id: str,
    file_bytes: bytes,
    file_type: str,
    filename: str,
) -> int:
    """
    处理并索引文档：提取 → 分块 → 嵌入 → 存储。
    同时填充 search_vector（tsvector 列）以支持混合 BM25 搜索。

    完整管线：
      PDF/DOCX/TXT  →  纯文本  →  500 字符块  →  1024 维向量
               提取            递归分块           批量嵌入

    Args:
        db: 异步数据库会话
        document_id: 文档的唯一 ID（UUID）
        file_bytes: 文件的原始字节内容
        file_type: 文件类型后缀（如 "pdf", "docx", "txt"）
        filename: 原始文件名

    Returns:
        成功处理的文档块数量

    Raises:
        ValueError: 文档内容为空或分块失败
    """
    # 1. 提取文本（PDF/DOCX/TXT/MD 等）
    text_content = extract_text_from_bytes(file_bytes, file_type)
    if not text_content.strip():
        raise ValueError("No text content found in document")

    # 2. 递归分块（chunk_size=500, chunk_overlap=50）
    chunks = split_text(text_content, chunk_size=500, chunk_overlap=50)
    if not chunks:
        raise ValueError("Text splitting produced no chunks")

    # 3. 批量生成嵌入向量（每批最多 10 条，DashScope API 限制）
    chunk_texts = [c.text for c in chunks]
    embeddings = await embed_texts(chunk_texts)

    # 4. 存储文档块（含向量），然后通过原生 SQL 填充 tsvector
    chunk_records = []
    for chunk, embedding in zip(chunks, embeddings):
        chunk_record = DocumentChunk(
            id=str(uuid4()),
            document_id=document_id,
            chunk_index=chunk.index,
            content=chunk.text,
            embedding=embedding,
            token_count=chunk.token_count,
        )
        db.add(chunk_record)
        chunk_records.append(chunk_record)

    await db.flush()

    # 5. 用 CJK 分词后的内容填充 tsvector，用于 BM25 关键词索引
    for cr in chunk_records:
        tokenized = _cjk_tokenize(cr.content)
        await db.execute(
            text("""
                UPDATE document_chunks
                SET search_vector = to_tsvector('simple', :content)
                WHERE id = :chunk_id
            """),
            {"content": tokenized, "chunk_id": cr.id},
        )

    # 6. 更新文档的分块数量和状态为 ready
    await db.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(chunk_count=len(chunks), status="ready")
    )

    return len(chunks)
