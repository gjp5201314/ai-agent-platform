"""
DifySandbox async client — secure code execution sandbox.

Provides a typed, retry-capable async HTTP client for:
  - Code execution  (Python 3, JavaScript/Node.js, Bash)
  - Dependency management (pip install, listing)
  - File upload/download
  - Health monitoring
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx

from app.config import settings
from app.core.logger import logger


# ---------------------------------------------------------------------------
#  Data models
# ---------------------------------------------------------------------------

class SandboxLanguage(str, Enum):
    PYTHON3 = "python3"
    JAVASCRIPT = "javascript"   # Node.js, if supported by sandbox image
    BASH = "bash"               # shell, if supported


@dataclass
class ExecutionResult:
    """Result from a sandbox code execution."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    exit_code: int = -1
    elapsed_ms: float = 0.0

    @property
    def is_timeout(self) -> bool:
        err = self.error.lower()
        return "timeout" in err or "timed out" in err

    @property
    def is_syntax_error(self) -> bool:
        err = (self.error + self.stderr).lower()
        return "syntaxerror" in err or "syntax error" in err


@dataclass
class SandboxHealth:
    """Sandbox service health status."""
    reachable: bool
    latency_ms: float = 0.0
    error: str = ""


@dataclass
class DependenciesInfo:
    """Installed packages in sandbox."""
    packages: list[str] = field(default_factory=list)
    count: int = 0


# ---------------------------------------------------------------------------
#  Async HTTP client
# ---------------------------------------------------------------------------

