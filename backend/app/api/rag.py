"""
================================================================================
RAG (检索增强生成) 知识库 API 模块
================================================================================

【模块职责】
  负责知识库文档的上传、管理、检索功能。支持PDF、DOCX、TXT、MD等格式的
  文档解析，自动分块(chunking)、向量嵌入(embedding)，并存储到 pgvector
  向量数据库中。提供混合检索（向量语义搜索 + BM25关键词搜索 + RRF融合）。

【API 设计规范】
  - 企业级安全设计：除 upload 端点因文件上传需要 multipart/form-data 外，
    其余所有端点均使用 POST + JSON Body 方式传参。
  - 文档ID、查询参数等敏感信息不会出现在 URL 中，避免被服务器日志记录。
  - 所有端点路径均不带查询字符串参数。

【5个核心端点一览】
  端点路径                      HTTP方法    请求方式                  用途
  ─────────────────────────────────────────────────────────────────────────
  /api/rag/documents/upload     POST        multipart/form-data      上传文档到知识库
  /api/rag/documents/list       POST        JSON Body {skip, limit}  分页列出所有文档
  /api/rag/documents/get        POST        JSON Body {id}           获取单个文档元数据
  /api/rag/documents/delete     POST        JSON Body {id}           删除文档及其所有分块
  /api/rag/search               POST        JSON Body {query, top_k} 混合搜索知识库
  /api/rag/stats                POST        无参数                   知识库统计信息

【重要：upload 端点的特殊性】
  upload 端点使用 multipart/form-data 编码，这是本项目中唯一不使用 JSON Body
  的 POST 端点。原因：浏览器原生的文件上传机制必须使用 form-data 格式，无法
  通过 JSON 传输二进制文件内容。

  前端调用示例（使用 fetch API）：
    const formData = new FormData();
    formData.append('file', fileObject);  // fileObject 来自 <input type="file">
    fetch('/api/rag/documents/upload', {
      method: 'POST',
      body: formData,  // 不要设置 Content-Type，浏览器会自动带 boundary
    });

  其他端点调用示例（POST + JSON）：
    fetch('/api/rag/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: '什么是RAG？', top_k: 5 }),
    });

【搜索返回结果格式说明】
  RagSearchResult 结构体包含以下字段：
    - document_id:  str   所属文档ID
    - chunk_index:  int   文档内的分块序号（从0开始）
    - content:      str   匹配到的文本片段内容
    - score:        float 混合检索相关性分数
    - filename:     str   来源文件名
    - chunk_id:     str   分块唯一ID

【混合检索 (Hybrid Search) 原理】
  本系统使用 "向量语义搜索 + BM25关键词搜索 + RRF融合" 的混合检索策略：

  1. 向量语义搜索 (Vector/Semantic Search)
     - 将用户查询通过 Embedding 模型转为高维向量
     - 在 pgvector 中做余弦相似度(cosine similarity)检索
     - 优点：理解语义，同义词/近义词也能匹配
     - 缺点：可能忽略精确的关键词匹配

  2. BM25 关键词搜索 (Keyword Search)
     - 经典的 TF-IDF 改进算法，对文档分词后建立倒排索引
     - 优点：精确匹配专业术语、缩写、编号等
     - 缺点：不理解语义，不会联想同义词

  3. RRF (Reciprocal Rank Fusion) 融合
     - 将两种搜索的结果通过倒数排名融合算法合并
     - 公式：RRF_score(d) = Σ 1/(k + rank_i(d))
       其中 k=60（平滑常数），rank_i 是文档在第 i 个排序列表中的排名
     - 优点：综合语义理解和关键词精确匹配的优势

【搜索分数 (score) 解读指南】

  前端展示时，分数含义参考如下：

    分数范围     含义                        前端建议操作
    ─────────────────────────────────────────────────────────────
    >= 0.8       高度相关，几乎确定命中       绿色/深色标记，优先展示
    0.5 - 0.8    中等相关，内容相关但不确定   黄色标记，正常展示
    0.3 - 0.5    低相关，可能部分匹配         灰色标记，谨慎参考
    < 0.3        基本不相关                   可考虑隐藏或标记为"低置信度"

  注意：分数是 RRF 融合后的排名分数，不是原始余弦相似度，不同查询之间的
  分数不具有可比性。建议设置 score 阈值（如 0.3）来过滤低质量结果。

【依赖组件】
  - app.rag.chunker:      文档解析与分块（支持 PDF/DOCX/TXT/MD）
  - app.rag.retriever:    向量索引与混合检索
  - app.shared:           共享工具函数（上传+索引的完整流程）
  - pgvector 扩展:        PostgreSQL 向量存储
"""

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Document, DocumentChunk
from app.rag.chunker import extract_text_from_bytes
from app.rag.retriever import index_document, hybrid_search
from app.shared import upload_and_index_document
from app.schemas import (
    DocumentOut,
    RagSearchResult,
    RagSearchRequest,
    RagDocumentListRequest,
    RagDocumentGetRequest,
    RagDocumentDeleteRequest,
)


