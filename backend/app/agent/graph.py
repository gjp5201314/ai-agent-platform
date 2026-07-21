"""
================================================================================
LangGraph 图定义 — Agent 执行流程编排（前端必读）
================================================================================

这个文件是整个 Agent 系统的"大脑"——它定义了 Agent 的执行流程图：
用户消息进入 → 可选 RAG 检索 → LLM 推理 → 工具调用 → 循环 → 最终回复。

对前端开发者来说，关键概念：
-------------------------------------
1. LangGraph 图结构
   这是一个有向图（DAG），节点是处理函数，边是数据流向：

   START
     │
     ▼
   [agent_node]  ←──────────────┐
     │                          │
     │  (LLM 决定是否调用工具)     │
     ▼                          │
   [should_continue] ── tools ──┘
     │
     │  end
     ▼
    END

   流程说明：
   - agent_node: LLM 推理节点，分析用户意图并决定是否调用工具
   - should_continue: 条件路由，检查 LLM 是否发出了工具调用请求
   - tools_node: 执行工具（搜索、计算、代码沙箱等），结果回传给 agent_node

2. 条件路由边（Conditional Edge）
   should_continue() 函数检查最后一条消息是否包含 tool_calls：
   - 有 tool_calls → 路由到 tools_node 执行工具
   - 无 tool_calls → 路由到 END，流结束
   - iteration >= 10 → 安全截断，强制结束（防止无限循环）

3. 两种运行模式
   a) run_agent() — 流式模式（前端对话使用）
      以 SSE 事件流方式返回结果，事件类型包括：
      - "token":       LLM 逐字输出的文本片段（前端逐字显示）
      - "tool_start":  工具开始执行的信号（前端可显示"正在搜索..."）
      - "agent_switch": Agent 委托切换信号（多 Agent 协作时使用）
      - "rag_context": 知识库检索结果（前端可展示参考来源）
      - "done":        整个响应完成信号

   b) run_agent_graph() — 非流式模式（子 Agent 调用使用）
      等待完整执行完毕，返回结构化结果 {response, sources, tool_calls}
      用于多 Agent 协作场景，父 Agent 需要等待子 Agent 完整结果

4. 图缓存机制
   相同工具配置的图会被缓存复用（_graph_cache），避免每次请求都重新编译图。
   缓存的键是启用的工具名称排序后的元组。

前端 SSE 事件流示例：
  {"type": "rag_context", "sources": [...]}
  {"type": "agent_switch", "to_agent": "rag-assistant", "task": "搜索XX"}
  {"type": "tool_start", "name": "web_search", "args": {...}}
  {"type": "token", "content": "根据"}
  {"type": "token", "content": "搜索结果"}
  ...
  {"type": "done", "sources": [...]}
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
    构建并编译 LangGraph Agent 执行图。

    图的拓扑结构：
        START → agent_node → [should_continue]
                                ├── "tools" → tools_node → agent_node (循环)
                                └── "end"   → END

    参数：
        enabled_tools: 当前 Agent 可使用的工具名称列表

    返回：
        编译后的 LangGraph 可运行对象（Runnable）

    工具节点仅在 enabled_tools 非空时添加。
    无工具时 agent_node 直接连接到 END，不走循环。
    """
    enabled_tools = enabled_tools or []

    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("agent", agent_node)

    # 工具节点：只添加非 "rag" 的工具（rag 是预处理步骤，不是图内工具）
    tools_list = [t for t in enabled_tools if t != "rag"]
    if tools_list:
        tool_node = create_tool_node(tools_list)
        if tool_node:
            graph.add_node("tools", tool_node)

    # Set entry point
    graph.set_entry_point("agent")

    # 条件路由边：agent → tools 或 END
    if tools_list:
        graph.add_conditional_edges(
            "agent",
            should_continue,
            {
                "tools": "tools",
                "end": END,
            },
        )
        # 工具执行完毕后回到 agent 节点继续推理
        graph.add_edge("tools", "agent")
    else:
        # 无工具：agent → END 直接结束
        graph.add_edge("agent", END)

    return graph.compile()


# ============================================================================
# 图缓存：相同工具配置的编译图会被复用
# 键 = 工具名称排序后的元组，如 ("calculator", "web_search")
# ============================================================================
_graph_cache: dict = {}


