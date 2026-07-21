"""
================================================================================
聊天 API 模块 (Chat API) — 前端开发者必读文档
================================================================================

## 概述

本模块是前端与后端交互的**核心入口**。前端通过 `POST /api/chat` 发送消息，
后端通过 **SSE (Server-Sent Events)** 流式返回 AI 回复。

## 支持的附件类型

| 类别       | 扩展名                        | 处理方式                              |
|------------|-------------------------------|---------------------------------------|
| 图片       | png, jpg, jpeg, gif, webp     | 转为 base64，作为多模态输入发送给 LLM |
| 文档       | pdf, docx                     | 解析文本内容，注入到消息文本中        |
| 代码/文本  | txt, md, csv, py, js, ts,     | 读取文本内容，注入到消息文本中        |
|            | json, yaml, xml, html, css,   |                                       |
|            | sql, log, env, cfg, ini, toml |                                       |

## 请求/响应完整流程

```
前端发送 POST /api/chat (JSON)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 1. 速率限制检查 (verify_chat_rate_limit)                 │
│ 2. _prepare_chat():                                     │
│    a. 获取或创建会话 (Conversation)                      │
│    b. 获取 Agent 配置                                    │
│    c. 构建消息内容 (文本 + 附件提取)                     │
│    d. 保存用户消息到数据库                               │
│    e. 加载对话历史                                       │
│    f. 上下文压缩 (如果超过 token 限制)                   │
│    g. 搜索长期记忆 (Mem0)                                │
│    h. 组装 Agent 配置 + system prompt                    │
│ 3. 判断 mock 模式 (request.mock_mode 或 全局设置)       │
│ 4. 判断 stream / non-stream                             │
│    ├── stream=true  → 返回 SSE 流                       │
│    └── stream=false → 收集所有事件后返回 JSON             │
└─────────────────────────────────────────────────────────┘
```

## SSE 事件类型参考表

前端通过 `EventSource` 或 `fetch` + `ReadableStream` 接收以下 SSE 事件。
所有事件格式均为 `data: <JSON>\n\n`，使用 `ensure_ascii=False` 编码。

| 事件类型        | JSON 字段                                | 触发时机                    | 前端处理                                       |
|----------------|------------------------------------------|-----------------------------|------------------------------------------------|
| conversation_id | { type, conversation_id }                | 流开始时，第一个事件         | 保存 conversation_id，用于后续请求            |
| rag_context     | { type, sources[] }                      | RAG 检索完成后              | 可选：展示引用来源列表                        |
| tool_start      | { type, name, args }                     | Agent 开始调用工具时        | 展示工具调用状态 (如 "正在搜索知识库...")     |
| agent_switch    | { type, to_agent, task }                 | 多 Agent 切换时             | 展示当前执行的 Agent 名称                     |
| token           | { type, content }                        | LLM 逐 token 输出时         | 逐字追加到聊天界面，实现打字机效果             |
| done            | { type, sources[] }                      | Agent 完成回复后            | 停止接收，标记回复完整                        |
| error           | { type, content }                        | 发生错误时                  | 展示错误提示信息                              |
| [DONE]          | 纯文本 "data: [DONE]\n\n"                | DB 持久化之前，流结束信号    | 关闭 SSE 连接，释放前端 loading 状态          |

### [DONE] 信号的关键时序

```
Agent 完成回复 (done 事件)
    → 立即发送 [DONE] 信号 (让前端停止等待)
    → 后端异步完成: 保存 assistant 消息到 DB + 更新会话标题 + 保存长期记忆
```

**前端注意**：收到 `[DONE]` 后应立即关闭连接，后续的 DB 写入和记忆保存不影响用户体验。
之前 [DONE] 放在所有 DB 操作之后，导致前端在 "发送中..." 状态卡 2-5 秒。

### Mock 模式

当 `request.mock_mode=true` 或全局 `settings.mock_mode_enabled=true` 时，
使用 `run_mock_agent` 代替 `run_agent`。Mock 代理不调用真实 LLM，而是返回预设的
模拟回复，用于前端开发调试，无需配置 API Key。

### 错误处理模式

- `_prepare_chat` 中的错误：抛出 `HTTPException`，FastAPI 自动返回 HTTP 错误响应
- `_stream_response` 中的错误：先发送 `error` SSE 事件，再发送 `[DONE]` 确保客户端正常关闭
- 非流式模式中的错误：由 Agent runner 内部处理，返回错误 token

### 非流式模式 (stream=false)

不返回 SSE，而是收集所有事件，最后返回一次 JSON：
```json
{
    "conversation_id": "...",
    "content": "完整的 AI 回复文本",
    "sources": [{ "title": "...", "url": "..." }]
}
```

================================================================================
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

# ============================================================================
# 全局常量
# ============================================================================

# 允许上传的图片类型，从配置文件读取并以逗号分割
ALLOWED_IMAGE_EXT = set(settings.allowed_image_types.split(","))
# 允许上传的文件类型（文档、代码等），从配置文件读取并以逗号分割
ALLOWED_FILE_EXT = set(settings.allowed_file_types.split(","))
# 单文件最大上传大小（字节），从配置的 MB 值换算
MAX_UPLOAD_SIZE = settings.max_upload_size_mb * 1024 * 1024


# ============================================================================
# 工具函数
# ============================================================================

def _extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """
    从常见文件类型的二进制数据中提取文本内容，用于注入到聊天消息中。

    前端注意：当用户上传非图片文件时，此函数负责将其内容提取为纯文本，
    然后拼接到用户消息的末尾。前端不需要做任何额外处理。

    支持的文件类型：
    - 文本类：txt, md, csv, py, js, ts, json, yaml, yml, xml, html, css, sql, log, env, cfg, ini, toml
      → 尝试 UTF-8 解码，失败则尝试 GBK，再失败返回提示
    - PDF：调用 RAG chunker 的 extract_text_from_bytes
    - DOCX：调用 RAG chunker 的 extract_text_from_bytes
    - 其他：返回不支持提示

    Args:
        file_bytes: 文件的二进制数据
        filename: 原始文件名（用于判断扩展名）

    Returns:
        提取的文本内容，或错误提示文本
    """
    # 获取文件扩展名（小写）
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # --- 文本类文件：直接解码 ---
    if ext in ("txt", "md", "csv", "py", "js", "ts", "json", "yaml", "yml",
               "xml", "html", "css", "sql", "log", "env", "cfg", "ini", "toml"):
        try:
            # 优先尝试 UTF-8 编码（最常用的编码）
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                # 降级尝试 GBK 编码（中文 Windows 常用编码）
                return file_bytes.decode("gbk")
            except UnicodeDecodeError:
                # 完全无法解码，返回提示文本
                return f"[二进制文件，无法提取文本: {filename}]"

    # --- PDF 文件：调用 RAG 解析器 ---
    if ext == "pdf":
        try:
            from app.rag.chunker import extract_text_from_bytes as extract_pdf
            return extract_pdf(file_bytes, "pdf")
        except Exception:
            return f"[PDF 解析失败: {filename}]"

    # --- DOCX 文件：调用 RAG 解析器 ---
    if ext == "docx":
        try:
            from app.rag.chunker import extract_text_from_bytes as extract_docx
            return extract_docx(file_bytes, "docx")
        except Exception:
            return f"[DOCX 解析失败: {filename}]"

    # --- 不支持的文件类型 ---
    return f"[不支持的文件类型: {filename}]"


# ============================================================================
# API 端点
# ============================================================================

@router.post("/upload")
async def upload_attachment(file: UploadFile = File(...)):
    """
    上传文件附件端点 - POST /api/chat/upload

    前端使用场景：
    1. 用户在聊天界面选择/拖拽文件
    2. 前端调用此接口上传文件，获取附件信息
    3. 将返回的附件信息放入 ChatRequest.attachments 数组
    4. 然后调用 POST /api/chat 发送消息

    请求：
    - Content-Type: multipart/form-data
    - 字段名: file (文件二进制数据)

    响应：
    ```json
    {
        "id": "去扩展名后的 UUID",
        "filename": "原始文件名",
        "url": "/uploads/202501/abc123.pdf",
        "type": "application/pdf",
        "size": 12345
    }
    ```

    验证规则：
    - 必须有文件名
    - 扩展名必须在 ALLOWED_IMAGE_EXT 或 ALLOWED_FILE_EXT 中
    - 文件大小不能超过 MAX_UPLOAD_SIZE

    文件存储：
    - 保存到 {settings.upload_dir}/{年月}/{UUID}.{ext}
    - URL 路径为 /uploads/{年月}/{UUID}.{ext}
    """
    # 验证文件名存在
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # 验证文件类型
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_IMAGE_EXT and ext not in ALLOWED_FILE_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{ext}. Allowed: {','.join(ALLOWED_IMAGE_EXT | ALLOWED_FILE_EXT)}"
        )

    # 读取文件内容并验证大小
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(file_bytes)} bytes). Max: {MAX_UPLOAD_SIZE} bytes"
        )

    # 生成唯一文件名：UUID + 原始扩展名
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    # 按年月分子目录存储
    timestamp = datetime.now().strftime("%Y%m")
    sub_dir = os.path.join(settings.upload_dir, timestamp)
    os.makedirs(sub_dir, exist_ok=True)

    # 写入磁盘
    file_path = os.path.join(sub_dir, unique_name)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # 返回附件信息
    mime_type, _ = mimetypes.guess_type(file.filename)
    url = f"/uploads/{timestamp}/{unique_name}"

    return {
        "id": unique_name.rsplit(".", 1)[0],
        "filename": file.filename,
        "url": url,
        "type": mime_type or "application/octet-stream",
        "size": len(file_bytes),
    }


# ============================================================================
# 图片/文件处理辅助函数
# ============================================================================

def _image_url_to_data(url: str) -> str:
    """
    将本地 /uploads/... URL 转换为 base64 data URL。

    为什么需要这个函数：
    DashScope 等远程 LLM API 无法访问服务器本地文件系统。
    因此必须将图片内联为 base64 编码的 data URL，才能发送给 LLM。

    转换规则：
    - 已经是 data: 或 http(s): 开头的 URL → 原样返回
    - /uploads/... 本地路径 → 读取文件并转为 base64
    - MIME 类型从文件扩展名猜测，回退到 image/png

    Args:
        url: 图片 URL（本地路径或远程 URL）

    Returns:
        base64 data URL，格式为 data:{mime_type};base64,{base64_string}
    """
    # 已经是 data URL 或远程 URL，无需转换
    if url.startswith("data:") or url.startswith("http://") or url.startswith("https://"):
        return url

    # 去除开头的 /，转为相对于当前工作目录的路径
    # 例如 /uploads/202501/abc.png → uploads/202501/abc.png
    local_path = url.lstrip("/")
    if not os.path.isfile(local_path):
        # 文件不存在，返回原始 URL 作为降级处理
        return url

    # 猜测 MIME 类型
    mime_type, _ = mimetypes.guess_type(local_path)
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/png"  # 回退 MIME 类型

    # 读取文件并编码为 base64
    with open(local_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{b64}"


def _estimate_tokens(messages: list) -> int:
    """
    粗略估算消息列表的 token 数量。
    算法：总字符数 / 2（中英文混合场景下的近似值）。
    这是一个非常粗略的估算，用于上下文压缩决策。
    """
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
    上下文压缩：当对话历史过长时，将早期消息压缩为摘要。

    前端注意：此函数完全在后端自动执行，前端无需关心。
    只在对话历史超过 max_tokens * threshold_ratio 时触发。

    压缩策略：
    1. 保留最近 keep_recent 条消息（默认 6 条）
    2. 将更早的消息通过 LLM 总结为一段摘要
    3. 在数据库中删除旧消息，替换为一条 system 角色的摘要消息
    4. 已有摘要标记 `"对话摘要:"` 的消息不会被重复压缩

    Args:
        db_messages: 数据库中的消息列表
        max_tokens: Agent 配置的最大 token 数
        conv_id: 会话 ID
        keep_recent: 保留的最近消息数
        threshold_ratio: 触发压缩的 token 比例阈值

    Returns:
        压缩后的消息列表（摘要 + 最近消息）
    """
    # 估算 token 数，未超过阈值则不压缩
    estimated = _estimate_tokens(db_messages)
    if estimated < max_tokens * threshold_ratio:
        return db_messages  # 无需压缩

    # 消息太少，不值得压缩
    if len(db_messages) <= keep_recent:
        return db_messages

    # 分离：旧消息（待压缩）和最近消息（保留原样）
    older = db_messages[:-keep_recent]
    recent = db_messages[-keep_recent:]

    # 检查是否已经压缩过（避免重复压缩）
    if any("对话摘要:" in (m.content or "") and m.role == "system" for m in older):
        return db_messages

    # 构建压缩提示词：将旧对话格式化为 "用户: ...\n助手: ..."
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

    # 调用 LLM 生成摘要
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
        # LLM 调用失败，使用原始文本截断作为降级处理
        logger.warning(f"Context compression failed: {e}")
        summary_text += convo_str[:1000]  # 降级：截取前 1000 字符

    # 在数据库中：删除旧的冗余消息，插入摘要消息
    try:
        async with async_session_factory() as db:
            older_ids = [m.id for m in older if m.id is not None]
            if older_ids:
                from sqlalchemy import delete
                await db.execute(
                    delete(Message).where(Message.id.in_(older_ids))
                )
            # 插入摘要消息（system 角色，metadata 标记为压缩消息）
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

    # 构建返回值：合成一个摘要对象 + 最近消息
    class _SummaryMsg:
        def __init__(self, content, role="system"):
            self.content = content
            self.role = role
            self.id = None
            self.metadata_ = {"compressed": True}

    compressed = [_SummaryMsg(summary_text)] + list(recent)
    return compressed


