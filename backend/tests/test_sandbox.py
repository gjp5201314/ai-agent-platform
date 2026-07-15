"""
Unit tests for DifySandbox integration.

Pure-logic tests (validation, models) run always.
Integration tests (actual sandbox calls) skip when sandbox is unreachable.
"""
import pytest

# ---------------------------------------------------------------------------
#  Pure-logic tests — always run
# ---------------------------------------------------------------------------


class TestSandboxCodeValidation:
    """Pre-flight code validation (defense-in-depth)."""

    @staticmethod
    def _validate(code: str, enable_network: bool = False):
        from app.core.sandbox import validate_sandbox_code
        return validate_sandbox_code(code, enable_network=enable_network)

    def test_valid_code(self):
        ok, msg = self._validate("print('hello world')")
        assert ok
        assert msg == ""

    def test_empty_code(self):
        ok, msg = self._validate("")
        assert not ok
        assert "empty" in msg.lower()

    def test_whitespace_only(self):
        ok, msg = self._validate("   \n\t  ")
        assert not ok

    def test_too_long_code(self):
        ok, msg = self._validate("x" * 60_000)
        assert not ok
        assert "too long" in msg.lower() or "50000" in msg

    def test_forbidden_subprocess(self):
        ok, msg = self._validate("import subprocess; subprocess.run('ls')")
        assert not ok
        assert "subprocess" in msg.lower()

    def test_forbidden_os_system(self):
        ok, msg = self._validate("os.system('rm -rf /')")
        assert not ok

    def test_forbidden_socket(self):
        ok, msg = self._validate("import socket; socket.connect()")
        assert not ok
        assert "socket" in msg.lower()

    def test_forbidden_requests(self):
        ok, msg = self._validate("import requests; requests.get('http://evil.com')")
        assert not ok

    def test_network_allowed_bypasses(self):
        """When enable_network=True, network-related patterns are not blocked."""
        ok, msg = self._validate("import requests; requests.get('http://ok.com')", enable_network=True)
        assert ok

    def test_subprocess_still_blocked_with_network(self):
        """Subprocess should be blocked even with network enabled."""
        ok, msg = self._validate("import subprocess", enable_network=True)
        assert not ok


class TestSandboxLanguageEnum:
    def test_valid_languages(self):
        from app.core.sandbox import SandboxLanguage
        assert SandboxLanguage.PYTHON3.value == "python3"
        assert SandboxLanguage.JAVASCRIPT.value == "javascript"
        assert SandboxLanguage.BASH.value == "bash"

    def test_from_string(self):
        from app.core.sandbox import SandboxLanguage
        assert SandboxLanguage("python3") == SandboxLanguage.PYTHON3
        assert SandboxLanguage("javascript") == SandboxLanguage.JAVASCRIPT

    def test_invalid_language(self):
        from app.core.sandbox import SandboxLanguage
        with pytest.raises(ValueError):
            SandboxLanguage("rust")


class TestExecutionResult:
    def test_success(self):
        from app.core.sandbox import ExecutionResult
        r = ExecutionResult(success=True, stdout="hello", exit_code=0)
        assert not r.is_timeout
        assert not r.is_syntax_error

    def test_timeout_detection(self):
        from app.core.sandbox import ExecutionResult
        r = ExecutionResult(success=False, error="Execution timed out after 30s")
        assert r.is_timeout

    def test_syntax_error_detection(self):
        from app.core.sandbox import ExecutionResult
        r = ExecutionResult(success=False, stderr="  File '<string>', line 1\n    print(\n         ^\nSyntaxError: unexpected EOF")
        assert r.is_syntax_error


# ---------------------------------------------------------------------------
#  Tool registration tests
# ---------------------------------------------------------------------------

_app_imports = False
try:
    from app.agent.tools import (
        ALL_TOOLS,
        TOOL_GROUPS,
        run_python_code,
        run_javascript_code,
        run_shell_command,
        install_python_packages,
        get_relevant_tools,
    )
    _app_imports = True
