"""
Pydantic request/response schemas — enterprise AI agent API design.
All read operations use POST with JSON body (never expose params in URLs).

================================================================================
  模块级说明（中文）
================================================================================

本文件定义了 AI Agent 平台 API 的所有请求/响应数据模型（Pydantic Schemas）。

核心设计原则：
  1. 所有 API 操作（增删改查）均使用 POST 方法 + JSON 请求体
  2. 资源 ID 始终放在 POST Body 中，**绝不**出现在 URL 路径或查询参数中
  3. 每个 Schema 类对应一个特定的 API 端点（endpoint）
  4. 前端开发者可通过本文件快速了解每个接口需要传什么、会收到什么

模型分组概览：
  - 公共/基础模型：PaginationRequest, IdRequest（被其他模型继承复用）
  - Chat 聊天模块：ChatRequest, ChatResponse, MessageOut, AttachmentInfo, MockModeToggle, MockModeStatus
  - Conversation 会话模块：ConversationCreate, ConversationListRequest, ConversationGetRequest,
                              ConversationDeleteRequest, ConversationTitleUpdate, ConversationOut, ConversationDetail
  - Document/RAG 知识库模块：RagDocumentListRequest, RagDocumentGetRequest, RagDocumentDeleteRequest,
                              DocumentOut, RagSearchRequest, RagSearchResult
  - Agent 智能体配置模块：AgentListRequest, AgentGetRequest, AgentDeleteRequest,
                           AgentConfigCreate, AgentConfigUpdate, AgentConfigOut
  - Health 健康检查模块：HealthCheck
  - Admin 管理/系统配置模块：DashboardStats, LLMProviderInfo, LLMConfigResponse, LLMConfigUpdate

注意事项：
  - 标记为 `Optional` 的字段可以不传，后端会使用默认值
  - 标记为 `Field(...)` 的字段为必填（required），省略会导致 422 校验错误
  - `from_attributes = True` 表示该模型可以从 ORM 对象（SQLAlchemy）直接转换，用于 API 响应
================================================================================
"""
from datetime import datetime
from typing import Any, Optional, List, Literal

from pydantic import BaseModel, Field, field_validator


# ============================================================
#  Common / Base  —  公共基础模型
# 说明：这些是基础 Schema，被其他模块的请求模型继承使用，
#       避免了在每个模块中重复定义相同的分页和 ID 校验逻辑。
# ============================================================

class PaginationRequest(BaseModel):
    """
    Reusable paginated list request.
    通用分页请求模型（基类）。

    对应端点：所有"列表查询"接口（如会话列表、文档列表、Agent列表）
    前端发送：{ "skip": 0, "limit": 50 }
    前端接收：N/A（此模型仅用于请求，不用于响应）
    必填字段：无（全部有默认值）
    """
    skip: int = Field(0, ge=0, description="Records to skip")
    # skip — 跳过的记录数，ge=0 表示必须 >=0，用于分页偏移
    limit: int = Field(50, ge=1, le=200, description="Max records to return")
    # limit — 最大返回条数，ge=1 最少1条，le=200 最多200条


class IdRequest(BaseModel):
    """
    Single-resource lookup by id (POST body, never URL path).
    单资源 ID 查询请求模型（基类）。

    对应端点：所有"按ID查询单个资源"的接口（如获取会话详情、获取文档详情、获取Agent详情）
    前端发送：{ "id": "resource-uuid-string" }
    前端接收：N/A（此模型仅用于请求）
    必填字段：id（资源唯一标识符）

    安全特性：id 字段会自动过滤路径遍历字符（../、\\、\\0 等），防止注入攻击
    """
    id: str = Field(..., min_length=1, max_length=64, description="Resource identifier")
    # id — 资源ID，... 表示必填，min_length=1 不允许空字符串，max_length=64 最长64字符

    @field_validator("id")
    @classmethod
    def sanitize_id(cls, v: str) -> str:
        """
        Reject IDs containing path traversal or injection chars.
        拒绝包含路径遍历或注入字符的 ID，确保 API 安全。
        会自动去除首尾空白字符。
        """
        dangerous = {"..", "/", "\\", "\0", "\n", "\r"}
        # 危险字符集：路径遍历符、目录分隔符、空字节、换行符
        for ch in dangerous:
            if ch in v:
                raise ValueError(f"id contains invalid character: {repr(ch)}")
                # 发现非法字符时抛出 ValueError，框架自动返回 422 错误
        return v.strip()
        # 返回去除首尾空白后的合法 ID


