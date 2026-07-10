"""
LLM factory: creates a chat model based on the configured provider.
Supports: Qwen (DashScope), OpenAI, Claude (Anthropic).
All accessed through OpenAI-compatible or native SDKs.
"""
from typing import Optional

from langchain_openai import ChatOpenAI

from app.config import settings


_llm_cache: dict = {}


def get_llm(
    provider: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> ChatOpenAI:
    """
    Create or retrieve a cached LLM instance.

    Args:
        provider:     Override the configured provider (qwen/openai/claude)
        temperature:  Sampling temperature
        max_tokens:   Max tokens for response

    Returns:
        A ChatOpenAI-compatible model instance.
        Qwen and OpenAI use ChatOpenAI directly (DashScope is OpenAI-compatible).
        Claude uses langchain_openai.ChatOpenAI with Anthropic's OpenAI-compat endpoint.

    Note: We use ChatOpenAI for all providers because:
      - DashScope (Qwen) provides an OpenAI-compatible endpoint
      - Anthropic also provides an OpenAI-compatible endpoint
      - This keeps the interface uniform for LangGraph tool calling
    """
    provider = provider or settings.llm_provider
    cache_key = f"{provider}_{temperature}_{max_tokens}"

    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    if provider == "qwen":
        llm = ChatOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
            model=settings.qwen_model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True,
        )
    elif provider == "openai":
        llm = ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True,
        )
    elif provider == "claude":
        # Anthropic OpenAI-compatible endpoint
        llm = ChatOpenAI(
            api_key=settings.anthropic_api_key,
            base_url="https://api.anthropic.com/v1/",
            model=settings.anthropic_model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Use: qwen, openai, or claude.")

    _llm_cache[cache_key] = llm
    return llm
