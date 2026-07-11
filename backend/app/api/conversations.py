"""
Conversation CRUD endpoints — enterprise design.
All operations use POST with JSON body. No IDs in URL paths.
"""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Conversation, Message
from app.schemas import (
    ConversationCreate,
    ConversationOut,
    ConversationDetail,
    ConversationListRequest,
    ConversationGetRequest,
    ConversationDeleteRequest,
    ConversationTitleUpdate,
    MessageOut,
)

router = APIRouter()


# ---- Create ----

@router.post("/create", response_model=ConversationOut)
async def create_conversation(
    request: ConversationCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new conversation."""
    conv = Conversation(
        id=str(uuid4()),
        title=request.title,
        agent_id=request.agent_id,
    )
    db.add(conv)
    await db.commit()

    result = await db.execute(select(Conversation).where(Conversation.id == conv.id))
    conv = result.scalar_one()
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        agent_id=conv.agent_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=0,
    )


# ---- List ----

@router.post("/list", response_model=list[ConversationOut])
async def list_conversations(
    request: ConversationListRequest,
    db: AsyncSession = Depends(get_db),
):
    """List all conversations (pagination in POST body)."""
    count_subq = (
        select(
            Message.conversation_id,
            func.count(Message.id).label("msg_count"),
        )
        .group_by(Message.conversation_id)
        .subquery()
    )

    result = await db.execute(
        select(
            Conversation,
            func.coalesce(count_subq.c.msg_count, 0).label("message_count"),
        )
        .outerjoin(count_subq, count_subq.c.conversation_id == Conversation.id)
        .order_by(Conversation.updated_at.desc())
        .offset(request.skip)
        .limit(request.limit)
    )
    rows = result.all()

    return [
        ConversationOut(
            id=conv.id,
            title=conv.title,
            agent_id=conv.agent_id,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=msg_count,
        )
        for conv, msg_count in rows
    ]


# ---- Get ----

@router.post("/get", response_model=ConversationDetail)
async def get_conversation(
    request: ConversationGetRequest,
    db: AsyncSession = Depends(get_db),
):
    """Get a conversation with all messages (id in POST body)."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == request.id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == request.id)
        .order_by(Message.id)
    )
    messages = msgs_result.scalars().all()

    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        agent_id=conv.agent_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=len(messages),
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                metadata=m.metadata_,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


# ---- Delete ----

@router.post("/delete")
async def delete_conversation(
    request: ConversationDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation (id in POST body)."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == request.id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.execute(delete(Conversation).where(Conversation.id == request.id))
    await db.commit()
    return {"detail": "Conversation deleted successfully"}


# ---- Update Title ----

@router.post("/update-title")
async def update_title(
    request: ConversationTitleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update conversation title (title + id in POST body, never query string)."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == request.conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv.title = request.title
    await db.commit()
    return {"detail": "Title updated", "title": request.title}
