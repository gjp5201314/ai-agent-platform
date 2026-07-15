"""
Custom tools for the LangGraph agent.
Each tool is a LangChain BaseTool with async support.
"""
import ast
import operator
import random
import urllib.request
import urllib.parse
import json
import re
import asyncio
import contextvars
from typing import Optional

from langchain_core.tools import tool

from app.config import settings
from app.core.logger import logger

# Track delegation depth per-request (async-safe, thread-safe)
_delegate_depth: contextvars.ContextVar[int] = contextvars.ContextVar(
    "delegate_depth", default=0
)
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

        with DDGS(timeout=settings.tool_timeout_seconds) as ddgs:
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


# ---- News Headlines (free public API, no key needed) ----

@tool
def get_news() -> str:
    """
    Get current trending news and hot topics in China.
    Returns the latest hot search topics. No API key required.

    Returns:
        Formatted list of trending news topics.
    """
    try:
        url = "https://api.vvhan.com/api/hotlist?type=wbHot"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        if not data.get("success"):
            return "获取新闻失败：API 返回异常。"

        items = data.get("data", [])[:15]
        if not items:
            return "暂无热门新闻数据。"

        lines = ["📰 当前热门新闻：", ""]
        for i, item in enumerate(items, 1):
            title = item.get("title", "无标题")
            hot = item.get("hot", "")
            lines.append(f"{i}. {title}" + (f" (热度: {hot})" if hot else ""))

        return "\n".join(lines)
    except Exception as e:
        return f"新闻获取失败: {e}"


# ---- IP Location Lookup (free API, no key needed) ----

@tool
def lookup_ip(ip: str) -> str:
    """
    Look up geolocation information for an IP address.
    Uses ip-api.com free service. No API key required.

    Args:
        ip: An IPv4 or IPv6 address, e.g. "8.8.8.8"

    Returns:
        Location info: country, region, city, ISP, etc.
    """
    try:
        url = f"http://ip-api.com/json/{urllib.parse.quote(ip)}?lang=zh-CN"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        if data.get("status") != "success":
            return f"IP 查询失败: {data.get('message', '未知错误')}"

        return (
            f"IP: {data.get('query', 'N/A')}\n"
            f"国家: {data.get('country', 'N/A')}\n"
            f"地区: {data.get('regionName', 'N/A')}\n"
            f"城市: {data.get('city', 'N/A')}\n"
            f"ISP: {data.get('isp', 'N/A')}\n"
            f"经纬度: {data.get('lat', 'N/A')}, {data.get('lon', 'N/A')}"
        )
    except Exception as e:
        return f"IP 查询失败: {e}"


# ---- Exchange Rate (free API, no key needed) ----

@tool
def exchange_rate(from_currency: str = "CNY", to_currency: str = "USD") -> str:
    """
    Get real-time exchange rate between two currencies.
    Uses exchangerate-api.com free service. No API key required.

    Args:
        from_currency: Source currency code, e.g. "CNY", "USD", "EUR" (default CNY)
        to_currency: Target currency code, e.g. "USD", "JPY", "EUR" (default USD)

    Returns:
        Exchange rate and conversion example.
    """
    try:
        frm = from_currency.upper().strip()
        to = to_currency.upper().strip()

        url = f"https://api.exchangerate-api.com/v4/latest/{frm}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        rates = data.get("rates", {})
        if to not in rates:
            return f"不支持的货币代码: {to}。支持的货币有: {', '.join(sorted(rates.keys())[:20])}..."

        rate = rates[to]
        return (
            f"1 {frm} = {rate:.4f} {to}\n"
            f"100 {frm} = {rate * 100:.2f} {to}\n"
            f"1000 {frm} = {rate * 1000:.2f} {to}\n"
            f"更新时间: {data.get('date', 'N/A')}"
        )
    except Exception as e:
        return f"汇率查询失败: {e}"


# ---- URL Content Fetcher ----