except ImportError:
    pass


@pytest.mark.skipif(not _app_imports, reason="App deps not available")
class TestNewSandboxTools:
    """Verify the new sandbox tools are properly registered."""

    def test_new_tools_in_all_tools(self):
        assert "run_javascript_code" in ALL_TOOLS
        assert "run_shell_command" in ALL_TOOLS
        assert "install_python_packages" in ALL_TOOLS

    def test_new_tools_in_code_exec_group(self):
        code_exec_tools = TOOL_GROUPS["code_exec"]["tools"]
        assert "run_python_code" in code_exec_tools
        assert "run_javascript_code" in code_exec_tools
        assert "run_shell_command" in code_exec_tools
        assert "install_python_packages" in code_exec_tools

    def test_all_tools_in_groups(self):
        """Verify every tool in ALL_TOOLS belongs to at least one group."""
        grouped = set()
        for group in TOOL_GROUPS.values():
            grouped.update(group["tools"])
        missing = set(ALL_TOOLS.keys()) - grouped
        assert not missing, f"Tools not in any group: {missing}"

    def test_code_exec_routing(self):
        """Queries about code execution should route to code_exec group."""
        queries = [
            "帮我写个Python脚本画个柱状图",
            "运行一段JS代码计算斐波那契",
            "安装pandas库",
            "用shell命令查看文件列表",
        ]
        for q in queries:
            tools, groups = get_relevant_tools(
                q,
                list(ALL_TOOLS.keys()),
                min_tools=6,
            )
            tool_names = {t.name for t in tools}
            assert "run_python_code" in tool_names, f"Query '{q}' should include code_exec tools"


# ---------------------------------------------------------------------------
#  Integration tests — require a running sandbox
# ---------------------------------------------------------------------------

_sandbox_available = False
try:
    import asyncio
    from app.core.sandbox import get_sandbox_client, SandboxClient

    async def _check_sandbox():
        client = get_sandbox_client()
        health = await client.health()
        return health.reachable

    try:
        _sandbox_available = asyncio.run(_check_sandbox())
    except Exception:
        _sandbox_available = False
except Exception:
    _sandbox_available = False


@pytest.mark.skipif(not _sandbox_available, reason="DifySandbox not reachable")
@pytest.mark.asyncio
class TestSandboxClientIntegration:
    """Integration tests against a running DifySandbox container."""

    async def test_health_check(self):
        client = get_sandbox_client()
        health = await client.health()
        assert health.reachable
        assert health.latency_ms > 0
        assert health.latency_ms < 5000  # Should respond quickly

    async def test_python_hello_world(self):
        client = get_sandbox_client()
        result = await client.run_code("print('hello, sandbox!')")
        assert result.success
        assert "hello, sandbox" in result.stdout
        assert result.exit_code == 0
        assert result.elapsed_ms > 0

    async def test_python_arithmetic(self):
        client = get_sandbox_client()
        result = await client.run_code("x = 2 ** 10\nprint(f'2^10 = {x}')")
        assert result.success
        assert "2^10 = 1024" in result.stdout

    async def test_python_syntax_error(self):
        client = get_sandbox_client()
        result = await client.run_code("print('hello'  # missing paren")
        assert not result.success
        assert result.exit_code != 0

    async def test_python_runtime_error(self):
        client = get_sandbox_client()
        result = await client.run_code("x = 1 / 0")
        assert not result.success
        assert "ZeroDivisionError" in result.error or "ZeroDivisionError" in result.stderr

    async def test_python_no_output(self):
        client = get_sandbox_client()
        result = await client.run_code("x = 42  # no print")
        assert result.success
        assert result.stdout.strip() == ""
        assert result.exit_code == 0

    async def test_list_dependencies(self):
        client = get_sandbox_client()
        deps = await client.list_dependencies()
        assert deps.count >= 0  # May be 0 on fresh sandbox

    async def test_list_files_empty(self):
        client = get_sandbox_client()
        files = await client.list_files()
        assert isinstance(files, list)
