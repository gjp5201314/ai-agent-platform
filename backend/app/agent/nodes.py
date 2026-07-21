"""
================================================================================
LangGraph 节点函数 — Agent 执行流程的三个核心节点（前端必读）
================================================================================

这个文件定义了 LangGraph 图中的三个节点函数，每个节点都是一个"处理器"：
接收 AgentState → 执行业务逻辑 → 返回部分状态更新。

对前端开发者来说，关键概念：
-------------------------------------
Agent 的每一次"思考-行动"循环经过这三个节点：

  1. rag_node     — 知识检索节点（可选，只在启用 RAG 时执行）
     从向量数据库检索与用户问题相关的文档片段，注入到系统提示词中

  2. agent_node   — LLM 推理节点（核心）
     调用大语言模型，根据对话历史 + 系统提示词 + 可用工具生成回复
     回复可能是直接文本，也可能是工具调用请求

  3. tool_node    — 工具执行节点
     执行 LLM 请求的工具（搜索、计算、代码运行等），返回结果给 agent_node

  4. should_continue — 路由决策函数（非节点，是条件边的判断逻辑）
     检查最后一条消息是否包含 tool_calls，决定是继续执行工具还是结束

数据流示意：
  用户问题 → rag_node（检索知识） → agent_node（LLM推理）
  → should_continue（检查是否需要工具）
  → [需要] tool_node（执行工具） → agent_node（基于工具结果继续推理）
  → [不需要] 返回最终回复给前端

错误处理（agent_node）：
  agent_node 包含完整的异常分类处理，将技术错误翻译为用户友好的中文提示：
  - 额度耗尽 → 提示充值或切换 Mock 模式
  - 认证失败 → 提示检查 API Key
  - 超时 → 提示重试
  - 速率限制 → 提示等待
  - 模型不存在 → 提示切换模型
"""
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import ToolNode
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import AgentState
from app.agent.llm import get_llm
from app.agent.tools import get_tools, get_relevant_tools
from app.config import settings
from app.core.logger import logger


def _ensure_str_content(msg):
    """
    确保消息内容是纯字符串或保持多模态格式。

    对前端的影响：
    - 纯文本消息：自动合并为字符串（LangChain 内部有时会存为列表）
    - 含图片的消息：保持原始的 content 列表格式（含 image_url），
      不做转换，否则会破坏视觉模型的输入
    """
    content = getattr(msg, "content", None)
    if content is not None and not isinstance(content, str):
        if isinstance(content, list):
            # 检查是否包含非文本块（图片）
            has_non_text = any(
                isinstance(part, dict) and "image_url" in part
                for part in content
            )
            if has_non_text:
                # 保持多模态内容原样，不转换
                return msg
            # 全部是文本块 → 合并为纯字符串
            parts = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict) and "text" in part:
                    parts.append(part["text"])
            return type(msg)(content="".join(parts))
    return msg


def _clean_messages(messages: list) -> list:
    """
    清理消息列表：去除重复的 SystemMessage，保证内容为字符串格式。

    为什么需要这个？
    - LangGraph 在循环中可能堆积多个 SystemMessage（每次 agent_node 添加一个）
    - 多个 SystemMessage 会导致 LLM API 报错或行为异常
    - 这里把后续的 SystemMessage 内容合并到第一个中
    """
    result = []
    has_system = False
    for msg in messages:
        msg = _ensure_str_content(msg)
        # 只保留第一个 SystemMessage，后续的合并内容进去
        if isinstance(msg, SystemMessage):
            if has_system:
                # 将内容合并到第一个 SystemMessage
                first = result[0]
                first = SystemMessage(content=first.content + "\n\n" + msg.content)
                result[0] = first
                continue
            has_system = True
        result.append(msg)
    return result


# ============================================================================
# 节点 1: rag_node — 知识库检索节点
# ============================================================================
async def rag_node(state: AgentState, db: AsyncSession) -> dict:
    """
    从知识库中检索与用户问题相关的文档片段。

    工作原理：
    1. 找到最新的用户消息
    2. 使用混合搜索（语义搜索 + BM25 关键词搜索）检索知识库
    3. 只返回文档内容（retrieved_context），不返回消息
       — agent_node 会负责将检索内容合并到系统提示词中

    何时执行：
    - state["use_rag"] 为 True 时执行
    - 这由 run_agent() / run_agent_graph() 在预处理阶段判断

    前端关注点：
    - 检索结果通过 "rag_context" SSE 事件发送到前端
    - sources 列表可用来展示"参考了以下文档"

    参数：
        state: 当前 AgentState，包含消息历史和配置
        db: 数据库会话，用于执行知识库查询

    返回：
        {"retrieved_context": [...]}  — 文档片段列表
    """
    if not state.get("use_rag", False):
        return {}

    # 获取最新用户消息
    messages = state["messages"]
    last_user_msg = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            # 多模态内容：仅提取文本部分用于 RAG 搜索
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, str):
                        text_parts.append(part)
                    elif isinstance(part, dict) and "text" in part:
                        text_parts.append(part["text"])
                last_user_msg = "".join(text_parts)
            else:
                last_user_msg = content
            break
        if isinstance(msg, dict) and msg.get("role") == "user":
            last_user_msg = msg["content"]
            break

    if not last_user_msg:
        return {}

    # 使用混合搜索（语义 + BM25 关键词）检索知识库
    from app.rag.retriever import hybrid_search
    agent_config = state.get("agent_config", {})
    top_k = agent_config.get("rag_top_k", 4)
    threshold = agent_config.get("rag_similarity_threshold", 0.5)

    results = await hybrid_search(db, last_user_msg, top_k=top_k, similarity_threshold=threshold)

    if not results:
        return {"retrieved_context": []}

    # 只返回上下文数据 — agent_node 会将其合并到系统提示词中
    return {
        "retrieved_context": [r.model_dump() for r in results],
    }


