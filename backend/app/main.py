"""
FastAPI application entry point — enterprise AI agent platform.
Security-first design: all read endpoints use POST with JSON body.
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

# Apply LangSmith tracing settings to environment before any LangChain import.
if settings.langsmith_tracing and settings.langsmith_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle: startup and shutdown."""
    # ---- Startup ----
    await init_db()
    await _seed_default_agent()
    redis = await get_redis()
    await redis.ping()
    os.makedirs(settings.upload_dir, exist_ok=True)
    logger.info(f"Database initialized, Redis connected. Provider: {settings.llm_provider}")

    yield

    # ---- Shutdown ----
    await close_sandbox_client()
    await close_redis()
    logger.info("Connections closed.")


app = FastAPI(
    title="AI Agent Platform",
    description="Enterprise-grade AI Agent with RAG, tool calling, and streaming chat. "
                "Powered by LangGraph + FastAPI + PostgreSQL/pgvector.",
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if not settings.app_debug else "/docs",
    redoc_url=None,  # Disable ReDoc in production
)


# ============================================================
#  Middleware Stack (order matters — outermost first)
# ============================================================

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Inject enterprise security headers + request-id on every response."""
    request_id = request.headers.get("X-Request-ID") or _uuid.uuid4().hex[:16]
    request.state.request_id = request_id
    request.state.start_time = time.time()

    response = await call_next(request)

    # Security headers
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

    # Audit: log request duration (non-blocking print; use structured logging in production)
    elapsed_ms = int((time.time() - request.state.start_time) * 1000)
    if elapsed_ms > 3000:
        logger.warning(f"Slow request: {request.method} {request.url.path} — {elapsed_ms}ms [rid={request_id}]")

    return response


@app.middleware("http")
async def request_size_guard(request: Request, call_next):
    """Reject oversized request bodies early (10 MB hard cap)."""
    if request.method == "POST":
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 10 * 1024 * 1024:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large. Maximum 10 MB."},
            )
    return await call_next(request)


# CORS — tightened for POST-only API
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

# Register routers under API version prefix
from app.api import chat, rag, conversations, agents, health, admin, sandbox  # noqa: E402

API_V1 = "/api/v1"

app.include_router(health.router, prefix=API_V1, tags=["health"])
app.include_router(chat.router, prefix=f"{API_V1}/chat", tags=["chat"])
app.include_router(rag.router, prefix=f"{API_V1}/rag", tags=["rag"])
app.include_router(conversations.router, prefix=f"{API_V1}/conversations", tags=["conversations"])
app.include_router(agents.router, prefix=f"{API_V1}/agents", tags=["agents"])
app.include_router(admin.router, prefix=f"{API_V1}/admin", tags=["admin"])
app.include_router(sandbox.router, prefix=f"{API_V1}/sandbox", tags=["sandbox"])

# Serve uploaded files through a controlled endpoint (not raw StaticFiles)
os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


async def _seed_default_agent():
    """Create default agents if missing (idempotent — uses fixed IDs)."""
    from sqlalchemy import select, func
    from app.database import async_session_factory
    from app.models import AgentConfig

    async with async_session_factory() as db:
        count_result = await db.execute(select(func.count(AgentConfig.id)))
        count = count_result.scalar()

        if count == 0:
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
                enabled_tools=["search_knowledge_base", "web_search", "calculator", "get_current_time", "get_weather", "get_news", "lookup_ip", "exchange_rate", "fetch_url", "tell_joke", "run_python_code", "run_javascript_code", "run_shell_command", "install_python_packages", "delegate_to_agent", "dispatch_tasks"],
                is_default=True,
                allow_delegation=True,
            )
            db.add(default_agent)
            await db.commit()
            logger.info("Default agent created.")

        # ---- Ensure the protected RAG-only agent exists (idempotent by fixed ID) ----
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
                rag_similarity_threshold=0.3,  # Lower threshold for broader matching
                is_default=False,
                is_protected=True,
                allow_delegation=True,
            )
            db.add(rag_agent)
            await db.commit()
            logger.info("Protected RAG-only agent created.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
