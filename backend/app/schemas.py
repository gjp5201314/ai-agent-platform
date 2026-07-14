"""
Pydantic request/response schemas — enterprise AI agent API design.
All read operations use POST with JSON body (never expose params in URLs).
"""
from datetime import datetime
from typing import Any, Optional, List, Literal

from pydantic import BaseModel, Field, field_validator


# ============================================================
#  Common / Base
# ============================================================

class PaginationRequest(BaseModel):
    """Reusable paginated list request."""
    skip: int = Field(0, ge=0, description="Records to skip")
    limit: int = Field(50, ge=1, le=200, description="Max records to return")


class IdRequest(BaseModel):
    """Single-resource lookup by id (POST body, never URL path)."""
    id: str = Field(..., min_length=1, max_length=64, description="Resource identifier")

    @field_validator("id")
    @classmethod
    def sanitize_id(cls, v: str) -> str:
        """Reject IDs containing path traversal or injection chars."""
        dangerous = {"..", "/", "\\", "\0", "\n", "\r"}
        for ch in dangerous:
            if ch in v:
                raise ValueError(f"id contains invalid character: {repr(ch)}")
        return v.strip()


# ============================================================
#  Chat
# ============================================================

class AttachmentInfo(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    filename: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., min_length=1, max_length=512)
    type: str = Field(..., min_length=1, max_length=128)  # image/png, application/pdf
    size: int = Field(..., ge=0)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=100000, description="User message")
    conversation_id: Optional[str] = Field(None, max_length=64)
    agent_id: Optional[str] = Field(None, max_length=64)
    stream: bool = True
    use_rag: bool = True
    attachments: List[AttachmentInfo] = Field(default_factory=list, max_length=20)
    model_provider: Optional[str] = Field(None, max_length=32, description="Override LLM provider: qwen/openai/claude")


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    metadata: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    conversation_id: str
    message: MessageOut


# ============================================================
#  Conversation
# ============================================================

class ConversationCreate(BaseModel):
    title: str = Field("New Conversation", min_length=1, max_length=200)
    agent_id: Optional[str] = Field(None, max_length=64)


class ConversationListRequest(PaginationRequest):
    """List conversations by POST body (never query string)."""
    pass


class ConversationGetRequest(IdRequest):
    """Get a single conversation — id in POST body only."""
    pass


class ConversationDeleteRequest(IdRequest):
    """Delete a conversation — id in POST body only."""
    pass


class ConversationTitleUpdate(BaseModel):
    """Update title — all params in POST body."""
    conversation_id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=200)


class ConversationOut(BaseModel):
    id: str
    title: str
    agent_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    class Config:
        from_attributes = True


class ConversationDetail(ConversationOut):
    messages: List[MessageOut] = []


# ============================================================
#  Document / RAG
# ============================================================

class RagDocumentListRequest(PaginationRequest):
    """List documents — pagination in POST body."""
    pass


class RagDocumentGetRequest(IdRequest):
    """Get a single document — id in POST body."""
    pass


class RagDocumentDeleteRequest(IdRequest):
    """Delete a document — id in POST body."""
    pass


class DocumentOut(BaseModel):
    id: str
    filename: str
    file_type: str
    file_size: int
    chunk_count: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class RagSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    content: str
    score: float


class RagSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    top_k: int = Field(4, ge=1, le=20)


# ============================================================
#  Agent Config
# ============================================================

class AgentListRequest(PaginationRequest):
    """List agents — pagination in POST body."""
    pass


class AgentGetRequest(IdRequest):
    """Get a single agent — id in POST body."""
    pass


class AgentDeleteRequest(IdRequest):
    """Delete an agent — id in POST body."""
    pass


class AgentConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)
    system_prompt: str = Field("You are a helpful AI assistant.", max_length=5000)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(4096, ge=1, le=131072)
    enabled_tools: List[str] = Field(default_factory=list, max_length=50)
    rag_top_k: int = Field(4, ge=1, le=20)
    rag_similarity_threshold: float = Field(0.5, ge=0.0, le=1.0)
    allow_delegation: bool = Field(True, description="Allow other agents to delegate tasks to this agent")


class AgentConfigUpdate(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=64)
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    system_prompt: Optional[str] = Field(None, max_length=5000)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=131072)
    enabled_tools: Optional[List[str]] = Field(None, max_length=50)
    rag_top_k: Optional[int] = Field(None, ge=1, le=20)
    rag_similarity_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    is_default: Optional[bool] = None
    allow_delegation: Optional[bool] = None


class AgentConfigOut(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str
    temperature: float
    max_tokens: int
    enabled_tools: List[str]
    rag_top_k: int
    rag_similarity_threshold: float
    is_default: bool
    is_protected: bool = False
    allow_delegation: bool = True

    class Config:
        from_attributes = True


# ============================================================
#  Health
# ============================================================

class HealthCheck(BaseModel):
    status: str = "ok"
    database: str = "unknown"
    redis: str = "unknown"
    llm_provider: str = "unknown"
    version: str = "1.0.0"


# ============================================================
#  Admin / System Config
# ============================================================

class DashboardStats(BaseModel):
    total_conversations: int = 0
    total_messages: int = 0
    total_documents: int = 0
    total_chunks: int = 0
    total_storage_mb: float = 0
    total_agents: int = 0
    conversations_today: int = 0
    messages_today: int = 0


class LLMProviderInfo(BaseModel):
    id: str = Field(..., description="Provider key: qwen/openai/claude")
    name: str = Field(..., description="Display name")
    enabled: bool = False
    models: List[str] = Field(default_factory=list)
    default_model: str = ""
    api_key_set: bool = False
    base_url: str = ""


class LLMConfigResponse(BaseModel):
    providers: List[LLMProviderInfo]
    default_provider: str = ""
    active_model: str = ""  # The currently active model name


class LLMConfigUpdate(BaseModel):
    provider: str = Field(..., min_length=1, max_length=32)
    api_key: Optional[str] = Field(None, max_length=512)
    base_url: Optional[str] = Field(None, max_length=256)
    model: Optional[str] = Field(None, max_length=128)
    enabled: Optional[bool] = None
