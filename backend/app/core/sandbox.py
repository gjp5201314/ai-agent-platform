"""
================================================================================
DifySandbox 异步客户端 — 安全代码执行沙盒的 Python SDK
================================================================================

【前端开发者必读】理解 DifySandbox 集成

1. DifySandbox 是什么？

   DifySandbox（https://github.com/langgenius/dify-sandbox）是 Dify 团队
   开发的开源代码执行沙盒。它以 Docker 容器的形式运行，提供：
     - 多语言代码执行（Python 3、JavaScript/Node.js、Bash）
     - Docker 容器级别的进程隔离（真正的安全隔离）
     - HTTP API 接口（RESTful，通过 JSON 交互）
     - 支持 pip 包管理和文件上传

2. 本文件的角色

   本文件是 DifySandbox HTTP API 的 Python 异步客户端封装。
   它不直接执行代码，而是：
     ① 将代码和参数序列化为 JSON
     ② 通过 HTTP 发送到 DifySandbox 容器
     ③ 接收执行结果并反序列化为类型安全的 Python 数据类

   你可以把它理解为"DifySandbox 的 Python SDK"。

3. 整体架构

   ┌──────────────┐    HTTP POST /v1/sandbox/run    ┌──────────────────┐
   │ FastAPI 后端  │ ──────────────────────────────→ │ DifySandbox      │
   │ (app/api/    │ ←────────────────────────────── │ Docker 容器      │
   │  sandbox.py) │    JSON Response                 │ (端口 8194)      │
   └──────────────┘                                  └──────────────────┘
         │                                                      │
         │  调用 SandboxClient.run_code()                       │
         │  本文件定义的异步 HTTP 客户端                         │
         │                                                      ▼
         │                                           ┌──────────────────┐
         │                                           │ Docker 容器内     │
         │                                           │  - Python 3.11   │
         │                                           │  - Node.js 20    │
         │                                           │  - pip 包管理    │
         │                                           │  - 文件系统隔离   │
         │                                           └──────────────────┘

================================================================================
代码执行流程（端到端）
================================================================================

以下是用户点击"运行代码"按钮后的完整数据流：

 步骤1: 前端 POST /sandbox/run
        → { "code": "print(1+1)", "language": "python3" }

 步骤2: FastAPI 路由 (api/sandbox.py)
        → validate_sandbox_code(code)    # 预检：检查危险模式
        → SandboxClient.run_code(code)   # 调用本文件的客户端

 步骤3: 本文件 (core/sandbox.py)
        → 构造 HTTP 请求 {"language":"python3","code":"print(1+1)"}
        → POST http://sandbox:8194/v1/sandbox/run
        → 自动重试（最多 3 次，指数退避）
        → 解析响应 JSON

 步骤4: DifySandbox 容器
        → 在容器内创建临时文件 write code to /tmp/xxx.py
        → 执行: timeout 30 python3 /tmp/xxx.py
        → 收集 stdout、stderr、exit_code
        → 返回 JSON: {"code":0, "data":{"stdout":"2\n","stderr":"","exit_code":0}}

 步骤5: 本文件
        → 解析 JSON → ExecutionResult 数据类
        → 返回给路由层

 步骤6: FastAPI 路由
        → 转换为 API 响应 JSON
        → 返回给前端

================================================================================
SandboxResult 数据类说明
================================================================================

  ExecutionResult（代码执行结果）:
    字段:
      success:    bool   — 执行是否成功（exit_code==0 且无异常）
      stdout:     str    — 标准输出内容（程序 print 的内容）
      stderr:     str    — 标准错误输出
      error:      str    — 执行异常信息
      exit_code:  int    — 退出码，0=成功，非零=失败
      elapsed_ms: float  — 执行耗时（毫秒）
    计算属性:
      is_timeout: bool   — 是否因为超时导致失败
      is_syntax_error: bool — 是否是语法错误（而非运行时错误）

  SandboxHealth（沙盒健康状态）:
    reachable:  bool   — 沙盒是否可达
    latency_ms: float  — 响应延迟（毫秒）
    error:      str    — 错误信息（仅在不可达时有值）

  DependenciesInfo（已安装包信息）:
    packages: list[str] — 已安装的包名+版本列表
    count:    int       — 包的数量

================================================================================
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


# ==============================================================================
# 数据模型（类型安全的响应封装）
# ==============================================================================

class SandboxLanguage(str, Enum):
    """
    沙盒支持的编程语言枚举。

    每个值对应 DifySandbox 容器中可用的运行时环境：
      PYTHON3:    Python 3.x 解释器
      JAVASCRIPT: Node.js JavaScript 运行时
      BASH:       Linux Shell (/bin/bash)
    """
    PYTHON3 = "python3"
    JAVASCRIPT = "javascript"   # Node.js, if supported by sandbox image
    BASH = "bash"               # shell, if supported


@dataclass
class ExecutionResult:
    """
    沙盒代码执行结果的数据类。

    这个数据类将 DifySandbox 的 JSON 响应转换为类型安全的 Python 对象，
    方便在代码中使用（IDE 自动补全、类型检查）。

    【前端关联】
    这个数据类的字段直接映射到 POST /sandbox/run 的响应 JSON 字段。
    前端接收到的 JSON 结构：
    {
      "success": true,
      "stdout": "Hello\n",
      "stderr": "",
      "error": "",
      "exit_code": 0,
      "elapsed_ms": 45.2
    }
    """
    success: bool
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    exit_code: int = -1
    elapsed_ms: float = 0.0

    @property
    def is_timeout(self) -> bool:
        """
        判断执行失败是否由超时引起。

        通过检查错误信息中是否包含 "timeout" 关键词来判断。
        前端可以据此显示不同的错误提示：
          - 超时：提示"执行时间过长，请优化代码或增加超时时间"
          - 其他错误：显示具体错误信息
        """
        err = self.error.lower()
        return "timeout" in err or "timed out" in err

    @property
    def is_syntax_error(self) -> bool:
        """
        判断执行失败是否由语法错误引起。

        通过检查错误信息中是否包含 "syntaxerror" 来判断。
        前端可以据此显示不同的 UI：
          - 语法错误：高亮代码中的错误位置
          - 运行时错误：显示错误堆栈
        """
        err = (self.error + self.stderr).lower()
        return "syntaxerror" in err or "syntax error" in err


@dataclass
class SandboxHealth:
    """
    沙盒服务健康状态的数据类。

    用于健康检查端点 POST /sandbox/health。
    """
    reachable: bool
    latency_ms: float = 0.0
    error: str = ""


@dataclass
class DependenciesInfo:
    """
    沙盒中已安装 Python 包信息的数据类。

    用于依赖列表端点 POST /sandbox/dependencies/list。
    """
    packages: list[str] = field(default_factory=list)
    count: int = 0


# ==============================================================================
# 异步 HTTP 客户端（核心）
# ==============================================================================

class SandboxClient:
    """
    DifySandbox 的异步 HTTP 客户端。

    【设计特点】
    1. 连接池复用（httpx 共享客户端）— 减少 TCP 握手开销
    2. 自动重试（最多 3 次，指数退避）— 处理临时网络抖动
    3. 可配置的每次调用超时 — 防止长时间阻塞
    4. 结构化的类型响应 — 返回 Python 数据类而非原始 dict

    【指数退避说明】
    重试间隔为：0.2秒 → 0.6秒 → 1.8秒（非严格指数，是手动配置的序列）
    这样设计是为了在快速失败和等待恢复之间取得平衡。
    只对网络错误重试（ConnectError、RemoteProtocolError、ReadError），
    HTTP 业务错误（4xx/5xx）不重试。
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        # 沙盒 API 的基础 URL（去除末尾斜杠）
        # 默认从配置读取：http://sandbox:8194
        self.base_url = (base_url or settings.difysandbox_url).rstrip("/")

        # 沙盒 API 的认证密钥（通过 X-Api-Key 请求头传递）
        self.api_key = api_key or settings.difysandbox_api_key

        # 默认超时时间（秒）— 可在单次调用时覆盖
        self.timeout = timeout

        # 最大重试次数（仅网络错误）
        self.max_retries = max_retries

        # HTTP 请求头（所有请求共用）
        self._headers = {
            "X-Api-Key": self.api_key,         # DifySandbox 认证方式
            "Content-Type": "application/json", # 大多数请求是 JSON 格式
        }

        # httpx 客户端 — 懒加载创建（避免事件循环问题）
        # 不能在 __init__ 中直接创建，因为此时可能还没有事件循环
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """
        获取或创建共享的 httpx 客户端（连接池复用）。

        【连接池配置说明】
        - max_keepalive_connections=5:  空闲连接保持数（复用最近用过的连接）
        - max_connections=10:           最大总连接数
        - keepalive_expiry=30.0:       空闲连接 30 秒后自动关闭

        这些值适合中等规模使用。如果并发请求很多，可以适当增大。
        """
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
        """
        关闭底层 HTTP 客户端，释放连接资源。

        应在应用关闭时调用（FastAPI lifespan/shutdown 事件）。
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ==========================================================================
    # 重试辅助方法
    # ==========================================================================

    async def _request_with_retry(
        self, method: str, path: str, **kwargs,
    ) -> httpx.Response:
        """
        执行 HTTP 请求，带指数退避重试。

        【重试策略】
        - 最多重试 max_retries 次（默认 3 次）
        - 只对网络错误重试（连接失败、协议错误、读取中断）
        - HTTP 业务错误（如 4xx/5xx）不重试（重试无意义）
        - 重试间隔：0.2s → 0.6s → 1.8s

        参数：
          method: HTTP 方法（GET/POST 等）
          path:   API 路径（如 "/v1/sandbox/run"）
          **kwargs: 传给 httpx.request 的额外参数（如 json=...）
        """
        last_exc: Exception | None = None
        delays = [0.2, 0.6, 1.8]  # 重试间隔（秒）

        for attempt in range(self.max_retries):
            try:
                client = await self._get_client()
                resp = await client.request(method, path, **kwargs)
                return resp
            except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError) as exc:
                # 这些是网络级别的临时错误，值得重试
                last_exc = exc
                if attempt < self.max_retries - 1:
                    delay = delays[min(attempt, len(delays) - 1)]
                    logger.debug(f"Sandbox retry {attempt + 1}/{self.max_retries} after {delay}s: {exc}")
                    await asyncio.sleep(delay)

        # 所有重试都失败了，抛出最后一个异常
        raise last_exc  # type: ignore[misc]

    # ===================================================================
    #  公共 API（外部调用的方法）
    # ===================================================================

    # ==========================================================================
    # 健康检查
    # ==========================================================================

    async def health(self) -> SandboxHealth:
        """
        检查沙盒服务健康状况。

        向 DifySandbox 的 /health 端点发送 GET 请求，
        测量往返延迟时间。

        返回 SandboxHealth 数据类，reachable=True 表示正常。
        """
        t0 = time.monotonic()          # 记录开始时间（高精度计时器）
        try:
            resp = await self._request_with_retry("GET", "/health")
            latency = (time.monotonic() - t0) * 1000   # 转为毫秒
            return SandboxHealth(
                reachable=resp.status_code == 200,
                latency_ms=round(latency, 1),
            )
        except Exception as exc:
            latency = (time.monotonic() - t0) * 1000
            return SandboxHealth(
                reachable=False,
                latency_ms=round(latency, 1),
                error=str(exc)[:200],    # 截断错误信息，防止过长日志
            )

    # ==========================================================================
    # 代码执行（核心功能）
    # ==========================================================================

    async def run_code(
        self,
        code: str,
        language: SandboxLanguage = SandboxLanguage.PYTHON3,
        enable_network: bool = False,
        timeout: float | None = None,
    ) -> ExecutionResult:
        """
        在沙盒中执行代码。

        【执行流程】
        1. 记录开始时间（用于计算耗时）
        2. 构造 JSON 请求体 {language, code, enable_network}
        3. POST 到 /v1/sandbox/run
        4. 解析响应 -> ExecutionResult 数据类
        5. 计算并填充 elapsed_ms

        【错误处理】
        - TimeoutException: 代码执行超时 → 返回 success=False
        - ConnectError:     沙盒不可达 → 返回 success=False 并提示检查容器
        - API 返回非零 code: 沙盒内部错误 → 返回 success=False 并包含错误信息

        参数：
          code:           源代码字符串
          language:       编程语言（默认 Python 3）
          enable_network: 是否允许网络访问（默认 false，安全考虑）
          timeout:        本次调用的超时时间（秒），可覆盖默认值

        返回：
          ExecutionResult 数据类对象
        """
        t0 = time.monotonic()

        # 构造发送给 DifySandbox 的 JSON 请求体
        payload = {
            "language": language.value,
            "code": code,
            "enable_network": enable_network,
        }

        request_kwargs = {"json": payload}
        if timeout is not None:
            # 用指定的超时时间覆盖默认值
            request_kwargs["timeout"] = httpx.Timeout(timeout)

        try:
            # 发送请求到 DifySandbox 容器（带自动重试）
            resp = await self._request_with_retry("POST", "/v1/sandbox/run", **request_kwargs)
            data = resp.json()
        except httpx.TimeoutException:
            # 执行超时 — 可能是死循环或计算量过大
            elapsed = (time.monotonic() - t0) * 1000
            return ExecutionResult(
                success=False,
                error=f"Sandbox execution timed out after {timeout or self.timeout}s",
                elapsed_ms=elapsed,
            )
        except httpx.ConnectError:
            # 沙盒容器不可达 — 检查容器是否在运行
            elapsed = (time.monotonic() - t0) * 1000
            return ExecutionResult(
                success=False,
                error="Sandbox service unreachable — is the container running?",
                elapsed_ms=elapsed,
            )

        # 计算总耗时
        elapsed = round((time.monotonic() - t0) * 1000, 1)

        # 解析 DifySandbox 的标准响应格式
        # 外层: {"code": 0, "message": "...", "data": {...}}
        api_code = data.get("code", -1)
        inner = data.get("data", {})

        # API 层面的错误（非零 code）
        if api_code != 0:
            return ExecutionResult(
                success=False,
                error=data.get("message", "Unknown sandbox API error"),
                elapsed_ms=elapsed,
            )

        # 内层数据: {"exit_code": 0, "stdout": "...", "stderr": "..."}
        exit_code = inner.get("exit_code", -1)
        return ExecutionResult(
            success=(exit_code == 0),          # exit_code==0 表示成功
            stdout=inner.get("stdout", ""),
            stderr=inner.get("stderr", ""),
            error=inner.get("error", ""),
            exit_code=exit_code,
            elapsed_ms=elapsed,
        )

    # ==========================================================================
    # 依赖管理（pip 包管理）
    # ==========================================================================

    async def list_dependencies(self) -> DependenciesInfo:
        """
        列出沙盒中已安装的 Python 包。

        调用 DifySandbox 的 GET /v1/sandbox/dependencies 端点。
        返回的包名格式为 "package==version"（如 "numpy==1.26.0"）。
        """
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
        通过 pip 在沙盒中安装 Python 包。

        参数 packages 格式示例：
          ["numpy"]                   — 安装最新版本
          ["pandas==2.0"]             — 指定版本
          ["numpy", "pandas==2.0"]   — 批量安装

        超时时间设置为 120 秒（2 分钟），因为某些包（如 numpy）的安装可能需要较长时间。
        """
        try:
            resp = await self._request_with_retry(
                "POST",
                "/v1/sandbox/dependencies",
                # DifySandbox 期望包名以空格分隔的字符串形式
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

    # ==========================================================================
    # 文件操作
    # ==========================================================================

    async def upload_file(self, filename: str, content: bytes | str) -> str:
        """
        上传文件到沙盒的工作目录。

        文件上传后，沙盒中的代码可以通过相对路径读取该文件。
        例如上传 data.csv → 在 Python 中用 open("data.csv") 读取。

        参数：
          filename: 沙盒中的目标文件名（仅文件名，不含路径）
          content:  文件内容（bytes 或 str，str 会自动编码为 UTF-8）
        """
        try:
            if isinstance(content, str):
                content = content.encode("utf-8")

            # 使用 io.BytesIO 包装字节内容为类文件对象
            files = {"file": (filename, io.BytesIO(content))}
            # 文件上传使用 multipart/form-data，需要单独构造请求
            # 不能复用带 JSON content-type 的 headers
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
        """
        列出沙盒工作目录中的文件。

        返回文件名列表（不含路径），如 ["data.csv", "output.png"]。
        """
        try:
            resp = await self._request_with_retry("GET", "/v1/sandbox/files")
            data = resp.json()
            if data.get("code") != 0:
                return []
            return list(data.get("data", {}).get("files", []))
        except Exception as exc:
            logger.warning(f"Failed to list sandbox files: {exc}")
            return []

    # ==========================================================================
    # 便捷方法
    # ==========================================================================

    async def ensure_data_science_packages(self) -> str:
        """
        确保沙盒中已安装常用的数据科学包。

        检查 numpy、pandas、matplotlib 是否已安装，
        如果缺失则自动安装。安装会花费一些时间（1-2 分钟）。

        这是为了给数据分析场景提供便捷的"一键准备环境"功能。

        返回：状态消息字符串（如"所有数据科学包已安装"）
        """
        # 获取当前已安装的包列表
        deps = await self.list_dependencies()
        # 提取包名（去除版本号），全部转为小写便于比较
        installed = {p.split("==")[0].lower() for p in deps.packages}

        # 需要但可能缺失的包
        needed = ["numpy", "pandas", "matplotlib"]
        missing = [p for p in needed if p not in installed]

        if not missing:
            return "All data science packages are already installed."

        # 安装缺失的包
        return await self.install_dependencies(missing)

    async def run_python_formatted(self, code: str) -> str:
        """
        执行 Python 代码并返回人类可读的结果字符串。

        这个方法将 ExecutionResult 格式化为易于阅读的文本格式，
        直接用作 LLM 工具的返回值（LLM 更容易理解格式化的文本）。

        输出格式示例：
          [stdout]
          Hello, World!

          [Execution: 45ms, exit_code=0]

        参数：
          code: Python 源代码字符串

        返回：格式化的文本字符串
        """
        result = await self.run_code(code)

        # 如果执行完全失败且没有任何输出，返回简洁的错误消息
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

        # 添加执行统计信息作为页脚
        footer = f"\n\n[Execution: {result.elapsed_ms:.0f}ms, exit_code={result.exit_code}]"
        return "\n\n".join(parts) + footer


# ==============================================================================
# 单例工厂（模块级别）
# ==============================================================================
# 为了简化使用，在整个应用中共享一个 SandboxClient 实例。
# 这样可以复用连接池，减少连接创建开销。

# 模块级别的单例变量
_sandbox_client: Optional[SandboxClient] = None


def get_sandbox_client() -> SandboxClient:
    """
    获取或创建模块级别的 SandboxClient 单例。

    首次调用时创建实例，后续调用返回同一个实例。
    这是 GoF 单例模式的 Python 实现。

    使用方式：
      from app.core.sandbox import get_sandbox_client
      client = get_sandbox_client()
      result = await client.run_code("print('hello')")
    """
    global _sandbox_client
    if _sandbox_client is None:
        _sandbox_client = SandboxClient()
    return _sandbox_client


async def close_sandbox_client():
    """
    关闭单例沙盒客户端（在应用关闭时调用）。

    应在 FastAPI 的 lifespan/shutdown 事件中调用，
    确保 HTTP 连接被正确关闭，避免资源泄漏。
    """
    global _sandbox_client
    if _sandbox_client is not None:
        await _sandbox_client.close()
        _sandbox_client = None


# ==============================================================================
# 代码验证辅助函数（防御性安全检查）
# ==============================================================================
# 在代码发送到沙盒容器执行之前，先在 Python 层面做一次轻量级的安全检查。
# 这不是真正的安全隔离（由 Docker 容器提供），而是额外的"防御纵深"策略：
# 在多个层面设置安全防线，即使一层被突破，还有另一层保护。

# 始终禁止的危险模式（涉及进程操作/系统调用）
# 这些模式无论 enable_network 是 true 还是 false 都会被阻止。
# 因为 subprocess/os.system 可以绕过 Docker 的 TCP 网络限制，
# 在容器内启动新进程进行网络通信。
_ALWAYS_FORBIDDEN = [
    "subprocess",       # subprocess.run(), subprocess.Popen() 等
    "multiprocessing",  # 多进程模块
    "os.system(",       # 直接调用系统命令
    "os.popen(",        # 打开管道执行命令
    "shutil.rmtree",    # 递归删除目录 — 破坏性操作
]

# 仅当网络禁用时阻止的模式（网络相关操作）
# 当 enable_network=false 时，阻止这些模式
# 当 enable_network=true 时，允许这些模式
_NETWORK_FORBIDDEN = [
    "socket.",          # 原始 socket 连接
    "requests.",        # requests 库
    "urllib.request",   # Python 标准库 HTTP 客户端
    "http.client",      # Python 标准库 HTTP 客户端
    "ftplib",           # FTP 协议库
]


def validate_sandbox_code(code: str, enable_network: bool = False) -> tuple[bool, str]:
    """
    发送前的代码安全验证（防御纵深策略）。

    Docker 容器本身提供了真正的安全隔离，但我们在代码层面增加
    一个轻量级的预检，以尽早捕获最明显的危险模式。

    检查项目（按顺序）：
      1. 代码不能为空
      2. 代码长度不能超过 50,000 字符
      3. 不能包含始终禁止的危险模式（subprocess、os.system 等）
      4. 如果网络禁用，不能包含网络操作模式（socket、requests 等）

    参数：
      code:           要执行的源代码
      enable_network: 是否允许网络访问

    返回：
      (is_safe, error_message)
        - is_safe=True,  error_message=""     → 安全检查通过
        - is_safe=False, error_message="..."  → 发现危险模式，拒绝执行
    """
    if not code or not code.strip():
        return False, "Code cannot be empty."

    if len(code) > 50_000:
        return False, f"Code too long ({len(code)} chars). Maximum 50,000 characters."

    # 转为小写进行比较（不区分大小写的模式匹配）
    code_lower = code.lower()

    # 检查始终禁止的模式
    for pattern in _ALWAYS_FORBIDDEN:
        if pattern in code_lower:
            return False, (
                f"Forbidden pattern detected: '{pattern}'. "
                f"Subprocess and system operations are always blocked."
            )

    # 检查网络相关模式（仅当网络禁用时）
    if not enable_network:
        for pattern in _NETWORK_FORBIDDEN:
            if pattern in code_lower:
                return False, (
                    f"Forbidden pattern detected: '{pattern}'. "
                    f"Network operations are disabled in sandbox mode."
                )

    return True, ""
