"""
FastAPI 应用入口 - 企业级 AI Agent 平台
========================================

【文件说明】
本文件是后端服务的启动入口，负责：
1. 创建并配置 FastAPI 应用实例
2. 注册中间件栈（安全头、请求大小限制、CORS）
3. 注册所有 API 路由模块
4. 管理应用生命周期（启动时初始化数据库/Redis/默认Agent，关闭时释放连接）
5. 挂载静态文件目录（上传文件访问）

【中间件栈 - 执行顺序（按注册顺序从外到内）】
┌─────────────────────────────────────────────────────┐
│  第1层: security_headers_middleware                  │
│    - 功能: 为每个响应注入安全头、生成请求ID           │
│    - 前端影响: 每个响应Header中会包含以下字段:        │
│      · X-Request-ID: 请求唯一追踪ID（16位hex）       │
│      · X-Content-Type-Options: "nosniff"             │
│      · X-Frame-Options: "DENY"（禁止iframe嵌入）     │
│      · Cache-Control: 强制禁止缓存                    │
│      · 其他安全相关Header                             │
│    - 慢请求告警: >3000ms的请求会记录到日志             │
├─────────────────────────────────────────────────────┤
│  第2层: request_size_guard                           │
│    - 功能: 拒绝超过10MB的POST请求体                   │
│    - 前端影响: 上传文件或提交大数据时需控制请求体大小  │
│    - 超限返回: 413状态码 + {"detail": "请求体过大..."} │
├─────────────────────────────────────────────────────┤
│  第3层: CORSMiddleware（跨域中间件）                  │
│    - 功能: 处理浏览器跨域请求（OPTIONS预检 + 实际请求）│
│    - 允许的来源: 由 settings.cors_origin_list 配置    │
│    - 允许的方法: 仅 POST 和 OPTIONS（安全设计）       │
│    - 允许的请求头: Content-Type, X-Request-ID 等      │
│    - 暴露的响应头: X-Request-ID                       │
│    - 预检缓存: 3600秒（1小时）                        │
│    - 注意事项:                                       │
│      · 前端必须使用 POST 方法调用所有API（包括查询）  │
│      · GET/PUT/DELETE 等方法被CORS拒绝               │
│      · 跨域请求需要携带 credentials 时需设置          │
│        withCredentials: true                         │
└─────────────────────────────────────────────────────┘

【CORS 工作机制（给前端开发者的说明）】
1. 简单请求（无自定义Header）: 浏览器直接发送POST，服务端返回响应
   并附带 Access-Control-Allow-Origin 头，浏览器检查后放行
2. 预检请求（有自定义Header如 X-Request-ID）:
   浏览器先发 OPTIONS 请求问服务端是否允许，服务端返回允许的
   方法/头/来源，浏览器确认后才发送真正的 POST 请求
3. max_age=3600: 预检结果缓存1小时，同一来源在此期间不重复发送 OPTIONS
4. allow_credentials=True: 允许前端携带 Cookie/Authorization 等凭证信息

【已注册的 API 路由】
  /api/v1/                 → health (健康检查)
  /api/v1/chat             → chat (聊天/流式对话)
  /api/v1/rag              → rag (知识库检索增强生成)
  /api/v1/conversations    → conversations (对话管理)
  /api/v1/agents           → agents (Agent 配置管理)
  /api/v1/admin            → admin (管理后台)
  /api/v1/sandbox          → sandbox (代码沙箱)
  /uploads                 → 静态文件 (上传文件访问)

【重要约定 - 前端开发者必读】
- 所有业务API统一使用 POST 方法 + JSON 请求体
- 请在请求头中携带 X-Request-ID 用于问题追踪
- 文件上传接口有 10MB 硬限制
- 响应中所有 Cache-Control 头禁止缓存，前端无需额外处理缓存策略
- API文档地址: 开发环境 /docs，生产环境 /api/docs

安全设计：所有读接口使用POST + JSON请求体
"""
import os
import time
import contextlib
import uuid as _uuid