# ============================================================
#  Chat  —  聊天模块
# 说明：Chat 模块处理用户与 AI 的对话交互，包括消息发送、
#       附件上传、流式/非流式响应、Mock 模式等。
# ============================================================

class AttachmentInfo(BaseModel):
    """
    附件信息模型。

    对应端点：POST /api/chat（作为 ChatRequest.attachments 的数组元素）
    前端发送：{ "id": "xxx", "filename": "报告.pdf", "url": "http://...", "type": "application/pdf", "size": 102400 }
    前端接收：N/A（此模型仅作为请求体的一部分，无独立端点）
    必填字段：全部字段
    """
    id: str = Field(..., min_length=1, max_length=128)
    # id — 附件唯一标识，1-128字符
    filename: str = Field(..., min_length=1, max_length=255)
    # filename — 附件文件名（含扩展名），如 "报告.pdf"，1-255字符
    url: str = Field(..., min_length=1, max_length=512)
    # url — 附件访问地址，1-512字符
    type: str = Field(..., min_length=1, max_length=128)  # 文件MIME类型，例如: image/png, application/pdf
    size: int = Field(..., ge=0)
    # size — 文件大小（字节），ge=0 必须 >=0


class ChatRequest(BaseModel):
    """
    聊天请求模型。

    对应端点：POST /api/chat —— 发送消息并获取 AI 回复
    前端发送：{ "message": "你好", "conversation_id": "xxx", "stream": true, ... }
    前端接收：ChatResponse（非流式）或 SSE 事件流（流式）
    必填字段：message
    可选字段：conversation_id, agent_id, stream, use_rag, attachments, model_provider, mock_mode
    """
    message: str = Field(..., min_length=1, max_length=100000, description="User message")
    # message — 用户消息内容，必填，最少1字符，最多100000字符
    conversation_id: Optional[str] = Field(None, max_length=64)
    # conversation_id — 会话ID，可选。不传则后端自动创建新会话
    agent_id: Optional[str] = Field(None, max_length=64)
    # agent_id — 智能体ID，可选。不传则使用默认智能体
    stream: bool = True
    # stream — 是否启用 SSE 流式输出，默认 true（流式），设为 false 则返回完整 JSON 响应
    use_rag: bool = True
    # use_rag — 是否启用 RAG 知识库检索增强，默认 true
    attachments: List[AttachmentInfo] = Field(default_factory=list, max_length=20)
    # attachments — 附件列表，最多20个附件
    model_provider: Optional[str] = Field(None, max_length=32, description="Override LLM provider: qwen/openai/claude")
    # model_provider — 覆盖默认 LLM 提供商，可选值: qwen / openai / claude
    mock_mode: bool = Field(False, description="Enable mock mode — returns simulated responses without calling LLM API")
    # mock_mode — Mock模式开关，true时返回模拟响应不调用真实LLM（用于开发调试）


class MockModeStatus(BaseModel):
    """
    Mock mode global status.
    Mock 模式全局状态模型。

    对应端点：GET /api/chat/mock-mode/status —— 查询 Mock 模式当前状态
    前端发送：无（GET 请求，无请求体）
    前端接收：{ "enabled": false, "description": "Mock mode is disabled" }
    """
    enabled: bool = False
    # enabled — Mock 模式是否启用
    description: str = ""
    # description — Mock 模式状态描述文本


class MockModeToggle(BaseModel):
    """
    Toggle mock mode on/off.
    Mock 模式开关请求模型。

    对应端点：POST /api/chat/mock-mode/toggle —— 开启/关闭 Mock 模式
    前端发送：{ "enabled": true }
    前端接收：MockModeStatus（切换后的新状态）
    必填字段：enabled
    """
    enabled: bool = Field(..., description="Enable or disable mock mode")
    # enabled — 必填，true 开启 Mock 模式 / false 关闭


