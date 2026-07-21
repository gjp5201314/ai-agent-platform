"""
FastAPI应用入口 - 企业级AI Agent平台
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

# 在导入LangChain之前设置LangSmith追踪环境变量
if settings.langsmith_tracing and settings.langsmith_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project


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


# CORS配置 - 仅允许POST和OPTIONS方法
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

# 注册路由器到API版本前缀
from app.api import chat, rag, conversations, agents, health, admin, sandbox  # noqa: E402

API_V1 = "/api/v1"

app.include_router(health.router, prefix=API_V1, tags=["health"])
app.include_router(chat.router, prefix=f"{API_V1}/chat", tags=["chat"])
app.include_router(rag.router, prefix=f"{API_V1}/rag", tags=["rag"])
app.include_router(conversations.router, prefix=f"{API_V1}/conversations", tags=["conversations"])
app.include_router(agents.router, prefix=f"{API_V1}/agents", tags=["agents"])
app.include_router(admin.router, prefix=f"{API_V1}/admin", tags=["admin"])
app.include_router(sandbox.router, prefix=f"{API_V1}/sandbox", tags=["sandbox"])

# 通过受控端点提供上传文件（非原始StaticFiles）
os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )