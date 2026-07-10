"""
Embedding model wrapper.
Uses DashScope (Qwen) OpenAI-compatible embedding API by default.
"""
from typing import List, Optional
import asyncio

from langchain_openai import OpenAIEmbeddings

from app.config import settings


# Singleton
_embedding_model: Optional[OpenAIEmbeddings] = None


def get_embedding_model() -> OpenAIEmbeddings:
    """
    Return the embedding model singleton.
    Default: DashScope text-embedding-v3 (OpenAI-compatible endpoint).
    """
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = OpenAIEmbeddings(
            api_key=settings.embedding_api_key or settings.dashscope_api_key,
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            # DashScope text-embedding-v3 supports dimensions param
            dimensions=settings.embedding_dimensions,
        )
    return _embedding_model


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a batch of texts asynchronously."""
    model = get_embedding_model()
    # langchain OpenAIEmbeddings.aembed_documents is async
    embeddings = await asyncio.to_thread(model.embed_documents, texts)
    return embeddings


async def embed_query(text: str) -> List[float]:
    """Embed a single query text."""
    model = get_embedding_model()
    embedding = await asyncio.to_thread(model.embed_query, text)
    return embedding