def _messages_to_langchain(db_messages: list) -> list:
    """
    将数据库 Message 记录转换为 LangChain 消息对象。

    前端注意：此函数是后端内部的数据转换，前端无需关心。
    但了解其逻辑有助于理解多模态流程：
    - 普通文本消息 → HumanMessage(content=文本)
    - 包含图片的消息 → HumanMessage(content=[{"type":"text",...}, {"type":"image_url",...}])
    - AI 回复 → AIMessage
    - 系统提示 → SystemMessage

    图片处理：
    从 Message.metadata_.attachments 中提取图片，
    调用 _image_url_to_data 转为 base64 data URL，
    组装成多模态 content 数组。

    Args:
        db_messages: 数据库中的 Message 对象列表

    Returns:
        LangChain 消息对象列表 [HumanMessage|AIMessage|SystemMessage, ...]
    """
    result = []
    for msg in db_messages:
        # 从 metadata 中提取附件信息
        attachments = (msg.metadata_ or {}).get("attachments", [])

        if msg.role == "user":
            # 检查是否有图片附件和文件附件
            has_images = any(a.get("type", "").startswith("image/") for a in attachments)
            has_files = any(not a.get("type", "").startswith("image/") for a in attachments)

            if has_images and msg.content:
                # --- 多模态消息：文本 + 图片 ---
                # 构建 content 数组，先放文本部分
                content_parts = [{"type": "text", "text": msg.content}]
                for att in attachments:
                    if att.get("type", "").startswith("image/"):
                        # 将本地图片 URL 转为 base64 data URL
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": _image_url_to_data(att["url"])}
                        })
                result.append(HumanMessage(content=content_parts))
            elif has_files and msg.content:
                # 文件附件：文本已经由 _build_user_message_content 注入到 content 中
                result.append(HumanMessage(content=msg.content))
            else:
                # 纯文本消息
                result.append(HumanMessage(content=msg.content))

        elif msg.role == "assistant":
            result.append(AIMessage(content=msg.content))

        elif msg.role == "system":
            result.append(SystemMessage(content=msg.content))

    return result


