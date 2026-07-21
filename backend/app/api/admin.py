"""
================================================================================
管理员 API 模块 — 仪表盘统计、LLM 配置、Mock 模式管理
================================================================================

【模块职责】
  提供系统管理相关的 API 端点，包括：
  1. 仪表盘统计数据（对话数、消息数、文档数、Agent数等）
  2. LLM 提供商配置（查看支持的模型列表、切换模型/API Key/Base URL）
  3. 管理端 RAG 知识库管理（管理员专属的文档上传/删除/统计）
  4. Mock 模式开关（调试/演示用，不消耗 API Key）

【API 设计规范】
  - 企业级安全设计：所有端点使用 POST + JSON Body（或 multipart/form-data）。
  - 敏感参数不出现在 URL 中，避免被服务器日志、代理缓存记录。
  - LLM 配置变更仅作用于当前进程（内存级修改），重启后恢复 .env 默认值。
  - 如需持久化配置变更，需修改 .env 文件后重新部署。

【端点总览】

  端点路径                    用途                             是否需要管理员密码
  ────────────────────────────────────────────────────────────────────────────
  /api/admin/dashboard        系统仪表盘统计数据                 目前未加密码保护*
  /api/admin/llm/list         列出所有LLM提供商及模型            否（公开信息）
  /api/admin/llm/update       更新LLM配置（切换模型/API Key等）  建议加密码保护*
  /api/admin/rag/upload       上传管理员知识库文档               否*
  /api/admin/rag/documents    列出管理员知识库文档               否*
  /api/admin/rag/delete       删除管理员知识库文档               否*
  /api/admin/rag/stats        管理员知识库统计                   否*
  /api/admin/models           前端获取可用模型列表               否（公开端点）
  /api/admin/mock/status      查看Mock模式状态                   否（公开端点）
  /api/admin/mock/toggle      切换Mock模式开关                   建议加密码保护*

  *注：目前代码中未强制验证管理员密码，实际部署时建议在前端路由层或网关层
  添加权限控制（如 Nginx basic auth、OAuth2、或前端路由守卫）。

================================================================================

【仪表盘统计端点详解】

  POST /api/admin/dashboard
  请求：无需参数
  响应 DashboardStats:

    {
      "total_conversations": 1024,    // 系统累计的对话会话总数
      "total_messages": 8192,         // 系统累计的消息条数（含用户消息和AI回复）
      "total_documents": 256,         // 知识库中已上传的文档总数
      "total_chunks": 10240,          // 所有文档拆分后的文本分块总数
      "total_storage_mb": 512.5,      // 知识库文档的总存储大小（MB）
      "total_agents": 8,              // 已创建的 AI Agent 配置数量
      "conversations_today": 42,      // 今日（UTC 00:00起）新增对话数
      "messages_today": 336           // 今日新增消息数
    }

  前端使用场景：
    - 管理员首页的概览面板（Dashboard）
    - 用卡片/图表展示各项指标的趋势
    - "今日"指标用 UTC 零点计算，注意与用户本地时区的差异
    - 建议定时刷新（如每 30 秒轮询一次）

  各字段的业务含义：
    ┌──────────────────────┬──────────────────────────────────────────────┐
    │ 字段                 │ 业务含义                                      │
    ├──────────────────────┼──────────────────────────────────────────────┤
    │ total_conversations  │ 反映系统的整体使用量，数值越大说明用户越活跃   │
    │ total_messages       │ 更细粒度的用量指标，可用于估算 API 调用成本    │
    │ total_documents      │ 知识库内容丰富度，越多说明知识沉淀越深         │
    │ total_chunks         │ 文档分块总数，更多chunk意味着更精细的检索粒度  │
    │ total_storage_mb     │ 存储空间占用，用于容量规划和告警               │
    │ total_agents         │ AI Agent 配置数量，反映系统的功能复杂度        │
    │ conversations_today  │ 今日活跃度指标，帮助发现异常峰值或低谷         │
    │ messages_today       │ 今日消息量，与 conversations_today 配合看      │
    │                      │ 比值（messages/conv）反映对话深度              │
    └──────────────────────┴──────────────────────────────────────────────┘

================================================================================

【LLM 配置端点详解】

  POST /api/admin/llm/list
  请求：无需参数
  响应 LLMConfigResponse:

    {
      "providers": [
        {
          "id": "qwen",                    // 提供商标识符
          "name": "通义千问 (DashScope)",    // 显示名称
          "enabled": true,                 // 是否可用（已配置 API Key）
          "models": [                      // 该提供商支持的模型列表
            "qwen-flash",                  // 最快最便宜，免费额度最充足
            "qwen-plus",                   // 性价比均衡
            "qwen-turbo",                  // 轻量快速
            "qwen-max",                    // 最强推理能力
            "qwen-plus-latest",            // 自动使用最新 plus 版本
            "qwen3.7-plus",                // 3.7 系列
            "qwen3.6-flash",               // 3.6 快速版
            "qwen3.5-flash",               // 3.5 快速版（独立免费额度）
            "qwen3.5-plus",                // 3.5 plus
            "qwen-vl-plus",                // 视觉理解模型
            "qwen-vl-max"                  // 最强视觉模型
          ],
          "default_model": "qwen-plus",    // 当前配置的默认模型
          "api_key_set": true,             // API Key 是否已配置（不返回 Key 内容）
          "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
        },
        {
          "id": "openai",
          "name": "OpenAI",
          "enabled": false,
          "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1-mini", "o1-preview"],
          "default_model": "",
          "api_key_set": false,
          "base_url": ""
        },
        {
          "id": "claude",
          "name": "Anthropic Claude",
          "enabled": false,
          "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"],
          "default_model": "",
          "api_key_set": false,
          "base_url": "https://api.anthropic.com/v1/"
        }
      ],
      "default_provider": "qwen",         // 系统默认提供商
      "active_model": "qwen-plus"         // 当前激活的模型
    }

  前端使用场景：
    - 设置页面中显示可用模型的列表
    - 根据 api_key_set 字段显示"已配置"/"未配置"状态
    - 根据 enabled 字段决定模型是否可选
    - active_model 可高亮标记当前正在使用的模型


  POST /api/admin/llm/update
  请求体 LLMConfigUpdate:
    {
      "provider": "qwen",          // 必填：要配置的提供商ID
      "model": "qwen-max",         // 可选：要切换到的模型名称（留空则使用默认）
      "api_key": "sk-xxx",         // 可选：新的 API Key（留空则不修改）
      "base_url": "https://..."    // 可选：自定义 Base URL（仅 qwen/openai 支持）
    }

  响应：
    {
      "detail": "Provider updated and active immediately.",
      "provider": "qwen",
      "model": "qwen-max",
      "api_key_set": true
    }

  重要注意事项：
    - 变更立即生效（修改内存中的 settings 对象）
    - 变更不会持久化到 .env 文件，重启服务后恢复默认值
    - 如需永久变更，请修改 .env 文件后重新部署
    - 切换提供商时如果未指定 model，会自动选择默认模型：
      qwen → qwen-plus, openai → gpt-4o-mini, claude → claude-3-5-sonnet
    - 更新后会清除 LLM 缓存，确保新配置立即被后续请求使用

================================================================================

【Mock 模式端点详解】

  Mock 模式是一种调试/演示模式。开启后，所有 LLM 对话请求将返回预设的模拟
  响应，不会实际调用 LLM API，因此不消耗任何 API Key 额度。

  适用场景：
    - 前端开发调试（无需真实 API Key 即可测试 UI 交互）
    - 产品演示（避免演示过程中的 API 调用失败）
    - 成本控制测试（验证功能流程但不消耗 Token）


  POST /api/admin/mock/status
  请求：无需参数
  响应 MockModeStatus:
    {
      "enabled": false,                    // 当前 Mock 模式是否开启
      "description": "Mock 模式已关闭..."   // 中文状态描述（可直接展示给用户）
    }

  前端使用建议：
    - 在页面顶部/设置区域显示 Mock 状态指示器
    - enabled=true 时显示橙色/黄色警告横幅："当前为 Mock 模式，对话不会调用真实 AI"
    - description 字段可直接作为 Tooltip 内容


  POST /api/admin/mock/toggle
  请求体 MockModeToggle:
    {
      "enabled": true   // true=开启Mock模式, false=关闭Mock模式
    }

  响应：
    {
      "detail": "Mock 模式已启用。所有对话将返回模拟响应。",
      "enabled": true
    }

  注意事项：
    - 切换立即生效（内存级修改）
    - 重启后恢复 .env 中 MOCK_MODE_ENABLED 的默认值
    - 如需持久化，请在 .env 中设置 MOCK_MODE_ENABLED=true 后重新部署

================================================================================

【管理员 RAG 知识库端点】

  管理员拥有独立的知识库空间（source="admin"），与用户上传的文档
  （source="user"）完全隔离。管理员知识库可用于：
    - 预设系统级知识（产品文档、FAQ、内部规范等）
    - 作为所有对话的公共知识背景


  POST /api/admin/rag/upload
  请求：multipart/form-data（字段名: file）
  功能：上传文档到管理员知识库
  响应：{ id, filename, file_type, file_size, chunk_count, status, source: "admin" }


  POST /api/admin/rag/documents
  请求：URL 查询参数 skip, limit（分页）
  功能：列出管理员知识库中的文档（仅 source="admin" 的文档）


  POST /api/admin/rag/delete
  请求体：{ "doc_id": "xxx" }
  功能：删除管理员知识库中的指定文档


  POST /api/admin/rag/stats
  请求：无需参数
  功能：管理员知识库统计（文档数、分块数）

================================================================================

【公开端点】

  POST /api/admin/models
  功能：前端获取可用模型列表（内部调用 llm/list）
  用途：聊天界面中让用户选择模型的下拉菜单数据源

================================================================================
"""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Conversation, Message, Document, DocumentChunk, AgentConfig
from app.config import settings
from app.schemas import (
    DashboardStats,
    LLMProviderInfo,
    LLMConfigResponse,
    LLMConfigUpdate,
    MockModeStatus,
    MockModeToggle,
)

