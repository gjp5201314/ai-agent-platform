"""
Chat endpoint with SSE streaming and file upload support.
This is the main interaction point: POST /api/chat with a message,
returns a Server-Sent Events stream of agent responses.

Supports:
- Text messages
- Image attachments (JPEG, PNG, GIF, WebP) → multimodal vision model
- File attachments (PDF, TXT, code files, etc.) → content extracted and injected

IMPORTANT: For streaming, we manage the DB session inside the generator
because FastAPI dependency cleanup may run before streaming completes.
"""
import json
import os
import uuid
import base64
import mimetypes
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Header
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.database import async_session_factory
from app.models import Conversation, Message, AgentConfig
from app.schemas import ChatRequest
from app.deps import get_default_agent, verify_chat_rate_limit
from app.agent.graph import run_agent
from app.agent.mock_agent import run_mock_agent
from app.config import settings
from app.core.memory import search_memories, add_memories
from app.core.logger import logger

router = APIRouter()

ALLOWED_IMAGE_EXT = set(settings.allowed_image_types.split(","))
ALLOWED_FILE_EXT = set(settings.allowed_file_types.split(","))
MAX_UPLOAD_SIZE = settings.max_upload_size_mb * 1024 * 1024


def _extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """Extract text content from common file types for injection into chat."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in ("txt", "md", "csv", "py", "js", "ts", "json", "yaml", "yml",
               "xml", "html", "css", "sql", "log", "env", "cfg", "ini", "toml"):
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return file_bytes.decode("gbk")
            except UnicodeDecodeError:
                return f"[二进制文件，无法提取文本: {filename}]"

    if ext == "pdf":
        try:
            from app.rag.chunker import extract_text_from_bytes as extract_pdf
            return extract_pdf(file_bytes, "pdf")
        except Exception:
            return f"[PDF 解析失败: {filename}]"

    if ext == "docx":
        try:
            from app.rag.chunker import extract_text_from_bytes as extract_docx
            return extract_docx(file_bytes, "docx")
        except Exception:
            return f"[DOCX 解析失败: {filename}]"

    return f"[不支持的文件类型: {filename}]"


@router.post("/upload")
async def upload_attachment(file: UploadFile = File(...)):
    """
    Upload a file attachment for chat (images, documents, code files).
    Returns attachment info to include in ChatRequest.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_IMAGE_EXT and ext not in ALLOWED_FILE_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{ext}. Allowed: {','.join(ALLOWED_IMAGE_EXT | ALLOWED_FILE_EXT)}"
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(file_bytes)} bytes). Max: {MAX_UPLOAD_SIZE} bytes"
        )

    # Generate unique filename
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    timestamp = datetime.now().strftime("%Y%m")
    sub_dir = os.path.join(settings.upload_dir, timestamp)
    os.makedirs(sub_dir, exist_ok=True)

    file_path = os.path.join(sub_dir, unique_name)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    mime_type, _ = mimetypes.guess_type(file.filename)
    url = f"/uploads/{timestamp}/{unique_name}"

    return {
        "id": unique_name.rsplit(".", 1)[0],
        "filename": file.filename,
        "url": url,
        "type": mime_type or "application/octet-stream",
        "size": len(file_bytes),
    }