@tool
def fetch_url(url: str, max_chars: int = 3000) -> str:
    """
    Fetch and extract readable text content from a web page URL.
    Strips HTML tags and scripts. Useful for summarizing articles.

    Args:
        url: Full URL of the web page to fetch
        max_chars: Maximum characters to return (default 3000)

    Returns:
        Extracted text content of the page.
    """
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AiAgent/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                return f"不支持的内容类型: {content_type}，仅支持 HTML/文本页面。"

            html = resp.read().decode("utf-8", errors="replace")

        # Remove script and style blocks
        html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", html)

        # Clean up whitespace
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&quot;", '"', text)
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n... (内容过长，已截断至 {max_chars} 字符)"

        if not text.strip():
            return "未能从该页面提取到有效文本内容。"

        return f"来源: {url}\n\n{text}"
    except Exception as e:
        return f"URL 抓取失败: {e}"


# ---- Random Jokes ----

_JOKES = [
    "程序员最讨厌的康熙的哪个儿子？——胤禩，因为他是八阿哥（bug）。",
    "一个程序员的妻子问他：「亲爱的，去便利店买一袋盐，如果看到西瓜，买一个。」程序员买了一个盐回来。妻子问：「为什么只买了盐？」程序员说：「因为我看到了西瓜。」",
    "为什么程序员总是分不清万圣节和圣诞节？因为 Oct 31 == Dec 25。",
    "产品经理：「这个需求很简单，怎么实现我不管。」程序员卒，享年 25 岁。",
    "前端工程师说：「这个布局在 Chrome、Firefox、Edge 上都完美。」IE 用户：「那我呢？」前端工程师：「你谁？」",
    "面试官：「你期望的薪资是多少？」程序员：「5k。」面试官：「给你 10k，只要你把这个 bug 修好。」程序员：「成交，什么 bug？」面试官：「世界和平。」",
    "程序员提了一个 bug：「这个功能不符合预期。」测试回复：「那你的预期是什么？」程序员：「我还没想好。」",
    "一个程序员在海边捡到一个神灯，灯神说：「我可以实现你三个愿望。」程序员：「第一，给我一台顶配 MacBook。」灯神：「没问题，第二个？」程序员：「给我一个永远不会出 bug 的代码库。」灯神沉默了很久：「第三个愿望是什么？」程序员：「把刚才那个取消了吧。」",
    "为什么程序员的女朋友总是生气？因为她们发现男朋友的 exception handling 只有 try，没有 catch。",
    "代码审查时，同事：「你这里为什么要写 sleep(1000)？」程序员：「因为我觉得代码跑得太快了，想让它等等后面的代码。」",
    "老板：「这个项目明天就要上线！」程序员：「没问题，我现在就开始删库。」老板：「？？？」程序员：「开个玩笑，我已经删完了。」",
    "产品经理：「这个按钮能不能再往左移 1 像素？」设计师：「能不能别这么矫情？」产品经理：「这不是矫情，这是优雅。」",
    "问: 为什么 Linux 用户不需要杀毒软件？答: 因为病毒作者也找不到怎么安装。",
    "Git 提交信息大全：'fix bug'、'fix bug again'、'final fix'、'final fix 2'、'really final fix'、'我放弃了'。",
]

@tool
def tell_joke() -> str:
    """
    Tell a random programming / tech related joke in Chinese.
    Great for lightening the mood.

    Returns:
        A random joke as text.
    """
    return random.choice(_JOKES)


# ============================================================
#  Tool Groups — semantic routing layer
# ============================================================