class SandboxClient:
    """
    Async client for DifySandbox.

    Features:
      - Connection pooling (httpx shared client)
      - Automatic retry on transient errors (3 attempts, exponential backoff)
      - Configurable per-call timeout
      - Structured typed responses
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self.base_url = (base_url or settings.difysandbox_url).rstrip("/")
        self.api_key = api_key or settings.difysandbox_api_key
        self.timeout = timeout
        self.max_retries = max_retries

        self._headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

        # Lazy client — created on first use to avoid event-loop issues
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared httpx client (connection pooling)."""
        if self._client is None:
            limits = httpx.Limits(
                max_keepalive_connections=5,
                max_connections=10,
                keepalive_expiry=30.0,
            )
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers,
                timeout=httpx.Timeout(self.timeout),
                limits=limits,
            )
        return self._client

    async def close(self):
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ---- Retry helper ----

    async def _request_with_retry(
        self, method: str, path: str, **kwargs,
    ) -> httpx.Response:
        """Execute an HTTP request with exponential backoff retry."""
        last_exc: Exception | None = None
        delays = [0.2, 0.6, 1.8]  # seconds

        for attempt in range(self.max_retries):
            try:
                client = await self._get_client()
                resp = await client.request(method, path, **kwargs)
                return resp
            except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError) as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    delay = delays[min(attempt, len(delays) - 1)]
                    logger.debug(f"Sandbox retry {attempt + 1}/{self.max_retries} after {delay}s: {exc}")
                    await asyncio.sleep(delay)

        raise last_exc  # type: ignore[misc]

    # ===================================================================
    #  Public API
    # ===================================================================

    # ---- Health ----

    async def health(self) -> SandboxHealth:
        """Check sandbox service health."""
        t0 = time.monotonic()
        try:
            resp = await self._request_with_retry("GET", "/health")
            latency = (time.monotonic() - t0) * 1000
            return SandboxHealth(
                reachable=resp.status_code == 200,
                latency_ms=round(latency, 1),
            )
        except Exception as exc:
            latency = (time.monotonic() - t0) * 1000
            return SandboxHealth(
                reachable=False,
                latency_ms=round(latency, 1),
                error=str(exc)[:200],
            )

    # ---- Code execution ----

    async def run_code(
        self,
        code: str,
        language: SandboxLanguage = SandboxLanguage.PYTHON3,
        enable_network: bool = False,
        timeout: float | None = None,
    ) -> ExecutionResult:
        """
        Execute code in the sandbox.

        Args:
            code: Source code string.
            language: python3, javascript, or bash.
            enable_network: Allow network access (default False for security).
            timeout: Per-call timeout in seconds (overrides client default).

        Returns:
            ExecutionResult with stdout, stderr, exit_code, elapsed_ms.
        """
        t0 = time.monotonic()

        payload = {
            "language": language.value,
            "code": code,
            "enable_network": enable_network,
        }

        request_kwargs = {"json": payload}
        if timeout is not None:
            request_kwargs["timeout"] = httpx.Timeout(timeout)

        try:
            resp = await self._request_with_retry("POST", "/v1/sandbox/run", **request_kwargs)
            data = resp.json()
        except httpx.TimeoutException:
            elapsed = (time.monotonic() - t0) * 1000
            return ExecutionResult(
                success=False,
                error=f"Sandbox execution timed out after {timeout or self.timeout}s",
                elapsed_ms=elapsed,
            )
        except httpx.ConnectError:
            elapsed = (time.monotonic() - t0) * 1000
            return ExecutionResult(
                success=False,
                error="Sandbox service unreachable — is the container running?",
                elapsed_ms=elapsed,
            )

        elapsed = round((time.monotonic() - t0) * 1000, 1)
        api_code = data.get("code", -1)
        inner = data.get("data", {})

        if api_code != 0:
            return ExecutionResult(
                success=False,
                error=data.get("message", "Unknown sandbox API error"),
                elapsed_ms=elapsed,
            )

        exit_code = inner.get("exit_code", -1)
        return ExecutionResult(
            success=(exit_code == 0),
            stdout=inner.get("stdout", ""),
            stderr=inner.get("stderr", ""),
            error=inner.get("error", ""),
            exit_code=exit_code,
            elapsed_ms=elapsed,
        )

    # ---- Dependencies ----

    async def list_dependencies(self) -> DependenciesInfo:
        """List installed Python packages in the sandbox."""
        try:
            resp = await self._request_with_retry("GET", "/v1/sandbox/dependencies")
            data = resp.json()
            if data.get("code") != 0:
                return DependenciesInfo()
            pkgs = data.get("data", {}).get("dependencies", [])
            return DependenciesInfo(packages=pkgs, count=len(pkgs))
        except Exception as exc:
            logger.warning(f"Failed to list sandbox dependencies: {exc}")
            return DependenciesInfo()

    async def install_dependencies(self, packages: list[str]) -> str:
        """
        Install Python packages via pip in the sandbox.

        Args:
            packages: List of package names (e.g. ["numpy", "pandas==2.0"]).

        Returns:
            Installation result message.
        """
        try:
            resp = await self._request_with_retry(
                "POST",
                "/v1/sandbox/dependencies",
                json={"dependencies": " ".join(packages)},
                timeout=httpx.Timeout(120.0),  # pip install can be slow
            )
            data = resp.json()
            if data.get("code") != 0:
                return f"Dependency installation failed: {data.get('message', 'unknown')}"
            return f"Successfully installed: {', '.join(packages)}"
        except httpx.TimeoutException:
            return "Dependency installation timed out (2 minutes). Try installing fewer packages."
        except Exception as exc:
            return f"Dependency installation failed: {str(exc)[:300]}"

    # ---- File operations ----

    async def upload_file(self, filename: str, content: bytes | str) -> str:
        """
        Upload a file to the sandbox's working directory.

        Args:
            filename: Target filename in sandbox.
            content: File content as bytes or str.

        Returns:
            Success message or error.
        """
        try:
            if isinstance(content, str):
                content = content.encode("utf-8")

            files = {"file": (filename, io.BytesIO(content))}
            # For multipart upload, use a separate client without JSON content-type
            client = await self._get_client()
            resp = await client.post(
                "/v1/sandbox/files",
                files=files,
                timeout=httpx.Timeout(30.0),
            )
            data = resp.json()
            if data.get("code") != 0:
                return f"File upload failed: {data.get('message', 'unknown')}"
            return f"File '{filename}' uploaded successfully."
        except Exception as exc:
            return f"File upload failed: {str(exc)[:300]}"

    async def list_files(self) -> list[str]:
        """List files in the sandbox working directory."""
        try:
            resp = await self._request_with_retry("GET", "/v1/sandbox/files")
            data = resp.json()
            if data.get("code") != 0:
                return []
            return list(data.get("data", {}).get("files", []))
        except Exception as exc:
            logger.warning(f"Failed to list sandbox files: {exc}")
            return []

    # ---- Convenience: prepare sandbox for data analysis ----

    async def ensure_data_science_packages(self) -> str:
        """
        Ensure common data science packages are available in the sandbox.
        Installs: numpy, pandas, matplotlib (if not already present).

        Returns:
            Status message.
        """
        deps = await self.list_dependencies()
        installed = {p.split("==")[0].lower() for p in deps.packages}

        needed = ["numpy", "pandas", "matplotlib"]
        missing = [p for p in needed if p not in installed]

        if not missing:
            return "All data science packages are already installed."

        return await self.install_dependencies(missing)

    # ---- Convenience: execute Python code block with result formatting ----

    async def run_python_formatted(self, code: str) -> str:
        """
        Execute Python code and return a human-readable result string.
        Used directly as tool output for the LLM.
        """
        result = await self.run_code(code)

        if not result.success and not result.stdout and not result.stderr:
            return f"Sandbox execution failed: {result.error}"

        parts = []
        if result.stdout.strip():
            parts.append(f"[stdout]\n{result.stdout.strip()}")
        if result.stderr.strip():
            parts.append(f"[stderr]\n{result.stderr.strip()}")
        if result.error and not result.success:
            parts.append(f"[error] exit_code={result.exit_code}\n{result.error.strip()}")

        if not parts:
            return "(no output)"

        footer = f"\n\n[Execution: {result.elapsed_ms:.0f}ms, exit_code={result.exit_code}]"
        return "\n\n".join(parts) + footer