from fastapi import FastAPI, Request
from app.core.logger import logger
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db
from app.core.redis_client import get_redis, close_redis
from app.core.sandbox import close_sandbox_client

# ---------------------------------------------------------------------------
# LangSmith 追踪环境变量 - 在导入 LangChain 之前设置
# 如果配置中启用了 LangSmith 追踪且提供了 API Key，
# 则在启动时设置环境变量，LangChain 导入时会自动激活追踪功能。
# 前端无需关心此配置，仅用于服务端LLM调用链追踪和调试。
# ---------------------------------------------------------------------------
if settings.langsmith_tracing and settings.langsmith_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project


# ===========================================================================
#  应用生命周期管理
# ===========================================================================
# lifespan 是 FastAPI 的异步上下文管理器，控制应用启动和关闭时的操作。
# 启动阶段（yield 之前）按顺序执行：
#   1. init_db()         → 初始化数据库连接池和表结构
#   2. _seed_default_agent() → 确保默认Agent和数据存在于数据库
#   3. get_redis()       → 建立 Redis 连接（用于会话缓存/消息队列）
#   4. redis.ping()      → 验证 Redis 连接可用
#   5. os.makedirs()     → 创建文件上传目录（如不存在）
# 关闭阶段（yield 之后）按顺序执行：
#   1. close_sandbox_client() → 关闭代码沙箱客户端（释放容器资源）
#   2. close_redis()          → 关闭 Redis 连接
# 前端影响：
#   - 启动阶段完成后所有API才可用
#   - 启动失败（DB/Redis不可达）会阻止应用启动
#   - 关闭阶段仅释放资源，前端无需感知
# ===========================================================================

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动和关闭"""
    # ---- 启动 ----
    await init_db()                    # 初始化数据库
    await _seed_default_agent()        # 创建默认Agent
    redis = await get_redis()          # 连接Redis
    await redis.ping()                 # 测试连接
    os.makedirs(settings.upload_dir, exist_ok=True)  # 创建上传目录
    logger.info(f"数据库初始化完成，Redis已连接。提供商: {settings.llm_provider}")

    yield

    # ---- 关闭 ----
    await close_sandbox_client()       # 关闭沙箱客户端
    await close_redis()                # 关闭Redis连接
    logger.info("连接已关闭。")


app = FastAPI(
    title="AI Agent Platform",
    description="企业级AI Agent平台，支持RAG、工具调用、流式聊天。基于LangGraph + FastAPI + PostgreSQL/pgvector。",
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if not settings.app_debug else "/docs",
    redoc_url=None,  # 生产环境禁用ReDoc
)


# ============================================================
#  中间件栈（顺序重要 - 最外层最先执行）
# ============================================================

# ---------------------------------------------------------------------------
# 中间件1: security_headers_middleware（安全头中间件）- 最外层，最先执行
# ---------------------------------------------------------------------------
# 【给前端的说明】
# 此中间件为每个HTTP响应自动注入以下安全头，前端无需做任何处理：
#
#   → X-Request-ID: 请求唯一标识（16位hex字符串）
#     用途: 追踪单个请求的完整生命周期，排查问题时将此ID提供给后端
#     建议: 前端在发起请求时主动在Header中传入 X-Request-ID，
#            如未传入则后端自动生成一个
#
#   → X-Content-Type-Options: "nosniff"
#     用途: 禁止浏览器MIME类型嗅探，防止将非可执行文件当作脚本执行
#
#   → X-Frame-Options: "DENY"
#     用途: 禁止页面被iframe嵌入，防止点击劫持攻击
#     注意: 这意味着前端无法在iframe中加载后端页面
#
#   → X-XSS-Protection: "1; mode=block"
#     用途: 启用浏览器内置XSS过滤器，检测到攻击时阻止页面渲染
#
#   → Referrer-Policy: "strict-origin-when-cross-origin"
#     用途: 跨域时仅发送来源域名（不发送完整路径），同源时发送完整URL
#
#   → Permissions-Policy: 禁用摄像头/麦克风/地理位置等敏感API
#     用途: 防止后端页面被恶意利用访问硬件设备
#
#   → Cache-Control: "no-store, no-cache, must-revalidate, private"
#   → Pragma: "no-cache"
#     用途: 强制禁止浏览器和中间代理缓存API响应
#     重要: 前端无需额外设置缓存策略，所有API响应均不缓存，
#            每次请求都会返回最新数据
#
#   额外功能: 超过3000毫秒的慢请求会在服务端日志中记录，
#            包含请求方法、路径、耗时和请求ID
# ---------------------------------------------------------------------------

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """为每个响应添加安全头和请求ID"""
    request_id = request.headers.get("X-Request-ID") or _uuid.uuid4().hex[:16]
    request.state.request_id = request_id
    request.state.start_time = time.time()

    response = await call_next(request)

    # 安全头
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), interest-cohort=()"
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"

    # 审计：记录慢请求
    elapsed_ms = int((time.time() - request.state.start_time) * 1000)
    if elapsed_ms > 3000:
        logger.warning(f"慢请求: {request.method} {request.url.path} — {elapsed_ms}ms [rid={request_id}]")

    return response


# ---------------------------------------------------------------------------
# 中间件2: request_size_guard（请求体大小限制中间件）
# ---------------------------------------------------------------------------
# 【给前端的说明】
# 此中间件在请求进入业务逻辑之前检查 Content-Length 头，
# 拒绝超过 10MB（10 * 1024 * 1024 字节）的 POST 请求。
#
# 限制规则:
#   - 仅拦截 POST 请求
#   - 阈值: 硬限制 10MB（不可配置，代码级硬编码）
#   - 超限时直接返回 413 状态码，不进入后续中间件和路由
#   - 响应格式: {"detail": "请求体过大。最大10MB。"}
#
# 前端注意事项:
#   - 上传文件前应在前端进行大小校验，避免用户等待后收到413错误
#   - 文件上传路径: /uploads 静态目录（通过StaticFiles挂载，
#     不走此中间件的POST检查，因为 GET 请求不受限）
#   - 通过 API 上传文件（base64编码或multipart）均受此限制
# ---------------------------------------------------------------------------

@app.middleware("http")
async def request_size_guard(request: Request, call_next):
    """拒绝过大的请求体（硬限制10MB）"""
    if request.method == "POST":
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 10 * 1024 * 1024:
            return JSONResponse(
                status_code=413,
                content={"detail": "请求体过大。最大10MB。"},
            )
    return await call_next(request)


# ---------------------------------------------------------------------------
# 中间件3: CORSMiddleware（跨域资源共享中间件）- CORS 配置
# ---------------------------------------------------------------------------
# 【给前端的说明 - 重要】
# 本平台采用严格的安全设计，所有业务API仅允许 POST 和 OPTIONS 方法。
# GET/PUT/PATCH/DELETE 等方法均被 CORS 策略拒绝。
#
# 配置细节:
#   allow_origins:    从 settings.cors_origin_list 读取允许的前端域名列表
#                     生产环境通常只包含一个前端域名，开发环境包含 localhost
#   allow_methods:    仅 ["POST", "OPTIONS"]
#                     注意: 没有 GET/PUT/DELETE/PATCH！
#                     前端必须通过 POST + JSON body 来传递查询参数
#   allow_headers:    允许前端在请求中携带以下自定义Header:
#                     - Content-Type: 请求体类型（application/json）
#                     - X-Request-ID: 请求追踪ID
#                     - X-Forwarded-For: 代理转发的客户端真实IP
#                     - X-Real-IP: 客户端真实IP
#   expose_headers:   允许前端JavaScript读取以下响应Header:
#                     - X-Request-ID: 请求追踪ID
#   allow_credentials: true - 允许跨域携带Cookie和HTTP认证信息
#   max_age:          3600秒 - 浏览器缓存预检结果1小时
#
# 前端接入注意事项:
#   1. API基础URL: /api/v1/
#   2. 所有请求方法: POST
#   3. 必须在请求头中设置 Content-Type: application/json
#   4. 推荐携带 X-Request-ID 用于日志追踪
#   5. 如使用 fetch:
#        fetch('/api/v1/xxx', {
#          method: 'POST',
#          headers: {
#            'Content-Type': 'application/json',
#            'X-Request-ID': crypto.randomUUID().replace(/-/g, '').slice(0, 16)
#          },
#          body: JSON.stringify({ ... })
#        })
#   6. 如使用 axios:
#        axios.post('/api/v1/xxx', { ... }, {
#          headers: { 'X-Request-ID': generateRequestId() }
#        })
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "X-Request-ID",
        "X-Forwarded-For",
        "X-Real-IP",
    ],
    expose_headers=["X-Request-ID"],
    max_age=3600,
)


# ===========================================================================
#  API 路由注册
# ===========================================================================
# 所有 API 路由统一挂在 /api/v1 前缀下。
# 每个模块对应一个独立的功能域，路由文件和标签如下:
#
#   health        → /api/v1/              健康检查与系统状态
#   chat          → /api/v1/chat           聊天对话（含SSE流式输出）
#   rag           → /api/v1/rag            知识库检索增强生成
#   conversations → /api/v1/conversations   对话记录管理
#   agents        → /api/v1/agents          Agent 配置的增删改查
#   admin         → /api/v1/admin           管理员后台功能
#   sandbox       → /api/v1/sandbox         代码沙箱执行环境
#
# 前端路由映射示例:
#   POST /api/v1/              → 健康检查
#   POST /api/v1/chat/send     → 发送消息（SSE流式响应）
#   POST /api/v1/rag/search    → 搜索知识库
#   POST /api/v1/conversations/list → 获取对话列表
#   POST /api/v1/agents/create → 创建新Agent
#   POST /api/v1/admin/stats   → 获取管理统计
#   POST /api/v1/sandbox/execute → 执行沙箱代码
# ===========================================================================

from app.api import chat, rag, conversations, agents, health, admin, sandbox  # noqa: E402

API_V1 = "/api/v1"

app.include_router(health.router, prefix=API_V1, tags=["health"])
app.include_router(chat.router, prefix=f"{API_V1}/chat", tags=["chat"])
app.include_router(rag.router, prefix=f"{API_V1}/rag", tags=["rag"])
app.include_router(conversations.router, prefix=f"{API_V1}/conversations", tags=["conversations"])
app.include_router(agents.router, prefix=f"{API_V1}/agents", tags=["agents"])
app.include_router(admin.router, prefix=f"{API_V1}/admin", tags=["admin"])
app.include_router(sandbox.router, prefix=f"{API_V1}/sandbox", tags=["sandbox"])

# ---------------------------------------------------------------------------
# 静态文件挂载 - 上传文件访问
# ---------------------------------------------------------------------------
# 将服务器本地的 upload_dir 目录挂载到 /uploads 路径下。
# 前端可通过 GET /uploads/{filename} 直接访问已上传的文件（图片、文档等）。
# 此路径走的是 StaticFiles，不经过上述中间件的 POST/安全头检查。
# 生产环境建议在前面加 Nginx 反向代理以控制访问权限和限速。
# ---------------------------------------------------------------------------
os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


# ===========================================================================
#  默认 Agent 种子数据
# ===========================================================================
# _seed_default_agent() 在应用启动时自动执行，确保数据库中存在两个默认Agent:
#
# 【Agent 1: "通用助手" (id="default")】
#   - 名称: 通用助手
#   - 定位: 默认 AI 助手，分配给所有新用户的默认Agent
#   - 能力: 知识库问答、Web搜索、计算器、天气/新闻/汇率/IP查询、
#            Python/JS/Shell 代码执行、安装Python包、任务委派和分发
#   - 温度: 0.7（较高创造性）
#   - 上下文: 4096 tokens
#   - 特性: 支持跨对话长期记忆、工具委派
#   - 持久性: 如果已存在则不做任何修改（幂等）
#   - 工具更新: 如果源码中的 DEFAULT_TOOLS 新增了工具，
#                启动时会自动合并到已有Agent的工具列表中（幂等更新）
#
# 【Agent 2: "知识库助手" (id="rag-assistant")】
#   - 名称: 知识库助手
#   - 定位: 专用知识库问答，不可被用户删除（is_protected=True）
#   - 能力: 仅 search_knowledge_base，不调用其他工具
#   - 温度: 0.5（中等创造性，答案更稳定）
#   - RAG配置: top_k=5（召回5个文档片段），similarity_threshold=0.3（宽松匹配）
#   - 规则: 必须基于知识库文档回答，查不到时明确告知用户
#   - 持久性: 如果已存在（id="rag-assistant"已占用）则不重新创建
#
# 设计意图:
#   - "通用助手" 覆盖日常工作场景，工具调用链丰富
#   - "知识库助手" 限定范围，保证回答的安全性和可追溯性
#   - 两个Agent互不重叠，用户可按需切换
# ===========================================================================

async def _seed_default_agent():
    """创建或更新默认Agent（幂等 - 使用固定ID）"""
    from sqlalchemy import select, func
    from app.database import async_session_factory
    from app.models import AgentConfig

    DEFAULT_TOOLS = [
        "search_knowledge_base", "web_search", "calculator",
        "get_current_time", "get_weather", "get_news", "lookup_ip",
        "exchange_rate", "fetch_url", "tell_joke",
        "run_python_code", "run_javascript_code", "run_shell_command",
        "install_python_packages",
        "delegate_to_agent", "dispatch_tasks",
    ]

    async with async_session_factory() as db:
        count_result = await db.execute(select(func.count(AgentConfig.id)))
        count = count_result.scalar()

        if count == 0:
            # 创建默认通用助手
            default_agent = AgentConfig(
                id="default",
                name="通用助手",
                description="默认 AI 助手，支持知识库问答和工具调用",
                system_prompt=(
                    "你是一个拥有长期记忆功能的专业 AI 助手。你能在跨对话中记住用户告诉你的个人信息、偏好和需求，"
                    "并在后续对话中主动引用相关记忆，提供更连贯、个性化的体验。\n\n"
                    "你可以：\n"
                    "1. 回答用户的问题\n"
                    "2. 当需要查询上传的文档时，调用 search_knowledge_base 工具搜索知识库\n"
                    "3. 调用 run_python_code 在安全沙箱中执行 Python 代码（数据分析、计算、绘图等）\n"
                    "4. 调用 run_javascript_code / run_shell_command 执行 JS 或 Shell 命令\n"
                    "5. 调用 install_python_packages 安装需要的 Python 库\n"
                    "6. 调用其他工具完成复杂任务（网络搜索、天气查询、新闻、汇率、IP查询等）\n"
                    "注意：只有用户的问题明确涉及已上传的文档内容时，才调用 search_knowledge_base。\n"
                    "对于一般知识问题，直接用你的知识回答即可。\n"
                    "不要声称自己没有记忆能力。请用清晰、专业的中文回答。"
                ),
                temperature=0.7,
                max_tokens=4096,
                enabled_tools=DEFAULT_TOOLS,
                is_default=True,
                allow_delegation=True,
            )
            db.add(default_agent)
            await db.commit()
            logger.info("默认Agent已创建。")

        # ---- 确保现有默认Agent包含所有当前工具（幂等更新）----
        result = await db.execute(select(AgentConfig).where(AgentConfig.id == "default"))
        existing = result.scalar_one_or_none()
        if existing:
            existing_tools = set(existing.enabled_tools or [])
            current_tools = set(DEFAULT_TOOLS)
            if not current_tools.issubset(existing_tools):
                merged = list(dict.fromkeys(list(existing.enabled_tools or []) + DEFAULT_TOOLS))
                existing.enabled_tools = merged
                await db.commit()
                logger.info(f"默认Agent工具已更新：现在启用 {len(merged)} 个工具。")

        # ---- 确保受保护的RAG专用Agent存在（幂等，固定ID）----
        result = await db.execute(select(AgentConfig).where(AgentConfig.id == "rag-assistant"))
        if not result.scalar_one_or_none():
            rag_agent = AgentConfig(
                id="rag-assistant",
                name="知识库助手",
                description="专用知识库问答 Agent，仅检索管理员配置的知识库文档，不可删除",
                system_prompt=(
                    "你是一个专业的知识库问答助手。\n"
                    "你只能基于知识库中的文档内容回答问题。\n"
                    "规则：\n"
                    "1. 如果知识库中有相关信息，请基于文档内容准确回答并注明来源\n"
                    "2. 如果知识库中没有相关信息，请明确告知用户'该问题在知识库中未找到相关内容'\n"
                    "3. 回答要引用原文片段，保持客观准确\n"
                    "请用清晰、专业的中文回答。"
                ),
                temperature=0.5,
                max_tokens=4096,
                enabled_tools=["search_knowledge_base"],
                rag_top_k=5,
                rag_similarity_threshold=0.3,  # 降低阈值以获得更广泛的匹配
                is_default=False,
                is_protected=True,
                allow_delegation=True,
            )
            db.add(rag_agent)
            await db.commit()
            logger.info("受保护的RAG专用Agent已创建。")


# ===========================================================================
#  直接运行入口（开发环境）
# ===========================================================================
# 通过 `python main.py` 直接启动时使用uvicorn运行。
# 生产环境推荐使用 `uvicorn app.main:app` 命令行方式启动，
# 配合 gunicorn + uvicorn workers 实现多进程部署。
# ===========================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )


# ===========================================================================
#  API 路由速查表（所有接口统一使用 POST 方法 + JSON 请求体）
# ===========================================================================
# ┌──────────┬────────────────────────────────┬──────────────────┬───────────────────────────────────────┐
# │  方法    │  路由前缀                       │  功能模块          │  用途说明                             │
# ├──────────┼────────────────────────────────┼──────────────────┼───────────────────────────────────────┤
# │  POST    │  /api/v1/                      │  health           │  健康检查：验证服务是否正常运行        │
# │          │                                │                  │  返回: 服务状态、数据库/Redis连接      │
# ├──────────┼────────────────────────────────┼──────────────────┼───────────────────────────────────────┤
# │  POST    │  /api/v1/chat                  │  chat             │  聊天对话模块                         │
# │          │  例如: /api/v1/chat/send       │                  │  - /send: 发送消息（SSE流式返回）      │
# │          │        /api/v1/chat/stream     │                  │  - /stream: 流式对话                   │
# │          │        /api/v1/chat/history    │                  │  - /history: 对话历史记录              │
# │          │        /api/v1/chat/stop       │                  │  - /stop: 停止生成                     │
# ├──────────┼────────────────────────────────┼──────────────────┼───────────────────────────────────────┤
# │  POST    │  /api/v1/rag                   │  rag              │  知识库检索增强生成                   │
# │          │  例如: /api/v1/rag/search      │                  │  - /search: 检索知识库                 │
# │          │        /api/v1/rag/documents   │                  │  - /documents/*: 文档管理              │
# │          │        /api/v1/rag/upload      │                  │  - /upload: 上传文档到知识库           │
# ├──────────┼────────────────────────────────┼──────────────────┼───────────────────────────────────────┤
# │  POST    │  /api/v1/conversations         │  conversations   │  对话管理模块                         │
# │          │  例如: /api/v1/conversations/list  │              │  - /list: 获取对话列表                 │
# │          │        /api/v1/conversations/create │             │  - /create: 创建新对话                 │
# │          │        /api/v1/conversations/delete │             │  - /delete: 删除对话                   │
# │          │        /api/v1/conversations/rename │             │  - /rename: 重命名对话                 │
# ├──────────┼────────────────────────────────┼──────────────────┼───────────────────────────────────────┤
# │  POST    │  /api/v1/agents                │  agents           │  Agent 配置管理模块                   │
# │          │  例如: /api/v1/agents/list     │                  │  - /list: 获取Agent列表                │
# │          │        /api/v1/agents/create   │                  │  - /create: 创建新Agent                │
# │          │        /api/v1/agents/update   │                  │  - /update: 更新Agent配置              │
# │          │        /api/v1/agents/delete   │                  │  - /delete: 删除Agent（受保护的不可删）│
# │          │        /api/v1/agents/detail   │                  │  - /detail: 获取Agent详情              │
# ├──────────┼────────────────────────────────┼──────────────────┼───────────────────────────────────────┤
# │  POST    │  /api/v1/admin                 │  admin            │  管理后台模块                         │
# │          │  例如: /api/v1/admin/stats     │                  │  - /stats: 系统统计数据                │
# │          │        /api/v1/admin/users     │                  │  - /users/*: 用户管理                  │
# │          │        /api/v1/admin/config    │                  │  - /config: 系统配置管理               │
# ├──────────┼────────────────────────────────┼──────────────────┼───────────────────────────────────────┤
# │  POST    │  /api/v1/sandbox               │  sandbox          │  代码沙箱执行环境                     │
# │          │  例如: /api/v1/sandbox/execute │                  │  - /execute: 执行代码（Python/JS/Shell)│
# │          │        /api/v1/sandbox/status  │                  │  - /status: 沙箱状态查询               │
# ├──────────┼────────────────────────────────┼──────────────────┼───────────────────────────────────────┤
# │  GET     │  /uploads/{filename}           │  静态文件服务      │  访问已上传的文件                      │
# │          │                                │                  │  不走CORS限制，通过StaticFiles直出     │
# ├──────────┼────────────────────────────────┼──────────────────┼───────────────────────────────────────┤
# │  GET     │  /api/docs（生产） /docs（开发） │  Swagger UI      │  API交互式文档（自动生成）             │
# │          │                                │                  │  生产: /api/docs，开发: /docs          │
# └──────────┴────────────────────────────────┴──────────────────┴───────────────────────────────────────┘
#
# 响应头速查:
# ┌─────────────────────────────────┬──────────────────────────────────────────────┐
# │  Header名称                      │  值/说明                                     │
# ├─────────────────────────────────┼──────────────────────────────────────────────┤
# │  X-Request-ID                   │  请求追踪ID，16位hex，前端可传入或自动生成      │
# │  Content-Type                   │  application/json                            │
# │  Cache-Control                  │  no-store, no-cache, must-revalidate, private │
# │  X-Content-Type-Options         │  nosniff                                     │
# │  X-Frame-Options                │  DENY                                        │
# │  Access-Control-Allow-Origin    │  根据请求来源动态返回                          │
# │  Access-Control-Allow-Methods   │  POST, OPTIONS                               │
# │  Access-Control-Expose-Headers  │  X-Request-ID                                │
# └─────────────────────────────────┴──────────────────────────────────────────────┘
#
# 常见错误码:
# ┌──────────┬──────────────────────────────────────────────────┐
# │  状态码   │  含义                                              │
# ├──────────┼──────────────────────────────────────────────────┤
# │  200     │  请求成功                                          │
# │  400     │  请求参数错误 / JSON解析失败                        │
# │  401     │  未认证（缺少或无效的认证信息）                      │
# │  403     │  无权限（已认证但权限不足）                          │
# │  404     │  资源不存在                                        │
# │  413     │  请求体超过 10MB 限制                              │
# │  422     │  请求体验证失败（字段类型/必填项不满足）             │
# │  500     │  服务器内部错误                                    │
# │  503     │  服务不可用（如DB/Redis未就绪）                     │
# └──────────┴──────────────────────────────────────────────────┘
"""