TOOL_GROUPS = {
    "search": {
        "description": "网页搜索、搜索查询、URL抓取、获取新闻热搜、实时信息、网络检索",
        "tools": ["web_search", "fetch_url", "get_news"],
    },
    "finance_math": {
        "description": "汇率换算、美元人民币日元欧元、货币兑换、金融计算、算一下、算数、数学计算、加减乘除、数值求值",
        "tools": ["exchange_rate", "calculator"],
    },
    "geo_time": {
        "description": "天气查询、温度气候、当前日期时间、现在几点、IP地址定位查IP、地理位置信息、时区",
        "tools": ["get_weather", "get_current_time", "lookup_ip"],
    },
    "fun": {
        "description": "讲个笑话、讲笑话、程序员幽默、娱乐放松、段子",
        "tools": ["tell_joke"],
    },
    "code_exec": {
        "description": "执行代码、运行Python、写脚本、数据分析、画图绘图、计算处理、编程、写程序、运行JS、JavaScript、Node.js、shell命令、bash、终端命令、安装pip包、安装python库",
        "tools": ["run_python_code", "run_javascript_code", "run_shell_command", "install_python_packages"],
    },
}


def _bigram_jaccard(text1: str, text2: str) -> float:
    """
    Character bigram Jaccard similarity.
    Works for both Chinese (character-level) and English (letter-level).
    No external dependencies, instant computation.
    """
    def bigrams(s: str) -> set:
        return {s[i:i+2] for i in range(len(s) - 1)}

    b1 = bigrams(text1.lower())
    b2 = bigrams(text2.lower())
    if not b1 or not b2:
        return 0.0
    return len(b1 & b2) / len(b1 | b2)


def get_relevant_tools(
    user_query: str,
    enabled_tool_names: list,
    top_k_groups: int = 2,
    min_tools: int = 6,
) -> tuple[list, list]:
    """
    Semantically filter tools based on user query intent.

    Two-layer funnel:
      1. Match user query against TOOL_GROUPS descriptions (bigram Jaccard)
      2. Expand matched groups → only those tools go to the LLM

    Meta-tools (delegate_to_agent, rag) always pass through unfiltered.

    Args:
        user_query:         The user's latest message text
        enabled_tool_names: All tool names enabled for this agent
        top_k_groups:       Max number of tool groups to include
        min_tools:          Only activate filtering when tool count exceeds this

    Returns:
        (filtered_tool_callables, selected_group_names)
    """
    if not user_query or len(enabled_tool_names) <= min_tools:
        return get_tools(enabled_tool_names), ["__all__"]

    # Separate meta-tools (always include)
    meta_names = {"delegate_to_agent", "dispatch_tasks", "search_knowledge_base", "rag"}
    meta_tools = [t for t in enabled_tool_names if t in meta_names]
    regular_tools = [t for t in enabled_tool_names if t not in meta_names]

    if not regular_tools:
        return get_tools(enabled_tool_names), ["__meta_only__"]

    # Score each group against the user query
    scored = []
    for group_name, group_info in TOOL_GROUPS.items():
        group_tools = [t for t in group_info["tools"] if t in regular_tools]
        if not group_tools:
            continue
        score = _bigram_jaccard(user_query, group_info["description"])
        scored.append((score, group_name, group_tools))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Select top_k_groups (only if score > 0)
    selected_tool_names = []
    selected_groups = []
    for score, group_name, group_tools in scored[:top_k_groups]:
        if score > 0.0:
            selected_tool_names.extend(group_tools)
            selected_groups.append(f"{group_name}({score:.2f})")

    # Fallback: if nothing matched, use all regular tools
    if not selected_tool_names:
        selected_tool_names = regular_tools
        selected_groups = ["__fallback_all__"]

    # Merge: selected + meta-tools, deduplicate
    all_selected = list(dict.fromkeys(selected_tool_names + meta_tools))

    # Convert names to tool callables
    tools = [ALL_TOOLS[name] for name in all_selected if name in ALL_TOOLS]
    if "delegate_to_agent" in enabled_tool_names:
        tools.append(delegate_to_agent)
    if "dispatch_tasks" in enabled_tool_names:
        tools.append(dispatch_tasks)

    logger.debug(f"Tool routing: query='{user_query[:60]}' → groups={selected_groups} → tools={[t.name for t in tools]}")
    return tools, selected_groups


# ---- Code Sandbox (DifySandbox) ----

