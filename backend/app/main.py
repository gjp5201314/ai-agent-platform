"""
FastAPI application entry point.
"""
import os
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.core.redis_client import get_redis, close_redis

# Apply LangSmith tracing settings to environment before any LangChain import.
# LangSmith uses LANGCHAIN_* env vars internally.
if settings.langsmith_tracing and settings.langsmith_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle: startup and shutdown."""
    # ---- Startup ----
    # Initialize database
    await init_db()
    # Seed default agent config if none exists
    await _seed_default_agent()
    # Warm up Redis
    redis = await get_redis()
    await redis.ping()
    # Ensure upload directory exists
    os.makedirs(settings.upload_dir, exist_ok=True)
    print(f"[Startup] Database initialized, Redis connected. Provider: {settings.llm_provider}")

    yield

    # ---- Shutdown ----
    await close_redis()
    print("[Shutdown] Connections closed.")


app = FastAPI(
    title="AI Agent Platform",
    description="Production-ready AI Agent with RAG, tool calling, and streaming chat. "
                "Powered by LangGraph + FastAPI + PostgreSQL/pgvector.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from app.api import chat, rag, conversations, agents, health  # noqa: E402

app.include_router(health.router, tags=["health"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(rag.router, prefix="/api/rag", tags=["rag"])
app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])

# Serve uploaded files — ensure directory exists first
os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


async def _seed_default_agent():
    """Create a default agent config if the table is empty."""
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
                    "你是一个专业的 AI 助手。你可以：\n"
                    "1. 回答用户的问题\n"
                    "2. 基于上传的知识库文档进行精准问答\n"
                    "3. 调用工具完成复杂任务（网络搜索、天气查询、新闻、汇率、IP查询等）\n"
                    "请用清晰、专业的中文回答。"
                ),
                temperature=0.7,
                max_tokens=4096,
                enabled_tools=["rag", "web_search", "calculator", "get_current_time", "get_weather", "get_news", "lookup_ip", "exchange_rate", "fetch_url", "tell_joke"],
                is_default=True,
            )
            db.add(default_agent)
            await db.commit()
            print("[Startup] Default agent created.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
