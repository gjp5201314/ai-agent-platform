"""
================================================================================
Mock Agent — 模拟 LLM 流式响应（前端必读）
================================================================================

当 mock_mode 启用时，此模块替代真实的 LangGraph Agent，
生成模拟的 SSE 事件流，用于前端开发和测试。

对前端开发者来说，关键概念：
-------------------------------------
Mock Agent 的设计目标：
  1. 无需配置任何 API Key 即可测试前端界面
  2. 完全模拟真实 Agent 的 SSE 事件格式和时序
  3. 提供多种响应模板（问候/代码/知识问答/默认），覆盖不同 UI 场景

Mock 模式与真实模式的区别：
  ┌────────────┬─────────────────┬─────────────────────┐
  │ 对比维度     │ 真实模式         │ Mock 模式            │
  ├────────────┼─────────────────┼─────────────────────┤
  │ LLM 调用    │ 真实 API 调用     │ 本地模板生成          │
  │ 工具执行     │ 真实执行           │ 模拟（只发事件，不执行）│
  │ RAG 检索     │ 真实向量数据库检索  │ 返回空结果            │
  │ Token 流     │ LLM 流式输出      │ 模板文本分块输出       │
  │ API Key      │ 需要配置           │ 不需要               │
  │ 适用场景     │ 生产环境           │ 开发/演示/测试         │
  └────────────┴─────────────────┴─────────────────────┘

SSE 事件类型（Mock Agent 与真实 Agent 完全一致）
-------------------------------------
  "rag_context"   — 知识库检索事件（Mock 下始终为空列表）
                     格式: {"type": "rag_context", "sources": []}

  "tool_start"    — 工具调用开始事件（仅在模板为 "code" 且有 calculator 工具时触发）
                     格式: {"type": "tool_start", "name": "calculator", "args": {"expression": "1+1"}}

  "token"         — 逐字输出的文本片段（模拟 LLM 流式效果）
                     格式: {"type": "token", "content": "文本片段"}

  "done"          — 响应完成信号
                     格式: {"type": "done", "sources": []}

前端如何使用 Mock 模式：
  1. 用户在输入框旁点击"Mock"切换按钮
  2. 前端在请求中设置 mock_mode=true（或使用专门的 mock API 端点）
  3. 后端调用 run_mock_agent() 替代 run_agent()
  4. 前端以完全相同的方式处理 SSE 事件


响应模板匹配逻辑
-------------------------------------
  _classify_user_message() 分析用户消息，选择对应模板：

  用户输入关键词           → 匹配模板
  ─────────────────────────────────────────────────
  你好/hello/hi/嘿/嗨       → greeting（平台介绍模板）
  代码/code/写/编程/函数...  → code（代码示例模板）
  什么/解释/原理/为什么...    → knowledge（知识讲解模板）
  其他                      → default（通用引导模板）
"""

import asyncio
from typing import AsyncIterator

# ============================================================================
# 预设的模拟响应模板
# ============================================================================
# 每个模板模拟不同类型的 LLM 回复，覆盖前端可能遇到的各种 UI 场景
# ============================================================================

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


# ============================================================================
# 消息分类器：根据用户输入选择最合适的响应模板
# ============================================================================

def _classify_user_message(message: str) -> str:
    """
    分析用户消息内容，匹配对应的响应模板。

    匹配规则（按优先级）：
    1. 包含问候语 → "greeting"
    2. 包含编程关键词 → "code"
    3. 包含提问关键词 → "knowledge"
    4. 其他 → "default"

    参数：
        message: 用户输入的文本

    返回：
        模板键名: "greeting" | "code" | "knowledge" | "default"
    """
    msg_lower = message.lower()

    if any(w in msg_lower for w in ["你好", "hello", "hi", "嘿", "嗨"]):
        return "greeting"

    if any(w in msg_lower for w in ["代码", "code", "写", "编写", "编程", "函数", "function", "class", "python", "javascript", "java"]):
        return "code"

    if any(w in msg_lower for w in ["什么", "解释", "原理", "怎么", "为什么", "如何", "what", "how", "why", "explain"]):
        return "knowledge"

    return "default"