class MessageOut(BaseModel):
    """
    消息输出模型（API 响应用）。

    对应端点：包含于 ChatResponse、ConversationDetail 等响应中
    前端发送：N/A（仅用于响应）
    前端接收：{ "id": 1, "role": "user", "content": "你好", "metadata": null, "created_at": "2025-01-01T00:00:00" }
    注意：`from_attributes = True` 表示可从 ORM 对象（数据库模型）直接转换
    """
    id: int
    # id — 消息数字ID（数据库自增主键）
    role: str
    # role — 消息角色，通常为 "user"（用户）或 "assistant"（AI助手）
    content: str
    # content — 消息正文内容
    metadata: Optional[dict] = None
    # metadata — 消息元数据（JSON 字典），可能包含 RAG 检索结果、工具调用信息等
    created_at: datetime
    # created_at — 消息创建时间（ISO 8601 格式）

    class Config:
        from_attributes = True
        # 启用 ORM 模式，允许从 SQLAlchemy 模型对象直接创建此 Schema 实例


class ChatResponse(BaseModel):
    """
    聊天响应模型。

    对应端点：POST /api/chat 的响应（非流式模式，stream=false 时返回）
    前端发送：N/A（仅用于响应）
    前端接收：{ "conversation_id": "uuid-string", "message": { ...MessageOut } }
    注意：流式模式（stream=true）下，此模型不被使用；响应通过 SSE 事件逐块推送
    """
    conversation_id: str
    # conversation_id — 会话ID，前端应保存此值用于后续消息的 conversation_id 参数
    message: MessageOut
    # message — AI 返回的回复消息对象（包含角色、内容、时间等）


# ============================================================
#  Conversation  —  会话模块
# 说明：管理对话会话的完整生命周期，包括创建、列表查询、
#       详情查看、标题更新、删除等操作。所有ID通过POST Body传递。
# ============================================================

class ConversationCreate(BaseModel):
    """
    会话创建请求模型。

    对应端点：POST /api/conversations/create —— 创建新会话
    前端发送：{ "title": "我的对话", "agent_id": "xxx" }
    前端接收：ConversationOut（新创建的会话信息）
    必填字段：无（全部有默认值）
    """
    title: str = Field("New Conversation", min_length=1, max_length=200)
    # title — 会话标题，默认 "New Conversation"，1-200字符
    agent_id: Optional[str] = Field(None, max_length=64)
    # agent_id — 关联的智能体ID，可选。不传则使用默认智能体


class ConversationListRequest(PaginationRequest):
    """
    List conversations by POST body (never query string).
    会话列表查询请求模型。

    对应端点：POST /api/conversations/list —— 分页获取会话列表
    前端发送：{ "skip": 0, "limit": 20 }
    前端接收：ConversationOut[]（会话对象数组，具体封装在外层响应中）
    必填字段：无（继承 PaginationRequest，全部有默认值）
    继承自：PaginationRequest（复用 skip/limit 分页字段）
    """
    pass


class ConversationGetRequest(IdRequest):
    """
    Get a single conversation — id in POST body only.
    会话详情查询请求模型。

    对应端点：POST /api/conversations/get —— 获取单个会话详情（含消息列表）
    前端发送：{ "id": "conversation-uuid" }
    前端接收：ConversationDetail（包含消息列表的完整会话信息）
    必填字段：id（会话唯一标识符）
    继承自：IdRequest（复用 id 字段及其安全校验）
    """
    pass


class ConversationDeleteRequest(IdRequest):
    """
    Delete a conversation — id in POST body only.
    会话删除请求模型。

    对应端点：POST /api/conversations/delete —— 删除指定会话
    前端发送：{ "id": "conversation-uuid" }
    前端接收：{ "success": true } 或类似确认信息
    必填字段：id（要删除的会话唯一标识符）
    继承自：IdRequest（复用 id 字段及其安全校验）
    注意：删除操作不可逆，前端应弹出确认对话框
    """
    pass


class ConversationTitleUpdate(BaseModel):
    """
    Update title — all params in POST body.
    会话标题更新请求模型。

    对应端点：POST /api/conversations/update-title —— 修改会话标题
    前端发送：{ "conversation_id": "uuid", "title": "新的标题" }
    前端接收：ConversationOut（更新后的会话信息）
    必填字段：conversation_id, title
    """
    conversation_id: str = Field(..., min_length=1, max_length=64)
    # conversation_id — 要修改的会话ID，必填，1-64字符
    title: str = Field(..., min_length=1, max_length=200)
    # title — 新的会话标题，必填，1-200字符


