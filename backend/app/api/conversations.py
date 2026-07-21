"""
Conversation CRUD endpoints — enterprise design.
会话 增删改查 API 端点 — 企业级设计。

================================================================================
  模块级说明（中文·前端开发者必读）
================================================================================

本模块提供会话（Conversation）的完整生命周期管理，共 5 个端点。

核心设计原则：
  - 所有操作使用 POST 方法 + JSON 请求体
  - 资源 ID 始终放在 POST Body 中，**绝不**出现在 URL 路径或查询参数中
  - 符合企业级 API 安全规范，ID 不暴露在服务器访问日志中

════════════════════════════════════════════════════════════════════════════════
端点总览（5个端点）
════════════════════════════════════════════════════════════════════════════════

  ┌───────────────────────────────────────────┬──────────┬──────────────────────────────────┐
  │  端点                                     │  方法    │  说明                             │
  ├───────────────────────────────────────────┼──────────┼──────────────────────────────────┤
  │  /api/conversations/create                │  POST    │  创建新会话                       │
  │  /api/conversations/list                  │  POST    │  分页获取会话列表                 │
  │  /api/conversations/get                   │  POST    │  获取会话详情（含消息列表）        │
  │  /api/conversations/delete                │  POST    │  删除会话（级联删除所有消息）      │
  │  /api/conversations/update-title          │  POST    │  修改会话标题                     │
  └───────────────────────────────────────────┴──────────┴──────────────────────────────────┘

════════════════════════════════════════════════════════════════════════════════
会话数据模型（前端核心概念）
════════════════════════════════════════════════════════════════════════════════

Conversation 对象字段说明：
  ┌──────────────────┬──────────┬────────────────────────────────────────────────┐
  │  字段            │  类型    │  说明                                           │
  ├──────────────────┼──────────┼────────────────────────────────────────────────┤
  │  id              │  string  │  会话唯一标识（UUID v4，后端自动生成）           │
  │  title           │  string  │  会话标题，创建时由前端传入，默认为              │
  │                  │          │  "New Conversation"                             │
  │  agent_id        │  string? │  关联的智能体ID，可为 null（使用默认智能体）     │
  │  created_at      │  string  │  创建时间（ISO 8601 格式）                      │
  │  updated_at      │  string  │  最后更新时间（新消息或标题变更时自动更新）       │
  │  message_count   │  number  │  消息总数（仅列表/详情响应中包含）              │
  └──────────────────┴──────────┴────────────────────────────────────────────────┘

Message 对象字段说明：
  ┌──────────────────┬──────────┬────────────────────────────────────────────────┐
  │  字段            │  类型    │  说明                                           │
  ├──────────────────┼──────────┼────────────────────────────────────────────────┤
  │  id              │  number  │  消息ID（数据库自增整数，非UUID）               │
  │  role            │  string  │  角色："user"（用户）或 "assistant"（AI助手）   │
  │  content         │  string  │  消息文本内容                                   │
  │  metadata        │  object? │  消息元数据（JSON对象），可能包含RAG检索结果等   │
  │  created_at      │  string  │  消息创建时间（ISO 8601 格式）                  │
  └──────────────────┴──────────┴────────────────────────────────────────────────┘

════════════════════════════════════════════════════════════════════════════════
通用注意事项
════════════════════════════════════════════════════════════════════════════════

1. 所有请求的 Content-Type 必须为 application/json
2. 所有日期时间均为 ISO 8601 UTC 格式（如 "2025-01-15T10:30:00"）
3. 分页参数 skip 起始为 0（即 skip=0 表示从第一条开始）
4. 删除操作不可逆，前端务必弹出二次确认对话框
5. 404 表示会话不存在（可能已被删除或 ID 错误）
6. 422 表示请求参数校验失败（字段格式/范围不符合要求）
================================================================================
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


# ═══════════════════════════════════════════════════════════════════════════════
# 端点 1/5：创建会话  POST /api/conversations/create
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/create", response_model=ConversationOut)
async def create_conversation(
    request: ConversationCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    ============================================================
    创建新会话。

    请求格式（Request JSON）：
    ```json
    {
      "title": "我的新对话",         // 可选，默认 "New Conversation"，1-200字符
      "agent_id": "uuid-string"    // 可选，不传则使用默认智能体
    }
    ```

    最简请求（全部使用默认值）：
    ```json
    {}
    ```

    响应格式（Response JSON）：
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "我的新对话",
      "agent_id": "uuid-string",
      "created_at": "2025-01-15T10:30:00",
      "updated_at": "2025-01-15T10:30:00",
      "message_count": 0
    }
    ```

    前端对接指南：
      1. 创建会话后，必须保存返回的 id 字段，
         后续发送消息时需要传入 conversation_id
      2. 新会话的 message_count 始终为 0
      3. 创建成功后，前端通常跳转到该会话的聊天界面
      4. agent_id 为空时，后端使用 is_default=true 的 Agent 配置
      5. 如果数据库中没有任何 Agent 配置，会话仍可创建但聊天功能
         可能无法正常工作（需要先创建至少一个 Agent）
    ============================================================
    """
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


