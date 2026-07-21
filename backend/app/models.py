"""
================================================================================
SQLAlchemy ORM 模型 — 数据库表结构的 Python 定义
================================================================================

【前端开发者必读】

本文件使用 SQLAlchemy ORM（对象关系映射）定义了数据库中的所有表结构。
每个 Python 类对应数据库中的一张表，每个类属性对应表中的一个字段。

前端开发者需要理解这些模型，因为：
  1. API 响应的 JSON 结构通常直接映射这些模型字段
  2. 前端需要根据这些字段定义 TypeScript 类型/接口
  3. 理解模型间的关系有助于理解 API 的嵌套数据结构

================================================================================
数据模型关系图（ER 图 - 实体关系图）
================================================================================

  AgentConfig（Agent 配置）
     │
     │ 1:N（一个 Agent 可以有多个对话）
     │ 外键: conversations.agent_id → agent_configs.id
     │
     ▼
  Conversation（对话）
     │
     │ 1:N（一个对话可以有多条消息）
     │ 外键: messages.conversation_id → conversations.id
     │
     ▼
  Message（消息）

  Document（文档）
     │
     │ 1:N（一个文档可以被切分为多个文本块）
     │ 外键: document_chunks.document_id → documents.id
     │
     ▼
  DocumentChunk（文档块 — 含向量嵌入）

================================================================================
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

# pgvector 是 PostgreSQL 的向量扩展，用于存储和搜索 AI Embedding 向量
# Vector 类型直接映射到 pgvector 的 vector 列类型
from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.database import Base


# ==============================================================================
# 辅助函数
# ==============================================================================

def _utcnow() -> datetime:
    """获取当前 UTC 时间，用于设置 created_at/updated_at 字段。"""
    return datetime.now(timezone.utc)


def _uuid() -> str:
    """生成 UUID v4 字符串，作为表的主键 ID。"""
    return str(uuid.uuid4())


# ==============================================================================
# Conversation — 对话表
# ==============================================================================
# 用途：存储每次用户与 AI 的对话会话
# 关系：一个 Conversation 属于一个 AgentConfig，包含多条 Message
# 前端对应：对话列表页面、对话详情页面

class Conversation(Base):
    __tablename__ = "conversations"

    # id: 对话的唯一标识符，36 位 UUID 字符串
    #   例如："a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    #   前端用这个 ID 来：获取对话历史、发送新消息、切换对话
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # title: 对话标题，显示在前端对话列表中
    #   默认值："New Conversation"
    #   AI 的第一条回复后，后端会自动根据对话内容生成标题
    title: Mapped[str] = mapped_column(String(256), default="New Conversation")

    # agent_id: 关联的 Agent 配置 ID（外键）
    #   指向 agent_configs 表的 id 字段
    #   nullable=True 表示对话可以不绑定特定 Agent（使用默认 Agent）
    #   前端可以在创建对话时指定使用哪个 Agent
    agent_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("agent_configs.id"), nullable=True)

    # metadata_: 扩展元数据字段（JSON 类型）
    #   存储灵活的键值对数据，如：
    #     - {"tags": ["重要", "技术"]}  对话标签
    #     - {"pinned": true}            是否置顶
    #     - {"summary": "..."}          对话摘要
    #   数据库列名是 "metadata"（因为 metadata 是 SQLAlchemy 保留字，所以加下划线）
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, default=dict)

    # created_at: 对话创建时间（UTC 时区）
    #   前端可以用此字段排序对话列表（按创建时间）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # updated_at: 对话最后更新时间（UTC 时区）
    #   每次对话有新消息时会自动更新（onupdate=_utcnow）
    #   前端可以用此字段排序对话列表（按最近活跃时间）
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # ---- 关系定义 ----

    # messages: 级联关系 — 删除对话时自动删除所有关联消息
    #   cascade="all, delete-orphan" 的含义：
    #     - all: 所有操作（增删改）级联到子对象
    #     - delete-orphan: 如果从列表移除子对象，自动删除
    #   order_by="Message.id": 按消息 ID 排序（即按发送时间顺序）
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )

    # agent: 反向引用到 AgentConfig
    #   通过 conversation.agent 可以访问对话绑定的 Agent 配置
    agent: Mapped[Optional["AgentConfig"]] = relationship(back_populates="conversations")


# ==============================================================================
# Message — 消息表
# ==============================================================================
# 用途：存储对话中的每一条消息（用户提问 + AI 回复 + 工具调用结果）
# 关系：每条 Message 属于一个 Conversation
# 前端对应：聊天界面的消息列表

class Message(Base):
    __tablename__ = "messages"

    # id: 消息的唯一标识符，自增整数
    #   注意：Unlike Conversation，这里使用自增整数而非 UUID
    #   因为消息数量可能很大，整数主键更高效
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # conversation_id: 所属对话的 ID（外键）
    #   ondelete="CASCADE" 表示删除对话时自动删除该对话的所有消息
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"))

    # role: 消息角色
    #   可选值（前端需要据此设置不同的气泡样式）：
    #     - "user":      用户发送的消息（前端气泡靠右/蓝色背景）
    #     - "assistant": AI 回复的消息（前端气泡靠左/灰色背景）
    #     - "tool":      工具调用结果（前端显示为可折叠的工具调用卡片）
    #     - "system":    系统内部消息（前端通常不显示）
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | tool | system

    # content: 消息正文内容（纯文本/Markdown）
    #   使用 Text 类型而非 String，因为消息内容可能非常长
    #   前端应使用 Markdown 渲染器来显示 AI 回复（支持代码块、表格、列表等）
    content: Mapped[str] = mapped_column(Text)

    # metadata_: 扩展元数据字段（JSON 类型）
    #   存储消息的附加信息，如：
    #     - 工具调用记录: {"tool_calls": [{"name": "web_search", "args": {...}}]}
    #     - 检索来源:     {"sources": [{"title": "...", "url": "..."}]}
    #     - 错误信息:     {"error": "..."}
    #   前端可以据此展示"查看引用来源"、"工具调用详情"等功能
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, default=dict)

    # created_at: 消息发送时间（UTC 时区）
    #   前端可以据此在聊天界面显示时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # conversation: 反向引用到 Conversation
    #   通过 message.conversation 可以访问消息所属的对话
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


# ==============================================================================
# Document — 文档元数据表
# ==============================================================================
# 用途：存储用户上传文档的元数据（文件名、大小、状态等）
# 关系：一个 Document 包含多个 DocumentChunk（文本块）
# 前端对应：知识库/文档管理页面
#
# 注意：本表只存储元数据，实际文本内容存储在 DocumentChunk 表中

class Document(Base):
    """Uploaded document metadata. The actual text chunks live in DocumentChunk."""
    __tablename__ = "documents"

    # id: 文档唯一标识符，UUID 字符串
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # filename: 原始文件名
    #   前端显示给用户的文件名
    filename: Mapped[str] = mapped_column(String(512))

    # file_type: 文件类型
    #   可选值（决定解析策略）：
    #     - "pdf":  PDF 文件，使用 PyPDF2 解析
    #     - "docx": Word 文件，使用 python-docx 解析
    #     - "txt":  纯文本文件
    #     - "md":   Markdown 文件
    file_type: Mapped[str] = mapped_column(String(20))  # pdf | docx | txt | md

    # file_size: 文件大小（字节）
    #   前端可以显示格式化后的大小（如 "1.2 MB"）
    file_size: Mapped[int] = mapped_column(Integer, default=0)

    # content_hash: 文件内容的 SHA-256 哈希值
    #   用途：去重 — 如果用户上传了两次同样的文件，可以跳过重复处理
    #   长度为 64 字符（SHA-256 的十六进制表示）
    content_hash: Mapped[str] = mapped_column(String(64))  # SHA-256 for dedup

    # chunk_count: 文档被切割成的文本块数量
    #   一个 10 页的 PDF 可能被切成 30-50 个 chunk
    #   前端可以展示"已处理 X 个文本块"
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    # status: 文档处理状态
    #   可选值（前端应根据不同状态显示不同的 UI）：
    #     - "processing": 正在处理中（显示加载动画/进度条）
    #     - "ready":      处理完成，可用于搜索（显示成功图标）
    #     - "error":      处理失败（显示错误信息和重试按钮）
    status: Mapped[str] = mapped_column(String(20), default="processing")  # processing | ready | error

    # source: 文档来源
    #   - "user":  用户自己上传的文档
    #   - "admin": 管理员预设的知识库文档
    #   前端可以据此显示不同的图标或标签
    source: Mapped[str] = mapped_column(String(20), default="user")  # "user" | "admin"

    # metadata_: 扩展元数据字段
    #   可以存储页码数、作者信息、标签等
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, default=dict)

    # created_at: 文档上传时间
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # chunks: 级联关系 — 删除文档时自动删除所有关联的文本块
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


# ==============================================================================
# DocumentChunk — 文档文本块表（含向量嵌入）
# ==============================================================================
# 用途：存储文档被切分后的每个文本段落及其向量嵌入（AI Embedding）
# 关系：每个 Chunk 属于一个 Document
# 前端对应：知识库搜索结果的来源引用
#
# 核心概念 —— 什么是向量嵌入（Vector Embedding）？
#   Embedding 是将文本转换为固定维度的浮点数数组（向量）的过程。
#   相似的文本内容会产生相似的向量，这样可以用数学方法（余弦相似度）
#   来搜索语义相近的文档片段。
#
#   例如："今天天气真好"和"今日气候宜人"虽然用词不同，
#   但它们的 embedding 向量在空间中距离很近，可以被搜索到。

class DocumentChunk(Base):
    """A piece of a document with its vector embedding."""
    __tablename__ = "document_chunks"

    # id: 文本块唯一标识符
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # document_id: 所属文档的 ID（外键）
    #   ondelete="CASCADE": 删除文档时自动删除所有 chunk
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id", ondelete="CASCADE"))

    # chunk_index: 文本块在文档中的序号（从 0 开始）
    #   用于保持原始文档的段落顺序
    chunk_index: Mapped[int] = mapped_column(Integer)

    # content: 文本块的实际内容
    #   通常 500-1000 个字符（取决于分块策略）
    #   前端展示搜索结果时，显示此内容的高亮片段
    content: Mapped[str] = mapped_column(Text)

    # embedding: 向量嵌入（Vector 类型 — pgvector 扩展）
    #   这是一个浮点数数组，维度和 settings.embedding_dimensions 一致（默认 1024）
    #   例如：[0.123, -0.456, 0.789, ..., 0.321]（共 1024 个数字）
    #   pgvector 支持高效向量搜索（近似最近邻 ANN 搜索），不需要遍历所有数据
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dimensions))

    # token_count: 文本块的 Token 数量（估算值）
    #   用于成本估算和上下文长度计算
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    # metadata_: 扩展元数据字段
    #   可以存储原文档页码、段落标题等位置信息
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, default=dict)

    # created_at: 文本块创建时间
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # document: 反向引用到 Document
    #   通过 chunk.document 可以访问所属文档的元数据（文件名等）
    document: Mapped["Document"] = relationship(back_populates="chunks")


# ==============================================================================
# AgentConfig — Agent 配置表
# ==============================================================================
# 用途：存储 Agent（AI 助手）的配置信息
# 关系：一个 AgentConfig 可以有多个 Conversation
# 前端对应：Agent 管理页面、"创建 Agent"、"编辑 Agent"功能
#
# 什么是 Agent？
#   Agent 是带有特定角色/能力的 AI 助手。不同的 Agent 有：
#     - 不同的 system_prompt（系统提示词 / 角色设定）
#     - 不同的 temperature（创造性程度）
#     - 不同的 enabled_tools（可用工具集）
#     - 不同的 RAG 设置（知识库检索参数）
#
#   例如：
#     - "代码助手" Agent：擅长编程，系统提示词包含代码规范
#     - "翻译官" Agent：专注于多语言翻译
#     - "数据分析师" Agent：启用了 Python 沙盒和图表工具

class AgentConfig(Base):
    """Persisted agent configurations (system prompt, tool settings, etc.)."""
    __tablename__ = "agent_configs"

    # id: Agent 配置的唯一标识符
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # name: Agent 的名称
    #   前端在 Agent 选择器/列表中显示
    #   例如："通用助手"、"Python 专家"、"翻译官"
    name: Mapped[str] = mapped_column(String(128))

    # description: Agent 的描述信息
    #   前端显示为 Agent 卡片的副标题
    #   例如："擅长 Python 编程、代码审查和技术文档编写"
    description: Mapped[str] = mapped_column(Text, default="")

    # system_prompt: 系统提示词（System Prompt）
    #   这是告诉 AI "你是谁、你该怎么做"的核心指令
    #   默认值是一个通用的 AI 助手提示词
    #   前端通常在"编辑 Agent"页面的一个大文本框中编辑此内容
    system_prompt: Mapped[str] = mapped_column(Text, default="You are a helpful AI assistant.")

    # temperature: 温度参数（0.0 ~ 2.0）
    #   控制 AI 回复的随机性和创造性：
    #     - 0.0 ~ 0.3: 更确定、更保守、更可预测（适合代码、数学、翻译）
    #     - 0.7 ~ 1.0: 平衡（默认值，适合大多数场景）
    #     - 1.0 ~ 2.0: 更有创意、更多样化（适合创意写作、头脑风暴）
    #   前端可以在 Agent 设置中显示为滑块控件
    temperature: Mapped[float] = mapped_column(Float, default=0.7)

    # max_tokens: 单次回复的最大 Token 数
    #   限制 AI 回复的最大长度，防止超长回复消耗过多额度
    #   4096 是常用值，对于大多数回复足够
    #   前端可以显示"预计最大回复长度"提示
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)

    # enabled_tools: 启用的工具列表（JSON 数组）
    #   决定了这个 Agent 可以使用哪些工具
    #   可选值示例：
    #     - "rag":          知识库检索
    #     - "web_search":   网页搜索
    #     - "calculator":   计算器
    #     - "python_sandbox": Python 沙盒执行
    #     - "image_gen":    图片生成
    #   前端可以在 Agent 编辑页显示为多选复选框
    enabled_tools: Mapped[list] = mapped_column(JSON, default=list)

    # ---- RAG（检索增强生成）设置 ----

    # rag_top_k: RAG 检索时返回的最相关文档块数量
    #   当用户提问时，从知识库中检索 top_k 个最相关的文档片段
    #   默认 4 表示找到 4 个最相关的段落，注入到 LLM 上下文中
    rag_top_k: Mapped[int] = mapped_column(Integer, default=4)

    # rag_similarity_threshold: 相似度阈值（0.0 ~ 1.0）
    #   只返回相似度 >= 此值的文档片段
    #   阈值越高，结果越精准但可能漏掉相关内容
    #   阈值越低，结果越全面但可能包含不相关内容
    #   0.5 是一个平衡的默认值
    rag_similarity_threshold: Mapped[float] = mapped_column(Float, default=0.5)

    # ---- Agent 元数据 ----

    # is_default: 是否为默认 Agent ★
    #   系统中只能有一个默认 Agent（通常是最通用的那个）
    #   当用户创建新对话但未指定 Agent 时，使用默认 Agent
    #   前端创建 Agent 时应提示"设为默认"（但确保只有一个默认）
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    # is_protected: 是否为受保护的 Agent ★
    #   受保护的 Agent 不允许被用户删除或大幅修改
    #   通常用于系统预设的 Agent（如"通用助手"、"代码审查员"）
    #   前端应在删除/编辑受保护 Agent 时禁用操作按钮并显示提示
    is_protected: Mapped[bool] = mapped_column(Boolean, default=False)

    # allow_delegation: 是否允许其他 Agent 委托任务给此 Agent ★
    #   在多 Agent 模式下，主管 Agent 可以将任务分配给允许委托的子 Agent
    #   设置为 false 的 Agent 只能被用户直接调用，不能被其他 Agent 委托
    #   【前端说明】这是"Agent 间协作"的设置项，在多 Agent 模式下才有意义
    allow_delegation: Mapped[bool] = mapped_column(Boolean, default=True, doc="Whether other agents can delegate tasks to this agent")

    # created_at: Agent 创建时间
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # conversations: 反向引用 — 使用此 Agent 的所有对话
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="agent")