class ConversationOut(BaseModel):
    """
    会话输出模型（API 响应用，摘要信息）。

    对应端点：包含于会话列表响应、会话创建响应中
    前端发送：N/A（仅用于响应）
    前端接收：{ "id": "uuid", "title": "标题", "agent_id": "xxx", "created_at": "2025-01-01T00:00:00",
                 "updated_at": "2025-01-01T00:00:00", "message_count": 5 }
    注意：message_count 为会话中的消息总数，用于列表页显示
    """
    id: str
    # id — 会话唯一标识（UUID 字符串）
    title: str
    # title — 会话标题
    agent_id: Optional[str]
    # agent_id — 关联的智能体ID，可能为 None
    created_at: datetime
    # created_at — 会话创建时间
    updated_at: datetime
    # updated_at — 会话最后更新时间
    message_count: int = 0
    # message_count — 消息总数，默认0

    class Config:
        from_attributes = True
        # 启用 ORM 模式


class ConversationDetail(ConversationOut):
    """
    会话详情模型（继承 ConversationOut，额外包含消息列表）。

    对应端点：POST /api/conversations/get 的响应
    前端发送：N/A（仅用于响应）
    前端接收：{ ...ConversationOut 所有字段, "messages": [ ...MessageOut[] ] }
    继承自：ConversationOut
    """
    messages: List[MessageOut] = []
    # messages — 该会话下的所有消息列表，按时间排序，默认空数组


# ============================================================
#  Document / RAG  —  知识库/文档检索模块
# 说明：管理上传到知识库的文档（PDF、Word等），支持文档的
#       CRUD 操作以及语义检索（RAG Search）。
# ============================================================

class RagDocumentListRequest(PaginationRequest):
    """
    List documents — pagination in POST body.
    知识库文档列表查询请求模型。

    对应端点：POST /api/documents/list —— 分页获取文档列表
    前端发送：{ "skip": 0, "limit": 20 }
    前端接收：DocumentOut[]（文档对象数组）
    必填字段：无（继承 PaginationRequest）
    继承自：PaginationRequest
    """
    pass


class RagDocumentGetRequest(IdRequest):
    """
    Get a single document — id in POST body.
    文档详情查询请求模型。

    对应端点：POST /api/documents/get —— 获取单个文档详情
    前端发送：{ "id": "document-uuid" }
    前端接收：DocumentOut（文档详细信息）
    必填字段：id
    继承自：IdRequest
    """
    pass


class RagDocumentDeleteRequest(IdRequest):
    """
    Delete a document — id in POST body.
    文档删除请求模型。

    对应端点：POST /api/documents/delete —— 删除指定文档
    前端发送：{ "id": "document-uuid" }
    前端接收：{ "success": true }
    必填字段：id
    继承自：IdRequest
    注意：删除文档同时会删除所有关联的向量分块（chunks）
    """
    pass


class DocumentOut(BaseModel):
    """
    文档输出模型（API 响应用）。

    对应端点：包含于文档列表、文档详情响应中
    前端发送：N/A（仅用于响应）
    前端接收：{ "id": "uuid", "filename": "报告.pdf", "file_type": "pdf", "file_size": 102400,
                 "chunk_count": 15, "status": "completed", "created_at": "2025-01-01T00:00:00" }
    status 字段含义：
      - "processing" — 文档正在解析和向量化
      - "completed"  — 处理完成，可用于检索
      - "failed"     — 处理失败
    """
    id: str
    # id — 文档唯一标识
    filename: str
    # filename — 原始文件名
    file_type: str
    # file_type — 文件类型（pdf / docx / txt / md 等）
    file_size: int
    # file_size — 文件大小（字节）
    chunk_count: int
    # chunk_count — 文档被切分为多少个向量分块
    status: str
    # status — 处理状态（processing / completed / failed）
    created_at: datetime
    # created_at — 文档上传/创建时间

    class Config:
        from_attributes = True
        # 启用 ORM 模式


class RagSearchResult(BaseModel):
    """
    RAG 检索结果模型（单个检索分块）。

    对应端点：包含于 POST /api/documents/search 响应的 results 数组中
    前端发送：N/A（仅用于响应）
    前端接收：{ "chunk_id": "xxx", "document_id": "yyy", "filename": "文档.pdf",
                 "content": "匹配的文本片段...", "score": 0.89 }
    score 说明：0.0-1.0 之间的余弦相似度分数，越高表示语义越接近
    """
    chunk_id: str
    # chunk_id — 分块唯一标识
    document_id: str
    # document_id — 所属文档ID
    filename: str
    # filename — 所属文档文件名
    content: str
    # content — 匹配到的文本片段内容
    score: float
    # score — 余弦相似度分数（0.0-1.0），越高越相关


