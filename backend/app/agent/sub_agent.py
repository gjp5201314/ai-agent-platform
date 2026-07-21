"""
================================================================================
多 Agent 编排 — 子 Agent 运行与并行调度（前端必读）
================================================================================

这个文件实现了多 Agent 协作的核心机制。当 Supervisor Agent（主管）判断当前
任务需要其他专业 Agent 协助时，会将子任务委托给对应的子 Agent 执行。

架构概览
-------------------------------------
多 Agent 协作采用"主管-执行者"模式（Supervisor-Executor Pattern）：

  Supervisor（主 Agent，LLM 驱动）
      │
      │  调用 delegate_to_agent 或 dispatch_tasks 工具
      │
      ├──→ run_sub_agent("search-agent", "搜索相关资料")
      │        │
      │        └── 运行完整的子 Agent 图（agent → tools → agent 循环）
      │            返回 SubAgentResult
      │
      ├──→ run_sub_agent("math-agent", "计算统计结果")   ← 通过 asyncio.gather
      │        │                                          并行执行
      │        └── 返回 SubAgentResult
      │
      └──→ aggregate_results() — LLM 汇总所有子 Agent 结果
               │
               └── 合并为最终回复返回给主 Agent

对前端开发者来说，关键概念
-------------------------------------
1. 委托模式（Delegation）
   - 主 Agent 调用 delegate_to_agent(agent_id, task)
   - 触发 "agent_switch" SSE 事件（在 graph.py 中发送）
   - 前端可据此显示"正在委托给 XX Agent"的过渡动画

2. 并行模式（Parallel Dispatch）
   - 主 Agent 调用 dispatch_tasks([{agent_id, task}, ...])
   - 多个子 Agent 通过 asyncio.gather 同时运行
   - 全部完成后由 aggregate_results() 汇总

3. SubAgentResult 数据结构
   - 每个子 Agent 返回标准化的结果对象
   - 包含响应文本、耗时、工具调用次数等信息
   - 前端可用于展示子 Agent 执行详情

4. agent_switch SSE 事件
   - 在 graph.py 的 run_agent() 流式模式中发送
   - 格式: {"type": "agent_switch", "from_agent": "current", "to_agent": "xxx", "task": "..."}
   - 前端可以：展示切换动画、更新 Agent 名称显示、记录任务分配日志

数据流（从前端视角）
-------------------------------------
  用户发送复杂请求
  → 主 Agent 分析后调用 delegate_to_agent
  → graph.py 发送 "agent_switch" SSE 事件（前端展示切换动画）
  → run_sub_agent() 执行子 Agent 的完整图
  → 子 Agent 在内部产生 token/tool_start 等事件
  → 子 Agent 完成后结果返回给主 Agent
  → 主 Agent 基于结果继续推理并回复用户
"""
import asyncio
from dataclasses import dataclass

from langchain_core.messages import SystemMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models import AgentConfig
from app.agent.graph import run_agent_graph
from app.agent.tools import get_tools
from app.core.logger import logger


# ============================================================================
# SubAgentResult — 子 Agent 执行结果的数据结构
# ============================================================================
# 每个子 Agent 执行完毕后返回此对象。前端关注字段：
# - agent_name: 显示在子 Agent 执行状态栏中
# - response: 子 Agent 的文本回复
# - elapsed_ms: 耗时，可展示性能指标
# - tool_calls: 工具调用次数，可展示子 Agent 能力使用情况
# - error: 失败时的错误信息（空字符串表示成功）
# ============================================================================

@dataclass
class SubAgentResult:
    """单个子 Agent 的执行结果。"""
    agent_id: str
    agent_name: str
    task: str
    response: str
    sources: list
    tool_calls: int
    elapsed_ms: float
    error: str = ""


# ============================================================================
# run_sub_agent — 串行运行单个子 Agent
# ============================================================================

