"""
================================================================================
  嵌入模型包装器（Embedding Model Wrapper）
================================================================================

本模块封装了对 DashScope 嵌入 API 的调用，为 RAG 系统提供文本到向量的转换能力。

================================================================================
  嵌入模型（Embedding Model）
================================================================================

  API 提供商：阿里云 DashScope（灵积模型服务）
  模型名称：text-embedding-v3（配置项：settings.embedding_model）
    
  text-embedding-v3 是目前 DashScope 最新的通用文本嵌入模型，特点：
  - 支持多语言（中文、英文为主）
  - 支持可变维度（dimensions 参数，默认 1024 维）
  - 最大输入：约 2048 tokens / 次（单条文本）
  - 批量请求上限：10 条 / 次（API 硬限制）

  API 端点：settings.embedding_base_url
  - 使用 DashScope 兼容的 OpenAI API 格式
  - 认证方式：API Key（settings.embedding_api_key 或 settings.dashscope_api_key）

  技术选型说明：
  - 直接使用 OpenAI SDK（openai 包）调用，而非 LangChain 的 OpenAIEmbeddings
  - 原因：LangChain 包装器会自动添加额外的 JSON 字段，与 DashScope 的
    OpenAI 兼容格式不完全一致，可能导致请求失败或返回空结果

================================================================================
  批量嵌入（Batch Embedding）
================================================================================

  为了在文档索引时高效处理大量文本块，本模块实现了批量嵌入策略：

  架构：
    ┌──────────────────────────────────────────────────────┐
    │  embed_texts(texts: List[str])                       │
    │  ─────────────────────────────────────────────       │
    │  异步入口（在 asyncio 事件循环中使用）                  │
    │         │                                            │
    │         ▼  asyncio.to_thread()  ← 避免阻塞事件循环    │
    │  _embed_texts_sync(texts: List[str])                 │
    │  ─────────────────────────────────────────────       │
    │  同步实现，分批次调用 DashScope API                    │
    │         │                                            │
    │         ├── 每批次最多 10 条（BATCH_SIZE = 10）        │
    │         │    这是 DashScope API 的硬限制               │
    │         │                                            │
    │         ├── 响应按 index 排序（API 可能打乱顺序）       │
    │         │                                            │
    │         └── 合并所有批次结果后返回                      │
    └──────────────────────────────────────────────────────┘

  单条查询嵌入：
    embed_query() 用于将用户搜索查询转为向量，与批量索引分离。
    查询也通过 asyncio.to_thread() 异步化，不阻塞 API 请求线程。
"""
from typing import List, Optional
import asyncio

from openai import OpenAI

from app.config import settings

# --------------------------------------------------------------------------
# 客户端单例：整个应用生命周期内复用同一个 OpenAI 客户端实例
# 避免重复创建连接的开销
# --------------------------------------------------------------------------
_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """
    获取或创建 OpenAI 客户端实例（懒加载单例模式）。
    
    客户端配置：
    - api_key：嵌入 API 的认证密钥
    - base_url：嵌入 API 的端点地址（DashScope 兼容 OpenAI 格式）

    Returns:
        OpenAI 客户端实例
    """
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.embedding_api_key or settings.dashscope_api_key,
            base_url=settings.embedding_base_url,
        )
    return _client


def _embed_query_sync(text: str) -> List[float]:
    """
    同步嵌入单个文本字符串。

    将一条文本转换为一个浮点数向量（如 1024 维）。
    用于将用户的搜索查询转为向量以进行语义搜索。

    Args:
        text: 待嵌入的文本（通常是用户搜索查询）

    Returns:
        浮点数向量列表（维度由 settings.embedding_dimensions 决定，默认 1024）
    """
    client = _get_client()
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=text,
        dimensions=settings.embedding_dimensions,
    )
    return response.data[0].embedding


def _embed_texts_sync(texts: List[str]) -> List[List[float]]:
    """
    同步批量嵌入文本列表（分批处理，每批最多 10 条）。

    将多条文本批量转换为向量。自动按 BATCH_SIZE=10 分批，
    每批独立调用一次 DashScope API。
    响应结果按 API 返回的 index 字段排序以确保顺序正确。

    分批原因：
    - DashScope API 限制每次请求最多 10 条文本
    - 超过 10 条会返回错误

    Args:
        texts: 待嵌入的文本列表（通常是一个文档的所有分块）

    Returns:
        向量列表的列表，与输入顺序一一对应
        每个内层列表是一个浮点数向量
    """
    client = _get_client()
    all_embeddings = []
    # DashScope 批量请求限制：每次最多 10 条
    BATCH_SIZE = 10
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
            dimensions=settings.embedding_dimensions,
        )
        # 按 API 返回的 index 排序，保证输出顺序与输入一致
        batch_embeddings = [d.embedding for d in sorted(response.data, key=lambda x: x.index)]
        all_embeddings.extend(batch_embeddings)
    return all_embeddings


# --------------------------------------------------------------------------
# 异步公开 API
# 前端/路由层调用这两个函数即可，无需关心同步/异步转换细节
# --------------------------------------------------------------------------

async def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    异步批量嵌入文本列表（文档索引时使用）。

    内部通过 asyncio.to_thread() 将同步 API 调用移到线程池执行，
    避免阻塞 asyncio 事件循环。

    Args:
        texts: 待嵌入的文本列表

    Returns:
        向量列表的列表，与输入顺序一一对应
    """
    return await asyncio.to_thread(_embed_texts_sync, texts)


async def embed_query(text: str) -> List[float]:
    """
    异步嵌入单个查询文本（用户搜索时使用）。

    内部通过 asyncio.to_thread() 将同步 API 调用移到线程池执行，
    避免阻塞 asyncio 事件循环。

    Args:
        text: 查询文本

    Returns:
        浮点数向量列表
    """
    return await asyncio.to_thread(_embed_query_sync, text)
