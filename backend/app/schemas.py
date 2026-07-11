"""
Pydantic request/response schemas.
"""
from datetime import datetime
from typing import Any, Optional, List, Literal

from pydantic import BaseModel, Field


# ---- Chat ----
class AttachmentInfo(BaseModel):
    id: str
    filename: str
    url: str
    type: str  # image/png, application/pdf, text/plain
    size: int


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")
    conversation_id: Optional[str] = None
    agent_id: Optional[str] = None
    stream: bool = True
    use_rag: bool = True
    attachments: List[AttachmentInfo] = []


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


# ---- Conversation ----
class ConversationCreate(BaseModel):
    title: str = "New Conversation"
    agent_id: Optional[str] = None


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


# ---- Document / RAG ----
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
    query: str = Field(..., min_length=1)
    top_k: int = Field(4, ge=1, le=20)


# ---- Agent Config ----
class AgentConfigCreate(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = "You are a helpful AI assistant."
    temperature: float = 0.7
    max_tokens: int = 4096
    enabled_tools: List[str] = []
    rag_top_k: int = 4
    rag_similarity_threshold: float = 0.5


class AgentConfigUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    enabled_tools: Optional[List[str]] = None
    rag_top_k: Optional[int] = None
    rag_similarity_threshold: Optional[float] = None
    is_default: Optional[bool] = None


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

    class Config:
        from_attributes = True


# ---- Health ----
class HealthCheck(BaseModel):
    status: str = "ok"
    database: str = "unknown"
    redis: str = "unknown"
    llm_provider: str = "unknown"
