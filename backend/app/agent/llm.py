"""
================================================================================
LLM 工厂 — 大语言模型实例创建（前端必读）
================================================================================

这个文件是"模型选择层"。整套 Agent 系统只通过 `get_llm()` 这一个函数
来获取 LLM 实例，不用关心底层用的是通义千问、OpenAI 还是 Claude。

对前端开发者来说，关键概念：
-------------------------------------
1. 工厂模式（Factory Pattern）
   - 你告诉它 provider + 参数，它返回配置好的 LLM 实例
   - 所有 provider 都通过 OpenAI 兼容接口调用（包括千问和 Claude）
   - 这意味着前端不需要知道任何 SDK 细节

2. 实例缓存（_llm_cache）
   - 相同参数创建的 LLM 实例会被复用，避免重复创建网络连接
   - 缓存键 = provider + model + temperature + max_tokens 的组合

3. 视觉模型自动检测（has_images 参数）
   - 当用户上传了图片到对话中，前端会在 agent_config 中设置 has_images=True
   - get_llm() 检测到这个标志后，自动切换为视觉模型（如 qwen-vl-plus）
   - 前端无需手动指定模型名，只需在消息中传递图片 URL 即可

数据流（从前端视角）：
  前端发送请求 → API 层提取 agent_config（含 provider, temperature, has_images）
  → 调用 get_llm() → 返回可流式输出的 LLM 实例 → Agent 节点使用它生成回复
  → 回复以 SSE token 事件逐个推送到前端
"""
from typing import Optional

from langchain_openai import ChatOpenAI

from app.config import settings


# ============================================================================
# LLM 实例缓存
# 相同参数创建的实例会被复用，减少重复初始化的开销。
# 键格式: "{provider}_{model}_{temperature}_{max_tokens}"
# ============================================================================
_llm_cache: dict = {}


def get_llm(
    provider: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    has_images: bool = False,
) -> ChatOpenAI:
    """
    创建或从缓存中获取 LLM 实例（工厂方法）。

    这是整个 Agent 系统中获取 LLM 的唯一入口。
    根据 provider 参数创建对应的模型客户端，所有 provider 统一使用
    OpenAI 兼容的 API 接口，前端无需关心底层 SDK 差异。

    参数说明：
        provider:    覆盖 .env 中配置的默认 provider（qwen / openai / claude）
        temperature: 采样温度（0-1），越低越确定，越高越有创造性
        max_tokens:  模型回复的最大 token 数
        has_images:  如果为 True，自动切换到视觉模型（如 qwen-vl-plus）

    返回：
        ChatOpenAI 兼容的模型实例，支持流式输出 (streaming=True)

    provider 选择逻辑：
        - "qwen"   → 阿里云百炼（DashScope），通过 OpenAI 兼容接口
        - "openai" → OpenAI API，支持自定义 base_url（用于中转 API）
        - "claude" → Anthropic Claude，通过 OpenAI 兼容代理

    视觉模型自动切换：
        仅对 qwen provider 有效。当 has_images=True 时，
        model 从 settings.qwen_model（如 qwen-plus）
        自动切换为 settings.qwen_vision_model（如 qwen-vl-plus）
    """
    provider = provider or settings.llm_provider

    # 视觉模型自动检测：当消息中包含图片时，自动切换为视觉模型
    model = settings.qwen_model
    if has_images and provider == "qwen":
        model = settings.qwen_vision_model

    cache_key = f"{provider}_{model}_{temperature}_{max_tokens}"

    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    if provider == "qwen":
        # 阿里云百炼（通义千问）— 通过 OpenAI 兼容接口调用
        llm = ChatOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True,
        )
    elif provider == "openai":
        # OpenAI / 中转 API — 标准的 OpenAI 协议
        llm = ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True,
        )
    elif provider == "claude":
        # Anthropic Claude — 通过 OpenAI 兼容代理调用
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
