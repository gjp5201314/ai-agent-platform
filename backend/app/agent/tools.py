"""
Custom tools for the LangGraph agent.
Each tool is a LangChain BaseTool with async support.
"""
import ast
import operator
from typing import Optional

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


# ---- Web Search (DuckDuckGo HTML scraping, no API key needed) ----

@tool
def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web for current information using DuckDuckGo.
    No API key required. Returns title, URL and snippet for each result.

    Args:
        query: The search query
        max_results: Maximum number of results to return (default 5)

    Returns:
        Formatted search results as text.
    """
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return f"未找到与 '{query}' 相关的搜索结果。"

        lines = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            href = r.get("href", "")
            body = r.get("body", "")
            lines.append(f"{i}. {title}\n   {body}\n   {href}")

        return "\n\n".join(lines)
    except ImportError:
        return "网络搜索功能不可用：缺少 duckduckgo_search 依赖包。"
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


# ---- Weather (wttr.in, no API key needed) ----

@tool
def get_weather(city: str) -> str:
    """
    Get current weather information for a city.
    Uses wttr.in free weather API (no key required).

    Args:
        city: City name in Chinese or English, e.g. "北京" or "Beijing"

    Returns:
        Weather information as formatted text.
    """
    try:
        import urllib.request
        import urllib.parse
        import json

        encoded_city = urllib.parse.quote(city)
        url = f"https://wttr.in/{encoded_city}?format=j1"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        current = data.get("current_condition", [{}])[0]
        if not current:
            return f"未找到 '{city}' 的天气数据，请检查城市名称是否正确。"

        # Get forecast for today
        weather_info = data.get("weather", [{}])[0]
        today_forecast = weather_info.get("hourly", [{}])

        temp_c = current.get("temp_C", "N/A")
        feels_like = current.get("FeelsLikeC", "N/A")
        humidity = current.get("humidity", "N/A")
        wind_speed = current.get("windspeedKmph", "N/A")
        wind_dir = current.get("winddir16Point", "N/A")
        weather_desc = current.get("weatherDesc", [{}])[0].get("value", "N/A")
        visibility = current.get("visibility", "N/A")

        # Get today's high/low
        today = weather_info
        max_temp = today.get("maxtempC", "N/A")
        min_temp = today.get("mintempC", "N/A")

        lines = [
            f"城市: {city}",
            f"天气: {weather_desc}",
            f"当前温度: {temp_c}°C (体感 {feels_like}°C)",
            f"今日最高: {max_temp}°C / 最低: {min_temp}°C",
            f"湿度: {humidity}%",
            f"风速: {wind_speed} km/h ({wind_dir})",
            f"能见度: {visibility} km",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"天气查询失败: {e}"


# ---- Tool registry ----

ALL_TOOLS = {
    "calculator": calculator,
    "web_search": web_search,
    "get_current_time": get_current_time,
    "get_weather": get_weather,
}


def get_tools(enabled_tool_names: list) -> list:
    """
    Return the list of tool callables for the given names.
    'rag' is handled separately by the graph (not a LangChain tool).
    """
    return [ALL_TOOLS[name] for name in enabled_tool_names if name in ALL_TOOLS]
