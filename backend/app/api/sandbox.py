"""
沙盒管理 API — 健康检查、代码执行、依赖管理、文件操作。

================================================================================
【前端开发者必读】什么是"沙盒"（Sandbox）？
================================================================================

沙盒（Sandbox）是一个**与宿主机完全隔离的执行环境**，通常以 Docker 容器的形式运行。
在这个项目中，沙盒用于安全地执行用户/AI 生成的代码。

为什么需要沙盒？
  1. 安全隔离：用户可能提交恶意代码（如 `rm -rf /`、`os.system(...)`），
     沙盒确保这些代码即使执行，也只会影响容器内部，不会破坏宿主机或数据库。
  2. 资源限制：沙盒可以限制 CPU、内存和执行时间，防止死循环或资源耗尽。
  3. 依赖隔离：每个沙盒实例有自己独立的 Python 环境，pip install 不会影响宿主机。
  4. 多语言支持：同一套沙盒可以运行 Python、JavaScript、Shell 等不同语言。

本项目的沙盒技术栈：
  - DifySandbox（https://github.com/langgenius/dify-sandbox）：开源代码执行沙盒
  - 通过 HTTP API 与沙盒容器通信
  - 内层由 Docker 容器提供真正的进程隔离

本文件定义了前端可以调用的所有沙盒相关 REST API 端点：
  POST /sandbox/health          — 检查沙盒服务是否正常运行
  POST /sandbox/run             — 在沙盒中执行代码（核心功能）
  POST /sandbox/dependencies/list   — 列出沙盒中已安装的 Python 包
  POST /sandbox/dependencies/install — 在沙盒中安装新的 Python 包
  POST /sandbox/dependencies/ensure-datascience — 确保数据科学包已安装
  POST /sandbox/files/list      — 列出沙盒工作目录中的文件
  POST /sandbox/files/upload    — 上传文件到沙盒工作目录
  POST /sandbox/stats           — 获取沙盒综合状态摘要

注意：所有端点都使用 POST 方法（包括只读操作），请求体为 JSON 格式。
这与其他 RESTful 惯例（GET 读/POST 写）不同，是为了 API 设计的一致性。
================================================================================
"""
from fastapi import APIRouter, HTTPException, UploadFile, File

from app.core.sandbox import (
    ExecutionResult,
    SandboxHealth,
    SandboxLanguage,
    get_sandbox_client,
    validate_sandbox_code,
)
from app.core.logger import logger

# 创建沙盒 API 的路由器实例
# 所有路由前缀为 /sandbox（在 main.py 中注册）
router = APIRouter()


# ==============================================================================
# 端点 1: 健康检查 — POST /sandbox/health
# ==============================================================================
# 【前端说明】
# 用途：检查 DifySandbox 服务是否可达且健康。
# 前端可以在应用启动时或"沙盒设置"页面调用此端点，
# 以确认沙盒容器正在运行，并在沙盒不可用时显示警告。
#
# 请求体：空 JSON {} 或不传
#
# 响应格式示例：
# {
#   "status": "ok",           // "ok" = 正常, "unreachable" = 无法连接
#   "reachable": true,        // 布尔值，沙盒是否可达
#   "latency_ms": 12.5,       // 延迟毫秒数，用于前端显示性能指标
#   "error": null             // 如果不可达，这里会包含错误信息字符串
# }

@router.post("/health")
async def sandbox_health() -> dict:
    """Check if the DifySandbox service is reachable and healthy."""
    client = get_sandbox_client()
    health: SandboxHealth = await client.health()

    return {
        "status": "ok" if health.reachable else "unreachable",
        "reachable": health.reachable,
        "latency_ms": health.latency_ms,
        "error": health.error if not health.reachable else None,
    }


# ==============================================================================
# 端点 2: 代码执行（核心功能）— POST /sandbox/run
# ==============================================================================
# 【前端说明】
# 这是沙盒最核心的端点，前端 AI 对话中用户说"帮我运行这段 Python 代码"时调用。
#
# 支持的语言（language 参数）：
#   - "python3"（默认）：Python 3 代码
#   - "javascript"：Node.js JavaScript 代码
#   - "bash"：Shell/Bash 脚本
#
# enable_network 参数：
#   - false（默认）：禁止代码访问网络（socket、requests、urllib 等）
#   - true：允许网络访问（仅受信场景使用）
#
# 请求体格式（JSON）：
# {
#   "code": "print('Hello, World!')",   // 必填：要执行的源代码字符串
#   "language": "python3",              // 可选，默认 "python3"
#   "enable_network": false             // 可选，默认 false
# }
#
# 响应格式示例（成功）：
# {
#   "success": true,
#   "stdout": "Hello, World!\n",        // 标准输出内容
#   "stderr": "",                        // 标准错误输出（通常为空）
#   "error": "",                         // 执行错误信息（成功时为空）
#   "exit_code": 0,                     // 退出码，0 表示成功
#   "elapsed_ms": 45.2                  // 执行耗时（毫秒）
# }
#
# 响应格式示例（代码错误）：
# {
#   "success": false,
#   "stdout": "",
#   "stderr": "Traceback (most recent call last):\n...",
#   "error": "NameError: name 'x' is not defined",
#   "exit_code": 1,                     // 非零表示执行失败
#   "elapsed_ms": 32.1
# }
#
# 安全检查说明：
#   代码在发送到沙盒之前会经过预检验证（validate_sandbox_code），
#   阻止以下危险操作：
#     - 始终阻止：subprocess、multiprocessing、os.system()、os.popen()、shutil.rmtree
#     - 网络禁用时阻止：socket、requests、urllib.request、http.client、ftplib
#   如果预检失败，直接返回 400 错误，不会发送到沙盒。