class RagSearchRequest(BaseModel):
    """
    RAG 语义检索请求模型。

    对应端点：POST /api/documents/search —— 在知识库中语义搜索
    前端发送：{ "query": "什么是人工智能？", "top_k": 4 }
    前端接收：RagSearchResult[]（检索结果数组）
    必填字段：query
    可选字段：top_k（默认4，范围1-20）
    """
    query: str = Field(..., min_length=1, max_length=5000)
    # query — 搜索查询文本，必填，1-5000字符
    top_k: int = Field(4, ge=1, le=20)
    # top_k — 返回最相似的分块数量，ge=1 至少1个，le=20 最多20个


# ============================================================
#  Agent Config  —  智能体配置模块
# 说明：管理 AI 智能体（Agent）的配置，包括系统提示词、
#       模型参数、工具开关、RAG 参数、委托权限等。
# ============================================================

class AgentListRequest(PaginationRequest):
    """
    List agents — pagination in POST body.
    智能体列表查询请求模型。

    对应端点：POST /api/agents/list —— 分页获取智能体列表
    前端发送：{ "skip": 0, "limit": 20 }
    前端接收：AgentConfigOut[]（智能体对象数组）
    必填字段：无（继承 PaginationRequest）
    继承自：PaginationRequest
    """
    pass


class AgentGetRequest(IdRequest):
    """
    Get a single agent — id in POST body.
    智能体详情查询请求模型。

    对应端点：POST /api/agents/get —— 获取单个智能体配置
    前端发送：{ "id": "agent-uuid" }
    前端接收：AgentConfigOut（智能体完整配置）
    必填字段：id
    继承自：IdRequest
    """
    pass


class AgentDeleteRequest(IdRequest):
    """
    Delete an agent — id in POST body.
    智能体删除请求模型。

    对应端点：POST /api/agents/delete —— 删除指定智能体
    前端发送：{ "id": "agent-uuid" }
    前端接收：{ "success": true }
    必填字段：id
    继承自：IdRequest
    注意：被保护（is_protected=true）的智能体无法删除
    """
    pass


class AgentConfigCreate(BaseModel):
    """
    智能体创建请求模型。

    对应端点：POST /api/agents/create —— 创建新智能体
    前端发送：
      {
        "name": "客服助手",
        "description": "处理客户咨询",
        "system_prompt": "你是一个专业的客服...",
        "temperature": 0.7,
        "max_tokens": 4096,
        "enabled_tools": ["web_search", "calculator"],
        "rag_top_k": 4,
        "rag_similarity_threshold": 0.5,
        "allow_delegation": true
      }
    前端接收：AgentConfigOut（新创建的智能体信息）
    必填字段：name
    其他字段均有默认值
    """
    name: str = Field(..., min_length=1, max_length=100)
    # name — 智能体名称，必填，1-100字符
    description: str = Field("", max_length=500)
    # description — 智能体描述，默认空字符串，最多500字符
    system_prompt: str = Field("You are a helpful AI assistant.", max_length=5000)
    # system_prompt — 系统提示词（System Prompt），定义智能体角色和行为，默认通用助手提示词，最多5000字符
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    # temperature — 模型温度参数，默认0.7，ge=0.0 不低于0，le=2.0 不高于2
    #   值越高回复越随机/有创意，值越低回复越确定/保守
    max_tokens: int = Field(4096, ge=1, le=131072)
    # max_tokens — 单次回复最大 Token 数，默认4096，ge=1 至少1个，le=131072 上限约128K
    enabled_tools: List[str] = Field(default_factory=list, max_length=50)
    # enabled_tools — 启用的工具列表（工具名称字符串数组），默认空数组（不启用任何工具），最多50个
    rag_top_k: int = Field(4, ge=1, le=20)
    # rag_top_k — RAG 检索时返回的 Top-K 分块数，默认4，ge=1 最少1，le=20 最多20
    rag_similarity_threshold: float = Field(0.5, ge=0.0, le=1.0)
    # rag_similarity_threshold — RAG 检索相似度阈值，默认0.5，ge=0.0 不低于0，le=1.0 不高于1
    #   低于此阈值的检索结果将被过滤，值越高检索越精准但可能结果越少
    allow_delegation: bool = Field(True, description="Allow other agents to delegate tasks to this agent")
    # allow_delegation — 是否允许其他智能体将任务委托给此智能体，默认 true（允许）


