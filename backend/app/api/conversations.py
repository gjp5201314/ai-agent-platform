"""
Conversation CRUD endpoints.
"""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Conversation, Message
from app.schemas import ConversationCreate, ConversationOut, ConversationDetail, MessageOut

router = APIRouter()


@router.post("", response_model=ConversationOut)
@router.post("/", response_model=ConversationOut)
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
    return ConversationOut.model_validate(conv).model_copy(update={"message_count": 0})


@router.get("", response_model=list[ConversationOut])
@router.get("/", response_model=list[ConversationOut])
async def list_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all conversations, newest first."""
    # Use a subquery to get message counts
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
        .offset(skip)
        .limit(limit)
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


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)):
    """Get a conversation with all its messages."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
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
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a conversation and all its messages."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.execute(delete(Conversation).where(Conversation.id == conversation_id))
    await db.commit()
    return {"detail": "Conversation deleted successfully"}


@router.patch("/{conversation_id}/title")
async def update_title(
    conversation_id: str,
    title: str,
    db: AsyncSession = Depends(get_db),
):
    """Update a conversation's title."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv.title = title
    await db.commit()
    return {"detail": "Title updated", "title": title}