def _build_user_message_content(request: ChatRequest) -> str:
    """
    构建完整的用户消息文本内容。

    前端注意：当用户消息附带文件附件时，此函数会将文件内容解析后拼接到消息末尾。
    前端不需要做额外处理，只需要将附件信息放入 ChatRequest.attachments。

    处理逻辑：
    1. 以 request.message 为基础
    2. 筛选出非图片的附件（文件附件）
    3. 读取每个文件的内容（调用 _extract_text_from_bytes）
    4. 拼接到消息末尾，格式为：
       --- 附件内容 ---
       [文件: 文件名]
       文件内容...

    图片附件不在此处理，由 _messages_to_langchain 单独处理。

    Args:
        request: 聊天请求对象

    Returns:
        包含附件内容的完整用户消息文本
    """
    content = request.message

    # 筛选非图片的文件附件（图片由多模态处理，不注入文本）
    file_attachments = [a for a in request.attachments
                        if not (a.type or "").startswith("image/")]

    if file_attachments:
        content += "\n\n--- 附件内容 ---\n"
        for att in file_attachments:
            # 本地路径（去除开头的 /）
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


# ============================================================================
# 核心函数：准备聊天上下文
# ============================================================================

async def _prepare_chat(request: ChatRequest, user_id: str = "default"):
    """
    准备聊天所需的所有上下文：会话、历史消息、Agent 配置。

    前端注意：此函数由 chat() 端点内部调用，前端无需关心。
    但了解其逻辑有助于理解错误可能发生在哪个阶段。

    执行步骤（按顺序）：
    1. 获取或创建会话
       - 如果提供了 request.conversation_id → 查找已有会话
       - 如果未提供 → 创建新会话（标题 "New Conversation"）
    2. 获取 Agent 配置
       - 优先使用 request.agent_id 指定的 Agent
       - 否则使用默认 Agent
    3. 构建完整消息内容（文本 + 文件附件内容）
    4. 保存用户消息到数据库（包含附件元数据）
    5. 加载对话历史
    6. 上下文压缩（如果历史过长）
    7. 搜索长期记忆（Mem0），注入到 system prompt
    8. 组装 Agent 运行配置

    Args:
        request: 前端发送的聊天请求
        user_id: 用户标识（用于长期记忆），默认使用客户端 IP

    Returns:
        tuple: (conversation_id, langchain_messages, agent_config, use_rag)
    """
    async with async_session_factory() as db:
        # ================================================================
        # 步骤 1: 获取或创建会话
        # ================================================================
        if request.conversation_id:
            # 前端传了 conversation_id → 继续已有会话
            result = await db.execute(
                select(Conversation).where(Conversation.id == request.conversation_id)
            )
            conv = result.scalar_one_or_none()
            if not conv:
                # 会话不存在，返回 404
                raise HTTPException(status_code=404, detail="Conversation not found")
        else:
            # 前端未传 conversation_id → 创建新会话
            conv = Conversation(id=str(uuid.uuid4()), title="New Conversation")
            if request.agent_id:
                conv.agent_id = request.agent_id
            db.add(conv)
            await db.flush()

        # ================================================================
        # 步骤 2: 获取 Agent 配置
        # ================================================================
        agent = None
        if request.agent_id:
            result = await db.execute(
                select(AgentConfig).where(AgentConfig.id == request.agent_id)
            )
            agent = result.scalar_one_or_none()
        # 未指定或未找到 → 使用默认 Agent
        if not agent:
            agent = await get_default_agent(db)

        # ================================================================
        # 步骤 3 & 4: 构建消息内容并保存用户消息
        # ================================================================
        # 构建完整消息（文本 + 文件附件提取的内容）
        full_content = _build_user_message_content(request)
        # 检查是否有图片附件（需要多模态模型）
        has_images = any(
            (a.type or "").startswith("image/") for a in request.attachments
        )

        # 保存用户消息到数据库
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content=full_content,
            # metadata 中存储附件列表，用于后续多模态处理
            metadata_={"attachments": [a.model_dump() for a in request.attachments]}
            if request.attachments else {},
        )
        db.add(user_msg)
        await db.flush()

        # ================================================================
        # 步骤 5: 加载对话历史
        # ================================================================
        msgs_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.id)
        )
        db_messages = list(msgs_result.scalars().all())

        # ================================================================
        # 步骤 5.5: 上下文压缩（如果对话历史太长）
        # ================================================================
        max_t = agent.max_tokens if agent else 4096
        db_messages = await _compress_context(db_messages, max_t, conv.id)

        # 将数据库消息转为 LangChain 格式
        langchain_messages = _messages_to_langchain(db_messages)

        await db.commit()

        # ================================================================
        # 步骤 6: 搜索长期记忆（Mem0）
        # ================================================================
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
            # 记忆搜索失败不影响正常聊天，仅记录警告
            logger.warning(f"Memory search failed: {e}")

        # ================================================================
        # 步骤 7: 组装 Agent 配置
        # ================================================================
        # 基础 system prompt（Agent 配置或默认值）
        system_prompt = agent.system_prompt if agent else (
            "你是一个拥有长期记忆功能的 AI 助手。你能在跨对话中记住用户告诉你的个人信息、偏好和需求。"
        )
        # 如果有长期记忆内容，注入到 system prompt
        if memory_context:
            system_prompt += (
                f"\n\n以下是你对当前用户的长期记忆（由你的记忆系统从历史对话中自动提取）：\n\n"
                f"{memory_context}\n\n"
                f"请利用这些记忆来提供更个性化、更连贯的回答。如果记忆与当前问题无关，请忽略。"
            )
        else:
            # 无记忆时提示用户可以使用长期记忆功能
            system_prompt += (
                "\n\n提示：你拥有长期记忆能力。如果用户要求你记住某些信息（如生日、偏好等），"
                "请确认收到并表示你会记住，对方可以在下次对话中验证。"
            )

        # Agent 运行配置（传递给 run_agent / run_mock_agent）
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

        # RAG 是否启用：需要前端请求开启 AND Agent 配置中启用了 rag 工具
        use_rag = request.use_rag and "rag" in (agent.enabled_tools if agent else ["rag"])

        return conv.id, langchain_messages, agent_config, use_rag