class AgentConfigUpdate(BaseModel):
    """
    智能体更新请求模型。

    对应端点：POST /api/agents/update —— 更新指定智能体配置
    前端发送：
      {
        "agent_id": "uuid",
        "name": "新名称",        // 可选，只传需要更新的字段
        "temperature": 0.5       // 可选
      }
    前端接收：AgentConfigOut（更新后的智能体信息）
    必填字段：agent_id
    其他字段全部可选（Optional），前端只需传需要更新的字段，未传字段保持原值不变
    """
    agent_id: str = Field(..., min_length=1, max_length=64)
    # agent_id — 要更新的智能体ID，必填，1-64字符
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    # name — 新的智能体名称，可选，1-100字符
    description: Optional[str] = Field(None, max_length=500)
    # description — 新的描述，可选，最多500字符
    system_prompt: Optional[str] = Field(None, max_length=5000)
    # system_prompt — 新的系统提示词，可选，最多5000字符
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    # temperature — 新的温度参数，可选，0.0-2.0
    max_tokens: Optional[int] = Field(None, ge=1, le=131072)
    # max_tokens — 新的最大Token数，可选，1-131072
    enabled_tools: Optional[List[str]] = Field(None, max_length=50)
    # enabled_tools — 新的工具列表，可选，最多50个。注意：传值会完全替换原列表
    rag_top_k: Optional[int] = Field(None, ge=1, le=20)
    # rag_top_k — 新的 Top-K 参数，可选，1-20
    rag_similarity_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    # rag_similarity_threshold — 新的相似度阈值，可选，0.0-1.0
    is_default: Optional[bool] = None
    # is_default — 是否设为默认智能体，可选。设为 true 会将此 Agent 标记为系统默认
    allow_delegation: Optional[bool] = None
    # allow_delegation — 是否允许委托，可选


class AgentConfigOut(BaseModel):
    """
    智能体输出模型（API 响应用）。

    对应端点：包含于智能体列表、详情、创建、更新响应中
    前端发送：N/A（仅用于响应）
    前端接收：
      {
        "id": "uuid", "name": "客服助手", "description": "处理咨询",
        "system_prompt": "你是一个...", "temperature": 0.7, "max_tokens": 4096,
        "enabled_tools": ["web_search"], "rag_top_k": 4, "rag_similarity_threshold": 0.5,
        "is_default": false, "is_protected": false, "allow_delegation": true
      }
    注意：
      - is_protected=true 的智能体是系统保留的，前端应禁止删除按钮
      - enabled_tools 返回的是工具名称字符串数组，前端可根据此列表渲染工具开关
    """
    id: str
    # id — 智能体唯一标识
    name: str
    # name — 智能体名称
    description: str
    # description — 智能体描述
    system_prompt: str
    # system_prompt — 系统提示词
    temperature: float
    # temperature — 温度参数
    max_tokens: int
    # max_tokens — 最大Token数
    enabled_tools: List[str]
    # enabled_tools — 已启用的工具列表
    rag_top_k: int
    # rag_top_k — RAG Top-K 参数
    rag_similarity_threshold: float
    # rag_similarity_threshold — RAG 相似度阈值
    is_default: bool
    # is_default — 是否为默认智能体。前端可据此高亮显示默认智能体
    is_protected: bool = False
    # is_protected — 是否为受保护智能体（系统内置），默认false。受保护的智能体不允许删除或修改核心配置
    allow_delegation: bool = True
    # allow_delegation — 是否允许任务委托，默认true

    class Config:
        from_attributes = True
        # 启用 ORM 模式


# ============================================================
#  Health  —  健康检查模块
# 说明：提供系统各组件的运行状态检查，用于监控和运维。
# ============================================================

