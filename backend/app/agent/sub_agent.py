"""
Multi-Agent orchestration: sub-agent runners and parallel dispatcher.

Architecture:
    Supervisor (LLM decides which agents to invoke)
        │
        ├── run_sub_agent("search-agent", task)  ──┐
        ├── run_sub_agent("math-agent", task)     ──┤ asyncio.gather
        └── run_sub_agent("writer-agent", task)   ──┘
        │
        ▼
    Aggregator (LLM merges results → final answer)
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


@dataclass
class SubAgentResult:
    """Result from a single sub-agent execution."""
    agent_id: str
    agent_name: str
    task: str
    response: str
    sources: list
    tool_calls: int
    elapsed_ms: float
    error: str = ""


async def run_sub_agent(
    agent_id: str,
    task: str,
    context_messages: list = None,
) -> SubAgentResult:
    """
    Run a named agent as a full LangGraph graph loop (agent → tools → agent …).

    Unlike the old delegate_to_agent (single LLM call), this runs the FULL
    graph: the sub-agent can call its own tools, do RAG retrieval, and go
    through multiple rounds of reasoning.

    Args:
        agent_id:          DB ID of the target agent (e.g. "rag-assistant")
        task:              The question/task for the sub-agent
        context_messages:  Optional conversation context to pass along

    Returns:
        SubAgentResult with the agent's final answer and metadata.
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

            # Build sub-agent config
            sub_config = {
                "provider": settings.llm_provider,
                "system_prompt": agent.system_prompt,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                "enabled_tools": [t for t in agent.enabled_tools if t != "delegate_to_agent"],
                "rag_top_k": agent.rag_top_k,
                "rag_similarity_threshold": agent.rag_similarity_threshold,
                "has_images": False,
            }

            # Build messages: optional context + task
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


async def run_sub_agents_parallel(
    tasks: list[dict],
    context_messages: list = None,
    max_concurrency: int = None,
) -> list[SubAgentResult]:
    """
    Run multiple sub-agents in PARALLEL using asyncio.gather.

    Args:
        tasks:             List of {"agent_id": str, "task": str} dicts
        context_messages:  Shared context for all sub-agents
        max_concurrency:   Max concurrent agents (default from settings)

    Returns:
        List of SubAgentResult objects, one per task.
    """
    if not tasks:
        return []

    max_parallel = max_concurrency or settings.multi_agent_max_parallel
    semaphore = asyncio.Semaphore(max_parallel)

    async def _run_with_limit(task: dict) -> SubAgentResult:
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


async def aggregate_results(
    results: list[SubAgentResult],
    original_query: str,
) -> str:
    """
    Use a lightweight LLM call to merge sub-agent results into a single
    coherent answer to the original user query.
    """
    if not results:
        return "无法获取任何子Agent的结果。"

    if len(results) == 1:
        return f"[{results[0].agent_name}]: {results[0].response}"

    # Build a prompt that asks the LLM to synthesize
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
        # Fallback: just concatenate
        return "\n\n---\n\n".join(
            f"**[{r.agent_name}]**\n{r.response}" for r in results
        )
