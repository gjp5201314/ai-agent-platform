"""
Pytest fixtures shared across all test modules.
"""
import os
import sys
import pytest

# Ensure the app package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def sample_agent_config():
    """Reusable agent config fixture."""
    return {
        "provider": "qwen",
        "system_prompt": "You are a helpful assistant.",
        "temperature": 0.7,
        "max_tokens": 4096,
        "enabled_tools": ["rag", "calculator", "web_search", "get_current_time"],
        "rag_top_k": 4,
        "rag_similarity_threshold": 0.5,
        "has_images": False,
        "tool_routing_enabled": False,
    }


@pytest.fixture
def sample_messages():
    """Mock LangChain message list."""
    from langchain_core.messages import HumanMessage, AIMessage
    return [
        HumanMessage(content="Hello"),
        AIMessage(content="Hi! How can I help?"),
        HumanMessage(content="What is 2+2?"),
    ]
