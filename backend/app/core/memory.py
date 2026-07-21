"""
================================================================================
Mem0 长期记忆集成 — AI Agent 的跨对话"记忆"系统
================================================================================

【前端开发者必读】理解"长期记忆"概念

1. 什么是"AI 长期记忆"？

   通常的 AI 对话是"无状态"的：每次新的对话，AI 对用户一无所知。
   长期记忆系统让 AI 能够"记住"用户的偏好、背景和过去的交流，
   就像 ChatGPT 的 Memory 功能和 Character.AI 的角色记忆一样。

   【例子】没有记忆：
     用户第1天："我叫张三，我是Python后端工程师"
     用户第2天："帮我写个排序算法"
     AI: "好的，请问你用什么编程语言？"（忘记了用户是 Python 工程师）

   【例子】有记忆：
     用户第1天："我叫张三，我是Python后端工程师"
     用户第2天："帮我写个排序算法"
     AI: "好的，我用 Python 给你写一个快排实现..."（记住了用户偏好）

2. Mem0 是什么？

   Mem0 (https://mem0.ai) 是一个开源的 AI 记忆层，专门设计给 Agent 应用使用。
   它能够：
     a) 自动从对话中提取关键记忆（通过 LLM 分析对话内容）
     b) 自动去重和更新已有的记忆（不会重复存储相同信息）
     c) 语义搜索相关记忆（不是关键词匹配，而是意图匹配）
     d) 持久化存储到 PostgreSQL + pgvector（重启不丢失）

3. 记忆是如何存储和检索的？

   【存储流程】（在每次对话结束时自动触发）
     ┌───────────────────────────────────────────────────┐
     │ 用户和 AI 的对话消息列表                           │
     │ [{"role":"user","content":"我叫张三..."},          │
     │  {"role":"assistant","content":"你好张三..."}]     │
     └──────────────────┬────────────────────────────────┘
                        ▼
     ┌───────────────────────────────────────────────────┐
     │ Mem0 的 LLM 自动分析和提取关键信息                │
     │ → "用户名叫张三"                                  │
     │ → "用户是 Python 后端工程师"                      │
     │ → "用户偏好简洁的回复风格"                        │
     └──────────────────┬────────────────────────────────┘
                        ▼
     ┌───────────────────────────────────────────────────┐
     │ 将每条记忆转为 Embedding 向量                     │
     │ 存入 PostgreSQL 的 pgvector 表中                  │
     │ 如果与已有记忆相似 → 去重/更新，不新建            │
     └───────────────────────────────────────────────────┘

   【检索流程】（在每次新对话开始时自动触发）
     ┌───────────────────────────────────────────────────┐
     │ 用户发送新消息："帮我写代码"                      │
     └──────────────────┬────────────────────────────────┘
                        ▼
     ┌───────────────────────────────────────────────────┐
     │ 将用户消息转为 Embedding 向量                     │
     │ 在记忆中搜索语义最相似的前 N 条记忆               │
     │ 找到："用户是 Python 后端工程师"（相似度 0.87）   │
     └──────────────────┬────────────────────────────────┘
                        ▼
     ┌───────────────────────────────────────────────────┐
     │ 将找到的记忆注入到 LLM 的系统提示词中             │
     │ "背景信息：用户是 Python 后端工程师..."           │
     │ AI 据此生成更个性化的回复                          │
     └───────────────────────────────────────────────────┘

4. 基于 IP 的 user_id 方案

   本项目使用客户端 IP 地址作为 user_id，因为：
     a) 前端可能没有实现用户登录/注册系统
     b) 普通访客也能享受记忆功能，无需创建账号
     c) 实现简单，无需维护用户认证系统

   局限：
     a) 同一 IP 的多个用户共享记忆（如公司内网）
     b) 用户更换网络后记忆"丢失"（实际还在，只是无法关联）
     c) 隐私考虑：IP 地址可能被视为个人信息

   未来可以升级为基于 Token/JWT 的 user_id 方案。

================================================================================
"""
from mem0 import Memory

from app.config import settings
from app.core.logger import logger

