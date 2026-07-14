"""
Mem0 long-term memory integration.

Provides semantic memory for AI agents: automatically extracts, deduplicates,
and retrieves memories across conversations.

Uses PostgreSQL + pgvector for persistent vector storage (survives restarts).
LLM and embedding calls go through DashScope's OpenAI-compatible endpoint.
"""
from mem0 import Memory

from app.config import settings
from app.core.logger import logger

# Lazy-initialized client — NOT created at module import time
# (API key might not be available until after container startup)
_memory_client = None
_init_attempted = False
_init_error = None


def _get_client():
    """Get or lazily create the Mem0 memory client. Retries once after failure."""
    global _memory_client, _init_attempted, _init_error

    if _memory_client is not None:
        return _memory_client

    _init_attempted = True

    api_key = settings.dashscope_api_key
    if not api_key:
        _init_error = "DASHSCOPE_API_KEY is empty"
        logger.warning(f"Mem0 skipped: {_init_error}")
        return None

    config = {
        # ---- LLM: DashScope Qwen for memory extraction ----
        "llm": {
            "provider": "openai",
            "config": {
                "model": settings.qwen_model,
                "api_key": api_key,
                "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            },
        },
        # ---- Embedder: DashScope text-embedding-v3 ----
        "embedder": {
            "provider": "openai",
            "config": {
                "model": settings.embedding_model,
                "api_key": settings.embedding_api_key or api_key,
                "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            },
        },
        # ---- Vector Store: PostgreSQL + pgvector (PERSISTENT) ----
        # Previously: no vector_store config → default Qdrant in-memory → data lost on restart
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "host": settings.postgres_host,
                "port": settings.postgres_port,
                "user": settings.postgres_user,
                "password": settings.postgres_password,
                "dbname": settings.postgres_db,
                "collection_name": "mem0_memories",
                "embedding_model_dims": settings.embedding_dimensions,
            },
        },
    }

    try:
        _memory_client = Memory.from_config(config)
        logger.info(
            f"Mem0 memory client initialized (pgvector@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db})"
        )
        return _memory_client
    except Exception as e:
        _init_error = str(e)
        logger.error(f"Mem0 init FAILED: {e}")
        _memory_client = None
        return None


def get_memory_status() -> dict:
    """Return the current status of the Mem0 memory client for health checks."""
    client = _get_client()
    return {
        "initialized": client is not None,
        "attempted": _init_attempted,
        "error": _init_error,
    }


async def search_memories(query: str, user_id: str, limit: int = 5) -> list[dict]:
    """
    Search for memories relevant to the query.

    Returns list of dicts with keys: id, memory, hash, metadata, score
    """
    client = _get_client()
    if client is None:
        logger.debug(f"Mem0 search skipped: not initialized ({_init_error})")
        return []
    try:
        results = client.search(query, filters={"user_id": user_id}, limit=limit)
        if isinstance(results, dict):
            result_list = results.get("results", [])
            if result_list:
                logger.debug(f"Mem0 search found {len(result_list)} memories for user={user_id}")
            return result_list
        return []
    except Exception as e:
        logger.warning(f"Mem0 search error: {e}")
        return []


async def add_memories(messages: list[dict], user_id: str) -> None:
    """
    Extract and store memories from a conversation.

    Mem0 uses its LLM to automatically extract, deduplicate, and update
    memories from the conversation messages.

    Args:
        messages: list of {"role": "user"|"assistant", "content": "..."}
        user_id: identifier for the user (typically IP address)
    """
    if not messages:
        return
    client = _get_client()
    if client is None:
        logger.debug(f"Mem0 add skipped: not initialized ({_init_error})")
        return
    try:
        client.add(messages, user_id=user_id)
        logger.debug(f"Mem0 add: processed {len(messages)} messages for user={user_id}")
    except Exception as e:
        logger.warning(f"Mem0 add error: {e}")
