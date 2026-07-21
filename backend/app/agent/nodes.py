"""
LangGraph node functions.
Each node receives AgentState and returns a partial state update.
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
    Ensure message content is either a plain string or a multimodal list.
    Preserves image_url blocks for vision models.
    Only converts content blocks to string when they're all text-only.
    """
    content = getattr(msg, "content", None)
    if content is not None and not isinstance(content, str):
        if isinstance(content, list):
            # Check if there are any non-text blocks (images)
            has_non_text = any(
                isinstance(part, dict) and "image_url" in part
                for part in content
            )
            if has_non_text:
                # Keep multimodal content as-is for vision models
                return msg
            # All text blocks → merge to plain string
            parts = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict) and "text" in part:
                    parts.append(part["text"])
            return type(msg)(content="".join(parts))
    return msg


def _clean_messages(messages: list) -> list:
    """Remove duplicate SystemMessages and ensure content is string."""
    result = []
    has_system = False
    for msg in messages:
        msg = _ensure_str_content(msg)
        # Only keep the first SystemMessage, skip subsequent ones
        if isinstance(msg, SystemMessage):
            if has_system:
                # Merge content into the first system message
                first = result[0]
                first = SystemMessage(content=first.content + "\n\n" + msg.content)
                result[0] = first
                continue
            has_system = True
        result.append(msg)
    return result


async def rag_node(state: AgentState, db: AsyncSession) -> dict:
    """
    Retrieve relevant document chunks from the knowledge base.
    Returns retrieved_context only (no messages) to avoid duplicate SystemMessages.
    """
    if not state.get("use_rag", False):
        return {}

    # Get the latest user message
    messages = state["messages"]
    last_user_msg = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            # For multimodal content, extract only the text part for RAG search
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

    # Hybrid search the knowledge base (semantic + BM25)
    from app.rag.retriever import hybrid_search
    agent_config = state.get("agent_config", {})
    top_k = agent_config.get("rag_top_k", 4)
    threshold = agent_config.get("rag_similarity_threshold", 0.5)

    results = await hybrid_search(db, last_user_msg, top_k=top_k, similarity_threshold=threshold)

    if not results:
        return {"retrieved_context": []}

    # Return context data only — agent_node will merge it into the system prompt
    return {
        "retrieved_context": [r.model_dump() for r in results],
    }


async def agent_node(state: AgentState) -> dict:
    """
    The main agent node: calls the LLM with conversation history and tools.
    Merges system prompt + RAG context into a single SystemMessage.
    """
    agent_config = state.get("agent_config", {})
    provider = agent_config.get("provider", settings.llm_provider)
    temperature = agent_config.get("temperature", 0.7)
    max_tokens = agent_config.get("max_tokens", 4096)
    system_prompt = agent_config.get("system_prompt", "You are a helpful AI assistant.")

    # Merge RAG context into the system prompt (single SystemMessage)
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

    # Bind tools if enabled — with semantic routing when there are many tools
    enabled_tools = state.get("tools_enabled", [])
    routing_enabled = agent_config.get("tool_routing_enabled", settings.tool_routing_enabled)

    if routing_enabled and len(enabled_tools) > settings.tool_routing_min_tools:
        # Extract latest user query for semantic matching
        user_query = ""
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                content = msg.content
                if isinstance(content, list):
                    # Multimodal: extract text parts only
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

    # Build messages: single system message + history
    raw_messages = [SystemMessage(content=full_system_prompt)] + list(state["messages"])
    # Ensure content is string and no duplicate system messages
    messages = _clean_messages(raw_messages)

    try:
        response = await llm.ainvoke(messages)
    except Exception as e:
        # Catch ALL LLM-related errors and return a user-friendly message
        # instead of letting the exception propagate silently (LangGraph may swallow it)
        error_name = type(e).__name__
        error_detail = str(e)[:500]

        # Classify the error for a helpful message
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


def should_continue(state: AgentState) -> str:
    """
    Router: determine the next node after the agent.
    - If the last message has tool calls -> go to tools
    - Otherwise -> end
    """
    messages = state["messages"]
    last_message = messages[-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        if state.get("iteration", 0) >= 10:
            return "end"
        return "tools"

    return "end"


def create_tool_node(enabled_tools: list) -> ToolNode:
    """Create a ToolNode from the enabled tool names."""
    tools = get_tools(enabled_tools)
    return ToolNode(tools) if tools else None