# ==============================================================================
# Mem0 客户端 — 懒加载初始化
# ==============================================================================
# 不在模块导入时创建客户端，因为：
#   1. API Key 可能在容器启动后才通过环境变量注入
#   2. 数据库可能还未就绪
#   3. 允许应用在 Mem0 不可用时仍然正常启动（优雅降级）

# 懒加载初始化的客户端实例
# 初始值为 None，首次调用 _get_client() 时创建
_memory_client = None

# 标记是否已经尝试过初始化（用于健康检查状态报告）
_init_attempted = False

# 如果初始化失败，存储错误信息（用于诊断和健康检查）
_init_error = None


def _get_client():
    """
    获取或懒加载创建 Mem0 记忆客户端。失败后支持重试一次。

    【懒加载设计的原因】
    在模块导入时，环境变量（特别是 DashScope API Key）可能尚未设置。
    懒加载确保客户端在真正需要时才初始化，此时配置已经就绪。

    【优雅降级策略】
    如果初始化失败（如 API Key 缺失），不会抛出异常，
    而是记录警告并返回 None。后续的 add_memories 和 search_memories
    会检查客户端是否为 None，如果是则静默跳过。

    这意味着：即使 Mem0 功能不可用，AI 对话功能仍然正常工作，
    只是没有"跨对话记忆"能力。
    """
    global _memory_client, _init_attempted, _init_error

    # 如果已经成功创建过，直接返回缓存实例
    if _memory_client is not None:
        return _memory_client

    _init_attempted = True

    # 获取 DashScope API Key（Mem0 用它来调用 LLM 提取记忆）
    api_key = settings.dashscope_api_key
    if not api_key:
        _init_error = "DASHSCOPE_API_KEY is empty"
        logger.warning(f"Mem0 skipped: {_init_error}")
        return None

    # 构建 Mem0 配置
    # Mem0 需要三个核心组件：
    #   1. LLM（大语言模型）：用于从对话中提取和总结记忆
    #   2. Embedder（嵌入模型）：用于将记忆文本转为向量
    #   3. Vector Store（向量存储）：用于存储和搜索向量
    config = {
        # ---- LLM: DashScope Qwen for memory extraction ----
        # 配置 Mem0 使用通义千问来分析和提取关键记忆
        "llm": {
            "provider": "openai",          # 使用 OpenAI 兼容接口
            "config": {
                "model": settings.qwen_model,
                "api_key": api_key,
                "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            },
        },
        # ---- Embedder: DashScope text-embedding-v3 ----
        # 配置 Mem0 使用 DashScope 的 Embedding 模型
        # 将记忆文本转换为向量（浮点数数组）
        "embedder": {
            "provider": "openai",
            "config": {
                "model": settings.embedding_model,
                "api_key": settings.embedding_api_key or api_key,
                "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                # CRITICAL: Must pass embedding_dims to avoid dimension mismatch.
                # Without this, Mem0 uses OpenAI default (1536), but DashScope
                # text-embedding-v3 only supports: 64/128/256/512/768/1024.
                # Default 1536 → 400 error → all add/search silently fail.
                # 【重要】必须正确指定维度，否则 Mem0 会使用 OpenAI 默认的 1536 维，
                # 但 DashScope 的 text-embedding-v3 只支持 {64,128,256,512,768,1024}。
                # 维度不匹配会导致 API 返回 400 错误，所有 add/search 操作静默失败。
                "embedding_dims": settings.embedding_dimensions,
            },
        },
        # ---- Vector Store: PostgreSQL + pgvector (PERSISTENT) ----
        # 使用 PostgreSQL 的 pgvector 扩展存储记忆向量
        # 之前没有配置 vector_store 时，Mem0 默认使用 Qdrant 内存模式，
        # 数据在容器重启后会丢失。
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "host": settings.postgres_host,
                "port": settings.postgres_port,
                "user": settings.postgres_user,
                "password": settings.postgres_password,
                "dbname": settings.postgres_db,
                "collection_name": "mem0_memories",     # 记忆数据存储在独立的集合中
                "embedding_model_dims": settings.embedding_dimensions,
            },
        },
    }

    try:
        # 使用 from_config 工厂方法创建 Mem0 实例
        _memory_client = Memory.from_config(config)
        logger.info(
            f"Mem0 memory client initialized (pgvector@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db})"
        )
        return _memory_client
    except Exception as e:
        # 初始化失败——记录错误并优雅降级
        _init_error = str(e)
        logger.error(f"Mem0 init FAILED: {e}")
        _memory_client = None
        return None