def _image_url_to_data(url: str) -> str:
    """
    Convert a local /uploads/... URL to a base64 data URL.
    DashScope (and other remote LLM APIs) cannot access local filesystem paths,
    so we must inline the image as base64.

    If the URL is already a data: or http(s): URL, return it unchanged.
    """
    if url.startswith("data:") or url.startswith("http://") or url.startswith("https://"):
        return url

    # Resolve local path (strip leading / to make it relative to cwd)
    local_path = url.lstrip("/")
    if not os.path.isfile(local_path):
        # File doesn't exist — return original URL as fallback
        return url

    mime_type, _ = mimetypes.guess_type(local_path)
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/png"  # fallback

    with open(local_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{b64}"


def _estimate_tokens(messages: list) -> int:
    """Rough token estimate: total chars / 2 for mixed CN/EN."""
    total = 0
    for msg in messages:
        total += len(msg.content or "")
    return max(1, total // 2)


async def _compress_context(
    db_messages: list,
    max_tokens: int,
    conv_id: str,
    keep_recent: int = 6,
    threshold_ratio: float = 0.7,
) -> list:
    """
    If conversation exceeds threshold_ratio of max_tokens, compress older messages
    into a summary using the LLM. Returns the compressed message list.

    Strategy: keep the last `keep_recent` messages as-is; summarize everything before that.
    Replace summarized messages in DB with a single summary `Message`.
    """
    estimated = _estimate_tokens(db_messages)
    if estimated < max_tokens * threshold_ratio:
        return db_messages  # no compression needed

    if len(db_messages) <= keep_recent:
        return db_messages  # too few messages to compress

    # Split: older messages to summarize, recent messages to keep
    older = db_messages[:-keep_recent]
    recent = db_messages[-keep_recent:]

    # Skip if already compressed (check for summary marker)
    if any("对话摘要:" in (m.content or "") and m.role == "system" for m in older):
        return db_messages

    # Build summary prompt
    convo_text = []
    for m in older:
        role_label = "用户" if m.role == "user" else "助手"
        convo_text.append(f"{role_label}: {m.content}")
    convo_str = "\n".join(convo_text)

    summary_prompt = (
        "请将以下对话历史压缩为一段简洁的摘要，保留关键事实、用户偏好、决定和上下文：\n\n"
        f"{convo_str}\n\n"
        "摘要（用中文，200 字以内）："
    )

    # Call LLM for summarization
    summary_text = f"对话摘要: (对话过长，已自动压缩。以下是历史要点)\n"
    try:
        from app.agent.llm import get_llm
        llm = get_llm(provider=settings.llm_provider,
                      temperature=0.3,
                      max_tokens=300,
                      has_images=False)
        resp = await llm.ainvoke([HumanMessage(content=summary_prompt)])
        summary_text += resp.content
    except Exception as e:
        logger.warning(f"Context compression failed: {e}")
        summary_text += convo_str[:1000]  # fallback: raw text truncation

    # Replace older messages in DB with a single summary message
    try:
        async with async_session_factory() as db:
            # Delete old summarized messages
            older_ids = [m.id for m in older if m.id is not None]
            if older_ids:
                from sqlalchemy import delete
                await db.execute(
                    delete(Message).where(Message.id.in_(older_ids))
                )
            # Insert summary as system message (with a low id to sort before recent)
            summary_msg = Message(
                conversation_id=conv_id,
                role="system",
                content=summary_text,
                metadata_={"compressed": True},
            )
            db.add(summary_msg)
            await db.flush()
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to persist compressed context: {e}")

    # Return: summary + recent messages (as DB models for consistency)
    # Build a synthetic summary Message object for the response
    class _SummaryMsg:
        def __init__(self, content, role="system"):
            self.content = content
            self.role = role
            self.id = None
            self.metadata_ = {"compressed": True}

    compressed = [_SummaryMsg(summary_text)] + list(recent)
    return compressed


def _messages_to_langchain(db_messages: list) -> list:
    """Convert DB Message records to LangChain message objects.
    Supports multimodal content (text + images)."""
    result = []
    for msg in db_messages:
        attachments = (msg.metadata_ or {}).get("attachments", [])

        if msg.role == "user":
            # Build multimodal content if there are image attachments
            has_images = any(a.get("type", "").startswith("image/") for a in attachments)
            has_files = any(not a.get("type", "").startswith("image/") for a in attachments)

            if has_images and msg.content:
                # Multimodal: text + images
                content_parts = [{"type": "text", "text": msg.content}]
                for att in attachments:
                    if att.get("type", "").startswith("image/"):
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": _image_url_to_data(att["url"])}
                        })
                result.append(HumanMessage(content=content_parts))
            elif has_files and msg.content:
                # Files with extracted text already embedded in message.content
                result.append(HumanMessage(content=msg.content))
            else:
                result.append(HumanMessage(content=msg.content))

        elif msg.role == "assistant":
            result.append(AIMessage(content=msg.content))

        elif msg.role == "system":
            result.append(SystemMessage(content=msg.content))

    return result


def _build_user_message_content(request: ChatRequest) -> str:
    """
    Build the full user message content, including text extracted from attachments.
    For images, keep them as separate multimodal parts (handled in _messages_to_langchain).
    For text-based files, extract and inject directly into the message text.
    """
    content = request.message

    file_attachments = [a for a in request.attachments
                        if not (a.type or "").startswith("image/")]

    if file_attachments:
        content += "\n\n--- 附件内容 ---\n"
        for att in file_attachments:
            file_path = att["url"].lstrip("/")
            if os.path.exists(file_path):
                try:
                    with open(file_path, "rb") as f:
                        file_bytes = f.read()
                    text = _extract_text_from_bytes(file_bytes, att["filename"])
                    content += f"\n[文件: {att['filename']}]\n{text}\n"
                except Exception as e:
                    content += f"\n[文件读取失败: {att['filename']}: {e}]\n"
            else:
                content += f"\n[文件未找到: {att['filename']}]\n"

    return content


