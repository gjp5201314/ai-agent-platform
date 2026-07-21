"""
================================================================================
应用配置 — 所有设置从环境变量加载，提供合理的默认值
================================================================================

【前端开发者必读】

本文件定义了整个后端应用的所有配置项。每个配置项都可以通过以下方式设置：
  1. 环境变量（推荐用于生产环境）
  2. .env 文件（推荐用于本地开发，位于项目根目录）
  3. 代码中的默认值（当上述两种方式都未设置时）

前端开发者关心的配置项（标注了 ★ 的）：
  - cors_origins        ★ 决定哪些前端域名可以跨域请求后端 API
  - max_upload_size_mb  ★ 文件上传大小限制，前端需在 UI 层面同步校验
  - allowed_image_types ★ 允许的图片格式，前端文件选择器应匹配
  - allowed_file_types  ★ 允许的文档格式，前端文件选择器应匹配
  - rate_limit_chat_max ★ 聊天请求速率限制，前端需处理后端 429 响应
  - sandbox_preinstall_packages ★ 沙盒是否预装数据科学包
  - mock_mode_enabled   ★ Mock 模式开关，前端可显示当前模式

配置项按功能分为以下几个大类：
  【应用基础】   宿主/端口/调试/CORS
  【LLM 大模型】 模型提供商、API Key、模型名、Embedding
  【数据库】     PostgreSQL 连接信息
  【Redis】      Redis 连接信息
  【工具路由】   语义工具过滤策略
  【速率限制】   聊天 API 的频率限制
  【工具执行】   单次工具调用超时、Agent 委派深度
  【DifySandbox】安全代码执行环境
  【多Agent编排】主管模式、并发子Agent
  【Mock 模式】  模拟 LLM 响应（不消耗 API Key）
  【LangSmith】  LLM 调用追踪和调试

================================================================================
"""
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    应用设置类。

    所有配置项自动从以下来源读取（优先级从高到低）：
      1. 操作系统环境变量（如 export APP_PORT=8080）
      2. .env 文件中的变量
      3. 类定义中的默认值

    使用 Pydantic Settings 自动完成类型转换和验证。
    """
    model_config = SettingsConfigDict(
        env_file=".env",            # 从项目根目录的 .env 文件加载
        env_file_encoding="utf-8",  # .env 文件的编码格式
        extra="ignore",             # 忽略 .env 中未定义的额外字段，避免启动报错
    )

    # ==========================================================================
    # 【应用基础配置】
    # ==========================================================================
    # app_host: FastAPI/Uvicorn 监听的 IP 地址
    #   - "0.0.0.0" = 监听所有网络接口，允许外部访问
    #   - "127.0.0.1" = 仅本地访问
    #   前端无需关注此配置
    app_host: str = "0.0.0.0"

    # app_port: FastAPI/Uvicorn 监听的端口号
    #   前端请求后端 API 时需要用到此端口（如 http://localhost:8000）
    #   如果前端使用 Vite 代理，需在 vite.config.ts 中配置对应的代理目标
    app_port: int = 8000

    # app_debug: 调试模式开关
    #   - true: FastAPI 显示详细错误信息、自动重载（开发环境推荐）
    #   - false: 生产模式，隐藏内部错误细节（生产环境必须）
    app_debug: bool = False

    # cors_origins ★【前端相关】CORS 跨域白名单
    #   决定哪些前端域名的 AJAX/Fetch 请求可以被后端接受
    #   这是一个逗号分隔的字符串，格式："http://localhost:5173,http://localhost:3000"
    #   多个来源用逗号分隔
    #   前端部署到生产环境后，需要在此添加生产域名
    cors_origins: str = "http://localhost:5173"

    # ==========================================================================
    # 【LLM 大模型配置】
    # ==========================================================================
    # llm_provider: 当前使用的 LLM 提供商
    #   可选值: "qwen"（通义千问）、"openai"（OpenAI）、"claude"（Anthropic Claude）
    #   这个值决定了后端使用哪一组 API Key 和模型配置
    #   前端可以在"设置"页面展示当前使用的模型提供商
    llm_provider: str = "qwen"  # qwen | openai | claude

    # ---- 通义千问 / DashScope（OpenAI 兼容接口） ----
    # dashscope_api_key: 阿里云 DashScope 的 API Key
    #   开通地址：https://dashscope.console.aliyun.com/
    #   前端无需关注（敏感信息，不会暴露给前端）
    dashscope_api_key: str = ""

    # dashscope_base_url: DashScope API 的基础 URL
    #   使用 OpenAI 兼容接口模式，路径为 /compatible-mode/v1
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # qwen_model: 通义千问的默认模型名称
    #   "qwen3.7-plus" 是当前主推的旗舰模型，中文能力强
    qwen_model: str = "qwen3.7-plus"

    # qwen_vision_model: 通义千问多模态模型（支持图像输入）
    #   当用户上传图片让 AI 分析时，会切换到此模型
    #   因为普通文本模型无法处理图像输入
    qwen_vision_model: str = "qwen-vl-plus"  # 多模态模型，用于图像输入

    # ---- 文件上传配置 ★【前端相关】 ----
    # upload_dir: 上传文件的存储目录
    #   相对路径，相对于后端项目根目录
    #   前端上传的文件会保存在此目录下
    upload_dir: str = "uploads"

    # max_upload_size_mb ★【前端相关】最大上传文件大小（MB）
    #   前端需要在文件选择时做客户端校验，拦截超大文件
    #   后端也会校验，超过此大小返回 413 错误
    #   【前端建议】在文件上传组件中显示此限制
    max_upload_size_mb: int = 20

    # allowed_image_types ★【前端相关】允许上传的图片格式
    #   逗号分隔的扩展名列表（不含点号）
    #   前端应在 <input type="file" accept="image/png,image/jpeg,..."> 中匹配
    allowed_image_types: str = "png,jpg,jpeg,gif,webp"

    # allowed_file_types ★【前端相关】允许上传的文档格式
    #   包括代码文件（py, js, ts）和文档文件（pdf, docx, md）等
    #   前端文件选择器应匹配这些格式
    allowed_file_types: str = "pdf,docx,txt,md,csv,py,js,ts,json,yaml,yml,xml,html,css,sql,log"

    # ---- OpenAI ----
    # openai_api_key: OpenAI 的 API Key
    #   从 https://platform.openai.com/api-keys 获取
    #   仅在 llm_provider="openai" 时使用
    openai_api_key: str = ""

    # openai_base_url: OpenAI API 基础 URL
    #   可以改为代理地址（如国内中转服务）以解决网络问题
    openai_base_url: str = "https://api.openai.com/v1"

    # openai_model: OpenAI 默认使用的模型
    #   "gpt-4o-mini" 性价比高，适合大多数场景
    openai_model: str = "gpt-4o-mini"

    # ---- Claude / Anthropic ----
    # anthropic_api_key: Anthropic 的 API Key
    #   从 https://console.anthropic.com/ 获取
    #   仅在 llm_provider="claude" 时使用
    anthropic_api_key: str = ""

    # anthropic_model: Claude 默认使用的模型
    #   "claude-3-5-sonnet-20241022" 是 Sonnet 系列的最新模型
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # ---- Embedding 配置 ----
    # Embedding 是将文本转换为数学向量（浮点数数组）的过程
    # 用于语义搜索、文档相似度计算、RAG（检索增强生成）
    # 前端无需直接使用 Embedding，但上传的文档会通过此服务建立向量索引
    embedding_api_key: str = ""

    # embedding_base_url: Embedding API 的基础 URL
    #   通常与 LLM 使用同一个服务（DashScope 同时提供 LLM 和 Embedding）
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # embedding_model: Embedding 模型名称
    #   "text-embedding-v3" 是 DashScope 的通用 Embedding 模型
    embedding_model: str = "text-embedding-v3"

    # embedding_dimensions: 输出向量的维度
    #   1024 维是常用值，维度越高能捕获越多的语义信息，但存储和计算开销更大
    #   此值需要与数据库的 pgvector 索引维度一致
    embedding_dimensions: int = 1024

    # ==========================================================================
    # 【数据库配置 — PostgreSQL + pgvector】
    # ==========================================================================
    # PostgreSQL 是项目的主数据库，用于存储：
    #   - 对话记录（conversations 表）
    #   - 消息历史（messages 表）
    #   - 上传的文档（documents 表）
    #   - 文档向量块（document_chunks 表，使用 pgvector 扩展）
    #   - Agent 配置（agent_configs 表）
    #   - Mem0 长期记忆（mem0_memories 表）
    #
    # 前端无需直接连接数据库，所有数据通过后端 API 访问。

    # postgres_host: PostgreSQL 服务器地址
    #   - 开发环境：通常为 "localhost"
    #   - Docker Compose：使用服务名，如 "postgres"
    postgres_host: str = "localhost"

    # postgres_port: PostgreSQL 端口号
    #   默认 5432，如果宿主机已占用可能需要改为 5433 等
    postgres_port: int = 5432

    # postgres_user: 数据库用户名
    #   本项目使用的专用用户名为 "agent"
    postgres_user: str = "agent"

    # postgres_password: 数据库密码
    #   敏感信息，不应暴露给前端
    postgres_password: str = ""

    # postgres_db: 数据库名称
    postgres_db: str = "aiagent"

    # database_url: 完整的数据库连接字符串
    #   如果为空，会由 assemble_db_url 验证器自动从上面的字段拼接
    #   格式：postgresql+asyncpg://user:password@host:port/dbname
    #   使用 asyncpg 驱动（高性能异步 PostgreSQL 驱动）
    database_url: str = ""

    # ==========================================================================
    # 【Redis 配置】
    # ==========================================================================
    # Redis 是内存数据存储，用于：
    #   1. 速率限制（rate limiting）：记录每个 IP 的请求频率
    #   2. 缓存（caching）：缓存频繁访问的数据，减少数据库查询
    #   3. 会话状态（session state）：存储临时的会话上下文
    #
    # 前端无需直接连接 Redis，但速率限制会影响前端请求的响应状态（429 Too Many Requests）。

    # redis_host: Redis 服务器地址
    redis_host: str = "localhost"

    # redis_port: Redis 端口号
    redis_port: int = 6379

    # redis_password: Redis 密码（如果设置了的话）
    redis_password: str = ""

    # redis_db: Redis 数据库编号（0-15）
    #   同一 Redis 实例可以有多个逻辑数据库
    redis_db: int = 0

    # ==========================================================================
    # 【工具路由（语义工具过滤）】
    # ==========================================================================
    # 当 AI Agent 可用的工具很多时（数十个），将全部工具列表发给 LLM 会：
    #   1. 消耗大量 Token（每个工具描述都计入上下文）
    #   2. 降低 LLM 选择正确工具的准确性
    #
    # 工具路由机制：根据用户意图自动筛选相关的工具组，
    # 只将相关工具发送给 LLM，减少干扰。

    # tool_routing_enabled: 是否启用工具路由
    #   - true: 当工具数量超过阈值时，自动筛选相关工具
    #   - false: 始终将所有工具发送给 LLM
    tool_routing_enabled: bool = True

    # tool_routing_mode: 路由模式
    #   - "keyword": 基于关键词匹配（快速，无需 API 调用）
    #   - "embedding": 基于向量相似度（更准确，但需额外 API 调用）
    tool_routing_mode: str = "keyword"      # "keyword"（即时，无API）| "embedding"（基于API，更准确）

    # tool_routing_top_k_groups: 过滤后最多保留的工具组数
    #   例如用户问"查天气"，可能匹配 weather 和 web_search 两个组
    tool_routing_top_k_groups: int = 2      # 过滤后包含的最大工具组数

    # tool_routing_min_tools: 触发过滤的最小工具数量
    #   当工具总数 <= 此值时，不过滤（因为工具很少，不需要优化）
    tool_routing_min_tools: int = 6         # 仅当工具数超过此值时激活

    # ==========================================================================
    # 【速率限制 ★【前端相关】】
    # ==========================================================================
    # 速率限制用于防止恶意请求或滥用 API。
    # 当前只对聊天端点（chat API）做速率限制，因为聊天是最消耗 LLM API 成本的端点。
    #
    # 【前端处理建议】
    #   当后端返回 HTTP 429（Too Many Requests）时：
    #     1. 显示 toast 提示："请求过于频繁，请稍后再试"
    #     2. 不要自动重试（避免进一步触发限制）
    #     3. 可以在 UI 上显示一个倒计时（等待窗口过期）

    # rate_limit_chat_max: 时间窗口内允许的最大聊天请求数
    #   默认每 60 秒最多 20 次请求（5 秒一次平均频率足够正常使用）
    rate_limit_chat_max: int = 20           # 窗口内最大聊天请求数

    # rate_limit_chat_window: 速率限制的时间窗口（秒）
    #   窗口从第一次请求开始计时
    rate_limit_chat_window: int = 60        # 窗口秒数

    # rate_limit_enabled: 全局速率限制开关
    #   - true: 启用速率限制（生产环境推荐）
    #   - false: 关闭速率限制（开发调试时方便）
    rate_limit_enabled: bool = True         # 全局速率限制开关

    # ==========================================================================
    # 【工具执行配置】
    # ==========================================================================
    # tool_timeout_seconds: 单次工具调用的超时时间（秒）
    #   适用于网络相关工具（如网页搜索、API 调用）
    #   超时后工具调用会被中断，防止 LLM 长时间等待
    #   前端可能会在超时后看到"工具执行超时"的错误消息
    tool_timeout_seconds: int = 30          # 每次工具调用的最大秒数（网络工具）

    # delegate_max_depth: Agent 委派的最大递归深度
    #   在主 Agent 委派任务给子 Agent 时，子 Agent 也可能再委派给孙 Agent
    #   此值限制了递归委派的层数，防止无限委派
    #   设置为 3 意味着：主 Agent → 子 Agent → 孙 Agent（孙 Agent 不能再委派）
    delegate_max_depth: int = 3             # Agent委派的最大递归深度

    # ==========================================================================
    # 【DifySandbox — 安全代码执行环境】
    # ==========================================================================
    # DifySandbox 是一个开源的代码执行沙盒，通过 Docker 容器提供隔离的执行环境。
    # 它允许 AI 生成和执行 Python/JS/Bash 代码，同时确保安全。
    #
    # 前端可以通过 /sandbox/* API 端点与沙盒交互。
    # 详见 app/api/sandbox.py 的注释。

    # difysandbox_url: DifySandbox 服务的 API URL
    #   - Docker Compose: 使用服务名 "sandbox" + 端口 8194
    #   - 独立部署: 改为实际 IP 或域名
    difysandbox_url: str = "http://sandbox:8194"  # DifySandbox API URL

    # difysandbox_api_key: DifySandbox 的认证 API Key
    #   默认值 "dify-sandbox" 是 DifySandbox 容器的默认密钥
    difysandbox_api_key: str = "dify-sandbox"     # DifySandbox认证API密钥

    # sandbox_timeout_seconds: 代码执行的默认超时时间（秒）
    #   用户代码超过此时间会被强制终止，防止死循环
    sandbox_timeout_seconds: int = 30             # 默认代码执行超时

    # sandbox_max_retries: 临时错误的重试次数
    #   当沙盒因网络抖动等临时原因不可达时，自动重试
    sandbox_max_retries: int = 3                  # 临时错误的重试次数

    # sandbox_max_code_length: 允许执行的最大代码长度（字符数）
    #   超过此长度的代码会被拒绝（防止恶意提交超大代码）
    #   50,000 字符对正常代码已经足够
    sandbox_max_code_length: int = 50_000         # 最大源代码长度（字符）

    # sandbox_preinstall_packages ★【前端相关】
    #   沙盒启动时是否自动预装 numpy、pandas、matplotlib
    #   - true: 启动时自动安装（增加启动时间但方便用户）
    #   - false: 需要用户手动触发安装
    #   前端可以在沙盒状态面板中显示是否已预装及安装进度
    sandbox_preinstall_packages: bool = True      # 启动时预装numpy/pandas/matplotlib

    # ==========================================================================
    # 【多 Agent 编排】
    # ==========================================================================
    # 多 Agent 模式是指一个"主管 Agent"可以将复杂任务拆分给多个"子 Agent"并行处理。
    # 例如："分析这个 CSV 文件并生成图表"→
    #   子 Agent 1: 使用 pandas 分析数据
    #   子 Agent 2: 使用 matplotlib 生成图表（可并行）
    # 每个子 Agent 运行自己完整的图循环（思考 → 调用工具 → 再思考）。

    # multi_agent_enabled: 是否启用多 Agent 主管模式
    #   - true: 启用，复杂任务自动拆分为子任务
    #   - false: 关闭，所有任务由单一 Agent 顺序执行
    multi_agent_enabled: bool = True        # 启用多Agent主管模式

    # multi_agent_max_parallel: 最大并发子 Agent 数量
    #   使用 asyncio.gather 并行执行子 Agent
    #   限制为 3 是为了控制 LLM API 并发调用数，避免触发速率限制
    multi_agent_max_parallel: int = 3       # 通过asyncio.gather的最大并发子Agent数

    # ==========================================================================
    # 【Mock 模式 ★【前端相关】】
    # ==========================================================================
    # Mock 模式是一个调试/开发功能：启用后所有 LLM 调用返回预定义的模拟响应，
    # 不会调用任何外部 API，也不消耗 API Key 额度。
    #
    # 用途：
    #   - 前端开发时不需要配置 API Key
    #   - 测试 UI 交互流程时不产生费用
    #   - 演示时不依赖网络连接
    #
    # 【前端建议】
    #   - 在设置页面显示当前模式（Mock 模式 / 正常模式）
    #   - Mock 模式下可以显示一个醒目的标识（如黄色横幅："Mock 模式已启用"）
    #   - 可以通过环境变量 MOCK_MODE_ENABLED=true 全局设置
    mock_mode_enabled: bool = False

    # ==========================================================================
    # 【LangSmith — LLM 调用追踪和调试】
    # ==========================================================================
    # LangSmith 是 LangChain 提供的 LLM 可观测性平台。
    # 开启后可以追踪每一次 LLM 调用：输入、输出、耗时、Token 消耗等。
    # 这对于：
    #   - 调试 Agent 的行为（为什么选择了这个工具？）
    #   - 性能分析（哪个环节耗时最长？）
    #   - 成本追踪（每个对话消耗了多少 Token？）
    #   非常有用。
    #
    # LangSmith 底层使用 LANGCHAIN_* 环境变量，在应用启动时由 main.py 通过 os.environ 应用。
    # 前端无需关注此配置。

    # langsmith_tracing: 是否启用 LangSmith 追踪
    #   - true: 记录所有 LLM 调用到 LangSmith
    #   - false: 不启用追踪
    langsmith_tracing: bool = False

    # langsmith_endpoint: LangSmith API 端点
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # langsmith_api_key: LangSmith API Key
    #   从 https://smith.langchain.com/settings 获取
    langsmith_api_key: str = ""

    # langsmith_project: LangSmith 项目名称
    #   用于在 LangSmith 仪表盘中区分不同项目的数据
    langsmith_project: str = "ai-agent-platform"

    # ==========================================================================
    # 以下为配置处理方法（非配置项），前端无需关注
    # ==========================================================================

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_db_url(cls, v, info):
        """
        自动组装数据库连接 URL。

        如果 database_url 已在 .env 中指定，则直接使用；
        否则从各个分离的字段（host/port/user/password/db）拼接完整 URL。

        格式：postgresql+asyncpg://user:password@host:port/dbname
        asyncpg 是高性能异步 PostgreSQL 驱动。
        """
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
        """
        将 cors_origins 字符串解析为 Python 列表。

        例如 "http://localhost:5173,http://localhost:3000"
        → ["http://localhost:5173", "http://localhost:3000"]

        这个列表被 FastAPI 的 CORSMiddleware 使用。
        """
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """
        获取同步版本的数据库 URL。

        将 asyncpg 驱动替换为 psycopg2（同步驱动），
        用于 Alembic 数据库迁移（Alembic 不支持 asyncpg）。
        """
        return self.database_url.replace("asyncpg", "psycopg2")

    @property
    def redis_url(self) -> str:
        """
        组装 Redis 连接 URL。

        格式：redis://[password@]host:port/db

        例如：redis://localhost:6379/0 或 redis://:mypassword@localhost:6379/0
        """
        pwd = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{pwd}{self.redis_host}:{self.redis_port}/{self.redis_db}"


# ==============================================================================
# 配置单例工厂
# ==============================================================================

# lru_cache 装饰器确保 Settings() 只实例化一次
# 之后每次调用 get_settings() 都返回同一个实例（缓存命中）
# 这避免了反复读取 .env 文件和创建新对象

@lru_cache
def get_settings() -> Settings:
    """
    获取设置实例（带缓存）。

    首次调用时创建 Settings 实例，后续调用返回缓存的同一个实例。
    这是 Python 中实现单例模式的常用方式。
    """
    return Settings()


# settings 模块级变量，项目中所有模块都通过 `from app.config import settings` 使用
settings = get_settings()
