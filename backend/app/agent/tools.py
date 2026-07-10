"""
Custom tools for the LangGraph agent.
Each tool is a LangChain BaseTool with async support.
"""
import ast
import operator
from typing import Optional

import httpx
from langchain_core.tools import tool


# ---- Calculator ----

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.FloorDiv: operator.floordiv,
}


def _safe_eval(node):
    """Recursively evaluate an AST node with a safe set of operators."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsafe expression: {ast.dump(node)}")


@tool
def calculator(expression: str) -> str:
    """
    Safely evaluate a mathematical expression.
    Supports: +, -, *, /, **, %, //, parentheses.

    Args:
        expression: A math expression like "2 + 3 * 4" or "(100 - 20) / 4"

    Returns:
        The computed result as a string.
    """
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        return f"{expression} = {result}"
    except Exception as e:
        return f"计算错误: {e}. 请检查表达式格式。"


# ---- Web Search (DuckDuckGo, no API key needed) ----

@tool
async def web_search(query: str) -> str:
    """
    Search the web for current information.
    Uses DuckDuckGo Instant Answer API (no key required).

    Args:
        query: The search query

    Returns:
        Search results summary as text.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # DuckDuckGo Instant Answer API
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1",
                },
            )
            data = resp.json()

            results = []
            if data.get("AnswerText"):
                results.append(data["AnswerText"])
            if data.get("AbstractText"):
                results.append(data["AbstractText"])
            for topic in (data.get("RelatedTopics") or [])[:5]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append(topic["Text"])

            if not results:
                return f"未找到与 '{query}' 相关的搜索结果。"
            return "\n---\n".join(results)
    except Exception as e:
        return f"网络搜索失败: {e}"


# ---- Get current time ----

@tool
def get_current_time() -> str:
    """
    Get the current date and time in Beijing timezone (UTC+8).

    Returns:
        Current date and time as a formatted string.
    """
    from datetime import datetime, timezone, timedelta
    beijing_tz = timezone(timedelta(hours=8))
    now = datetime.now(beijing_tz)
    return now.strftime("%Y年%m月%d日 %H:%M:%S (北京时间)")


# ---- Tool registry ----

ALL_TOOLS = {
    "calculator": calculator,
    "web_search": web_search,
    "get_current_time": get_current_time,
}


def get_tools(enabled_tool_names: list) -> list:
    """
    Return the list of tool callables for the given names.
    'rag' is handled separately by the graph (not a LangChain tool).
    """
    return [ALL_TOOLS[name] for name in enabled_tool_names if name in ALL_TOOLS]