# ============================================================================
# 节点 2: agent_node — LLM 推理节点（核心）
# ============================================================================
async def agent_node(state: AgentState) -> dict:
    """
    调用大语言模型进行推理，是整个 Agent 系统的核心节点。

    执行流程：
    1. 从 state 中读取 agent_config（provider, temperature, system_prompt 等）
    2. 将 RAG 检索结果合并到系统提示词中（如果有的话）
    3. 绑定启用的工具（如果有的话），工具支持语义路由优化
    4. 构建消息列表（SystemMessage + 历史消息）
    5. 调用 LLM 并返回响应

    工具语义路由（Tool Semantic Routing）：
        当启用的工具数量超过阈值（默认6个）时，启动语义路由：
        - 分析用户问题意图，与工具组描述进行相似度匹配
        - 只把相关工具组的工具发给 LLM，减少 token 消耗和选择困难
        - 元工具（delegate_to_agent, dispatch_tasks, search_knowledge_base）始终保留

    错误处理：
        分类处理 LLM 调用异常，将技术错误翻译为中文用户友好提示：
        - 额度耗尽 (quota/exhausted)
        - 认证失败 (authentication/api_key/unauthorized)
        - 超时 (timeout/timed out)
        - 速率限制 (rate/too many)
        - 模型不存在 (model_not_found/does not exist)
        - 其他未知错误

    返回：
        {"messages": [AI回复], "iteration": N}  — 部分状态更新
    """
    agent_config = state.get("agent_config", {})
    provider = agent_config.get("provider", settings.llm_provider)
    temperature = agent_config.get("temperature", 0.7)
    max_tokens = agent_config.get("max_tokens", 4096)
    system_prompt = agent_config.get("system_prompt", "You are a helpful AI assistant.")

    # 将 RAG 知识库检索结果合并到系统提示词（单一 SystemMessage，避免冲突）
    rag_context = state.get("retrieved_context", [])
    if rag_context:
        context_parts = []
        for i, r in enumerate(rag_context, 1):
            filename = r.get("filename", "unknown") if isinstance(r, dict) else "unknown"
            content = r.get("content", "") if isinstance(r, dict) else str(r)
            context_parts.append(f"[文档{i}] 来源: {filename}\n内容: {content}")
        context_text = (
            "\n\n以下是从知识库中检索到的相关内容：\n\n"
            + "\n\n---\n\n".join(context_parts)
            + "\n\n请基于以上知识库内容回答用户问题。如果知识库中没有相关信息，请说明并使用你的知识回答。"
        )
        full_system_prompt = system_prompt + context_text
    else:
        full_system_prompt = system_prompt

    has_images = agent_config.get("has_images", False)
    llm = get_llm(provider=provider, temperature=temperature, max_tokens=max_tokens, has_images=has_images)

    # 绑定工具 — 如果启用语义路由，则按用户意图筛选工具
    enabled_tools = state.get("tools_enabled", [])
    routing_enabled = agent_config.get("tool_routing_enabled", settings.tool_routing_enabled)

    if routing_enabled and len(enabled_tools) > settings.tool_routing_min_tools:
        # 提取最新用户查询用于语义匹配
        user_query = ""
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                content = msg.content
                if isinstance(content, list):
                    # 多模态内容：只提取文本部分
                    text_parts = []
                    for part in content:
                        if isinstance(part, str):
                            text_parts.append(part)
                        elif isinstance(part, dict) and "text" in part:
                            text_parts.append(part["text"])
                    user_query = "".join(text_parts)
                else:
                    user_query = str(content)
                break

        top_k = agent_config.get("tool_routing_top_k_groups", settings.tool_routing_top_k_groups)
        mode = agent_config.get("tool_routing_mode", settings.tool_routing_mode)
        tools, selected_groups = get_relevant_tools(
            user_query, enabled_tools,
            top_k_groups=top_k,
            min_tools=settings.tool_routing_min_tools,
        )
        logger.debug(f"agent_node: selected groups={selected_groups}, tool_count={len(tools)}")
    else:
        tools = get_tools(enabled_tools)

    if tools:
        llm = llm.bind_tools(tools)

    # 构建消息列表：单个 SystemMessage + 对话历史
    raw_messages = [SystemMessage(content=full_system_prompt)] + list(state["messages"])
    # 确保内容为字符串，去除重复的 SystemMessage
    messages = _clean_messages(raw_messages)

    # ========================================================================
    # LLM 调用 + 错误分类处理
    # 将技术异常翻译为前端可直接展示的中文友好提示
    # ========================================================================
    try:
        response = await llm.ainvoke(messages)
    except Exception as e:
        # 分类处理不同错误类型，返回用户友好的中文提示
        error_name = type(e).__name__
        error_detail = str(e)[:500]

        msg_lower = error_detail.lower()
        if "quota" in msg_lower or "exhausted" in msg_lower:
            friendly = (
                f"抱歉，当前使用的 AI 模型免费额度已用尽。\n\n"
                f"解决方案：\n"
                f"1. 前往阿里云百炼控制台充值或关闭「仅使用免费额度」限制\n"
                f"2. 切换到 Mock 模式继续测试（点击输入框旁的 Mock 按钮）\n"
                f"3. 在管理后台切换到其他可用的模型\n\n"
                f"技术细节：{error_detail[:200]}"
            )
        elif "authentication" in msg_lower or "api_key" in msg_lower or "unauthorized" in msg_lower:
            friendly = (
                f"抱歉，AI 模型认证失败。请检查 API Key 是否正确配置。\n\n"
                f"可以在管理后台或 .env 文件中更新 API Key。\n\n"
                f"技术细节：{error_detail[:200]}"
            )
        elif "timeout" in msg_lower or "timed out" in msg_lower:
            friendly = (
                f"抱歉，AI 模型响应超时。可能是网络问题或模型服务暂时繁忙。\n"
                f"请稍后重试，或切换到 Mock 模式继续测试。"
            )
        elif "rate" in msg_lower or "too many" in msg_lower:
            friendly = (
                f"抱歉，请求太频繁，AI 模型触发了速率限制。\n"
                f"请等待几秒后重试。"
            )
        elif "model_not_found" in msg_lower or "does not exist" in msg_lower:
            friendly = (
                f"抱歉，当前配置的模型不可用或不存在。\n"
                f"请在管理后台切换到其他模型。\n\n"
                f"当前模型：{settings.qwen_model}\n"
                f"技术细节：{error_detail[:200]}"
            )
        else:
            friendly = (
                f"抱歉，AI 模型返回了错误，暂时无法处理您的请求。\n\n"
                f"错误类型：{error_name}\n"
                f"错误详情：{error_detail[:300]}\n\n"
                f"您可以尝试：\n"
                f"1. 稍后重试\n"
                f"2. 切换到 Mock 模式（点击输入框旁的 Mock 按钮）\n"
                f"3. 检查后端日志获取更多信息"
            )

        logger.error(f"LLM call failed: {error_name}: {error_detail}")
        return {"messages": [AIMessage(content=friendly)], "iteration": state.get("iteration", 0) + 1}

    return {"messages": [response], "iteration": state.get("iteration", 0) + 1}


