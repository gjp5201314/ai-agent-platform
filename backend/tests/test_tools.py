"""
Unit tests for tool functions.
Pure-logic tests run always; app-dependent tests skip gracefully.
"""
import ast
import pytest

# --- Pure-logic tests (always run) ---

class TestBigramJaccard:
    @staticmethod
    def _bigram_jaccard(text1: str, text2: str) -> float:
        def bigrams(s):
            return {s[i:i+2] for i in range(len(s) - 1)}
        b1 = bigrams(text1.lower())
        b2 = bigrams(text2.lower())
        if not b1 or not b2:
            return 0.0
        return len(b1 & b2) / len(b1 | b2)

    def test_exact_match(self):
        assert self._bigram_jaccard("天气查询", "天气查询") == pytest.approx(1.0)

    def test_partial_match(self):
        score = self._bigram_jaccard("今天天气怎么样", "天气查询、温度气候")
        assert score > 0.01

    def test_no_match(self):
        assert self._bigram_jaccard("zzz", "天气查询") == 0.0

    def test_english(self):
        score = self._bigram_jaccard("hello", "hello world")
        assert score > 0.3

    def test_empty_strings(self):
        assert self._bigram_jaccard("", "test") == 0.0
        assert self._bigram_jaccard("test", "") == 0.0
        assert self._bigram_jaccard("", "") == 0.0

    def test_single_char(self):
        assert self._bigram_jaccard("a", "a") == 0.0


class TestSafeEval:
    """Verify the AST sandbox blocks code injection."""
    _SAFE_OPS = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.Pow: lambda a, b: a ** b,
        ast.Mod: lambda a, b: a % b,
        ast.USub: lambda a: -a,
        ast.UAdd: lambda a: +a,
        ast.FloorDiv: lambda a, b: a // b,
    }

    def _safe_eval(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self._SAFE_OPS:
            return self._SAFE_OPS[type(node.op)](self._safe_eval(node.left), self._safe_eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._SAFE_OPS:
            return self._SAFE_OPS[type(node.op)](self._safe_eval(node.operand))
        raise ValueError(f"Unsafe expression: {ast.dump(node)}")

    def test_simple_arithmetic(self):
        tree = ast.parse("1 + 1", mode="eval")
        assert self._safe_eval(tree.body) == 2

    def test_compound(self):
        tree = ast.parse("(10 + 5) * 2", mode="eval")
        assert self._safe_eval(tree.body) == 30

    def test_blocks_import(self):
        with pytest.raises(ValueError, match="Unsafe"):
            tree = ast.parse("__import__('os')", mode="eval")
            self._safe_eval(tree.body)

    def test_blocks_dunder(self):
        with pytest.raises(ValueError):
            tree = ast.parse("().__class__", mode="eval")
            self._safe_eval(tree.body)

    def test_blocks_eval(self):
        with pytest.raises(ValueError):
            tree = ast.parse("eval('1+1')", mode="eval")
            self._safe_eval(tree.body)


# --- App-dependent tests (skip if deps unavailable) ---

_app_deps = False
try:
    from app.agent.tools import calculator, TOOL_GROUPS
    from app.agent.tools import get_relevant_tools, ALL_TOOLS
    _app_deps = True
except ImportError:
    pass


@pytest.mark.skipif(not _app_deps, reason="App dependencies not installed (Docker-only)")
class TestCalculatorApp:
    def test_basic(self):
        assert calculator("2 + 3") == "2 + 3 = 5"
        assert calculator("10 - 4") == "10 - 4 = 6"

    def test_error_handling(self):
        result = calculator("import os")
        assert "错误" in result


@pytest.mark.skipif(not _app_deps, reason="App dependencies not installed (Docker-only)")
class TestToolRoutingApp:
    QUERIES = {
        "今天深圳天气怎么样": "geo_time",
        "帮我算一下 23 * 45 + 100": "finance_math",
        "美元兑人民币汇率是多少": "finance_math",
        "最近有什么热门新闻": "search",
        "讲个笑话听听": "fun",
        "现在几点了": "geo_time",
        "帮我搜索一下 Python 最新版本": "search",
    }

    @pytest.mark.parametrize("query,expected_group", list(QUERIES.items()))
    def test_routing_accuracy(self, query, expected_group):
        all_tools = ["web_search", "fetch_url", "get_news", "exchange_rate",
                     "calculator", "get_weather", "get_current_time", "lookup_ip",
                     "tell_joke"]
        tools, groups = get_relevant_tools(query, all_tools, min_tools=5)
        tool_names = {t.name for t in tools}
        expected_tools = set(TOOL_GROUPS[expected_group]["tools"])
        assert expected_tools.issubset(tool_names), \
            f"Query '{query}' → expected {expected_group}, got {tool_names}"

    def test_fallback_on_no_match(self):
        tools, groups = get_relevant_tools(
            "xyzzy nonsense",
            ["web_search", "calculator", "get_weather", "tell_joke",
             "get_current_time", "fetch_url", "get_news"],
            min_tools=5,
        )
        assert len(tools) > 0

    def test_small_toolset_no_filter(self):
        tools, groups = get_relevant_tools("anything", ["calculator", "tell_joke"], min_tools=6)
        assert groups == ["__all__"]
        assert len(tools) == 2

    def test_all_tools_in_groups(self):
        grouped = set()
        for group in TOOL_GROUPS.values():
            grouped.update(group["tools"])
        missing = set(ALL_TOOLS.keys()) - grouped
        assert not missing, f"Tools not in any group: {missing}"
