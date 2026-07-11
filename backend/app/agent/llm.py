"""
LLM factory: creates a chat model based on the configured provider.
Supports: Qwen (DashScope), OpenAI, Claude (Anthropic).
All accessed through OpenAI-compatible or native SDKs.
Auto-switches to vision models when image content is detected.
"""
from typing import Optional

from langchain_openai import ChatOpenAI

from app.config import settings


_llm_cache: dict = {}


def get_llm(
    provider: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    has_images: bool = False,
) -> ChatOpenAI:
    """
    Create or retrieve a cached LLM instance.

    Args:
        provider:     Override the configured provider (qwen/openai/claude)
        temperature:  Sampling temperature
        max_tokens:   Max tokens for response
        has_images:   If True, use vision-capable model (e.g. qwen-vl-plus)

    Returns:
        A ChatOpenAI-compatible model instance.
    """
    provider = provider or settings.llm_provider

    # Auto-select vision model for Qwen when images are present
    model = settings.qwen_model
    if has_images and provider == "qwen":
        model = settings.qwen_vision_model

    cache_key = f"{provider}_{model}_{temperature}_{max_tokens}"

    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    if provider == "qwen":
        llm = ChatOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
            model=model,
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
