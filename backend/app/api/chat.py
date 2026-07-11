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

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage, AIMessage

from app.database import async_session_factory
from app.models import Conversation, Message, AgentConfig
from app.schemas import ChatRequest
from app.deps import get_default_agent
from app.agent.graph import run_agent
from app.config import settings
from app.core.memory import search_memories, add_memories

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


async def _prepare_chat(request: ChatRequest):
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
        db_messages = msgs_result.scalars().all()
        langchain_messages = _messages_to_langchain(db_messages)

        await db.commit()

        # 6. Search long-term memories
        memory_context = ""
        try:
            memories = await search_memories(request.message, user_id=conv.id)
            if memories:
                memory_lines = []
                for i, mem in enumerate(memories, 1):
                    content = mem.get("memory", "") or mem.get("content", "")
                    if content:
                        memory_lines.append(f"{i}. {content}")
                if memory_lines:
                    memory_context = "\n\n".join(memory_lines)
        except Exception as e:
            print(f"[Chat] Memory search failed: {e}")

        # 7. Build agent config dict
        system_prompt = agent.system_prompt if agent else "You are a helpful AI assistant."
        if memory_context:
            system_prompt += (
                f"\n\n以下是与当前用户相关的长期记忆（从历史对话中提取）：\n\n"
                f"{memory_context}\n\n"
                f"请利用这些记忆来提供更个性化、更连贯的回答。如果记忆与当前问题无关，请忽略。"
            )

        agent_config = {
            "provider": None,
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
async def chat(request: ChatRequest):
    """
    Send a message (text + optional attachments) and receive streaming AI response.

    Attachments support:
    - Images (png, jpg, gif, webp): sent to vision model for analysis
    - Files (pdf, txt, code, etc.): text content extracted and injected

    Returns SSE stream with events:
    - conversation_id, rag_context, token, tool_start, done
    """
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
        full_response = ""
        sources = []
        async with async_session_factory() as db:
            async for event in run_agent(langchain_messages, agent_config, use_rag, db):
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

        return {
            "conversation_id": conversation_id,
            "content": full_response,
            "sources": sources,
        }


async def _stream_response(conversation_id, messages, agent_config, use_rag):
    """Generator that yields SSE-formatted events from the agent."""
    yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conversation_id}, ensure_ascii=False)}\n\n"

    full_response = ""
    sources = []

    try:
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
        full_response = f"\u26a0\ufe0f {error_msg}"
    finally:
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

                    # Save to long-term memory (Mem0)
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
                                user_id=conversation_id,
                            )
                    except Exception as e:
                        print(f"[Chat] Memory save failed: {e}")
            except Exception as e:
                print(f"[Chat] Failed to save assistant message: {e}")

        yield "data: [DONE]\n\n"
