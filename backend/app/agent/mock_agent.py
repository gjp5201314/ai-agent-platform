"""
Mock Agent - mock LLM streaming responses, no API Key required.

When mock_mode is enabled, this module replaces the real LangGraph Agent
to generate realistic streaming SSE event sequences for frontend dev/testing.
"""
import asyncio
from typing import AsyncIterator

# Preset mock response templates (raw strings for safety)
_MOCK_GREETING = """你好！我是 AI Agent 平台的智能助手（当前处于 **Mock 模式**）。

在 Mock 模式下，我不会调用真实的大语言模型 API，而是返回模拟的响应。这对于以下场景非常有用：

- 前端开发调试（无需配置 API Key）
- 功能演示和 Demo
- 快速验证 UI 交互

关闭 Mock 模式后，我将连接到真实的大模型（如通义千问、OpenAI、Claude）为你提供智能回答。有什么我可以帮你的吗？"""

_MOCK_CODE = """好的，以下是你需要的代码示例：

```python
def fibonacci(n: int) -> list[int]:
    '''Generate first n Fibonacci numbers'''
    if n <= 0:
        return []
    if n == 1:
        return [0]
    result = [0, 1]
    for i in range(2, n):
        result.append(result[-1] + result[-2])
    return result

# Output: [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
print(fibonacci(10))
```

这段代码展示了 Python 中生成斐波那契数列的简洁实现。在实际项目中，你还可以使用生成器（yield）来优化内存使用。需要我解释更多细节吗？"""

_MOCK_KNOWLEDGE = """这是一个很好的问题！让我为你详细解答：

**关于 AI Agent 的工作原理**

AI Agent（人工智能代理）是一种能够自主感知环境、做出决策并执行行动的智能系统。在 LLM（大语言模型）的驱动下，现代 AI Agent 具备以下核心能力：

1. **感知与理解** - 能够理解用户的自然语言输入，包括上下文和隐含意图
2. **推理与规划** - 基于大模型的推理能力，分解复杂任务为可执行的步骤
3. **工具调用** - 通过 Function Calling 机制调用外部工具（搜索、计算、代码执行等）
4. **记忆与学习** - 利用短期记忆（对话历史）和长期记忆（向量数据库）提供连续性体验
5. **反思与纠错** - 在 ReAct 或 LangGraph 框架下，能够评估结果并自我修正

在 Mock 模式下，我不会真正执行工具调用，但这正是我们平台的亮点——支持真实工具调用和 RAG 知识库检索！"""

_MOCK_DEFAULT = """收到你的消息了！

当前处于 **Mock 模式**，这是一条模拟回复。在 Mock 模式下：
- 不会消耗任何 API 额度
- 不会进行真实的工具调用
- 响应由模板生成，用于开发和测试

你可以尝试以下操作：
- 发送「你好」获取介绍信息
- 发送「写代码」查看代码生成示例
- 发送「解释 AI Agent」查看知识问答示例
- 点击切换按钮关闭 Mock 模式进行真实对话

有什么想继续了解的？"""


def _classify_user_message(message: str) -> str:
    """Classify user message to select appropriate mock response template."""
    msg_lower = message.lower()

    if any(w in msg_lower for w in ["你好", "hello", "hi", "嘿", "嗨"]):
        return "greeting"

    if any(w in msg_lower for w in ["代码", "code", "写", "编写", "编程", "函数", "function", "class", "python", "javascript", "java"]):
        return "code"

    if any(w in msg_lower for w in ["什么", "解释", "原理", "怎么", "为什么", "如何", "what", "how", "why", "explain"]):
        return "knowledge"

    return "default"


async def run_mock_agent(
    messages: list,
    agent_config: dict,
    use_rag: bool,
    db=None,
) -> AsyncIterator:
    """
    Run Mock Agent, generating simulated streaming SSE events.

    Yields event types:
    - rag_context: Empty sources list (interface compatibility)
    - token: Token-by-token streaming text chunks
    - tool_start: Simulated tool call (optional)
    - done: Response complete signal
    """
    # Extract last user message
    last_user_msg = ""
    for msg in reversed(messages):
        if hasattr(msg, "type") and (msg.type == "human" or msg.type == "user"):
            last_user_msg = msg.content or ""
            break
        elif hasattr(msg, "content"):
            msg_type = getattr(msg, "type", "")
            if msg_type in ("human", "user"):
                last_user_msg = msg.content or ""
                break
        elif isinstance(msg, dict) and msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            break

    # Select response template
    template_key = _classify_user_message(last_user_msg)
    response_map = {
        "greeting": _MOCK_GREETING,
        "code": _MOCK_CODE,
        "knowledge": _MOCK_KNOWLEDGE,
        "default": _MOCK_DEFAULT,
    }
    response_text = response_map.get(template_key, _MOCK_DEFAULT)

    # Mock RAG context (interface compatibility)
    if use_rag:
        yield {"type": "rag_context", "sources": []}

    # Simulate tool call
    if template_key == "code" and "calculator" in agent_config.get("enabled_tools", []):
        yield {
            "type": "tool_start",
            "name": "calculator",
            "args": {"expression": "1+1"},
        }
        await asyncio.sleep(0.3)

    # Stream chunks with natural delay
    chunks = _split_into_chunks(response_text)
    for chunk in chunks:
        yield {"type": "token", "content": chunk}
        await asyncio.sleep(0.02 + len(chunk) * 0.001)

    yield {"type": "done", "sources": []}


def _split_into_chunks(text: str, min_chunk: int = 3, max_chunk: int = 20) -> list:
    """
    Split text into chunks suitable for streaming output.

    Strategy:
    - Split at natural boundaries (newlines, punctuation)
    - Keep chunks between min_chunk and max_chunk characters
    - Preserve Markdown structure
    """
    chunks = []
    current = ""

    for char in text:
        current += char

        is_boundary = (
            char == "\n"
            or (char in "。！？；，.!?;," and len(current) >= min_chunk)
            or len(current) >= max_chunk
        )

        if is_boundary and current.strip():
            chunks.append(current)
            current = ""

    if current.strip():
        chunks.append(current)

    return chunks
