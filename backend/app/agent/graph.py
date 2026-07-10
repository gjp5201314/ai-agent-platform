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

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import AgentState
from app.agent.nodes import rag_node, agent_node, should_continue, create_tool_node


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

    # Step 1: RAG retrieval (if enabled)
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
        if rag_result.get("messages"):
            messages = messages + rag_result["messages"]
        rag_context = rag_result.get("retrieved_context", [])

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

    # Stream the graph execution
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
                    yield {
                        "type": "tool_start",
                        "name": tc.get("name", "unknown"),
                        "args": tc.get("args", {}),
                    }
            if isinstance(chunk, type(None)):
                continue

    yield {"type": "done", "sources": rag_context}