router = APIRouter()

# ============================================================================
# 端点 1/6: 上传文档 (multipart/form-data)
# ============================================================================
# 【特别注意】这是项目中唯一使用 multipart/form-data 的 POST 端点。
# 原因：浏览器文件上传必须使用 form-data 格式，无法通过 JSON 传输二进制内容。
# 前端调用时不要手动设置 Content-Type header，让浏览器自动添加 boundary 参数。
#
# 请求格式：multipart/form-data
#   字段名: file
#   类型:   File (PDF, DOCX, TXT, MD)
#   大小限制: 由服务端 upload_and_index_document 函数控制
#
# 处理流程：
#   1. 接收上传文件
#   2. 解析文档内容（PDF→文本、DOCX→文本等）
#   3. 将文本按语义边界切分为 chunks
#   4. 对每个 chunk 生成 Embedding 向量
#   5. 存储原文+向量到 pgvector 数据库
#   6. 返回 DocumentOut（包含 id, filename, chunk_count 等）
#
# 响应示例：
#   {
#     "id": "doc_abc123",
#     "filename": "产品手册.pdf",
#     "file_type": "pdf",
#     "file_size": 1048576,
#     "chunk_count": 42,
#     "status": "completed",
#     "source": "user"
#   }

@router.post("/documents/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    上传文档到知识库。
    文件会被解析、分块、向量化嵌入，并存储到 pgvector。
    支持格式：PDF, DOCX, TXT, MD
    """
    doc = await upload_and_index_document(file, db, source="user")
    return doc


# ============================================================================
# 端点 2/6: 列出文档 (POST + JSON Body)
# ============================================================================
# 分页查询所有已上传文档的元数据列表。
# 通过 POST Body 传递分页参数，而非 URL 查询字符串，避免参数被服务器日志记录。
#
# 请求体 (RagDocumentListRequest):
#   {
#     "skip": 0,    // 跳过前 N 条记录（偏移量），默认 0
#     "limit": 20   // 返回的最大记录数（每页条数），默认 20
#   }
#
# 响应：DocumentOut[] 数组，按 created_at 降序（最新上传的在前）。
# 前端可用于构建文档管理列表页面。

@router.post("/documents/list", response_model=list[DocumentOut])
async def list_documents(
    request: RagDocumentListRequest,
    db: AsyncSession = Depends(get_db),
):
    """列出所有文档（分页参数通过 POST Body 传递，而非 URL 查询字符串）。"""
    result = await db.execute(
        select(Document)
        .order_by(Document.created_at.desc())
        .offset(request.skip)
        .limit(request.limit)
    )
    return result.scalars().all()


# ============================================================================
# 端点 3/6: 获取文档详情 (POST + JSON Body)
# ============================================================================
# 根据文档 ID 获取单个文档的元数据。文档 ID 在 POST Body 中传递。
#
# 请求体 (RagDocumentGetRequest):
#   {
#     "id": "doc_abc123"  // 文档唯一ID（上传时返回的 id）
#   }
#
# 响应：DocumentOut 对象，包含文档的完整元数据。
# 如果文档不存在，返回 404 错误。
# 注意：此端点只返回元数据，不返回文档的实际内容和分块。如需查看分块内容，
# 请使用 search 端点。

@router.post("/documents/get", response_model=DocumentOut)
async def get_document(
    request: RagDocumentGetRequest,
    db: AsyncSession = Depends(get_db),
):
    """获取单个文档的元数据（doc_id 通过 POST Body 传递）。"""
    result = await db.execute(select(Document).where(Document.id == request.id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


# ============================================================================
# 端点 4/6: 删除文档 (POST + JSON Body)
# ============================================================================
# 删除指定文档及其所有关联的向量分块。
# 删除是级联的：删除 Document 记录时，所有关联的 DocumentChunk 也会被删除。
#
# 请求体 (RagDocumentDeleteRequest):
#   {
#     "id": "doc_abc123"  // 要删除的文档ID
#   }
#
# 响应：
#   {
#     "detail": "Document '产品手册.pdf' deleted successfully"
#   }
#
# 注意：删除操作不可逆，前端应弹出确认对话框。

@router.post("/documents/delete")
async def delete_document(
    request: RagDocumentDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """删除文档及其所有关联的分块（doc_id 通过 POST Body 传递）。"""
    result = await db.execute(select(Document).where(Document.id == request.id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.execute(delete(Document).where(Document.id == request.id))
    await db.commit()
    return {"detail": f"Document '{doc.filename}' deleted successfully"}


# ============================================================================
# 端点 5/6: 混合搜索 (POST + JSON Body) — 核心检索端点
# ============================================================================
# 对知识库进行混合检索，结合向量语义搜索和 BM25 关键词搜索。
#
# 请求体 (RagSearchRequest):
#   {
#     "query": "什么是RAG架构？",  // 搜索查询文本，支持自然语言
#     "top_k": 5                   // 返回最相关的前 K 条结果，默认 5
#   }
#
# 响应：RagSearchResult[] 数组，按 score 降序排列。
#
# 搜索分数解读（详见文件顶部注释）：
#   >= 0.8  高度相关（绿色标记）
#   0.5-0.8 中等相关（黄色标记）
#   0.3-0.5 低相关  （灰色标记）
#   < 0.3   基本不相关（可隐藏）
#
# 前端使用建议：
#   1. 显示搜索结果时按 score 降序排列
#   2. 可用不同颜色深浅表示相关度高低
#   3. 建议设置最低分数阈值（如 score > 0.3）过滤噪音
#   4. 高亮显示 content 中与 query 匹配的关键词
#   5. 显示来源文件名 (filename) 方便用户溯源

@router.post("/search", response_model=list[RagSearchResult])
async def search_knowledge_base(
    request: RagSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    混合搜索知识库（语义相似度 + BM25 关键词）。
    通过 RRF (Reciprocal Rank Fusion) 算法融合两种搜索结果。
    """
    results = await hybrid_search(
        db,
        query=request.query,
        top_k=request.top_k,
    )
    return results


# ============================================================================
# 端点 6/6: 知识库统计 (POST + JSON Body，无参数)
# ============================================================================
# 获取知识库的整体统计信息，无需任何请求参数。
#
# 响应示例：
#   {
#     "document_count": 128,    // 已上传文档总数
#     "chunk_count": 3840,      // 所有文档的分块总数
#     "total_size_mb": 256.5    // 文档总存储大小（MB）
#   }
#
# 前端使用场景：知识库管理页面的概览面板、存储空间监控。

@router.post("/stats")
async def knowledge_base_stats(db: AsyncSession = Depends(get_db)):
    """获取知识库统计信息（POST，无敏感参数）。"""
    doc_count = await db.execute(select(func.count(Document.id)))
    chunk_count = await db.execute(select(func.count(DocumentChunk.id)))
    total_size = await db.execute(select(func.sum(Document.file_size)))

    return {
        "document_count": doc_count.scalar(),
        "chunk_count": chunk_count.scalar(),
        "total_size_mb": round((total_size.scalar() or 0) / 1024 / 1024, 2),
    }
