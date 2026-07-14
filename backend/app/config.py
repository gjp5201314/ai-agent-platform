"""
Application configuration.
All settings are loaded from environment variables with sensible defaults.
"""
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- App ----
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False
    cors_origins: str = "http://localhost:5173"

    # ---- LLM ----
    llm_provider: str = "qwen"  # qwen | openai | claude

    # Qwen / DashScope (OpenAI-compatible)
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    qwen_vision_model: str = "qwen-vl-plus"  # multimodal model for image input

    # File upload
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 20
    allowed_image_types: str = "png,jpg,jpeg,gif,webp"
    allowed_file_types: str = "pdf,docx,txt,md,csv,py,js,ts,json,yaml,yml,xml,html,css,sql,log"

    # OpenAI
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # Claude / Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # Embedding
    embedding_api_key: str = ""
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v3"
    embedding_dimensions: int = 1024

    # ---- Database ----
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "agent"
    postgres_password: str = ""
    postgres_db: str = "aiagent"
    database_url: str = ""

    # ---- Redis ----
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # ---- Tool Routing (semantic tool filtering) ----
    # When tools exceed the threshold, semantically filter to only relevant groups
    # before binding to the LLM. Reduces token cost and improves selection accuracy.
    tool_routing_enabled: bool = True
    tool_routing_mode: str = "keyword"      # "keyword" (instant, no API) | "embedding" (API-based, more accurate)
    tool_routing_top_k_groups: int = 2      # Max tool groups to include after filtering
    tool_routing_min_tools: int = 6         # Only activate when tool count exceeds this

    # ---- Rate Limiting ----
    # Chat endpoint is the most expensive (LLM API cost per request).
    # Stricter limit: 20 requests per minute per IP.
    # Read/write endpoints have their own limits in deps.py.
    rate_limit_chat_max: int = 20           # Max chat requests per window
    rate_limit_chat_window: int = 60        # Window in seconds
    rate_limit_enabled: bool = True         # Global rate limit toggle

    # ---- Tool Execution ----
    tool_timeout_seconds: int = 30          # Max seconds per tool call (network tools)
    delegate_max_depth: int = 3             # Max recursion depth for agent delegation

    # ---- LangSmith ----
    # LangSmith uses LANGCHAIN_* env vars under the hood.
    # We store them here and apply via os.environ in main startup.
    langsmith_tracing: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_api_key: str = ""
    langsmith_project: str = "ai-agent-platform"

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_db_url(cls, v, info):
        if isinstance(v, str) and v:
            return v
        values = info.data
        return (
            f"postgresql+asyncpg://{values.get('postgres_user', 'agent')}:"
            f"{values.get('postgres_password', '')}@{values.get('postgres_host', 'localhost')}:"
            f"{values.get('postgres_port', 5432)}/{values.get('postgres_db', 'aiagent')}"
        )

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """SQLAlchemy sync URL (for Alembic migrations)."""
        return self.database_url.replace("asyncpg", "psycopg2")

    @property
    def redis_url(self) -> str:
        pwd = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{pwd}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