# ============================================================================
# 路由函数: should_continue — 决定下一步走向
# ============================================================================
def should_continue(state: AgentState) -> str:
    """
    条件路由函数：检查 LLM 回复后应该走向哪个节点。

    这是 LangGraph 条件边的决策函数，每次 agent_node 执行后调用：

    路由逻辑：
    - 最后一条消息包含 tool_calls → 返回 "tools"，进入工具执行节点
      （LLM 想要调用工具来获取更多信息）
    - 最后一条消息不包含 tool_calls → 返回 "end"，流程结束
      （LLM 已经给出了最终回复，无需再调用工具）
    - iteration >= 10 → 强制返回 "end"，安全截断防止无限循环

    前端关注点：
    - 当路由到 "tools" 时，graph.py 会产出 "tool_start" SSE 事件
    - 工具执行完毕后会回到 agent_node，可能产出更多 "token" 事件
    - 当路由到 "end" 时，graph.py 会产出 "done" SSE 事件，前端可停止 loading

    返回：
        "tools" — 进入工具执行节点
        "end"   — 流程结束
    """
    messages = state["messages"]
    last_message = messages[-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        if state.get("iteration", 0) >= 10:
            return "end"
        return "tools"

    return "end"


# ============================================================================
# 工厂函数: create_tool_node — 创建工具执行节点
# ============================================================================
def create_tool_node(enabled_tools: list) -> ToolNode:
    """
    根据启用的工具名称列表创建 LangGraph ToolNode。

    ToolNode 是 LangGraph 内置的工具执行器：
    - 接收 agent_node 产出的 tool_calls
    - 并行执行所有工具调用
    - 将结果封装为 ToolMessage 返回给 agent_node
    """
    tools = get_tools(enabled_tools)
    return ToolNode(tools) if tools else None