async def run_sub_agent(
    agent_id: str,
    task: str,
    context_messages: list = None,
) -> SubAgentResult:
    """
    运行指定 ID 的子 Agent 完整图循环（agent → tools → agent …）。

    与旧版 delegate_to_agent（单次 LLM 调用）不同，此函数运行完整的
    LangGraph 图：子 Agent 可以调用自己的工具、执行 RAG 检索、
    进行多轮推理。

    执行流程：
    1. 从数据库加载 Agent 配置（system_prompt, temperature, enabled_tools 等）
    2. 校验 Agent 是否存在、是否允许被委托
    3. 构建子 Agent 需要的消息和配置
    4. 调用 run_agent_graph() 运行完整的图（非流式，等待完整结果）
    5. 封装为 SubAgentResult 返回

    委托安全机制：
    - 子 Agent 的 enabled_tools 会移除 delegate_to_agent（防止无限嵌套）
    - 通过 settings.delegate_max_depth 控制最大委托深度
    - 不存在的 Agent → 返回错误提示
    - 未开启委托的 Agent → 返回错误提示
    - 超时 → 返回超时提示

    参数：
        agent_id:         目标 Agent 的数据库 ID（如 "rag-assistant"）
        task:             要委托的任务描述
        context_messages: 可选的对话上下文（父 Agent 的已处理信息）

    返回：
        SubAgentResult — 包含子 Agent 的完整回复和执行元数据
    """
    import time
    t0 = time.time()

    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(AgentConfig).where(AgentConfig.id == agent_id)
            )
            agent = result.scalar_one_or_none()

            if not agent:
                return SubAgentResult(
                    agent_id=agent_id,
                    agent_name="unknown",
                    task=task,
                    response=f"委托失败: 找不到Agent '{agent_id}'",
                    sources=[],
                    tool_calls=0,
                    elapsed_ms=0,
                    error="agent_not_found",
                )

            if not agent.allow_delegation:
                return SubAgentResult(
                    agent_id=agent_id,
                    agent_name=agent.name,
                    task=task,
                    response=f"委托失败: Agent '{agent.name}' 未开启委托功能",
                    sources=[],
                    tool_calls=0,
                    elapsed_ms=0,
                    error="delegation_blocked",
                )

            # 构建子 Agent 配置（从数据库加载的 AgentConfig）
            sub_config = {
                "provider": settings.llm_provider,
                "system_prompt": agent.system_prompt,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                # 移除 delegate_to_agent，防止子 Agent 再嵌套委托
                "enabled_tools": [t for t in agent.enabled_tools if t != "delegate_to_agent"],
                "rag_top_k": agent.rag_top_k,
                "rag_similarity_threshold": agent.rag_similarity_threshold,
                "has_images": False,
            }

            # 构建消息：可选的上下文 + 任务描述
            messages = []
            if context_messages:
                messages.extend(context_messages)
            messages.append(HumanMessage(content=task))

            use_rag = "rag" in agent.enabled_tools

            logger.info(f"Sub-agent [{agent.name}] starting: {task[:80]}...")
            result = await run_agent_graph(
                messages=messages,
                agent_config=sub_config,
                use_rag=use_rag,
                db=db,
            )
            elapsed = (time.time() - t0) * 1000

            logger.info(
                f"Sub-agent [{agent.name}] done in {elapsed:.0f}ms, "
                f"tools={result.get('tool_calls', 0)}, "
                f"response_len={len(result.get('response', ''))}"
            )

            return SubAgentResult(
                agent_id=agent_id,
                agent_name=agent.name,
                task=task,
                response=result["response"],
                sources=result.get("sources", []),
                tool_calls=result.get("tool_calls", 0),
                elapsed_ms=elapsed,
            )

    except asyncio.TimeoutError:
        elapsed = (time.time() - t0) * 1000
        return SubAgentResult(
            agent_id=agent_id,
            agent_name="unknown",
            task=task,
            response=f"[超时] 子Agent '{agent_id}' 在 {elapsed:.0f}ms 内未完成。",
            sources=[],
            tool_calls=0,
            elapsed_ms=elapsed,
            error="timeout",
        )
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        logger.error(f"Sub-agent [{agent_id}] failed: {e}")
        return SubAgentResult(
            agent_id=agent_id,
            agent_name="unknown",
            task=task,
            response=f"子Agent执行失败: {str(e)[:200]}",
            sources=[],
            tool_calls=0,
            elapsed_ms=elapsed,
            error=str(e)[:200],
        )