def get_memory_status() -> dict:
    """
    获取 Mem0 记忆客户端的当前状态（用于健康检查）。

    【前端关联】
    可以在 /health 端点中返回此信息，让前端知道记忆功能是否可用。
    前端可以据此显示/隐藏"记忆"相关功能按钮。

    返回格式：
    {
      "initialized": true,       // Mem0 是否成功初始化
      "attempted": true,         // 是否已经尝试过初始化
      "error": null              // 如果失败，这里包含错误原因
    }
    """
    client = _get_client()
    return {
        "initialized": client is not None,
        "attempted": _init_attempted,
        "error": _init_error,
    }


async def search_memories(query: str, user_id: str, limit: int = 5) -> list[dict]:
    """
    搜索与用户查询相关的记忆。

    【工作流程】
    1. 将查询文本转为向量（通过 Embedding 模型）
    2. 在 pgvector 中搜索余弦相似度最高的记忆
    3. 返回前 limit 条最相关的结果

    【前端关联】
    前端无需直接调用此函数。记忆搜索在后端处理用户消息时自动触发。
    搜索到的记忆会被注入到 system prompt 中（如"背景信息"）。

    参数：
      query:   用户的查询文本（如"帮我写代码"）
      user_id: 用户标识符（目前使用客户端 IP 地址）
      limit:   最多返回的记忆条数（默认 5）

    返回：
      记忆列表，每条记忆包含：
        - id: 记忆唯一 ID
        - memory: 记忆文本内容（如"用户是Python工程师"）
        - hash: 内容哈希（用于去重）
        - metadata: 元数据（来源对话 ID 等）
        - score: 相似度分数（0.0~1.0，越高越相关）
    """
    client = _get_client()
    if client is None:
        logger.debug(f"Mem0 search skipped: not initialized ({_init_error})")
        return []
    try:
        # 调用 Mem0 的 search 方法进行语义搜索
        results = client.search(query, user_id=user_id, limit=limit)

        # Mem0 可能返回 dict（包含 results 键）或 list
        # 这里做一次兼容处理
        if isinstance(results, dict):
            result_list = results.get("results", [])
            if result_list:
                logger.debug(f"Mem0 search found {len(result_list)} memories for user={user_id}")
            return result_list
        return []
    except Exception as e:
        # 搜索失败不应该中断主流程
        logger.warning(f"Mem0 search error: {e}")
        return []


async def add_memories(messages: list[dict], user_id: str) -> None:
    """
    从对话消息中提取并存储记忆。

    【工作流程】
    1. 将对话消息列表发送给 Mem0 的 LLM
    2. LLM 自动分析对话中包含的关键信息
    3. 提取出需要"记住"的要点（如用户姓名、偏好、技能）
    4. 自动去重：如果记忆中已有类似信息，则更新而非新建
    5. 将新的/更新的记忆存入 pgvector

    【前端关联】
    此函数在用户与 AI 的对话完成后自动调用（后端内部逻辑）。
    前端无需主动触发，但可以：
      1. 提供"忘记我"按钮：调用删除记忆的 API
      2. 显示"AI 已记住以下信息"的提示
      3. 提供"管理记忆"页面：查看/删除已存储的记忆

    参数：
      messages: 对话消息列表
        格式：[{"role": "user"|"assistant", "content": "消息内容"}, ...]
        通常包含最后一轮的用户消息和 AI 回复
      user_id:  用户标识符（目前使用客户端 IP 地址）
    """
    if not messages:
        return
    client = _get_client()
    if client is None:
        logger.debug(f"Mem0 add skipped: not initialized ({_init_error})")
        return
    try:
        # 调用 Mem0 的 add 方法，让它自动分析、提取、去重
        # Mem0 内部会调用 LLM 来理解对话内容
        client.add(messages, user_id=user_id)
        logger.debug(f"Mem0 add: processed {len(messages)} messages for user={user_id}")
    except Exception as e:
        # 添加记忆失败不应该中断主流程
        logger.warning(f"Mem0 add error: {e}")