def get_graph(enabled_tools: list = None):
    """获取缓存中的编译图（对应给定工具配置）。"""
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
    【非流式模式】运行 Agent 图 — 等待完整结果后返回。

    与 run_agent() 的区别：
    - run_agent() 用于前端对话，以 SSE token 事件流逐步返回
    - run_agent_graph() 用于子 Agent 调用，父 Agent 需要完整结果

    返回：
        dict: {
            "response": "AI 的完整文本回复",
            "sources":  [...],   // 知识库检索来源
            "tool_calls": 0      // 工具调用次数
        }

    超时处理：
        默认超时 = tool_timeout_seconds * 10
        超时时返回友好的中文错误提示
    """
    enabled_tools = agent_config.get("enabled_tools", [])
    rag_context = []

    # RAG 检索 — 仅当使用旧版 "rag" 预处理模式时执行
    # 当 "search_knowledge_base" 作为工具启用时，跳过预处理，
    # 由 LLM 按需决定是否搜索知识库
    use_preprocess_rag = use_rag and "rag" in enabled_tools and "search_knowledge_base" not in enabled_tools
    if use_preprocess_rag:
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

    # 从最终状态中提取 AI 回复
    final_messages = final_state.get("messages", [])
    response_text = ""
    for msg in reversed(final_messages):
        if isinstance(msg, AIMessage) and msg.content:
            response_text = msg.content
            break
        # 统计工具调用次数
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
    【流式模式】运行 Agent 图 — 以 SSE 事件流方式逐 token 返回结果。

    这是前端对话的主入口。执行流程：
    1. 可选的 RAG 知识库检索（如果启用了旧版预处理模式）
    2. 构建初始状态
    3. 流式执行 LangGraph 图
    4. 将图的输出转换为 SSE 事件流

    Yields（逐条产出的事件）：
        Dict 事件，type 字段取值为：
        - "rag_context":  知识库检索结果，sources 为文档列表（前端可展示参考来源）
        - "agent_switch": 当 LLM 调用 delegate_to_agent 工具时触发，表示切换子 Agent
                          {type, from_agent, to_agent, task}
        - "tool_start":   工具开始执行 {type, name, args}
        - "token":        LLM 输出的文本片段 {type, content}（前端逐字追加显示）
        - "done":         整个响应完成 {type, sources}
    """
    enabled_tools = agent_config.get("enabled_tools", [])
    use_preprocess_rag = use_rag and "rag" in enabled_tools and "search_knowledge_base" not in enabled_tools
    logger.debug(f"run_agent: use_rag={use_rag}, preprocess_rag={use_preprocess_rag}, tools={enabled_tools}")

    # Step 1: RAG 检索 — 仅用于旧版预处理模式（非按需工具模式）
    rag_context = []
    if use_preprocess_rag:
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
        # 注意：不要把 rag_result["messages"] 加入到消息列表 —
        # agent_node 会自己把检索结果合并到系统提示词中

    # 产出 RAG 上下文事件（前端可据此展示参考来源）
    if rag_context:
        yield {
            "type": "rag_context",
            "sources": rag_context,
        }

    # Step 2: 运行 Agent 图
    tools_for_graph = [t for t in enabled_tools if t != "rag"]
    graph = get_graph(tools_for_graph)

    initial_state = AgentState(
        messages=messages,
        retrieved_context=rag_context,
        tools_enabled=tools_for_graph,
        use_rag=False,  # 已在上面处理
        agent_config=agent_config,
        iteration=0,
    )

    # 流式执行图，带全局超时保护
    # asyncio.timeout 包裹整个异步迭代过程，包括每个 __anext__() 调用
    try:
        async with asyncio.timeout(settings.tool_timeout_seconds * 10):
            async for event in graph.astream(initial_state, stream_mode="messages"):
                # stream_mode="messages" 产出 (message, metadata) 元组
                if isinstance(event, tuple):
                    chunk, metadata = event
                    # 流式输出 LLM token
                    if hasattr(chunk, "content") and chunk.content:
                        yield {
                            "type": "token",
                            "content": chunk.content,
                        }
                    # 工具调用事件
                    if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                        for tc in chunk.tool_calls:
                            tool_name = tc.get("name", "unknown")
                            tool_args = tc.get("args", {})
                            # delegate_to_agent 调用时发送 agent_switch 事件
                            # 前端可用此事件展示"正在委托给子 Agent"的过渡动画
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
    except Exception as e:
        # 兜底异常处理：捕获 agent_node 没有处理的 LLM/图级异常
        # 这是 LangGraph 异常传播不干净时的最后防线
        error_name = type(e).__name__
        error_detail = str(e)[:300]
        logger.error(f"LangGraph execution error: {error_name}: {error_detail}", exc_info=True)
        yield {
            "type": "token",
            "content": (
                f"\n\n抱歉，AI 服务暂时不可用。\n\n"
                f"错误类型：{error_name}\n"
                f"建议：切换到 Mock 模式继续测试，或检查后端日志。\n"
                f"详情：{error_detail}"
            ),
        }

    yield {"type": "done", "sources": rag_context}