class HealthCheck(BaseModel):
    """
    系统健康检查响应模型。

    对应端点：POST /api/health（或 GET /api/health）—— 检查系统各组件状态
    前端发送：无（或空请求体）
    前端接收：
      {
        "status": "ok",
        "database": "connected",
        "redis": "connected",
        "memory": { "used_gb": 2.5, "total_gb": 16 },
        "llm_provider": "qwen",
        "version": "1.0.0"
      }
    前端用途：在管理面板中展示各服务组件的在线状态，用于故障排查
    """
    status: str = "ok"
    # status — 整体状态，"ok" 正常 / "degraded" 部分降级 / "error" 故障
    database: str = "unknown"
    # database — 数据库连接状态，"connected" / "disconnected" / "unknown"
    redis: str = "unknown"
    # redis — Redis 缓存连接状态，"connected" / "disconnected" / "unknown"
    memory: dict | None = None
    # memory — 内存使用情况（字典），如 { "used_gb": 2.5, "total_gb": 16 }，可能为 None
    llm_provider: str = "unknown"
    # llm_provider — 当前使用的 LLM 提供商名称
    version: str = "1.0.0"
    # version — 系统版本号


# ============================================================
#  Admin / System Config  —  管理后台/系统配置模块
# 说明：提供仪表盘统计数据、LLM 提供商配置等管理功能。
# ============================================================

class DashboardStats(BaseModel):
    """
    仪表盘统计数据响应模型。

    对应端点：POST /api/admin/dashboard —— 获取仪表盘汇总数据
    前端发送：无（或空请求体）
    前端接收：
      {
        "total_conversations": 120, "total_messages": 3500,
        "total_documents": 45, "total_chunks": 1200,
        "total_storage_mb": 156.8, "total_agents": 5,
        "conversations_today": 12, "messages_today": 240
      }
    前端用途：在管理面板首页（Dashboard）展示关键运营数据
    """
    total_conversations: int = 0
    # total_conversations — 会话总数
    total_messages: int = 0
    # total_messages — 消息总数
    total_documents: int = 0
    # total_documents — 文档总数
    total_chunks: int = 0
    # total_chunks — 向量分块总数
    total_storage_mb: float = 0
    # total_storage_mb — 文档存储总大小（MB）
    total_agents: int = 0
    # total_agents — 智能体总数
    conversations_today: int = 0
    # conversations_today — 今日新增会话数
    messages_today: int = 0
    # messages_today — 今日新增消息数


class LLMProviderInfo(BaseModel):
    """
    LLM 提供商信息模型。

    对应端点：包含于 LLMConfigResponse.providers 数组中
    前端发送：N/A（仅用于响应）
    前端接收：
      {
        "id": "qwen", "name": "通义千问", "enabled": true,
        "models": ["qwen-turbo", "qwen-plus"], "default_model": "qwen-turbo",
        "api_key_set": true, "base_url": "https://dashscope.aliyuncs.com/api/v1"
      }
    注意：api_key_set 只返回 true/false，不返回实际的 API Key 值（安全考虑）
    """
    id: str = Field(..., description="Provider key: qwen/openai/claude")
    # id — 提供商唯一标识键，如 qwen / openai / claude
    name: str = Field(..., description="Display name")
    # name — 提供商显示名称，如 "通义千问" / "OpenAI" / "Claude"
    enabled: bool = False
    # enabled — 是否已启用
    models: List[str] = Field(default_factory=list)
    # models — 该提供商支持的模型列表
    default_model: str = ""
    # default_model — 默认使用的模型名称
    api_key_set: bool = False
    # api_key_set — API Key 是否已配置（true/false，不暴露实际 Key 值）
    base_url: str = ""
    # base_url — API 基础地址


class LLMConfigResponse(BaseModel):
    """
    LLM 配置查询响应模型。

    对应端点：POST /api/admin/llm-config —— 获取 LLM 配置信息
    前端发送：无（或空请求体）
    前端接收：
      {
        "providers": [ ...LLMProviderInfo[] ],
        "default_provider": "qwen",
        "active_model": "qwen-turbo"
      }
    前端用途：在 LLM 配置页面展示所有提供商及其状态，高亮当前激活的提供商和模型
    """
    providers: List[LLMProviderInfo]
    # providers — 所有 LLM 提供商配置列表
    default_provider: str = ""
    # default_provider — 默认提供商 ID
    active_model: str = ""  # 当前实际使用的模型名称 The currently active model name
    # active_model — 当前激活使用的模型名称（如 "qwen-turbo"）