# ═══════════════════════════════════════════════════════════════════════════════
# 端点 2/5：会话列表  POST /api/conversations/list
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/list", response_model=list[ConversationOut])
async def list_conversations(
    request: ConversationListRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    ============================================================
    分页获取会话列表，按最后更新时间降序排列。

    请求格式（Request JSON）：
    ```json
    {
      "skip": 0,     // 跳过的记录数，默认 0（从第一条开始）
      "limit": 20    // 最大返回条数，默认 50，范围 1-200
    }
    ```

    请求示例（获取第 1 页，每页 20 条）：
    ```json
    { "skip": 0, "limit": 20 }
    ```

    请求示例（获取第 2 页）：
    ```json
    { "skip": 20, "limit": 20 }
    ```

    响应格式（Response JSON）：
    ```json
    [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "产品方案讨论",
        "agent_id": "uuid-string",
        "created_at": "2025-01-14T08:00:00",
        "updated_at": "2025-01-15T22:30:00",
        "message_count": 42
      },
      {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "title": "技术问题咨询",
        "agent_id": null,
        "created_at": "2025-01-15T09:00:00",
        "updated_at": "2025-01-15T10:00:00",
        "message_count": 5
      }
    ]
    ```

    排序规则：
      - 按 updated_at 降序排列（最近活跃的会话排在最前面）
      - 发送新消息、修改标题都会更新 updated_at

    message_count 说明：
      - 通过 SQL JOIN + COUNT 子查询实时计算，始终准确
      - 用于在列表页显示每个会话的消息数量，如 "42 条消息"

    前端对接指南：
      1. 典型前端分页实现：
         ```javascript
         const [page, setPage] = useState(1); // 从 1 开始
         const PAGE_SIZE = 20;

         const { data } = await apiPost('/api/conversations/list', {
           skip: (page - 1) * PAGE_SIZE,  // 第1页 skip=0, 第2页 skip=20
           limit: PAGE_SIZE,
         });
         // 如果返回的数据长度 < PAGE_SIZE，说明已是最后一页
         const hasMore = data.length === PAGE_SIZE;
         ```

      2. 列表内容实时更新策略：
         - 创建新会话后：刷新列表
         - 发送新消息后：当前会话的 updated_at 和 message_count 会变化，
           但后端不会推送到前端，建议前端在消息发送成功后同步更新
           本地状态中的 message_count（+1）
         - 删除会话后：刷新列表，并将当前 active 会话取消选中

      3. 空状态处理：
         如果列表返回空数组 []，前端应显示空状态占位图（Empty State），
         引导用户点击"新建会话"按钮。

      4. 性能优化：
         - 列表接口建议在用户进入侧边栏时调用一次即可
         - 不需要轮询，会话列表变化是低频事件（由用户操作驱动）
    ============================================================
    """
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


# ═══════════════════════════════════════════════════════════════════════════════
# 端点 3/5：获取会话详情  POST /api/conversations/get
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/get", response_model=ConversationDetail)
async def get_conversation(
    request: ConversationGetRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    ============================================================
    获取单个会话的完整详情，包含所有消息列表。

    请求格式（Request JSON）：
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```

    响应格式（Response JSON）：
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "产品方案讨论",
      "agent_id": "uuid-string",
      "created_at": "2025-01-14T08:00:00",
      "updated_at": "2025-01-15T22:30:00",
      "message_count": 3,
      "messages": [
        {
          "id": 1,
          "role": "user",
          "content": "帮我分析一下这个产品方案",
          "metadata": null,
          "created_at": "2025-01-14T08:00:00"
        },
        {
          "id": 2,
          "role": "assistant",
          "content": "好的，我来帮您分析...",
          "metadata": { "sources": ["文档A", "文档B"] },
          "created_at": "2025-01-14T08:00:05"
        },
        {
          "id": 3,
          "role": "user",
          "content": "继续",
          "metadata": null,
          "created_at": "2025-01-14T08:01:00"
        }
      ]
    }
    ```

    可能的错误状态码：
      404 — 会话不存在（id 错误或已被删除）
      422 — id 格式不合法（包含危险字符）

    messages 字段说明：
      - 消息按 id 升序排列（即按发送时间先后顺序）
      - role 值为 "user" 或 "assistant"
      - metadata 可能为 null（无额外数据）或包含 JSON 对象
        （如 RAG 检索来源、工具调用结果等）
      - 每条消息的 id 是数据库自增整数（在同一会话内递增），
        不跨会话共享

    前端对接指南：
      1. 此接口通常在用户点击侧边栏中的某个会话时调用，
         用于加载该会话的完整聊天记录。

      2. 消息渲染：
         - user 消息：显示在聊天气泡的右侧（或用户侧）
         - assistant 消息：显示在聊天气泡的左侧（或 AI 侧）
         - metadata 中包含 sources 时，可在 AI 回复底部展示"参考来源"链接

      3. 加载状态：
         会话详情首次加载时建议显示骨架屏（Skeleton）或加载动画，
         因为消息数量可能较多，网络传输需要一定时间。

      4. 关于"继续获取更多消息"（分页消息）：
         当前版本一次性返回会话的全部消息，不支持分页加载。
         如果会话消息数量非常大（如 > 200 条），建议在产品层面
         引导用户开启新会话，或将旧会话归档。

      5. WebSocket / 实时更新：
         当前版本为 REST API，不支持 WebSocket 实时推送。
         新消息不会自动出现在已加载的详情页中。
         前端需要在发送消息后手动将 AI 回复追加到本地 messages 数组中。
    ============================================================
    """
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


# ═══════════════════════════════════════════════════════════════════════════════
# 端点 4/5：删除会话  POST /api/conversations/delete
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/delete")
async def delete_conversation(
    request: ConversationDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    ============================================================
    删除指定会话。注意：此操作会级联删除该会话下的所有消息。

    请求格式（Request JSON）：
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```

    响应格式（Response JSON）：
    ```json
    {
      "detail": "Conversation deleted successfully"
    }
    ```

    可能的错误状态码：
      404 — 会话不存在（可能已被删除或 ID 错误）
      422 — id 格式不合法

    级联删除说明：
      - 删除会话时，该会话下的所有 Message 记录也会被删除
      - 数据库层面通过 ForeignKey(ondelete="CASCADE") 保证一致性
      - 删除操作不可逆！一旦删除，消息记录无法恢复

    不会影响的数据：
      - 关联的 AgentConfig 不会被删除（Agent 是独立存在的）
      - 知识库文档（Document）不会被删除
      - 其他会话不受影响

    前端对接指南：
      1. 务必在调用此接口前弹出确认对话框（Modal Confirm）：
         "确定要删除此对话吗？所有聊天记录将被永久删除且无法恢复。"

      2. 删除成功后的前端状态更新：
         ```javascript
         async function handleDelete(conversationId) {
           const confirmed = await showConfirmDialog('确定删除此对话？');
           if (!confirmed) return;

           await apiPost('/api/conversations/delete', { id: conversationId });

           // 从本地列表中移除被删除的会话
           setConversations(prev => prev.filter(c => c.id !== conversationId));

           // 如果当前正在查看此会话，跳转到空状态或下一个会话
           if (activeConversationId === conversationId) {
             setActiveConversationId(null);
             setMessages([]);
           }
         }
         ```

      3. 乐观删除 vs 确认后删除：
         推荐使用"确认后删除"（如上例），而非"乐观删除"。
         因为删除是不可逆操作，确认步骤能有效防止误操作。

      4. 错误处理：
         如果 404（会话不存在），可能是其他用户或标签页已删除了同一会话，
         前端应静默地从列表中移除该项，不弹错误提示。
    ============================================================
    """
    result = await db.execute(
        select(Conversation).where(Conversation.id == request.id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.execute(delete(Conversation).where(Conversation.id == request.id))
    await db.commit()
    return {"detail": "Conversation deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════════
# 端点 5/5：更新会话标题  POST /api/conversations/update-title
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/update-title")
async def update_title(
    request: ConversationTitleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    ============================================================
    修改会话标题。注意：只有 title 字段可更新，agent_id 不可通过此接口修改。

    请求格式（Request JSON）：
    ```json
    {
      "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "产品方案讨论（更新版）"
    }
    ```

    响应格式（Response JSON）：
    ```json
    {
      "detail": "Title updated",
      "title": "产品方案讨论（更新版）"
    }
    ```

    可能的错误状态码：
      404 — 会话不存在
      422 — 参数校验失败（conversation_id 为空、title 为空或超过200字符）

    字段说明：
      - conversation_id：要修改的会话 ID，必填
      - title：新的标题文本，必填，1-200 字符

    为什么是独立端点而非通用 update？
      - 遵循 REST 单一职责原则：一个端点只做一件事
      - 简化权限校验：标题修改不需要验证其他字段
      - 减少错误：不会因为误传 agent_id 而错误修改 Agent 关联

    前端对接指南：
      1. 触发场景示例：
         - 用户在侧边栏右键点击会话 → "重命名"
         - 用户在聊天顶部点击标题 → 进入编辑模式（Inline Edit）
         - AI 首次回复后，前端自动调用此接口将标题从
           "New Conversation" 更新为 AI 生成的摘要标题

      2. 内联编辑实现（推荐）：
         ```javascript
         async function handleRename(conversationId, newTitle) {
           // 空标题或纯空白标题不提交
           const trimmed = newTitle.trim();
           if (!trimmed) return;

           try {
             await apiPost('/api/conversations/update-title', {
               conversation_id: conversationId,
               title: trimmed,
             });

             // 更新本地状态
             setConversations(prev => prev.map(c =>
               c.id === conversationId ? { ...c, title: trimmed } : c
             ));
           } catch (err) {
             // 标题更新失败不应影响聊天主功能
             console.error('标题更新失败:', err);
           }
         }
         ```

      3. 标题自动生成（可选增强）：
         在 AI 回复第一条消息后，可以调用 LLM 生成简短摘要作为标题。
         这是一个可选的前端增强功能，后端不支持自动标题生成。
         实现参考：
         ```javascript
         // 在收到 AI 第一条回复后
         if (messages.length === 2) {  // 只有一问一答
           const summary = await generateTitleSummary(messages);
           await updateConversationTitle(conversationId, summary);
         }
         ```
    ============================================================
    """
    result = await db.execute(
        select(Conversation).where(Conversation.id == request.conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv.title = request.title
    await db.commit()
    return {"detail": "Title updated", "title": request.title}