@tool
async def run_python_code(code: str) -> str:
    """
    Execute Python code in a secure sandboxed environment and return the output.
    Use this when the user asks you to write and run Python code (data analysis,
    calculations, file processing, plotting, etc.).

    The sandbox has NO network access and a 30-second timeout.
    Long-running or network-heavy code will fail.
    Common packages (numpy, pandas, matplotlib) are pre-installed.
    Use install_python_packages first if you need other libraries.

    For plotting: use matplotlib and save to 'output.png', the result file will
    be accessible.

    Args:
        code: The Python source code to execute. Must be complete and self-contained.

    Returns:
        The stdout/stderr from the executed code, or an error message.
    """
    from app.core.sandbox import get_sandbox_client, validate_sandbox_code

    # Pre-flight validation
    is_safe, err_msg = validate_sandbox_code(code)
    if not is_safe:
        return f"代码安全校验未通过: {err_msg}"

    try:
        client = get_sandbox_client()
        result = await client.run_code(code)

        if result.error and not result.stdout and not result.stderr:
            return f"沙箱执行失败: {result.error}"

        parts = []
        if result.stdout.strip():
            parts.append(f"[stdout]\n{result.stdout.strip()}")
        if result.stderr.strip():
            parts.append(f"[stderr]\n{result.stderr.strip()}")
        if result.error:
            parts.append(f"[error] exit_code={result.exit_code}\n{result.error.strip()}")
        if not parts:
            return "(no output)"

        footer = f"\n\n⏱ {result.elapsed_ms:.0f}ms | exit_code={result.exit_code}"
        return "\n\n".join(parts) + footer
    except Exception as e:
        return f"沙箱调用异常: {str(e)[:300]}"


@tool
async def run_javascript_code(code: str) -> str:
    """
    Execute JavaScript (Node.js) code in a secure sandboxed environment.
    Use this when the user asks you to write and run JavaScript code.

    The sandbox has NO network access and a 15-second timeout.
    Use console.log() for output.

    Args:
        code: The JavaScript source code to execute.

    Returns:
        The stdout/stderr from the executed code, or an error message.
    """
    from app.core.sandbox import get_sandbox_client, SandboxLanguage

    try:
        client = get_sandbox_client()
        result = await client.run_code(code, language=SandboxLanguage.JAVASCRIPT)

        if result.error and not result.stdout and not result.stderr:
            return f"JavaScript 沙箱执行失败: {result.error}"

        parts = []
        if result.stdout.strip():
            parts.append(f"[stdout]\n{result.stdout.strip()}")
        if result.stderr.strip():
            parts.append(f"[stderr]\n{result.stderr.strip()}")
        if result.error:
            parts.append(f"[error] exit_code={result.exit_code}\n{result.error.strip()}")
        if not parts:
            return "(no output)"

        footer = f"\n\n⏱ {result.elapsed_ms:.0f}ms | exit_code={result.exit_code}"
        return "\n\n".join(parts) + footer
    except Exception as e:
        return f"JavaScript 沙箱异常: {str(e)[:300]}"


@tool
async def run_shell_command(command: str) -> str:
    """
    Execute a bash shell command in the secure sandbox.
    Use sparingly — prefer run_python_code or run_javascript_code for script tasks.
    Useful for: file listing, text processing, package checks.

    The sandbox has NO network access and a 10-second timeout.

    Args:
        command: The shell command to execute, e.g. "ls -la" or "cat file.txt"

    Returns:
        The stdout/stderr from the command, or an error message.
    """
    from app.core.sandbox import get_sandbox_client, SandboxLanguage

    try:
        client = get_sandbox_client()
        result = await client.run_code(
            command,
            language=SandboxLanguage.BASH,
            timeout=10.0,
        )

        if result.error and not result.stdout and not result.stderr:
            return f"Shell 执行失败: {result.error}"

        parts = []
        if result.stdout.strip():
            parts.append(result.stdout.strip())
        if result.stderr.strip():
            parts.append(f"[stderr]\n{result.stderr.strip()}")
        if result.error:
            parts.append(f"[error] exit_code={result.exit_code}\n{result.error.strip()}")
        if not parts:
            return "(no output)"

        return "\n\n".join(parts)
    except Exception as e:
        return f"Shell 执行异常: {str(e)[:300]}"


