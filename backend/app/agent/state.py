"""
LangGraph agent state definition.
This TypedDict is passed through the graph nodes.
"""
from typing import Annotated, TypedDict, List, Optional, Any
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    The state that flows through the LangGraph nodes.

    Attributes:
        messages:      Conversation history (LangGraph message reducer auto-appends)
        retrieved_context: RAG chunks relevant to the current query
        tools_enabled: Which tools the agent can use this turn
        use_rag:       Whether to search the knowledge base
        agent_config:  AgentConfig fields (system_prompt, temperature, etc.)
        iteration:     Safety counter to prevent infinite loops
    """
    messages: Annotated[list, add_messages]
    retrieved_context: List[dict]
    tools_enabled: List[str]
    use_rag: bool
    agent_config: dict
    iteration: int