class LLMConfigUpdate(BaseModel):
    """
    LLM 配置更新请求模型。

    对应端点：POST /api/admin/llm-config/update —— 更新 LLM 提供商配置
    前端发送：
      {
        "provider": "qwen",       // 必填
        "api_key": "sk-xxx",      // 可选
        "base_url": "https://...",// 可选
        "model": "qwen-plus",     // 可选
        "enabled": true           // 可选
      }
    前端接收：LLMConfigResponse（更新后的完整配置）
    必填字段：provider
    其他字段可选：未传的字段保持原值不变
    """
    provider: str = Field(..., min_length=1, max_length=32)
    # provider — 要配置的提供商 ID，必填，1-32字符，如 "qwen" / "openai" / "claude"
    api_key: Optional[str] = Field(None, max_length=512)
    # api_key — API 密钥，可选，最多512字符
    base_url: Optional[str] = Field(None, max_length=256)
    # base_url — API 基础地址，可选，最多256字符
    model: Optional[str] = Field(None, max_length=128)
    # model — 要使用的模型名称，可选，最多128字符，如 "qwen-plus"
    enabled: Optional[bool] = None
    # enabled — 是否启用该提供商，可选


# =================================================================================
#  模型-端点对照总表（Summary Table）
#  ═════════════════════════════════════════════════════════════════════════════
#  以下表格列出了本文件中所有数据模型与其对应 API 端点的映射关系，
#  方便前端开发者快速查找每个接口应该使用哪个请求/响应模型。
# =================================================================================
#
#  ┌──────────────────────────────────────┬────────────────────────────────────┬───────────────────┐
#  │  API 端点 (Endpoint)                 │  请求模型 (Request)                │  响应模型 (Response)│
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/chat                      │  ChatRequest                       │  ChatResponse      │
#  │                                      │                                    │  (或 SSE 流)       │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  GET /api/chat/mock-mode/status      │  (无请求体)                        │  MockModeStatus    │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/chat/mock-mode/toggle     │  MockModeToggle                    │  MockModeStatus    │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/conversations/create      │  ConversationCreate                │  ConversationOut   │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/conversations/list        │  ConversationListRequest           │  ConversationOut[] │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/conversations/get         │  ConversationGetRequest            │  ConversationDetail│
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/conversations/delete      │  ConversationDeleteRequest         │  { success: bool } │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/conversations/update-title│  ConversationTitleUpdate           │  ConversationOut   │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/documents/list            │  RagDocumentListRequest            │  DocumentOut[]     │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/documents/get             │  RagDocumentGetRequest             │  DocumentOut       │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/documents/delete          │  RagDocumentDeleteRequest          │  { success: bool } │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/documents/search          │  RagSearchRequest                  │  RagSearchResult[] │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/agents/list               │  AgentListRequest                  │  AgentConfigOut[]  │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/agents/get                │  AgentGetRequest                   │  AgentConfigOut    │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/agents/create             │  AgentConfigCreate                 │  AgentConfigOut    │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/agents/update             │  AgentConfigUpdate                 │  AgentConfigOut    │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/agents/delete             │  AgentDeleteRequest                │  { success: bool } │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST(或 GET) /api/health            │  (无请求体)                        │  HealthCheck       │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/admin/dashboard           │  (无请求体)                        │  DashboardStats    │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/admin/llm-config          │  (无请求体)                        │  LLMConfigResponse │
#  ├──────────────────────────────────────┼────────────────────────────────────┼───────────────────┤
#  │  POST /api/admin/llm-config/update   │  LLMConfigUpdate                   │  LLMConfigResponse │
#  └──────────────────────────────────────┴────────────────────────────────────┴───────────────────┘
#
#  ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
#  │  基础模型（被其他模型继承，不直接对应端点）                                                    │
#  ├──────────────────────────────────────────────────────────────────────────────────────────────┤
#  │  PaginationRequest  — 分页请求基类，提供 skip/limit 字段                                      │
#  │  IdRequest          — ID 查询请求基类，提供 id 字段及安全校验                                 │
#  └──────────────────────────────────────────────────────────────────────────────────────────────┘
#
#  ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
#  │  辅助模型（嵌入在其他模型中，不直接对应端点）                                                  │
#  ├──────────────────────────────────────────────────────────────────────────────────────────────┤
#  │  AttachmentInfo  — 附件信息，嵌入在 ChatRequest.attachments 中                                │
#  │  MessageOut      — 消息输出，嵌入在 ChatResponse / ConversationDetail 中                     │
#  │  LLMProviderInfo — LLM提供商信息，嵌入在 LLMConfigResponse.providers 中                       │
#  └──────────────────────────────────────────────────────────────────────────────────────────────┘