@tool
async def install_python_packages(packages: str) -> str:
    """
    Install Python packages in the sandbox via pip.
    Use this BEFORE run_python_code if your code needs libraries not in the
    standard library. Common packages (numpy, pandas, matplotlib) may already
    be installed.

    Args:
        packages: Space-separated package names, e.g. "requests beautifulsoup4"
                  or with versions: "numpy==1.24 pandas>=2.0"

    Returns:
        Installation result message.
    """
    from app.core.sandbox import get_sandbox_client

    pkg_list = [p.strip() for p in packages.split() if p.strip()]
    if not pkg_list:
        return "请提供要安装的包名，例如: install_python_packages('numpy pandas')"

    if len(pkg_list) > 10:
        return "一次最多安装 10 个包，请分批安装。"

    try:
        client = get_sandbox_client()
        return await client.install_dependencies(pkg_list)
    except Exception as e:
        return f"包安装异常: {str(e)[:300]}"


# ---- Tool registry ----

ALL_TOOLS = {
    "calculator": calculator,
    "web_search": web_search,
    "get_current_time": get_current_time,
    "get_weather": get_weather,
    "get_news": get_news,
    "lookup_ip": lookup_ip,
    "exchange_rate": exchange_rate,
    "fetch_url": fetch_url,
    "tell_joke": tell_joke,
    "run_python_code": run_python_code,
    "run_javascript_code": run_javascript_code,
    "run_shell_command": run_shell_command,
    "install_python_packages": install_python_packages,
}


def get_tools(enabled_tool_names: list) -> list:
    """
    Return the list of tool callables for the given names.
    'rag' is a legacy pre-process flag (deprecated in favor of search_knowledge_base).
    'search_knowledge_base' / 'delegate_to_agent' / 'dispatch_tasks' are meta-tools.
    """
    tools = [ALL_TOOLS[name] for name in enabled_tool_names if name in ALL_TOOLS]
    if "search_knowledge_base" in enabled_tool_names:
        tools.append(search_knowledge_base)
    if "delegate_to_agent" in enabled_tool_names:
        tools.append(delegate_to_agent)
    if "dispatch_tasks" in enabled_tool_names:
        tools.append(dispatch_tasks)
    return tools


# ---- Knowledge Base Search (on-demand, not pre-processing) ----

@tool
async def search_knowledge_base(query: str) -> str:
    """
    Search the knowledge base for relevant documents, chunks, or information.
    Use this when the user asks about something that might be in the uploaded
    documents. The LLM decides WHEN to call this — not every query.

    Args:
        query: A focused search query (can be different from the user's exact words)

    Returns:
        Relevant document chunks with filename and content, or an empty result message.
    """
    from app.database import async_session_factory
    from app.rag.retriever import hybrid_search
    from app.config import settings

    try:
        async with async_session_factory() as db:
            results = await hybrid_search(
                db, query,
                top_k=4,
                similarity_threshold=getattr(settings, 'rag_similarity_threshold', 0.5),
            )

        if not results:
            return "知识库中未找到与查询相关的内容。"

        lines = ["以下是知识库中与查询相关的内容："]
        for i, r in enumerate(results, 1):
            lines.append(f"\n[文档 {i}] {r.filename} (相似度: {r.score:.0%})")
            lines.append(f"{r.content[:500]}")
            if len(r.content) > 500:
                lines.append("...(内容过长已截断)")

        return "\n".join(lines)

    except Exception as e:
        return f"知识库搜索失败: {str(e)[:200]}"


# ---- Agent Delegation (meta-tool: delegates task to another agent) ----

