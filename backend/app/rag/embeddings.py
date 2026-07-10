"""
Embedding model wrapper.
Uses the openai library directly (not langchain's OpenAIEmbeddings)
to ensure correct request format for DashScope's OpenAI-compatible API.
"""
from typing import List, Optional
import asyncio

from openai import OpenAI

from app.config import settings

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """Get or create the OpenAI client for embedding API."""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.embedding_api_key or settings.dashscope_api_key,
            base_url=settings.embedding_base_url,
        )
    return _client


def _embed_query_sync(text: str) -> List[float]:
    """Synchronously embed a single text string."""
    client = _get_client()
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=text,
        dimensions=settings.embedding_dimensions,
    )
    return response.data[0].embedding


def _embed_texts_sync(texts: List[str]) -> List[List[float]]:
    """Synchronously embed a list of text strings (batched, max 10 per request)."""
    client = _get_client()
    all_embeddings = []
    # DashScope limits batch size to 10
    BATCH_SIZE = 10
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
            dimensions=settings.embedding_dimensions,
        )
        batch_embeddings = [d.embedding for d in sorted(response.data, key=lambda x: x.index)]
        all_embeddings.extend(batch_embeddings)
    return all_embeddings


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a batch of texts asynchronously."""
    return await asyncio.to_thread(_embed_texts_sync, texts)


async def embed_query(text: str) -> List[float]:
    """Embed a single query text."""
    return await asyncio.to_thread(_embed_query_sync, text)
