"""
LangGraph node functions.
Each node receives AgentState and returns a partial state update.
"""
import json
from typing import AsyncIterator

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import ToolNode
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import AgentState
from app.agent.llm import get_llm
from app.agent.tools import get_tools
from app.config import settings


async def rag_node(state: AgentState, db: AsyncSession) -> dict:
    """
    Retrieve relevant document chunks from the knowledge base
    and inject them as context into the conversation.
    """
    if not state.get("use_rag", False):
        return {}

    # Get the latest user message
    messages = state["messages"]
    last_user_msg = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_msg = msg.content
            break
        # Messages might be dicts (from API)
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

    # Build context message
    context_parts = []
    for i, r in enumerate(results, 1):
        context_parts.append(f"[文档{i}] 来源: {r.filename}\n内容: {r.content}")

    context_text = "以下是从知识库中检索到的相关内容：\n\n" + "\n\n---\n\n".join(context_parts)
    context_text += "\n\n请基于以上知识库内容回答用户问题。如果知识库中没有相关信息，请说明并使用你的知识回答。"

    return {
        "retrieved_context": [r.model_dump() for r in results],
        "messages": [SystemMessage(content=context_text)],
    }


async def agent_node(state: AgentState) -> dict:
    """
    The main agent node: calls the LLM with conversation history and tools.
    Supports streaming via astream.
    """
    agent_config = state.get("agent_config", {})
    provider = agent_config.get("provider", settings.llm_provider)
    temperature = agent_config.get("temperature", 0.7)
    max_tokens = agent_config.get("max_tokens", 4096)
    system_prompt = agent_config.get("system_prompt", "You are a helpful AI assistant.")

    llm = get_llm(provider=provider, temperature=temperature, max_tokens=max_tokens)

    # Bind tools if enabled
    enabled_tools = state.get("tools_enabled", [])
    tools = get_tools(enabled_tools)
    if tools:
        llm = llm.bind_tools(tools)

    # Build message list: system prompt + history
    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    response = await llm.ainvoke(messages)

    return {"messages": [response], "iteration": state.get("iteration", 0) + 1}


def should_continue(state: AgentState) -> str:
    """
    Router: determine the next node after the agent.
    - If the last message has tool calls → go to tools
    - Otherwise → end
    """
    messages = state["messages"]
    last_message = messages[-1]

    # Check if the AI message has tool calls
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        # Safety: prevent infinite tool loops
        if state.get("iteration", 0) >= 10:
            return "end"
        return "tools"

    return "end"


# The ToolNode handles tool execution automatically
def create_tool_node(enabled_tools: list) -> ToolNode:
    """Create a ToolNode from the enabled tool names."""
    tools = get_tools(enabled_tools)
    return ToolNode(tools) if tools else None
