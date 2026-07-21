"""
应用配置
所有设置从环境变量加载，提供合理的默认值
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

    # ---- 应用配置 ----
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False
    cors_origins: str = "http://localhost:5173"

    # ---- LLM配置 ----
    llm_provider: str = "qwen"  # qwen | openai | claude

    # 通义千问 / DashScope（OpenAI兼容）
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen3.7-plus"
    qwen_vision_model: str = "qwen-vl-plus"  # 多模态模型，用于图像输入

    # 文件上传
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

    # Embedding配置
    embedding_api_key: str = ""
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v3"
    embedding_dimensions: int = 1024

    # ---- 数据库配置 ----
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "agent"
    postgres_password: str = ""
    postgres_db: str = "aiagent"
    database_url: str = ""

    # ---- Redis配置 ----
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # ---- 工具路由（语义工具过滤）----
    # 当工具数量超过阈值时，在绑定到LLM之前语义过滤到相关组
    # 降低Token成本，提高选择准确性
    tool_routing_enabled: bool = True
    tool_routing_mode: str = "keyword"      # "keyword"（即时，无API）| "embedding"（基于API，更准确）
    tool_routing_top_k_groups: int = 2      # 过滤后包含的最大工具组数
    tool_routing_min_tools: int = 6         # 仅当工具数超过此值时激活

    # ---- 速率限制 ----
    # 聊天端点最昂贵（每次请求LLM API成本）
    # 更严格的限制：每IP每分钟20次请求
    # 读/写端点在deps.py中有各自的限制
    rate_limit_chat_max: int = 20           # 窗口内最大聊天请求数
    rate_limit_chat_window: int = 60        # 窗口秒数
    rate_limit_enabled: bool = True         # 全局速率限制开关

    # ---- 工具执行 ----
    tool_timeout_seconds: int = 30          # 每次工具调用的最大秒数（网络工具）
    delegate_max_depth: int = 3             # Agent委派的最大递归深度

    # ---- DifySandbox（安全代码执行）----
    difysandbox_url: str = "http://sandbox:8194"  # DifySandbox API URL
    difysandbox_api_key: str = "dify-sandbox"     # DifySandbox认证API密钥
    sandbox_timeout_seconds: int = 30             # 默认代码执行超时
    sandbox_max_retries: int = 3                  # 临时错误的重试次数
    sandbox_max_code_length: int = 50_000         # 最大源代码长度（字符）
    sandbox_preinstall_packages: bool = True      # 启动时预装numpy/pandas/matplotlib

    # ---- 多Agent编排 ----
    # 启用后，主管可以将任务分发给多个子Agent并行执行
    # 每个子Agent运行自己的完整图循环（agent → tools → agent）
    multi_agent_enabled: bool = True        # 启用多Agent主管模式
    multi_agent_max_parallel: int = 3       # 通过asyncio.gather的最大并发子Agent数

    # ---- Mock模式 ----
    # 启用后所有LLM调用返回模拟响应，不消耗任何API Key
    # 可通过环境变量 MOCK_MODE_ENABLED=true 全局开启，或通过前端切换
    mock_mode_enabled: bool = False

    # ---- LangSmith ----
    # LangSmith底层使用LANGCHAIN_*环境变量
    # 我们在这里存储它们，并在main启动时通过os.environ应用
    langsmith_tracing: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_api_key: str = ""
    langsmith_project: str = "ai-agent-platform"

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_db_url(cls, v, info):
        """组装数据库URL"""
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
        """CORS来源列表"""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """SQLAlchemy同步URL（用于Alembic迁移）"""
        return self.database_url.replace("asyncpg", "psycopg2")

    @property
    def redis_url(self) -> str:
        """Redis连接URL"""
        pwd = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{pwd}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    """获取设置实例（缓存）"""
    return Settings()


settings = get_settings()