"""
Mem0 long-term memory integration.

Provides semantic memory for AI agents: automatically extracts, deduplicates,
and retrieves memories across conversations.

Mem0 uses Qdrant (in-process mode by default) for vector storage with
OpenAI-compatible embedding APIs (DashScope text-embedding-v3).
"""

from mem0 import Memory

from app.config import settings
from app.core.logger import logger

# Mem0 config — uses DashScope for both LLM (extraction) and embedding
_mem0_config = {
    "llm": {
        "provider": "openai",
        "config": {
            "model": settings.qwen_model,
            "api_key": settings.dashscope_api_key,
            "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        },
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "model": settings.embedding_model,
            "api_key": settings.embedding_api_key or settings.dashscope_api_key,
            "embedding_dims": settings.embedding_dimensions,
            "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        },
    },
}

try:
    _memory_client = Memory.from_config(_mem0_config)
except Exception as e:
    logger.warning(f"Mem0 init failed: {e}")
    _memory_client = None


async def search_memories(query: str, user_id: str, limit: int = 5) -> list[dict]:
    """
    Search for memories relevant to the query.

    Returns list of dicts with keys: id, memory, hash, metadata, score
    """
    if _memory_client is None:
        return []
    try:
        results = _memory_client.search(query, user_id=user_id, limit=limit)
        return results.get("results", []) if isinstance(results, dict) else []
    except Exception as e:
        logger.warning(f"Mem0 search error: {e}")
        return []


async def add_memories(messages: list[dict], user_id: str) -> None:
    """
    Extract and store memories from a conversation.

    Args:
        messages: list of {"role": "user"|"assistant", "content": "..."}
        user_id: identifier for the user (typically conversation_id or IP)
    """
    if _memory_client is None:
        return
    if not messages:
        return
    try:
        _memory_client.add(messages, user_id=user_id)
    except Exception as e:
        logger.warning(f"Mem0 add error: {e}")