async def _prepare_chat(request: ChatRequest, user_id: str = "default"):
    """
    Execute pre-stream DB operations: get/create conversation, save user message,
    load history, and build agent config.
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
            conv = Conversation(id=str(uuid.uuid4()), title="New Conversation")
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

        # 3. Build full message content (text + extracted file contents)
        full_content = _build_user_message_content(request)
        has_images = any(
            (a.type or "").startswith("image/") for a in request.attachments
        )

        # 4. Save user message with attachment metadata
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content=full_content,
            metadata_={"attachments": [a.model_dump() for a in request.attachments]}
            if request.attachments else {},
        )
        db.add(user_msg)
        await db.flush()

        # 5. Load conversation history
        msgs_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.id)
        )
        db_messages = list(msgs_result.scalars().all())

        # 5.5 Compress context if conversation is too long
        max_t = agent.max_tokens if agent else 4096
        db_messages = await _compress_context(db_messages, max_t, conv.id)

        langchain_messages = _messages_to_langchain(db_messages)

        await db.commit()

        # 6. Search long-term memories
        memory_context = ""
        try:
            memories = await search_memories(request.message, user_id=user_id)
            if memories:
                memory_lines = []
                for i, mem in enumerate(memories, 1):
                    content = mem.get("memory", "") or mem.get("content", "")
                    if content:
                        memory_lines.append(f"{i}. {content}")
                if memory_lines:
                    memory_context = "\n\n".join(memory_lines)
        except Exception as e:
            logger.warning(f"Memory search failed: {e}")

        # 7. Build agent config dict with memory self-awareness
        system_prompt = agent.system_prompt if agent else (
            "你是一个拥有长期记忆功能的 AI 助手。你能在跨对话中记住用户告诉你的个人信息、偏好和需求。"
        )
        if memory_context:
            system_prompt += (
                f"\n\n以下是你对当前用户的长期记忆（由你的记忆系统从历史对话中自动提取）：\n\n"
                f"{memory_context}\n\n"
                f"请利用这些记忆来提供更个性化、更连贯的回答。如果记忆与当前问题无关，请忽略。"
            )
        else:
            system_prompt += (
                "\n\n提示：你拥有长期记忆能力。如果用户要求你记住某些信息（如生日、偏好等），"
                "请确认收到并表示你会记住，对方可以在下次对话中验证。"
            )

        agent_config = {
            "provider": request.model_provider,
            "system_prompt": system_prompt,
            "temperature": agent.temperature if agent else 0.7,
            "max_tokens": agent.max_tokens if agent else 4096,
            "enabled_tools": agent.enabled_tools if agent else ["rag"],
            "rag_top_k": agent.rag_top_k if agent else 4,
            "rag_similarity_threshold": agent.rag_similarity_threshold if agent else 0.5,
            "has_images": has_images,
        }

        use_rag = request.use_rag and "rag" in (agent.enabled_tools if agent else ["rag"])

        return conv.id, langchain_messages, agent_config, use_rag


@router.post("")
@router.post("/")
async def chat(
    request: ChatRequest,
    req: Request,
    x_forwarded_for: str | None = Header(None),
    x_real_ip: str | None = Header(None),
    _rate_limited=Depends(verify_chat_rate_limit),
):
    """
    Send a message (text + optional attachments) and receive streaming AI response.

    Attachments support:
    - Images (png, jpg, gif, webp): sent to vision model for analysis
    - Files (pdf, txt, code, etc.): text content extracted and injected

    Returns SSE stream with events:
    - conversation_id, rag_context, token, tool_start, done
    """
    # Use IP as stable user_id for cross-conversation memory
    ip = x_real_ip or x_forwarded_for or req.client.host if req.client else "default"
    if "," in (ip or ""):
        ip = ip.split(",")[0].strip()

    conversation_id, langchain_messages, agent_config, use_rag = await _prepare_chat(request, user_id=ip)

    # Determine if mock mode should be used:
    # Priority: 1) per-request flag, 2) global setting
    use_mock = request.mock_mode or settings.mock_mode_enabled

    if request.stream:
        return StreamingResponse(
            _stream_response(conversation_id, langchain_messages, agent_config, use_rag, user_id=ip, mock_mode=use_mock),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        full_response = ""
        sources = []
        async with async_session_factory() as db:
            agent_runner = run_mock_agent if use_mock else run_agent
            async for event in agent_runner(langchain_messages, agent_config, use_rag, db):
                if event["type"] == "token":
                    full_response += event["content"]
                elif event["type"] == "rag_context":
                    sources = event.get("sources", [])
                elif event["type"] == "done":
                    if event.get("sources"):
                        sources = event["sources"]

            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=full_response,
                metadata_={"sources": sources} if sources else {},
            )
            db.add(assistant_msg)
            await db.commit()

        # Save to long-term memory (non-streaming path)
        if full_response:
            try:
                await add_memories(
                    [
                        {"role": "user", "content": request.message},
                        {"role": "assistant", "content": full_response},
                    ],
                    user_id=ip,
                )
            except Exception as e:
                logger.warning(f"Memory save failed (non-streaming): {e}")

        return {
            "conversation_id": conversation_id,
            "content": full_response,
            "sources": sources,
        }


async def _stream_response(conversation_id, messages, agent_config, use_rag, user_id="default", mock_mode=False):
    """Generator that yields SSE-formatted events from the agent."""
    yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conversation_id}, ensure_ascii=False)}\n\n"

    full_response = ""
    sources = []

    try:
        async with async_session_factory() as agent_db:
            agent_runner = run_mock_agent if mock_mode else run_agent
            async for event in agent_runner(messages, agent_config, use_rag, agent_db):
                if event["type"] == "rag_context":
                    sources = event.get("sources", [])
                    yield f"data: {json.dumps({'type': 'rag_context', 'sources': sources}, ensure_ascii=False)}\n\n"
                elif event["type"] == "token":
                    full_response += event["content"]
                    yield f"data: {json.dumps({'type': 'token', 'content': event['content']}, ensure_ascii=False)}\n\n"
                elif event["type"] == "tool_start":
                    yield f"data: {json.dumps({'type': 'tool_start', 'name': event['name'], 'args': event['args']}, ensure_ascii=False)}\n\n"
                elif event["type"] == "agent_switch":
                    yield f"data: {json.dumps({'type': 'agent_switch', 'to_agent': event.get('to_agent', ''), 'task': event.get('task', '')}, ensure_ascii=False)}\n\n"
                elif event["type"] == "done":
                    if event.get("sources"):
                        sources = event["sources"]
                    yield f"data: {json.dumps({'type': 'done', 'sources': sources}, ensure_ascii=False)}\n\n"

        # --- Stream phase complete: send [DONE] IMMEDIATELY ---
        # This unblocks the client BEFORE the slow DB/memory operations below.
        # Previously [DONE] was yielded after the finally block, causing the client
        # to hang with "sending..." spinner for 2-5s while DB writes and Mem0 LLM calls ran.
        try:
            yield "data: [DONE]\n\n"
        except (GeneratorExit, StopAsyncIteration, RuntimeError):
            pass

    except Exception as e:
        # Log full traceback server-side, return sanitized message to client
        import traceback
        logger.error(f"Agent error: {type(e).__name__}: {e}", exc_info=True)
        traceback.print_exc()
        error_msg = "抱歉，服务暂时不可用，请稍后重试。"
        # Yield [DONE] before error to ensure client always terminates
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg}, ensure_ascii=False)}\n\n"
        full_response = f"[系统提示] {error_msg}"
        try:
            yield "data: [DONE]\n\n"
        except (GeneratorExit, StopAsyncIteration, RuntimeError):
            pass

    # --- Post-stream: DB persistence (client already disconnected) ---
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

                # Save to long-term memory (Mem0) — fire and forget, don't block
                try:
                    ur = await db.execute(
                        select(Message)
                        .where(Message.conversation_id == conversation_id)
                        .where(Message.role == "user")
                        .order_by(Message.id.desc())
                        .limit(1)
                    )
                    last_user = ur.scalar_one_or_none()
                    if last_user and full_response:
                        await add_memories(
                            [
                                {"role": "user", "content": last_user.content},
                                {"role": "assistant", "content": full_response},
                            ],
                            user_id=user_id,
                        )
                except Exception as e:
                    logger.warning(f"Memory save failed: {e}")
        except Exception as e:
            logger.warning(f"Failed to save assistant message: {e}")