# ---------------------------------------------------------------------------
#  Singleton factory (module-level)
# ---------------------------------------------------------------------------

_sandbox_client: Optional[SandboxClient] = None


def get_sandbox_client() -> SandboxClient:
    """Get or create the module-level SandboxClient singleton."""
    global _sandbox_client
    if _sandbox_client is None:
        _sandbox_client = SandboxClient()
    return _sandbox_client


async def close_sandbox_client():
    """Close the singleton sandbox client (call on app shutdown)."""
    global _sandbox_client
    if _sandbox_client is not None:
        await _sandbox_client.close()
        _sandbox_client = None


# ---------------------------------------------------------------------------
#  Code validation helpers
# ---------------------------------------------------------------------------

# Minimal blacklist for obvious dangerous patterns (defense-in-depth;
# the real isolation is provided by the container).
# Patterns ALWAYS blocked (subprocess/process manipulation).
_ALWAYS_FORBIDDEN = [
    "subprocess",
    "multiprocessing",
    "os.system(",
    "os.popen(",
    "shutil.rmtree",
]

# Patterns blocked only when network is disabled.
_NETWORK_FORBIDDEN = [
    "socket.",
    "requests.",
    "urllib.request",
    "http.client",
    "ftplib",
]


def validate_sandbox_code(code: str, enable_network: bool = False) -> tuple[bool, str]:
    """
    Pre-flight code validation (defense-in-depth).

    The container itself provides isolation, but we add a lightweight
    pre-check to catch the most obvious dangerous patterns early.

    Returns:
        (is_safe, error_message)
    """
    if not code or not code.strip():
        return False, "Code cannot be empty."

    if len(code) > 50_000:
        return False, f"Code too long ({len(code)} chars). Maximum 50,000 characters."

    code_lower = code.lower()

    # Always-blocked patterns (subprocess, os.system, etc.)
    for pattern in _ALWAYS_FORBIDDEN:
        if pattern in code_lower:
            return False, (
                f"Forbidden pattern detected: '{pattern}'. "
                f"Subprocess and system operations are always blocked."
            )

    # Network-blocked patterns (only when network is disabled)
    if not enable_network:
        for pattern in _NETWORK_FORBIDDEN:
            if pattern in code_lower:
                return False, (
                    f"Forbidden pattern detected: '{pattern}'. "
                    f"Network operations are disabled in sandbox mode."
                )

    return True, ""