# ============================================================================
# 主聊天端点
# ============================================================================

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
    主聊天端点 - POST /api/chat

    前端调用流程：
    ```javascript
    // 1. 先上传附件（如果有）
    const attachmentResult = await fetch('/api/chat/upload', {
        method: 'POST',
        body: formData
    });
    const attachment = await attachmentResult.json();

    // 2. 发送聊天请求
    const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message: "你好",
            conversation_id: "可选的已有会话ID",
            attachments: [attachment],      // 上传返回的附件信息
            stream: true,                    // 是否流式返回
            agent_id: "可选的Agent ID",
            model_provider: "可选的模型提供商",
            use_rag: true,                   // 是否启用知识库检索
            mock_mode: false                 // 是否使用模拟模式
        })
    });

    // 3. 读取 SSE 流
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const text = decoder.decode(value);
        // 解析 SSE 事件
        for (const line of text.split('\n')) {
            if (line.startsWith('data: ')) {
                const data = line.slice(6);
                if (data === '[DONE]') {
                    // 流结束，关闭连接
                    return;
                }
                const event = JSON.parse(data);
                switch (event.type) {
                    case 'conversation_id':
                        // 保存 conversation_id
                        break;
                    case 'token':
                        // 追加文本到聊天界面
                        break;
                    case 'rag_context':
                        // 展示引用来源
                        break;
                    case 'tool_start':
                        // 展示工具调用状态
                        break;
                    case 'done':
                        // 回复完成
                        break;
                    case 'error':
                        // 展示错误信息
                        break;
                }
            }
        }
    }
    ```

    请求参数说明：
    - message (必填): 用户输入的消息文本
    - conversation_id (可选): 会话ID，不传则创建新会话
    - attachments (可选): 附件列表，先通过 /api/chat/upload 上传获取
    - stream (可选, 默认 true): 是否使用 SSE 流式返回
    - agent_id (可选): 指定使用的 Agent ID，不传则使用默认 Agent
    - model_provider (可选): 指定模型提供商
    - use_rag (可选, 默认 true): 是否启用知识库检索增强
    - mock_mode (可选, 默认 false): 是否使用模拟模式（不调用真实 LLM）

    SSE 流式返回 (stream=true)：
    - Content-Type: text/event-stream
    - 每行格式: data: <JSON>\n\n
    - 以 data: [DONE]\n\n 结束

    非流式返回 (stream=false)：
    - Content-Type: application/json
    - 收集所有事件后一次性返回 JSON
    """
    # ================================================================
    # 获取客户端 IP 作为 user_id，用于跨会话记忆关联
    # 优先级：X-Real-IP > X-Forwarded-For > 直接连接 IP
    # ================================================================
    ip = x_real_ip or x_forwarded_for or req.client.host if req.client else "default"
    # X-Forwarded-For 可能包含多个 IP（逗号分隔），取第一个
    if "," in (ip or ""):
        ip = ip.split(",")[0].strip()

    # ================================================================
    # 准备聊天上下文（会话、历史、Agent 配置）
    # ================================================================
    conversation_id, langchain_messages, agent_config, use_rag = await _prepare_chat(request, user_id=ip)

    # ================================================================
    # 判断是否使用 Mock 模式
    # 优先级：1) 请求级别的 mock_mode 参数 > 2) 全局配置 mock_mode_enabled
    # Mock 模式不调用真实 LLM，返回预设模拟回复，用于前端开发调试
    # ================================================================
    use_mock = request.mock_mode or settings.mock_mode_enabled

    # ================================================================
    # 流式 vs 非流式 分支
    # ================================================================
    if request.stream:
        # --- 流式模式：返回 SSE 流 ---
        # StreamingResponse 将 _stream_response 生成器的每个 yield 作为 SSE 事件发送
        # 请求头设置：
        #   Cache-Control: no-cache       → 禁止浏览器缓存 SSE 流
        #   Connection: keep-alive        → 保持 TCP 连接
        #   X-Accel-Buffering: no         → 禁用 Nginx 代理缓冲（确保实时传输）
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
        # --- 非流式模式：收集所有事件后返回 JSON ---
        # 前端传入 stream=false 时进入此分支
        # 遍历 agent_runner 的所有事件，收集完整回复文本和引用来源
        full_response = ""
        sources = []
        async with async_session_factory() as db:
            # 根据 mock_mode 选择运行器
            agent_runner = run_mock_agent if use_mock else run_agent
            async for event in agent_runner(langchain_messages, agent_config, use_rag, db):
                if event["type"] == "token":
                    # 累积 token 输出
                    full_response += event["content"]
                elif event["type"] == "rag_context":
                    # 保存 RAG 引用来源
                    sources = event.get("sources", [])
                elif event["type"] == "done":
                    # 保存最终来源（done 事件可能包含更新的 sources）
                    if event.get("sources"):
                        sources = event["sources"]

            # 保存 assistant 消息到数据库
            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=full_response,
                metadata_={"sources": sources} if sources else {},
            )
            db.add(assistant_msg)
            await db.commit()

        # 保存到长期记忆（非流式路径）
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

        # 返回一次性 JSON 响应
        return {
            "conversation_id": conversation_id,
            "content": full_response,
            "sources": sources,
        }


# ============================================================================
# SSE 流式响应生成器
# ============================================================================

async def _stream_response(conversation_id, messages, agent_config, use_rag, user_id="default", mock_mode=False):
    """
    SSE 流式响应生成器 — 前端交互的核心函数。

    此生成器是一个 async generator，每个 yield 产生一个 SSE 事件帧（data: <JSON>\n\n）。
    FastAPI 的 StreamingResponse 会将这些帧实时推送给前端。

    ### 发送事件顺序（正常流程）
    ```
    conversation_id → rag_context? → tool_start* → agent_switch* → token* → done → [DONE]
    ```
    - conversation_id: 总是第一个事件
    - rag_context: 如果启用了 RAG 且检索到结果，在 token 之前发送
    - tool_start: Agent 调用工具时发送（可能多次）
    - agent_switch: 多 Agent 协作时切换 Agent 时发送（可能多次）
    - token: LLM 逐 token 输出（可能多次），前端应逐字追加
    - done: Agent 完成回复时发送
    - [DONE]: 流结束信号（纯文本，非 JSON）

    ### [DONE] 的发送时机
    [DONE] 在 Agent 完成所有事件后**立即发送**，不等待后续的 DB 写入和记忆保存。
    这样前端可以尽快结束 loading 状态，而后端在后台完成数据持久化。

    ### 错误处理
    异常发生时，发送 error 事件 + [DONE]，确保前端连接正常关闭。

    Args:
        conversation_id: 会话 ID（前端应保存此值）
        messages: LangChain 格式的消息列表
        agent_config: Agent 运行配置
        use_rag: 是否启用知识库检索
        user_id: 用户标识（用于长期记忆）
        mock_mode: 是否使用模拟模式
    """
    # ================================================================
    # 第 1 个 SSE 事件: conversation_id
    # 前端处理: 保存 conversation_id，后续请求需要携带此 ID 继续会话
    # ================================================================
    yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conversation_id}, ensure_ascii=False)}\n\n"

    # 累积完整的 AI 回复文本（用于后续 DB 保存和记忆存储）
    full_response = ""
    # 累积知识库引用来源
    sources = []

    try:
        # ================================================================
        # 创建独立的数据库会话用于 Agent 运行期间
        # 使用 async_session_factory 创建专属于此生成器的会话，
        # 因为 FastAPI 的请求级依赖项注入在流式响应中不可靠
        # ================================================================
        async with async_session_factory() as agent_db:
            # 根据 mock_mode 选择 Agent 运行器
            agent_runner = run_mock_agent if mock_mode else run_agent

            # 遍历 Agent 产生的每个事件
            async for event in agent_runner(messages, agent_config, use_rag, agent_db):
                if event["type"] == "rag_context":
                    # ================================================
                    # rag_context 事件: RAG 知识库检索结果
                    # JSON: { type: "rag_context", sources: [{title, url, content_preview}, ...] }
                    # 前端处理: 可选展示引用来源列表，如 "参考了以下文档: ..."
                    # ================================================
                    sources = event.get("sources", [])
                    yield f"data: {json.dumps({'type': 'rag_context', 'sources': sources}, ensure_ascii=False)}\n\n"

                elif event["type"] == "token":
                    # ================================================
                    # token 事件: LLM 输出的单个 token（通常是一个词或几个字符）
                    # JSON: { type: "token", content: "你好" }
                    # 前端处理: 将 content 追加到聊天消息气泡中，实现打字机流式效果
                    # 注意: content 可能是中文、英文、标点符号、换行符等任意文本
                    # ================================================
                    full_response += event["content"]
                    yield f"data: {json.dumps({'type': 'token', 'content': event['content']}, ensure_ascii=False)}\n\n"

                elif event["type"] == "tool_start":
                    # ================================================
                    # tool_start 事件: Agent 开始调用某个工具
                    # JSON: { type: "tool_start", name: "rag_search", args: {query: "..."} }
                    # 前端处理: 展示工具调用状态，如 "正在搜索知识库: xxx"
                    # 常见工具名称: rag_search (知识库搜索), web_search (网络搜索), calculator (计算器)
                    # ================================================
                    yield f"data: {json.dumps({'type': 'tool_start', 'name': event['name'], 'args': event['args']}, ensure_ascii=False)}\n\n"

                elif event["type"] == "agent_switch":
                    # ================================================
                    # agent_switch 事件: 多 Agent 模式下切换执行的 Agent
                    # JSON: { type: "agent_switch", to_agent: "researcher", task: "搜索相关信息" }
                    # 前端处理: 展示当前执行 Agent 的名称或图标
                    # 仅多 Agent 模式会触发（如 supervisor 模式下的子 Agent 切换）
                    # ================================================
                    yield f"data: {json.dumps({'type': 'agent_switch', 'to_agent': event.get('to_agent', ''), 'task': event.get('task', '')}, ensure_ascii=False)}\n\n"

                elif event["type"] == "done":
                    # ================================================
                    # done 事件: Agent 完成回复
                    # JSON: { type: "done", sources: [...] }
                    # 前端处理: 标记回复完成，停止 token 追加，展示最终来源列表
                    # 注意: 此事件后还会有一个 [DONE] 信号
                    # ================================================
                    if event.get("sources"):
                        sources = event["sources"]
                    yield f"data: {json.dumps({'type': 'done', 'sources': sources}, ensure_ascii=False)}\n\n"

        # ================================================================
        # [DONE] 信号: 流结束
        # 前端处理: 收到此信号后应立即关闭 SSE 连接，结束 loading 状态
        #
        # 重要时序说明:
        # [DONE] 在此处立即发送，不等待后续的 DB 写入和 Mem0 记忆保存。
        # 这样前端不会因为后端持久化操作（通常 2-5 秒）而卡在 loading 状态。
        # 后续的 DB 操作在 finally / 清理代码中异步完成，不影响用户体验。
        # ================================================================
        try:
            yield "data: [DONE]\n\n"
        except (GeneratorExit, StopAsyncIteration, RuntimeError):
            # 如果客户端已断开连接，忽略 yield 错误
            pass

    except Exception as e:
        # ================================================================
        # 异常处理: Agent 运行过程中发生错误
        # 前端处理: 展示错误信息，正常结束 loading
        #
        # 安全考虑: 不在 SSE 事件中暴露详细的错误信息（避免泄露内部实现）
        # 详细的错误信息记录在服务器日志中（logger.error + traceback.print_exc）
        # 前端仅收到友好的错误提示文本
        # ================================================================
        import traceback
        logger.error(f"Agent error: {type(e).__name__}: {e}", exc_info=True)
        traceback.print_exc()
        error_msg = "抱歉，服务暂时不可用，请稍后重试。"

        # ================================================================
        # error 事件: 通知前端发生错误
        # JSON: { type: "error", content: "抱歉，服务暂时不可用，请稍后重试。" }
        # 前端处理: 在聊天界面展示错误提示，结束 loading 状态
        # ================================================================
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg}, ensure_ascii=False)}\n\n"
        full_response = f"[系统提示] {error_msg}"

        # ================================================================
        # 错误后仍发送 [DONE]，确保前端连接能正常关闭
        # ================================================================
        try:
            yield "data: [DONE]\n\n"
        except (GeneratorExit, StopAsyncIteration, RuntimeError):
            pass

    # ================================================================
    # 后处理: DB 持久化和长期记忆保存（在 [DONE] 之后执行）
    #
    # 前端注意: 此段代码在 [DONE] 发送后才执行，
    # 前端收不到这些操作的任何通知。这是有意设计的——
    # 持久化不应阻塞用户的交互体验。
    # ================================================================
    if full_response:
        try:
            async with async_session_factory() as db:
                # ================================================================
                # 1. 保存 assistant 消息到数据库
                # ================================================================
                assistant_msg = Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_response,
                    metadata_={"sources": sources} if sources else {},
                )
                db.add(assistant_msg)

                # ================================================================
                # 2. 更新会话标题（如果是新会话，用第一条用户消息作为标题）
                # 规则：仅当标题为默认值 "New Conversation" 时更新
                # 标题取第一条用户消息的前 50 个字符
                # ================================================================
                conv_result = await db.execute(
                    select(Conversation).where(Conversation.id == conversation_id)
                )
                conv = conv_result.scalar_one_or_none()
                if conv and conv.title == "New Conversation":
                    # 查找第一条用户消息
                    user_result = await db.execute(
                        select(Message)
                        .where(Message.conversation_id == conversation_id)
                        .where(Message.role == "user")
                        .order_by(Message.id)
                        .limit(1)
                    )
                    first_user = user_result.scalar_one_or_none()
                    if first_user:
                        # 截取前 50 字符，超出部分加 "..."
                        conv.title = first_user.content[:50] + ("..." if len(first_user.content) > 50 else "")

                await db.commit()

                # ================================================================
                # 3. 保存到长期记忆（Mem0）
                # 注意：记忆保存在独立的 try 块中，失败不影响消息持久化
                # ================================================================
                try:
                    # 获取最后一条用户消息用于记忆关联
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
                    # 记忆保存失败不影响整体流程，仅记录警告
                    logger.warning(f"Memory save failed: {e}")
        except Exception as e:
            # DB 持久化失败，仅记录警告（此时前端已断开连接）
            logger.warning(f"Failed to save assistant message: {e}")