@router.post("/run")
async def sandbox_run(body: dict) -> dict:
    """
    Execute code in the sandbox.

    Request body:
      - code: str (required) — source code to execute
      - language: str (optional, default "python3") — python3 | javascript | bash
      - enable_network: bool (optional, default false)

    Returns:
      - success, stdout, stderr, error, exit_code, elapsed_ms
    """
    # 从请求体中提取参数
    code = body.get("code", "")
    language_str = body.get("language", "python3")
    enable_network = body.get("enable_network", False)

    # Validate language
    try:
        language = SandboxLanguage(language_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language: '{language_str}'. Supported: python3, javascript, bash",
        )

    # 代码预检验证（防御性安全检查）
    # 在将代码发送到沙盒之前，先在 Python 层面做一次轻量级的安全检查
    # 这不会替代容器的隔离，而是作为额外的防护层
    is_safe, err_msg = validate_sandbox_code(code, enable_network=enable_network)
    if not is_safe:
        raise HTTPException(status_code=400, detail=err_msg)

    client = get_sandbox_client()
    # 将代码发送到 DifySandbox 容器中执行
    result: ExecutionResult = await client.run_code(
        code=code,
        language=language,
        enable_network=enable_network,
    )

    return {
        "success": result.success,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "error": result.error,
        "exit_code": result.exit_code,
        "elapsed_ms": result.elapsed_ms,
    }


# ==============================================================================
# 端点 3a: 列出已安装的依赖 — POST /sandbox/dependencies/list
# ==============================================================================
# 【前端说明】
# 用途：查询沙盒中当前安装的所有 Python 包及版本。
# 前端可以在"沙盒环境"面板中展示，让用户了解哪些库可用。
#
# 响应格式示例：
# {
#   "packages": ["numpy==1.26.0", "pandas==2.1.0", "matplotlib==3.8.0", ...],
#   "count": 3
# }

@router.post("/dependencies/list")
async def list_dependencies() -> dict:
    """List installed Python packages in the sandbox."""
    client = get_sandbox_client()
    deps = await client.list_dependencies()
    return {
        "packages": deps.packages,
        "count": deps.count,
    }


# ==============================================================================
# 端点 3b: 安装依赖 — POST /sandbox/dependencies/install
# ==============================================================================
# 【前端说明】
# 用途：在沙盒中安装新的 Python 包（通过 pip install）。
# 前端可以在"沙盒环境"面板提供包安装输入框。
#
# 请求体格式（JSON）：
# {
#   "packages": ["numpy", "pandas==2.0"]   // 必填：要安装的包名列表，支持版本约束
# }
#
# 包名校验规则：
#   - 只允许字母、数字、连字符、下划线、点号、版本约束字符
#   - 这是为了防止命令注入攻击
#
# 响应格式示例：
# {
#   "message": "Successfully installed: numpy, pandas==2.0",
#   "requested": ["numpy", "pandas==2.0"]
# }
#
# 超时说明：安装操作超时时间为 120 秒（2 分钟），
# 因为 pip install 可能需要下载大包或编译 C 扩展。

@router.post("/dependencies/install")
async def install_dependencies(body: dict) -> dict:
    """
    Install Python packages in the sandbox.

    Request body:
      - packages: list[str] (required) — package names, e.g. ["numpy", "pandas==2.0"]
    """
    packages = body.get("packages", [])
    if not packages or not isinstance(packages, list):
        raise HTTPException(status_code=400, detail="'packages' must be a non-empty list of package names.")

    # 输入安全校验：使用正则表达式过滤包名，防止命令注入
    # 允许的字符：字母、数字、-、_、.、[]、版本约束符号（<>、=、!、~、;、,）
    # 这确保了 package 参数不会被用来注入额外的 shell 命令
    import re
    for pkg in packages:
        if not re.match(r'^[a-zA-Z0-9\-_\.\[\]<>=!~;,\s]+$', pkg):
            raise HTTPException(status_code=400, detail=f"Invalid package name: '{pkg}'")

    client = get_sandbox_client()
    result_msg = await client.install_dependencies(packages)

    return {
        "message": result_msg,
        "requested": packages,
    }


