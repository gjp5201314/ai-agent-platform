"""
LangGraph agent graph definition.

Flow:
    START → rag_node → agent_node → [should_continue]
                                        ↓ tool_calls
                                    tools_node → agent_node (loop)
                                        ↓ no calls
                                       END
"""
from typing import Optional, AsyncIterator
import asyncio

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import AgentState
from app.agent.nodes import rag_node, agent_node, should_continue, create_tool_node
from app.config import settings
from app.core.logger import logger


def build_graph(enabled_tools: list = None):
    """
    Build and compile the LangGraph agent graph.

    Args:
        enabled_tools: List of tool names the agent can use.

    Returns:
        A compiled LangGraph runnable.
    """
    enabled_tools = enabled_tools or []

    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("agent", agent_node)

    tools_list = [t for t in enabled_tools if t != "rag"]
    if tools_list:
        tool_node = create_tool_node(tools_list)
        if tool_node:
            graph.add_node("tools", tool_node)

    # Set entry point
    graph.set_entry_point("agent")

    # Add conditional edge: agent → tools or END
    if tools_list:
        graph.add_conditional_edges(
            "agent",
            should_continue,
            {
                "tools": "tools",
                "end": END,
            },
        )
        # After tools, loop back to agent
        graph.add_edge("tools", "agent")
    else:
        # No tools: agent → END directly
        graph.add_edge("agent", END)

    return graph.compile()


# Cache compiled graphs by tool signature
_graph_cache: dict = {}


def get_graph(enabled_tools: list = None):
    """Get a cached compiled graph for the given tool configuration."""
    key = tuple(sorted(enabled_tools or []))
    if key not in _graph_cache:
        _graph_cache[key] = build_graph(enabled_tools)
    return _graph_cache[key]


async def run_agent_graph(
    messages: list,
    agent_config: dict,
    use_rag: bool,
    db: AsyncSession,
    timeout_seconds: int = None,
) -> dict:
    """
    Run the agent graph NON-STREAMING — returns the final state.
    Used by sub-agents and parallel dispatchers that need the complete result,
    not individual tokens.

    Returns:
        dict with keys: "response" (str), "sources" (list), "tool_calls" (int)
    """
    enabled_tools = agent_config.get("enabled_tools", [])
    rag_context = []

    # RAG retrieval
    if use_rag and "rag" in enabled_tools:
        state_for_rag = AgentState(
            messages=messages,
            retrieved_context=[],
            tools_enabled=enabled_tools,
            use_rag=True,
            agent_config=agent_config,
            iteration=0,
        )
        rag_result = await rag_node(state_for_rag, db)
        rag_context = rag_result.get("retrieved_context", [])

    # Build and run the graph
    tools_for_graph = [t for t in enabled_tools if t != "rag"]
    graph = get_graph(tools_for_graph)

    initial_state = AgentState(
        messages=messages,
        retrieved_context=rag_context,
        tools_enabled=tools_for_graph,
        use_rag=False,
        agent_config=agent_config,
        iteration=0,
    )

    timeout = timeout_seconds or settings.tool_timeout_seconds * 10
    tool_call_count = 0

    try:
        async with asyncio.timeout(timeout):
            final_state = await graph.ainvoke(initial_state)
    except asyncio.TimeoutError:
        return {
            "response": "[子Agent超时] 任务在限定时间内未完成。",
            "sources": rag_context,
            "tool_calls": tool_call_count,
        }

    # Extract the final AI response
    final_messages = final_state.get("messages", [])
    response_text = ""
    for msg in reversed(final_messages):
        if isinstance(msg, AIMessage) and msg.content:
            response_text = msg.content
            break
        # Count tool calls
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_call_count += len(msg.tool_calls)

    return {
        "response": response_text or "[子Agent完成，但未生成文本回复]",
        "sources": rag_context,
        "tool_calls": tool_call_count,
    }


async def run_agent(
    messages: list,
    agent_config: dict,
    use_rag: bool,
    db: AsyncSession,
) -> AsyncIterator:
    """
    Run the agent graph and yield streaming events.

    This is a convenience wrapper that:
    1. Optionally runs RAG retrieval first
    2. Builds the initial state
    3. Streams the graph execution

    Yields:
        Dict events with type 'token', 'tool_start', 'tool_end', 'done'.
    """
    enabled_tools = agent_config.get("enabled_tools", [])
    logger.debug(f"run_agent: use_rag={use_rag}, enabled_tools={enabled_tools}, rag in tools={'rag' in enabled_tools}")

    # Step 1: RAG retrieval (if enabled) — returns context only, no messages
    rag_context = []
    if use_rag and "rag" in enabled_tools:
        state_for_rag = AgentState(
            messages=messages,
            retrieved_context=[],
            tools_enabled=enabled_tools,
            use_rag=True,
            agent_config=agent_config,
            iteration=0,
        )
        rag_result = await rag_node(state_for_rag, db)
        rag_context = rag_result.get("retrieved_context", [])
        logger.debug(f"rag_node returned {len(rag_context)} context items")
        # NOTE: Do NOT add rag_result["messages"] — agent_node merges context into system prompt

    # Yield RAG context info
    if rag_context:
        yield {
            "type": "rag_context",
            "sources": rag_context,
        }

    # Step 2: Run the agent graph
    tools_for_graph = [t for t in enabled_tools if t != "rag"]
    graph = get_graph(tools_for_graph)

    initial_state = AgentState(
        messages=messages,
        retrieved_context=rag_context,
        tools_enabled=tools_for_graph,
        use_rag=False,  # Already handled above
        agent_config=agent_config,
        iteration=0,
    )

    # Stream the graph execution with global timeout
    # asyncio.timeout wraps every await inside the block, including
    # each __anext__() call of the async generator (LLM token / tool step).
    try:
        async with asyncio.timeout(settings.tool_timeout_seconds * 10):
            async for event in graph.astream(initial_state, stream_mode="messages"):
                # stream_mode="messages" yields (message, metadata) tuples
                if isinstance(event, tuple):
                    chunk, metadata = event
                    # Stream tokens from the LLM
                    if hasattr(chunk, "content") and chunk.content:
                        yield {
                            "type": "token",
                            "content": chunk.content,
                        }
                    # Tool call events
                    if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                        for tc in chunk.tool_calls:
                            tool_name = tc.get("name", "unknown")
                            tool_args = tc.get("args", {})
                            # Emit agent_switch event for delegate_to_agent calls
                            if tool_name == "delegate_to_agent":
                                target_id = tool_args.get("agent_id", "")
                                delegate_task = tool_args.get("task", "")
                                yield {
                                    "type": "agent_switch",
                                    "from_agent": "current",
                                    "to_agent": target_id,
                                    "task": delegate_task[:100],
                                }
                            yield {
                                "type": "tool_start",
                                "name": tool_name,
                                "args": tool_args,
                            }
                    if chunk is None:
                        continue
    except asyncio.TimeoutError:
        yield {
            "type": "token",
            "content": "\n\n[Agent 执行超时，已终止当前请求。请重试或简化问题。]",
        }

    yield {"type": "done", "sources": rag_context}