@tool
async def delegate_to_agent(agent_id: str, task: str) -> str:
    """
    Delegate a sub-task to another specialized agent.
    Use this to hand off work that another agent is better suited for.

    Args:
        agent_id: The ID of the target agent (e.g. "rag-assistant" for knowledge base queries,
                  "default" for general tasks). Use the exact agent ID.
        task: A clear description of what you need the target agent to do.
              Include all necessary context.

    Returns:
        The result from the target agent.
    """
    # ---- recursion guard ----
    depth = _delegate_depth.get()
    if depth >= settings.delegate_max_depth:
        return (
            f"委托失败: 已达到最大委托深度({settings.delegate_max_depth}层)。"
            f"当前深度={depth}，请直接回答问题，不要再委托。"
        )
    _delegate_depth.set(depth + 1)

    try:
        from app.agent.sub_agent import run_sub_agent

        result = await run_sub_agent(agent_id=agent_id, task=task)
        _delegate_depth.set(depth)
        return (
            f"[Agent: {result.agent_name} | "
            f"耗时: {result.elapsed_ms:.0f}ms | "
            f"工具调用: {result.tool_calls}次]\n\n"
            f"{result.response}"
        )

    except Exception as e:
        _delegate_depth.set(depth)
        return f"委托执行失败: {str(e)}"


# ---- Parallel Multi-Agent Dispatch ----

@tool
async def dispatch_tasks(sub_tasks_json) -> str:
    """
    Dispatch multiple sub-tasks to specialized agents IN PARALLEL.
    Use this when a user request requires multiple agents working simultaneously.

    Args:
        sub_tasks_json: A JSON array (or already-parsed list) of objects, each with
            "agent_id" and "task".
            Example: [{"agent_id":"rag-assistant","task":"搜索XX"},
                      {"agent_id":"default","task":"计算XX"}]

    Returns:
        Combined results from all sub-agents.
    """
    import json as _json

    # ---- Parse input (accept both JSON string and Python list/dict) ----
    tasks = None
    if isinstance(sub_tasks_json, (list, dict)):
        tasks = sub_tasks_json if isinstance(sub_tasks_json, list) else [sub_tasks_json]
    elif isinstance(sub_tasks_json, str):
        try:
            tasks = _json.loads(sub_tasks_json)
            if not isinstance(tasks, list):
                return "dispatch_tasks 参数格式错误: 需要 JSON 数组。得到: " + type(tasks).__name__
        except (_json.JSONDecodeError, TypeError):
            return "dispatch_tasks 参数格式错误: 无法解析 JSON。"
    else:
        return f"dispatch_tasks 参数类型错误: {type(sub_tasks_json).__name__}"

    if not tasks:
        return "dispatch_tasks: 任务列表为空。"

    if len(tasks) > settings.multi_agent_max_parallel * 2:
        return f"一次最多并行 {settings.multi_agent_max_parallel * 2} 个任务，你传了 {len(tasks)} 个。"

    # ---- Validate task format ----
    agent_tasks = []
    for i, t in enumerate(tasks):
        if not isinstance(t, dict):
            return f"dispatch_tasks: 第 {i+1} 个任务格式错误，需要对象。得到: {type(t).__name__}"
        agent_tasks.append({
            "agent_id": t.get("agent_id", "default"),
            "task": t.get("task", ""),
        })
        if not agent_tasks[-1]["task"]:
            return f"dispatch_tasks: 第 {i+1} 个任务缺少 'task' 字段。"

    # ---- Execute (full try/except so the tool ALWAYS returns a string) ----
    try:
        from app.agent.sub_agent import run_sub_agents_parallel, aggregate_results
        results = await run_sub_agents_parallel(agent_tasks)
        combined = await aggregate_results(
            results,
            original_query="并行处理多个子任务",
        )
        return combined

    except asyncio.TimeoutError:
        return "dispatch_tasks: 部分子任务超时，已返回已有结果。"
    except Exception as e:
        logger.error(f"dispatch_tasks failed: {e}", exc_info=True)
        return f"dispatch_tasks 执行失败: {str(e)[:200]}"