# ==============================================================================
# 端点 3c: 确保数据科学包已安装 — POST /sandbox/dependencies/ensure-datascience
# ==============================================================================
# 【前端说明】
# 用途：确保沙盒中安装了常用的数据科学三大件：numpy、pandas、matplotlib。
# 这是一个便捷端点，前端可以在用户首次使用数据分析功能时调用，
# 也可以作为"一键安装数据科学环境"的按钮。
# 如果已安装则跳过，只安装缺失的包。

@router.post("/dependencies/ensure-datascience")
async def ensure_data_science() -> dict:
    """Install common data science packages (numpy, pandas, matplotlib) if missing."""
    client = get_sandbox_client()
    result = await client.ensure_data_science_packages()
    return {"message": result}


# ==============================================================================
# 端点 4a: 列出文件 — POST /sandbox/files/list
# ==============================================================================
# 【前端说明】
# 用途：查看沙盒工作目录中有哪些文件。
# 前端可以在"沙盒文件管理"面板中展示文件列表。
#
# 响应格式示例：
# {
#   "files": ["data.csv", "output.png", "script.py"],
#   "count": 3
# }

@router.post("/files/list")
async def list_files() -> dict:
    """List files in the sandbox working directory."""
    client = get_sandbox_client()
    files = await client.list_files()
    return {"files": files, "count": len(files)}


# ==============================================================================
# 端点 4b: 上传文件 — POST /sandbox/files/upload
# ==============================================================================
# 【前端说明】
# 用途：上传文件到沙盒工作目录，以便代码可以读取和处理。
# 这是让用户数据进入沙盒的唯一入口。
#
# 前端调用方式：
#   使用 multipart/form-data 格式，字段名为 "file"
#
# 示例（JavaScript fetch API）：
#   const formData = new FormData();
#   formData.append("file", fileInput.files[0]);
#   fetch("/sandbox/files/upload", { method: "POST", body: formData });
#
# 限制：
#   - 文件大小上限：10 MB（超过返回 413 错误）
#   - 必须提供文件名（否则返回 400 错误）
#
# 响应格式示例：
# {
#   "filename": "data.csv",
#   "size_bytes": 1024,
#   "message": "File 'data.csv' uploaded successfully."
# }

@router.post("/files/upload")
async def upload_file(file: UploadFile = File(...)) -> dict:
    """
    Upload a file to the sandbox.

    Multipart form: file field with the file to upload.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a name.")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB limit — 前端上传文件前应自行校验大小
        raise HTTPException(status_code=413, detail="File too large. Maximum 10 MB.")

    client = get_sandbox_client()

    # First upload to sandbox via the client's internal mechanism
    result = await client.upload_file(file.filename, content)

    return {
        "filename": file.filename,
        "size_bytes": len(content),
        "message": result,
    }


# ==============================================================================
# 端点 5: 综合状态摘要 — POST /sandbox/stats
# ==============================================================================
# 【前端说明】
# 用途：一次性获取沙盒的完整状态，包括健康状态、已安装包列表、文件列表。
# 这是一个组合端点，避免了前端需要依次调用多个端点的麻烦。
# 适合用于"沙盒仪表盘"页面或定期轮询状态更新。
#
# 注意：依赖列表和文件列表只返回前 20 项，避免响应体过大。
#
# 响应格式示例：
# {
#   "health": {
#     "reachable": true,
#     "latency_ms": 12.5
#   },
#   "dependencies": {
#     "count": 45,
#     "packages": ["numpy==1.26.0", "pandas==2.1.0", ...]  // 前 20 个
#   },
#   "files": {
#     "count": 5,
#     "names": ["data.csv", "output.png", ...]  // 前 20 个
#   }
# }

@router.post("/stats")
async def sandbox_stats() -> dict:
    """
    Get a comprehensive sandbox status summary.
    Combines health, dependencies, and files.
    """
    client = get_sandbox_client()

    health = await client.health()
    deps = await client.list_dependencies()
    files = await client.list_files()

    return {
        "health": {
            "reachable": health.reachable,
            "latency_ms": health.latency_ms,
        },
        "dependencies": {
            "count": deps.count,
            "packages": deps.packages[:20],  # 只返回前 20 项，避免 JSON 过大
        },
        "files": {
            "count": len(files),
            "names": files[:20],  # 只返回前 20 项
        },
    }