# ============================================================================
# run_sub_agents_parallel — 并行运行多个子 Agent
# ============================================================================

async def run_sub_agents_parallel(
    tasks: list[dict],
    context_messages: list = None,
    max_concurrency: int = None,
) -> list[SubAgentResult]:
    """
    使用 asyncio.gather 并行运行多个子 Agent。

    这是 dispatch_tasks 工具的后端实现。当用户请求涉及多个专业领域时，
    所有子 Agent 同时运行，而非串行等待。

    并发控制：
    - 通过 asyncio.Semaphore 限制最大并发数
    - 默认值来自 settings.multi_agent_max_parallel
    - 每个子 Agent 内部仍运行完整的图循环

    参数：
        tasks:             任务列表 [{"agent_id": str, "task": str}, ...]
        context_messages:  所有子 Agent 共享的对话上下文
        max_concurrency:   最大并发数（默认从 settings 读取）

    返回：
        SubAgentResult 列表，顺序与输入 tasks 对应
    """
    if not tasks:
        return []

    max_parallel = max_concurrency or settings.multi_agent_max_parallel
    semaphore = asyncio.Semaphore(max_parallel)

    async def _run_with_limit(task: dict) -> SubAgentResult:
        """带并发限制的子 Agent 执行包装器。"""
        async with semaphore:
            return await run_sub_agent(
                agent_id=task["agent_id"],
                task=task["task"],
                context_messages=context_messages,
            )

    logger.info(f"Dispatching {len(tasks)} sub-agents in parallel (max_concurrent={max_parallel})")
    results = await asyncio.gather(*[_run_with_limit(t) for t in tasks])
    logger.info(
        f"All sub-agents complete: "
        + ", ".join(f"[{r.agent_name}]({r.elapsed_ms:.0f}ms)" for r in results)
    )
    return list(results)


# ============================================================================
# aggregate_results — 汇总多个子 Agent 的结果
# ============================================================================

async def aggregate_results(
    results: list[SubAgentResult],
    original_query: str,
) -> str:
    """
    使用轻量 LLM 调用将多个子 Agent 的结果合并为一个连贯的回答。

    工作流程：
    1. 如果只有一个结果，直接返回（不做汇总）
    2. 将多个结果格式化后作为一个提示词发给 LLM
    3. LLM 负责：去重、合并、结构化为统一回答
    4. 如果汇总 LLM 调用失败，使用纯文本拼接兜底

    为什么需要汇总？
    - 不同子 Agent 的回答可能相互矛盾或重复
    - 需要统一的语气和格式
    - 需要针对原始问题做最终判断

    参数：
        results:        子 Agent 执行结果列表
        original_query: 用户的原始问题（用于汇总时的上下文）

    返回：
        汇总后的最终回答文本
    """
    if not results:
        return "无法获取任何子Agent的结果。"

    if len(results) == 1:
        return f"[{results[0].agent_name}]: {results[0].response}"

    # 构建汇总提示词，要求 LLM 综合所有子 Agent 的结果
    from app.agent.llm import get_llm
    llm = get_llm(temperature=0.3, max_tokens=2048)

    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"### Agent {i}: {r.agent_name}\n任务: {r.task}\n回答: {r.response}")
    sub_results = "\n\n".join(parts)

    prompt = f"""你是一个协调者。请将以下多个子Agent的结果合并成一个连贯、全面的回答。

**用户原始问题**: {original_query}

**子Agent结果**:
{sub_results}

**要求**:
1. 综合所有子Agent的信息，不要遗漏
2. 去重：如果多个Agent说了相同的内容，只保留一份
3. 结构清晰：用段落或列表组织
4. 如果有矛盾，指出并给出你的判断
5. 直接给出最终回答，不要说"综合以上"之类的元描述"""

    try:
        response = await llm.ainvoke([
            SystemMessage(content="你是一个信息综合助手，将多个来源的结果合并成清晰、准确的回答。"),
            HumanMessage(content=prompt),
        ])
        return response.content
    except Exception as e:
        logger.warning(f"Aggregation failed: {e}, returning raw results")
        # 兜底：直接拼接所有结果
        return "\n\n---\n\n".join(
            f"**[{r.agent_name}]**\n{r.response}" for r in results
        )
