"""
Admin API: dashboard stats, LLM configuration, system management.
Enterprise security: all operations are POST with JSON body.
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
)

router = APIRouter()


# ---- Dashboard Stats ----

@router.post("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Aggregate system-wide statistics."""
    # Total conversation count
    conv_count = await db.execute(select(func.count(Conversation.id)))
    total_conv = conv_count.scalar() or 0

    # Today's conversations
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_conv = await db.execute(
        select(func.count(Conversation.id))
        .where(Conversation.created_at >= today_start)
    )
    conv_today = today_conv.scalar() or 0

    # Total messages
    msg_count = await db.execute(select(func.count(Message.id)))
    total_msg = msg_count.scalar() or 0

    # Today's messages
    today_msg = await db.execute(
        select(func.count(Message.id))
        .where(Message.created_at >= today_start)
    )
    msg_today = today_msg.scalar() or 0

    # Document stats
    doc_count = await db.execute(select(func.count(Document.id)))
    total_docs = doc_count.scalar() or 0

    chunk_count = await db.execute(select(func.count(DocumentChunk.id)))
    total_chunks = chunk_count.scalar() or 0

    total_size = await db.execute(select(func.sum(Document.file_size)))
    storage_mb = round((total_size.scalar() or 0) / 1024 / 1024, 2)

    # Agents
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


# ---- LLM Configuration ----

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


@router.post("/llm/list", response_model=LLMConfigResponse)
async def list_llm_config():
    """Return available LLM providers, models, and their status."""
    providers = []

    for pid, meta in _PROVIDER_META.items():
        api_key = ""
        base_url = ""
        default_model = ""
        enabled = False

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

    # Determine active model
    active = settings.qwen_model if settings.llm_provider == "qwen" \
        else settings.openai_model if settings.llm_provider == "openai" \
        else settings.anthropic_model

    return LLMConfigResponse(
        providers=providers,
        default_provider=settings.llm_provider,
        active_model=active,
    )


@router.post("/llm/update")
async def update_llm_config(request: LLMConfigUpdate):
    """
    Update LLM provider configuration.
    Changes are applied immediately (in-memory) for the running process.
    Note: a deployment (docker stack deploy) will reset to .env defaults.
    """
    # Validate provider
    if request.provider not in _PROVIDER_META:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")

    # Apply provider change + auto-select default model for new provider
    old_provider = settings.llm_provider
    settings.llm_provider = request.provider

    # If switching providers WITHOUT specifying a model, auto-select the default
    if request.provider != old_provider and not request.model:
        if request.provider == "qwen":
            settings.qwen_model = "qwen-plus"
        elif request.provider == "openai":
            settings.openai_model = "gpt-4o-mini"
        elif request.provider == "claude":
            settings.anthropic_model = "claude-3-5-sonnet-20241022"

    # Apply explicit model change
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

    # Apply API key / base URL
    if request.api_key:
        if request.provider == "qwen":
            settings.dashscope_api_key = request.api_key
        elif request.provider == "openai":
            settings.openai_api_key = request.api_key
        elif request.provider == "claude":
            settings.anthropic_api_key = request.api_key

    if request.base_url:
        if request.provider == "qwen":
            settings.dashscope_base_url = request.base_url
        elif request.provider == "openai":
            settings.openai_base_url = request.base_url

    # Clear LLM cache so new config is picked up
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


# ---- Admin RAG Management ----

from fastapi import UploadFile, File
from app.shared import upload_and_index_document


@router.post("/rag/documents")
async def list_admin_documents(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List admin-uploaded documents only."""
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


@router.post("/rag/upload")
async def upload_admin_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document to the admin knowledge base (separate from user KB)."""
    doc = await upload_and_index_document(file, db, source="admin")
    return {
        "id": doc.id, "filename": doc.filename, "file_type": doc.file_type,
        "file_size": doc.file_size, "chunk_count": doc.chunk_count,
        "status": doc.status, "source": doc.source,
    }


@router.post("/rag/delete")
async def delete_admin_document(doc_id: str = Body(..., embed=True), db: AsyncSession = Depends(get_db)):
    """Delete an admin document."""
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


@router.post("/rag/stats")
async def admin_rag_stats(db: AsyncSession = Depends(get_db)):
    """Stats for admin knowledge base only."""
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


# ---- Frontend-accessible model list ----

@router.post("/models", response_model=LLMConfigResponse)
async def get_public_models():
    """Public endpoint for frontend to list available models."""
    return await list_llm_config()
