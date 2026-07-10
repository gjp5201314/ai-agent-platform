"""
Chat endpoint with SSE streaming.
This is the main interaction point: POST /api/chat with a message,
returns a Server-Sent Events stream of agent responses.

IMPORTANT: For streaming, we manage the DB session inside the generator
because FastAPI dependency cleanup may run before streaming completes.
"""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage, AIMessage

from app.database import async_session_factory
from app.models import Conversation, Message, AgentConfig
from app.schemas import ChatRequest
from app.deps import get_default_agent
from app.agent.graph import run_agent

router = APIRouter()


def _messages_to_langchain(db_messages: list) -> list:
    """Convert DB Message records to LangChain message objects."""
    result = []
    for msg in db_messages:
        if msg.role == "user":
            result.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            result.append(AIMessage(content=msg.content))
    return result


async def _prepare_chat(request: ChatRequest):
    """
    Execute pre-stream DB operations: get/create conversation, save user message,
    load history, and build agent config.
    Returns all data needed for the streaming phase.
    """
    async with async_session_factory() as db:
        # 1. Get or create conversation
        if request.conversation_id:
            result = await db.execute(
                select(Conversation).where(Conversation.id == request.conversation_id)
            )
            conv = result.scalar_one_or_none()
            if not conv:
                raise HTTPException(status_code=404, detail="Conversation not found")
        else:
            conv = Conversation(id=str(__import__("uuid").uuid4()), title="New Conversation")
            if request.agent_id:
                conv.agent_id = request.agent_id
            db.add(conv)
            await db.flush()

        # 2. Get agent config
        agent = None
        if request.agent_id:
            result = await db.execute(
                select(AgentConfig).where(AgentConfig.id == request.agent_id)
            )
            agent = result.scalar_one_or_none()
        if not agent:
            agent = await get_default_agent(db)

        # 3. Save user message
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content=request.message,
        )
        db.add(user_msg)
        await db.flush()

        # 4. Load conversation history
        msgs_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.id)
        )
        db_messages = msgs_result.scalars().all()
        langchain_messages = _messages_to_langchain(db_messages)

        await db.commit()

        # 5. Build agent config dict
        agent_config = {
            "provider": None,
            "system_prompt": agent.system_prompt if agent else "You are a helpful AI assistant.",
            "temperature": agent.temperature if agent else 0.7,
            "max_tokens": agent.max_tokens if agent else 4096,
            "enabled_tools": agent.enabled_tools if agent else ["rag"],
            "rag_top_k": agent.rag_top_k if agent else 4,
            "rag_similarity_threshold": agent.rag_similarity_threshold if agent else 0.5,
        }

        use_rag = request.use_rag and "rag" in (agent.enabled_tools if agent else ["rag"])

        return conv.id, langchain_messages, agent_config, use_rag


@router.post("")
@router.post("/")
async def chat(request: ChatRequest):
    """
    Send a message and receive a streaming AI response.

    Returns SSE stream with events:
    - conversation_id: the conversation ID (first event)
    - rag_context: knowledge base sources (if RAG used)
    - token: streamed LLM token
    - tool_start: agent is calling a tool
    - done: stream complete

    Set stream=false for a non-streaming JSON response.
    """
    # Prepare: create conversation, save user message, load history
    conversation_id, langchain_messages, agent_config, use_rag = await _prepare_chat(request)

    if request.stream:
        return StreamingResponse(
            _stream_response(conversation_id, langchain_messages, agent_config, use_rag),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        # Non-streaming: collect all tokens and return JSON
        full_response = ""
        sources = []

        # Use a DB session for RAG search and message persistence
        async with async_session_factory() as db:
            async for event in run_agent(langchain_messages, agent_config, use_rag, db):
                if event["type"] == "token":
                    full_response += event["content"]
                elif event["type"] == "rag_context":
                    sources = event.get("sources", [])
                elif event["type"] == "done":
                    if event.get("sources"):
                        sources = event["sources"]

            # Save assistant message
            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=full_response,
                metadata_={"sources": sources} if sources else {},
            )
            db.add(assistant_msg)
            await db.commit()

        return {
            "conversation_id": conversation_id,
            "content": full_response,
            "sources": sources,
        }


async def _stream_response(conversation_id, messages, agent_config, use_rag):
    """
    Generator that yields SSE-formatted events from the agent.
    Manages its own DB session for saving the assistant message.
    """
    # First event: send conversation ID so frontend can track it
    yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conversation_id}, ensure_ascii=False)}\n\n"

    full_response = ""
    sources = []

    try:
        # The RAG search needs a DB session — create one for the agent
        async with async_session_factory() as agent_db:
            async for event in run_agent(messages, agent_config, use_rag, agent_db):
                if event["type"] == "rag_context":
                    sources = event.get("sources", [])
                    yield f"data: {json.dumps({'type': 'rag_context', 'sources': sources}, ensure_ascii=False)}\n\n"

                elif event["type"] == "token":
                    full_response += event["content"]
                    yield f"data: {json.dumps({'type': 'token', 'content': event['content']}, ensure_ascii=False)}\n\n"

                elif event["type"] == "tool_start":
                    yield f"data: {json.dumps({'type': 'tool_start', 'name': event['name'], 'args': event['args']}, ensure_ascii=False)}\n\n"

                elif event["type"] == "done":
                    if event.get("sources"):
                        sources = event["sources"]
                    yield f"data: {json.dumps({'type': 'done', 'sources': sources}, ensure_ascii=False)}\n\n"

    except Exception as e:
        error_msg = f"Agent 执行错误: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg}, ensure_ascii=False)}\n\n"
        full_response = f"⚠️ {error_msg}"
    finally:
        # Persist the assistant message in a fresh session
        if full_response:
            try:
                async with async_session_factory() as db:
                    assistant_msg = Message(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=full_response,
                        metadata_={"sources": sources} if sources else {},
                    )
                    db.add(assistant_msg)

                    # Update conversation title if it's new
                    conv_result = await db.execute(
                        select(Conversation).where(Conversation.id == conversation_id)
                    )
                    conv = conv_result.scalar_one_or_none()
                    if conv and conv.title == "New Conversation":
                        user_result = await db.execute(
                            select(Message)
                            .where(Message.conversation_id == conversation_id)
                            .where(Message.role == "user")
                            .order_by(Message.id)
                            .limit(1)
                        )
                        first_user = user_result.scalar_one_or_none()
                        if first_user:
                            conv.title = first_user.content[:50] + ("..." if len(first_user.content) > 50 else "")

                    await db.commit()
            except Exception as e:
                print(f"[Chat] Failed to save assistant message: {e}")

        yield "data: [DONE]\n\n"
