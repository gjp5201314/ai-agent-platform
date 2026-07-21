"""
================================================================================
  共享工具函数（Shared Utilities）
================================================================================

本模块提供 admin.py 和 rag.py 路由间复用的共享逻辑，
主要涵盖文档上传和索引的完整管线，避免在两个路由文件中重复实现。

================================================================================
  文档处理管线（Document Processing Pipeline）
================================================================================

  完整管线流程图：

    用户上传文件
         │
         ▼
  ┌──────────────────────┐
  │  1. 文件类型验证      │  ← get_file_type() 提取后缀
  │     检查后缀是否在     │     supported_types 集合中
  │     支持列表中         │
  └──────────┬───────────┘
             │
             ▼
  ┌──────────────────────┐
  │  2. 重复检测（SHA-256）│  ← 计算文件内容哈希
  │     相同内容的文件     │     按 content_hash + source 查重
  │     不允许重复上传     │
  └──────────┬───────────┘
             │
             ▼
  ┌──────────────────────┐
  │  3. 创建 Document 行   │  ← 状态设为 "processing"
  │     写入数据库         │     source: "user" 或 "admin"
  └──────────┬───────────┘
             │
             ▼
  ┌──────────────────────┐
  │  4. 文档索引           │  ← 调用 index_document()
  │     提取 → 分块 → 嵌入 │    (retriever.py)
  │     → 存储向量         │
  └──────────┬───────────┘
             │
             ▼
  ┌──────────────────────┐
  │  5. 提交事务           │  ← 状态自动变为 "ready"
  │     返回完整 Document  │     若失败则标记 "error"
  │     对象               │
  └──────────────────────┘

================================================================================
  双来源设计（Source Field）
================================================================================

  Document 表有一个 source 字段，用于区分文档的来源：

  - "user"  ：外部用户通过 RAG 聊天界面（rag.py）上传的知识库文档
  - "admin" ：管理员通过管理后台（admin.py）上传的公共参考文档

  这种设计允许：
  1. 用户只能搜索自己上传的文档（source="user"）
  2. 管理员配置的 Agent 可以访问管理员文档（source="admin"）
  3. 通过 content_hash + source 的组合唯一约束防止跨来源的误判重复

================================================================================
  支持的文件类型（SUPPORTED_RAG_TYPES）
================================================================================

  当前支持上传到 RAG 知识库的文件格式：
  - 文档类：pdf, docx, txt, md
  - 数据类：csv, json, yaml, yml, xml
  - 代码类：py, js, ts, html, css, sql
  - 日志类：log
"""
import hashlib
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document
from app.rag.retriever import index_document

# 支持上传到 RAG 知识库的文件类型后缀集合
# 注意：chunker.py 的 extract_text_from_bytes() 额外支持 PDF/DOCX/MD 的
# 文本提取，但上传层面允许更多格式（如代码文件作为纯文本处理）
SUPPORTED_RAG_TYPES = {
    "pdf", "docx", "txt", "md", "csv", "py", "js", "ts",
    "json", "yaml", "yml", "xml", "html", "css", "sql", "log",
}


def get_file_type(filename: str) -> str:
    """
    从文件名中提取小写文件扩展名。

    例如：
      "report.pdf"    → "pdf"
      "script.PY"     → "py"
      "README"        → ""（无后缀）

    Args:
        filename: 文件名（可以是完整的文件路径或仅文件名）

    Returns:
        小写的文件扩展名，不含点号；若无后缀则返回空字符串
    """
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


async def upload_and_index_document(
    file: UploadFile,
    db: AsyncSession,
    *,
    source: str = "user",
    supported_types: set = None,
) -> Document:
    """
    文档上传 + 索引的完整管线（admin.py 和 rag.py 的公共入口）。

    管线步骤：
    1. 验证文件类型（检查后缀是否在允许列表中）
    2. 计算 SHA-256 哈希，检测重复上传
    3. 创建 Document 数据库记录（status="processing"）
    4. 调用 index_document() 执行文本提取、分块、嵌入、向量存储
    5. 提交事务，返回完整的 Document ORM 对象

    错误处理：
    - 不支持的文件类型 → HTTP 400
    - 空文件          → HTTP 400
    - 重复文件        → HTTP 409
    - 索引失败        → HTTP 500（同时将文档状态标记为 "error"）

    Args:
        file: FastAPI 上传文件对象（UploadFile）
        db: 异步数据库会话
        source: 文档来源标识（"user" 或 "admin"），影响后续搜索可见性
        supported_types: 自定义允许的文件类型集合（默认使用 SUPPORTED_RAG_TYPES）

    Returns:
        已索引的 Document ORM 对象（包含 id, filename, status, source 等字段）

    Raises:
        HTTPException: 上传或索引过程中的各类错误
    """
    if supported_types is None:
        supported_types = SUPPORTED_RAG_TYPES

    # 步骤 1：文件类型验证
    file_type = get_file_type(file.filename)
    if file_type not in supported_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_type}. Supported: {', '.join(sorted(supported_types))}",
        )

    # 读取文件内容到内存
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # 步骤 2：SHA-256 哈希去重
    # 相同内容 + 相同来源的文档不允许重复上传
    content_hash = hashlib.sha256(file_bytes).hexdigest()
    existing = await db.execute(
        select(Document).where(
            Document.content_hash == content_hash,
            Document.source == source,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This document has already been uploaded.")

    # 步骤 3：创建 Document 记录（状态：processing）
    doc = Document(
        id=str(uuid4()),
        filename=file.filename,
        file_type=file_type,
        file_size=len(file_bytes),
        content_hash=content_hash,
        status="processing",
        source=source,
    )
    db.add(doc)
    await db.flush()

    # 步骤 4 & 5：索引文档并提交事务
    try:
        await index_document(db, doc.id, file_bytes, file_type, file.filename)
        await db.commit()
    except Exception as e:
        # 索引失败：标记为 error 状态，保持记录以便排查
        doc.status = "error"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Document indexing failed: {str(e)}")

    # 步骤 6：重新查询并返回完整的 Document 对象
    result = await db.execute(select(Document).where(Document.id == doc.id))
    return result.scalar_one()