router = APIRouter()


# ============================================================================
# 1. 仪表盘统计 — 系统概览数据
# ============================================================================
# 汇总系统级别的各类统计数据，包括对话、消息、文档、Agent等维度的总计和
# 当日（UTC 00:00 起）的新增数量。
#
# 统计说明：
#   total_conversations:  累计对话会话数（每次创建新对话 +1）
#   conversations_today:  今日新增对话数（UTC 零点至今）
#   total_messages:       累计消息数（含用户消息和AI回复，每条 +1）
#   messages_today:       今日新增消息数
#   total_documents:      知识库文档数
#   total_chunks:         文档分块总数（一个文档可被切分为多个 chunk）
#   total_storage_mb:     文档总存储大小（MB）
#   total_agents:         Agent 配置数
#
# 前端使用建议：
#   - 仪表盘首页卡片展示
#   - 可用 ECharts/Recharts 绘制趋势图
#   - messages_today / conversations_today 的比值反映平均对话深度

@router.post("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """汇总系统级别的统计信息。"""
    # 统计累计对话总数
    conv_count = await db.execute(select(func.count(Conversation.id)))
    total_conv = conv_count.scalar() or 0

    # 统计今日新增对话数（UTC 00:00 至今）
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_conv = await db.execute(
        select(func.count(Conversation.id))
        .where(Conversation.created_at >= today_start)
    )
    conv_today = today_conv.scalar() or 0

    # 统计累计消息总数
    msg_count = await db.execute(select(func.count(Message.id)))
    total_msg = msg_count.scalar() or 0

    # 统计今日新增消息数
    today_msg = await db.execute(
        select(func.count(Message.id))
        .where(Message.created_at >= today_start)
    )
    msg_today = today_msg.scalar() or 0

    # 统计知识库文档数量
    doc_count = await db.execute(select(func.count(Document.id)))
    total_docs = doc_count.scalar() or 0

    # 统计文档分块数量（每个文档被切分为多个chunk）
    chunk_count = await db.execute(select(func.count(DocumentChunk.id)))
    total_chunks = chunk_count.scalar() or 0

    # 统计文档总存储大小并转换为 MB
    total_size = await db.execute(select(func.sum(Document.file_size)))
    storage_mb = round((total_size.scalar() or 0) / 1024 / 1024, 2)

    # 统计 Agent 配置数量
    agent_count = await db.execute(select(func.count(AgentConfig.id)))
    total_agents = agent_count.scalar() or 0

    return DashboardStats(
        total_conversations=total_conv,
        total_messages=total_msg,
        total_documents=total_docs,
        total_chunks=total_chunks,
        total_storage_mb=storage_mb,
        total_agents=total_agents,
        conversations_today=conv_today,
        messages_today=msg_today,
    )


# ============================================================================
# 2. LLM 配置管理
# ============================================================================

# ---- LLM 提供商元数据定义 ----
# 定义系统支持的所有 LLM 提供商及其可用模型列表。
# 前端使用时：
#   - id:          用于 API 调用时指定提供商
#   - name:        用于 UI 显示（中文友好名称）
#   - models:      下拉菜单/选择器的选项列表
#   - enabled:     是否可用（取决于 API Key 是否已配置）
#   - api_key_set: 显示 Key 配置状态，true 时在 UI 中显示"已配置"绿色标记
#
# 模型选择建议（qwen 系列）：
#   免费额度充足: qwen-flash, qwen3.5-flash
#   性价比均衡:   qwen-plus, qwen3.5-plus
#   最强推理:     qwen-max
#   视觉理解:     qwen-vl-plus, qwen-vl-max

_PROVIDER_META = {
    "qwen": {
        "name": "通义千问 (DashScope)",
        "models": [
            "qwen-flash",          # 最快最便宜，免费额度最充足
            "qwen-plus",           # 性价比均衡（你的额度已用完）
            "qwen-turbo",          # 轻量快速
            "qwen-max",            # 最强推理
            "qwen-plus-latest",    # 自动使用最新 plus
            "qwen3.7-plus",        # 最新 3.7 系列
            "qwen3.6-flash",       # 3.6 快速版
            "qwen3.5-flash",       # 3.5 快速版（独立免费额度）
            "qwen3.5-plus",        # 3.5 plus
            "qwen-vl-plus",        # 视觉模型
            "qwen-vl-max",         # 视觉最强
        ],
    },
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1-mini", "o1-preview"],
    },
    "claude": {
        "name": "Anthropic Claude",
        "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"],
    },
}


# ---- 端点 2a: 列出 LLM 配置 ----
# 返回所有支持的 LLM 提供商的详细信息，包括可用模型列表、当前激活的模型、
# API Key 配置状态等。这是前端获取模型选择列表的主要数据源。
#
# 公开端点 — 无需管理员密码。
# 不返回 API Key 的实际内容（仅返回 api_key_set 布尔值）。

@router.post("/llm/list", response_model=LLMConfigResponse)
async def list_llm_config():
    """返回可用的 LLM 提供商、模型及其状态。"""
    providers = []

    for pid, meta in _PROVIDER_META.items():
        api_key = ""
        base_url = ""
        default_model = ""
        enabled = False

        # 根据不同提供商读取对应的配置
        if pid == "qwen":
            api_key = settings.dashscope_api_key
            base_url = settings.dashscope_base_url
            default_model = settings.qwen_model
            enabled = bool(api_key)
        elif pid == "openai":
            api_key = settings.openai_api_key
            base_url = settings.openai_base_url
            default_model = settings.openai_model
            enabled = bool(api_key)
        elif pid == "claude":
            api_key = settings.anthropic_api_key
            base_url = "https://api.anthropic.com/v1/"
            default_model = settings.anthropic_model
            enabled = bool(api_key)

        providers.append(LLMProviderInfo(
            id=pid,
            name=meta["name"],
            enabled=enabled,
            models=meta["models"],
            default_model=default_model,
            api_key_set=bool(api_key),
            base_url=base_url,
        ))

    # 确定当前激活的模型（根据 settings.llm_provider 选择对应提供商的模型）
    active = settings.qwen_model if settings.llm_provider == "qwen" \
        else settings.openai_model if settings.llm_provider == "openai" \
        else settings.anthropic_model

    return LLMConfigResponse(
        providers=providers,
        default_provider=settings.llm_provider,
        active_model=active,
    )


# ---- 端点 2b: 更新 LLM 配置 ----
# 用于切换 LLM 提供商/模型、更新 API Key 或 Base URL。
# 变更仅作用于当前进程（内存级），重启后恢复 .env 默认值。
#
# 建议：此端点应加管理员密码保护，防止未授权修改。
#
# 切换逻辑：
#   1. 验证 provider 是否在 _PROVIDER_META 中（防止非法提供商）
#   2. 如果切换了提供商且未指定 model，自动选择默认模型
#   3. 如果指定了 model，验证 model 是否在对应提供商的模型列表中
#   4. 更新 API Key 和 Base URL（如果提供）
#   5. 清除 LLM 缓存，确保新配置立即生效

@router.post("/llm/update")
async def update_llm_config(request: LLMConfigUpdate):
    """
    更新 LLM 提供商配置。
    变更立即生效（内存级），但 docker stack deploy 重启后会重置为 .env 默认值。
    """
    # 验证提供商是否合法
    if request.provider not in _PROVIDER_META:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")

    # 切换提供商，记录旧提供商用于判断是否需要自动选择模型
    old_provider = settings.llm_provider
    settings.llm_provider = request.provider

    # 如果切换了提供商且未指定模型，自动选择该提供商的默认模型
    if request.provider != old_provider and not request.model:
        if request.provider == "qwen":
            settings.qwen_model = "qwen-plus"
        elif request.provider == "openai":
            settings.openai_model = "gpt-4o-mini"
        elif request.provider == "claude":
            settings.anthropic_model = "claude-3-5-sonnet-20241022"

    # 如果指定了模型，验证并应用
    if request.model:
        if request.model not in _PROVIDER_META[request.provider]["models"]:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model '{request.model}' for provider '{request.provider}'"
            )
        if request.provider == "qwen":
            settings.qwen_model = request.model
        elif request.provider == "openai":
            settings.openai_model = request.model
        elif request.provider == "claude":
            settings.anthropic_model = request.model

    # 更新 API Key（如果提供了新的 Key）
    if request.api_key:
        if request.provider == "qwen":
            settings.dashscope_api_key = request.api_key
        elif request.provider == "openai":
            settings.openai_api_key = request.api_key
        elif request.provider == "claude":
            settings.anthropic_api_key = request.api_key

    # 更新 Base URL（仅 qwen 和 openai 支持自定义 Base URL）
    if request.base_url:
        if request.provider == "qwen":
            settings.dashscope_base_url = request.base_url
        elif request.provider == "openai":
            settings.openai_base_url = request.base_url

    # 清除 LLM 缓存，确保新配置被后续请求使用
    from app.agent.llm import _llm_cache
    _llm_cache.clear()

    current_model = (
        settings.qwen_model if request.provider == "qwen"
        else settings.openai_model if request.provider == "openai"
        else settings.anthropic_model
    )

    return {
        "detail": "Provider updated and active immediately.",
        "provider": request.provider,
        "model": current_model,
        "api_key_set": bool(request.api_key),
    }


# ============================================================================
# 3. 管理员 RAG 知识库管理
# ============================================================================
# 管理员有独立的知识库空间（source="admin"），与用户知识库（source="user"）
# 完全隔离。管理员上传的文档不会与用户文档混在一起。

from fastapi import UploadFile, File
from app.shared import upload_and_index_document


# ---- 列出管理员文档 ----
# 仅返回 source="admin" 的文档（管理员专属空间）
# 注意：此端点使用 URL 查询参数（skip, limit），与其他 POST+JSON 端点不同。
# 这是一个例外设计，因为这些参数不包含敏感信息。

@router.post("/rag/documents")
async def list_admin_documents(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """列出管理员上传的文档（仅 source="admin" 的文档）。"""
    result = await db.execute(
        select(Document)
        .where(Document.source == "admin")
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    docs = result.scalars().all()
    return [
        {
            "id": d.id, "filename": d.filename, "file_type": d.file_type,
            "file_size": d.file_size, "chunk_count": d.chunk_count,
            "status": d.status, "source": d.source,
            "created_at": d.created_at.isoformat(),
        }
        for d in docs
    ]


# ---- 上传管理员文档 ----
# 将文档上传到管理员知识库（source="admin"）。
# 请求方式：multipart/form-data（字段名: file）
# 支持格式：PDF, DOCX, TXT, MD

@router.post("/rag/upload")
async def upload_admin_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """上传文档到管理员知识库（与用户知识库隔离）。"""
    doc = await upload_and_index_document(file, db, source="admin")
    return {
        "id": doc.id, "filename": doc.filename, "file_type": doc.file_type,
        "file_size": doc.file_size, "chunk_count": doc.chunk_count,
        "status": doc.status, "source": doc.source,
    }


# ---- 删除管理员文档 ----
# 删除管理员知识库中的指定文档（仅限 source="admin" 的文档）。
# 安全性：通过 doc_id + source="admin" 双重校验，防止误删用户文档。

@router.post("/rag/delete")
async def delete_admin_document(doc_id: str = Body(..., embed=True), db: AsyncSession = Depends(get_db)):
    """删除管理员知识库中的文档。"""
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.source == "admin")
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Admin document not found")

    from sqlalchemy import delete
    await db.execute(delete(Document).where(Document.id == doc_id))
    await db.commit()
    return {"detail": f"Deleted {doc.filename}"}


# ---- 管理员知识库统计 ----
# 仅统计 source="admin" 的文档和分块数量。
# 与用户知识库统计完全隔离。

@router.post("/rag/stats")
async def admin_rag_stats(db: AsyncSession = Depends(get_db)):
    """管理员知识库统计（仅统计 source="admin" 的文档）。"""
    doc_count = await db.execute(
        select(func.count(Document.id)).where(Document.source == "admin")
    )
    chunk_count = await db.execute(
        select(func.count(DocumentChunk.id))
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(Document.source == "admin")
    )
    return {
        "document_count": doc_count.scalar() or 0,
        "chunk_count": chunk_count.scalar() or 0,
    }


# ============================================================================
# 4. 前端可访问的模型列表（公开端点）
# ============================================================================
# 为前端聊天界面提供可用模型列表，内部复用 llm/list 的逻辑。
# 用户在聊天界面可以通过下拉菜单切换不同的 LLM 模型。

@router.post("/models", response_model=LLMConfigResponse)
async def get_public_models():
    """前端获取可用模型列表的公开端点。"""
    return await list_llm_config()


# ============================================================================
# 5. Mock 模式管理
# ============================================================================
# Mock 模式：开启后所有 LLM 请求返回预设的模拟响应，不调用真实 API。
# 适用场景：前端开发调试、产品演示、功能测试（不消耗 Token）。

# ---- 查看 Mock 模式状态 ----
# 公开端点，前端可直接调用来判断是否需要显示 Mock 模式提示横幅。

@router.post("/mock/status", response_model=MockModeStatus)
async def get_mock_status():
    """获取当前 Mock 模式的开关状态。"""
    return MockModeStatus(
        enabled=settings.mock_mode_enabled,
        description=(
            "Mock 模式已启用 — 所有对话将返回模拟响应，不消耗 API Key。"
            if settings.mock_mode_enabled
            else "Mock 模式已关闭 — 对话将使用真实的 LLM API。"
        ),
    )


# ---- 切换 Mock 模式 ----
# 建议加管理员密码保护。切换后立即生效（内存级修改），重启后恢复 .env 默认值。
#
# 前端交互建议：
#   - 使用 Switch/Toggle 组件
#   - 切换前弹出确认对话框："确定要开启 Mock 模式吗？所有对话将不调用真实 AI。"
#   - 开启后在页面顶部显示显眼的橙色/黄色警告横幅

@router.post("/mock/toggle")
async def toggle_mock_mode(request: MockModeToggle):
    """
    全局切换 Mock 模式的开关。
    变更立即生效（内存级），但 docker stack deploy 重启后会重置。
    如需持久化，请在 .env 中设置 MOCK_MODE_ENABLED=true。
    """
    settings.mock_mode_enabled = request.enabled
    status = "已启用" if request.enabled else "已关闭"
    return {
        "detail": f"Mock 模式{status}。"
        + (" 所有对话将返回模拟响应。" if request.enabled else " 对话将使用真实 LLM API。"),
        "enabled": request.enabled,
    }