# ============================================================================
# run_mock_agent — Mock 模式的主入口
# ============================================================================

async def run_mock_agent(
    messages: list,
    agent_config: dict,
    use_rag: bool,
    db=None,
) -> AsyncIterator:
    """
    运行 Mock Agent，生成模拟的流式 SSE 事件。

    这是 Mock 模式的入口函数，接口参数与 run_agent() 完全兼容。
    前端不需要关心后端使用的是真实 Agent 还是 Mock Agent —
    SSE 事件格式完全一致。

    产出的 SSE 事件类型：
    - "rag_context": 空 sources 列表（保持接口兼容）
    - "tool_start":  模拟的工具调用（仅在 code 模板 + 有 calculator 工具时）
    - "token":       逐字输出的文本片段（模拟真实 LLM 流式效果）
    - "done":        响应完成信号

    流式输出模拟：
    - 使用 _split_into_chunks() 将文本拆分为适合流式输出的片段
    - 每个片段之间有 20ms + 字符数×1ms 的延迟
    - 模拟工具调用前有 300ms 延迟（模拟工具执行时间）

    参数：
        messages:      对话消息列表
        agent_config:  Agent 配置（system_prompt, enabled_tools 等）
        use_rag:       是否启用 RAG（Mock 下为兼容接口，返回空结果）
        db:            数据库会话（Mock 下未使用，保持接口兼容）
    """
    # 提取最后一条用户消息
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

    # 选择响应模板
    template_key = _classify_user_message(last_user_msg)
    response_map = {
        "greeting": _MOCK_GREETING,
        "code": _MOCK_CODE,
        "knowledge": _MOCK_KNOWLEDGE,
        "default": _MOCK_DEFAULT,
    }
    response_text = response_map.get(template_key, _MOCK_DEFAULT)

    # === 事件 1: rag_context（接口兼容，Mock 下始终为空）===
    if use_rag:
        yield {"type": "rag_context", "sources": []}

    # === 事件 2: tool_start（模拟工具调用）===
    # 仅在 code 模板 + 启用了 calculator 工具时触发，模拟真实工具调用流程
    if template_key == "code" and "calculator" in agent_config.get("enabled_tools", []):
        yield {
            "type": "tool_start",
            "name": "calculator",
            "args": {"expression": "1+1"},
        }
        await asyncio.sleep(0.3)

    # === 事件 3: token（模拟 LLM 流式输出）===
    # 将响应文本拆分为小块，逐个产出，模拟真实 LLM 的逐字输出效果
    chunks = _split_into_chunks(response_text)
    for chunk in chunks:
        yield {"type": "token", "content": chunk}
        # 模拟网络延迟：基础 20ms + 按字符数递增
        await asyncio.sleep(0.02 + len(chunk) * 0.001)

    # === 事件 4: done（响应完成）===
    yield {"type": "done", "sources": []}


# ============================================================================
# 文本分块工具：将模板文本拆分为适合流式输出的片段
# ============================================================================

def _split_into_chunks(text: str, min_chunk: int = 3, max_chunk: int = 20) -> list:
    """
    将文本拆分为适合流式输出的字符片段。

    拆分策略：
    - 优先在自然边界处切分（换行符、中文/英文标点符号）
    - 保持片段长度在 min_chunk ~ max_chunk 字符之间
    - 保留 Markdown 结构（代码块、标题等不会被从中间切断）

    这种拆分方式模拟了真实 LLM 的 token 流输出效果，
    确保前端的"打字机效果"动画自然流畅。

    参数：
        text:      要拆分的文本
        min_chunk: 最小片段长度（字符数）
        max_chunk: 最大片段长度（字符数）

    返回：
        文本片段列表
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
