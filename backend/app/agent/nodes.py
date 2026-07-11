"""
LangGraph node functions.
Each node receives AgentState and returns a partial state update.
"""
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import ToolNode
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import AgentState
from app.agent.llm import get_llm
from app.agent.tools import get_tools
from app.config import settings


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

    # Search the knowledge base
    from app.rag.retriever import search_similar
    agent_config = state.get("agent_config", {})
    top_k = agent_config.get("rag_top_k", 4)
    threshold = agent_config.get("rag_similarity_threshold", 0.5)

    results = await search_similar(db, last_user_msg, top_k=top_k, similarity_threshold=threshold)

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

    # Bind tools if enabled
    enabled_tools = state.get("tools_enabled", [])
    tools = get_tools(enabled_tools)
    if tools:
        llm = llm.bind_tools(tools)

    # Build messages: single system message + history
    raw_messages = [SystemMessage(content=full_system_prompt)] + list(state["messages"])
    # Ensure content is string and no duplicate system messages
    messages = _clean_messages(raw_messages)

    response = await llm.ainvoke(messages)

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
