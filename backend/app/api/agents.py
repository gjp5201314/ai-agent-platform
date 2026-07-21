"""
Agent configuration CRUD endpoints — enterprise design.
智能体配置 增删改查 API 端点 — 企业级设计。

================================================================================
  模块级说明（中文·前端开发者必读）
================================================================================

本模块提供 AI 智能体（Agent）的完整配置管理，共 6 个端点。

核心设计原则：
  - 所有操作使用 POST 方法 + JSON 请求体
  - 资源 ID 始终放在 POST Body 中，**绝不**出现在 URL 路径或查询参数中
  - 符合企业级 API 安全规范

════════════════════════════════════════════════════════════════════════════════
端点总览（6个端点）
════════════════════════════════════════════════════════════════════════════════

  ┌───────────────────────────────────────────┬──────────┬──────────────────────────────────┐
  │  端点                                     │  方法    │  说明                             │
  ├───────────────────────────────────────────┼──────────┼──────────────────────────────────┤
  │  /api/agents/tools                        │  POST    │  获取所有可用工具列表             │
  │  /api/agents/list                         │  POST    │  分页获取 Agent 列表              │
  │  /api/agents/create                       │  POST    │  创建新的 Agent 配置              │
  │  /api/agents/get                          │  POST    │  获取单个 Agent 配置              │
  │  /api/agents/update                       │  POST    │  更新 Agent 配置                  │
  │  /api/agents/delete                       │  POST    │  删除 Agent（受保护/默认的除外）   │
  └───────────────────────────────────────────┴──────────┴──────────────────────────────────┘

════════════════════════════════════════════════════════════════════════════════
AgentConfig 数据模型（前端核心概念）
════════════════════════════════════════════════════════════════════════════════

AgentConfig 是一个 AI 智能体的"人格配置文件"，定义了 AI 的行为方式：

  ┌────────────────────────────┬──────────┬──────────────────────────────────────────────┐
  │  字段                      │  类型    │  说明                                         │
  ├────────────────────────────┼──────────┼──────────────────────────────────────────────┤
  │  id                        │  string  │  Agent 唯一标识（UUID v4）                    │
  │  name                      │  string  │  Agent 名称，如"客服助手"、"代码审查员"       │
  │  description               │  string  │  Agent 功能描述，用于前端展示                 │
  │  system_prompt             │  string  │  系统提示词——定义 AI 的"人设"和角色行为       │
  │                            │          │  默认："You are a helpful AI assistant."      │
  │  temperature               │  number  │  模型温度（0.0-2.0），控制回答的随机性/创造性 │
  │                            │          │  0.0=严格保守, 2.0=极度发散, 默认 0.7         │
  │  max_tokens                │  number  │  单次回复最大 Token 数，默认 4096              │
  │  enabled_tools             │  array   │  启用的工具列表，如 ["rag", "web_search"]     │
  │  rag_top_k                 │  number  │  RAG 检索返回分块数，默认 4，范围 1-20        │
  │  rag_similarity_threshold  │  number  │  RAG 检索相似度阈值，默认 0.5，范围 0.0-1.0   │
  │  is_default                │  boolean │  是否为系统默认 Agent（只能有一个）            │
  │  is_protected              │  boolean │  是否为受保护 Agent（系统内置，不可删除）      │
  │  allow_delegation          │  boolean │  是否允许其他 Agent 将子任务委托给此 Agent     │
  │  created_at                │  string  │  创建时间（ISO 8601 UTC 格式）                │
  └────────────────────────────┴──────────┴──────────────────────────────────────────────┘

关键概念详解：

1. system_prompt（系统提示词）
   - 这是 Agent 的"灵魂"，定义了 Agent 的角色、知识范围和行为准则
   - 示例："你是一个专业的前端开发顾问，精通 React、TypeScript 和 CSS。请用简洁的语言回答技术问题。"
   - system_prompt 在每次对话开始时注入，对用户不可见
   - 前端可在 Agent 编辑器中提供一个多行文本框用于编辑此字段

2. temperature（温度参数）
   - 控制 LLM 输出的"创造性"程度
   - 0.0-0.3：适合代码生成、数学计算等需要精确性的场景
   - 0.5-0.7：适合一般对话、客服等平衡场景（默认值）
   - 0.8-1.5：适合创意写作、头脑风暴等发散性场景
   - 1.5-2.0：输出可能变得不稳定、不可预测，通常不推荐
   - 前端建议用滑块（Slider）组件展示，标注"保守 ← → 创意"

3. enabled_tools（启用的工具）
   - 这是一个字符串数组，列出 Agent 可以使用的工具
   - 可用的工具通过 /api/agents/tools 接口查询
   - 常见工具：rag（知识库检索）、web_search（联网搜索）、calculator（计算器）
   - 空数组 [] 表示不启用任何工具，Agent 只能纯对话
   - 前端建议用多选开关（Toggle/Checkbox）组件展示

4. rag_top_k 和 rag_similarity_threshold（RAG 参数）
   - 仅当 enabled_tools 包含 "rag" 时生效
   - rag_top_k：从知识库中检索多少个最相关的文档分块，值越大上下文越丰富但 Token 消耗越多
   - rag_similarity_threshold：相似度阈值，低于此值的检索结果被丢弃，值越高检索越精准
   - 前端建议显示为高级配置（可折叠区域），并提供合理的默认值

5. is_protected（受保护标记）
   - 系统内置 Agent（如默认助手）的 is_protected=true
   - 受保护的 Agent 不可删除，前端应隐藏删除按钮或置灰
   - 此字段由后端在数据库中直接设置，前端创建 Agent 时不会自动设为 true
   - 判断逻辑：if (agent.is_protected) { /* 禁用删除按钮 */ }

6. allow_delegation（委托权限）
   - 控制此 Agent 是否可以被其他 Agent 作为子任务委托目标
   - 在多 Agent 协作场景下使用（主管 Agent 将子任务分发给专员 Agent）
   - true  = 允许被委托（默认），此 Agent 可以接收其他 Agent 派发的任务
   - false = 仅独立工作，不接受委托
   - 前端建议显示为一个开关（Switch），并附带说明文字

════════════════════════════════════════════════════════════════════════════════
字段默认值汇总（创建 Agent 时的默认值）
════════════════════════════════════════════════════════════════════════════════

  ┌────────────────────────────┬───────────────────────────────────────────┐
  │  字段                      │  默认值                                    │
  ├────────────────────────────┼───────────────────────────────────────────┤
  │  name                      │  （必填，无默认值）                         │
  │  description               │  ""（空字符串）                             │
  │  system_prompt             │  "You are a helpful AI assistant."        │
  │  temperature               │  0.7                                       │
  │  max_tokens                │  4096                                      │
  │  enabled_tools             │  []（空数组，不启用任何工具）               │
  │  rag_top_k                 │  4                                         │
  │  rag_similarity_threshold  │  0.5                                       │
  │  is_default                │  false（创建时不可设置，由 update 接口设置）│
  │  is_protected              │  false（由系统设置，前端不可修改）           │
  │  allow_delegation          │  true（允许委托）                          │
  └────────────────────────────┴───────────────────────────────────────────┘

════════════════════════════════════════════════════════════════════════════════
前端错误处理参考
════════════════════════════════════════════════════════════════════════════════

  常见错误码及处理建议：
  ┌────────┬──────────────────────────────────────────────────────────────────┐
  │  400   │  "Cannot delete a protected system agent"                        │
  │        │  前端应隐藏受保护 Agent 的删除按钮，或置灰并显示 Tooltip 说明    │
  ├────────┼──────────────────────────────────────────────────────────────────┤
  │  400   │  "Cannot delete the default agent"                               │
  │        │  默认 Agent 不可删除，需先将其他 Agent 设为默认后再操作          │
  ├────────┼──────────────────────────────────────────────────────────────────┤
  │  404   │  Agent 不存在（ID 错误或已被删除），前端应从列表中移除该项       │
  ├────────┼──────────────────────────────────────────────────────────────────┤
  │  422   │  请求参数校验失败，检查字段格式是否符合要求                      │
  ├────────┼──────────────────────────────────────────────────────────────────┤
  │  429   │  触发了 write 层速率限制（10次/60秒），请稍后再试                │
  └────────┴──────────────────────────────────────────────────────────────────┘

================================================================================
"""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AgentConfig
from app.schemas import (
    AgentConfigCreate,
    AgentConfigUpdate,
    AgentConfigOut,
    AgentListRequest,
    AgentGetRequest,
    AgentDeleteRequest,
)
from app.agent.tools import ALL_TOOLS

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# 端点 1/6：获取可用工具列表  POST /api/agents/tools
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/tools")
async def list_available_tools():
    """
    ============================================================
    获取系统中所有可用的工具列表。
    此接口不需要任何参数（POST 空请求体），用于前端渲染工具选择器。

    工具类型说明：
      - "function"  — 标准函数工具（HTTP请求、代码执行、数学计算等）
      - "rag"       — 知识库检索工具（搜索已上传的文档）
      - "meta"      — 元工具（如 Agent 委托，不调用外部 API）

    请求格式（Request JSON）：
    ```json
    {}
    ```
    注意：虽然不需要参数，但必须发送 POST 请求（符合 API 设计规范）。

    响应格式（Response JSON）：
    ```json
    {
      "tools": [
        {
          "name": "web_search",
          "description": "联网搜索：在互联网上搜索最新信息",
          "type": "function"
        },
        {
          "name": "calculator",
          "description": "计算器：执行数学表达式计算",
          "type": "function"
        },
        {
          "name": "python_executor",
          "description": "Python 代码沙箱：安全执行 Python 代码片段",
          "type": "function"
        },
        {
          "name": "rag",
          "description": "知识库检索：搜索上传的文档进行精准问答",
          "type": "rag"
        },
        {
          "name": "delegate_to_agent",
          "description": "Agent 委托：将子任务委托给其他专业 Agent 处理",
          "type": "meta"
        }
      ]
    }
    ```

    tools 数组元素字段说明：
      - name        — 工具名称（英文标识符），存入 Agent.enabled_tools 数组时使用此值
      - description — 工具的中文功能描述，前端可在工具选择器中展示
      - type        — 工具类型："function" | "rag" | "meta"

    前端对接指南：
      1. 在 Agent 创建/编辑页面加载时调用此接口，
         将返回的 tools 数组渲染为可多选的工具选择器

      2. 工具选择器实现示例：
         ```javascript
         const { data } = await apiPost('/api/agents/tools', {});
         const availableTools = data.tools;

         // 渲染为多选 Checkbox 列表
         {availableTools.map(tool => (
           <label key={tool.name}>
             <input
               type="checkbox"
               checked={selectedTools.includes(tool.name)}
               onChange={() => toggleTool(tool.name)}
             />
             <span>{tool.description}</span>
             <span className="tool-type-badge">{tool.type}</span>
           </label>
         ))}
         ```

      3. 工具数量说明：
         内置工具：rag（知识库检索）、delegate_to_agent（Agent 委托）
         ALL_TOOLS 中注册的其他工具会动态追加到列表末尾

      4. 工具与 Agent 的关联：
         用户在创建/编辑 Agent 时选择的工具名称，
         会存入 AgentConfig.enabled_tools 数组字段。
         例如：enabled_tools: ["rag", "web_search"]
    ============================================================
    """
    # 构建内置工具列表（rag 和 delegate_to_agent 是平台核心工具）
    tools = [{
        "name": "rag",
        "description": "知识库检索：搜索上传的文档进行精准问答",
        "type": "rag",
    }, {
        "name": "delegate_to_agent",
        "description": "Agent 委托：将子任务委托给其他专业 Agent 处理（如知识库助手）",
        "type": "meta",
    }]
    # 动态追加 ALL_TOOLS 中注册的所有函数工具
    for name, tool_obj in ALL_TOOLS.items():
        tools.append({
            "name": name,
            "description": tool_obj.description or "",
            "type": "function",
        })
    return {"tools": tools}


# ═══════════════════════════════════════════════════════════════════════════════
# 端点 2/6：Agent 列表  POST /api/agents/list
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/list", response_model=list[AgentConfigOut])
async def list_agents(
    request: AgentListRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    ============================================================
    分页获取 Agent 配置列表，按创建时间降序排列。

    请求格式（Request JSON）：
    ```json
    {
      "skip": 0,     // 跳过的记录数，默认 0
      "limit": 20    // 最大返回条数，默认 50，范围 1-200
    }
    ```

    响应格式（Response JSON）：
    ```json
    [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "客服助手",
        "description": "专业处理客户咨询",
        "system_prompt": "你是一个客服专家...",
        "temperature": 0.7,
        "max_tokens": 4096,
        "enabled_tools": ["rag", "web_search"],
        "rag_top_k": 4,
        "rag_similarity_threshold": 0.5,
        "is_default": true,
        "is_protected": true,
        "allow_delegation": true
      },
      {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "name": "代码审查员",
        "description": "审查代码质量",
        "system_prompt": "你是一个高级代码审查员...",
        "temperature": 0.2,
        "max_tokens": 8192,
        "enabled_tools": [],
        "rag_top_k": 4,
        "rag_similarity_threshold": 0.5,
        "is_default": false,
        "is_protected": false,
        "allow_delegation": true
      }
    ]
    ```

    排序规则：按 created_at 降序（最新创建的排在最前面）

    前端对接指南：
      1. Agent 列表通常展示在管理页面的表格或卡片中
      2. is_default=true 的 Agent 应在列表中高亮显示（如金色边框/徽章）
      3. is_protected=true 的 Agent 应隐藏删除按钮或置灰
      4. allow_delegation 可在列表中显示为一个小的状态标签
      5. enabled_tools 可用 Tag/Badge 组件展示工具名称
      6. system_prompt 在列表中建议截断显示（如只显示前 80 字符 + "..."）
      7. 此列表建议在页面加载时调用一次，不需要轮询
    ============================================================
    """
    result = await db.execute(
        select(AgentConfig)
        .order_by(AgentConfig.created_at.desc())
        .offset(request.skip)
        .limit(request.limit)
    )
    return result.scalars().all()


# ═══════════════════════════════════════════════════════════════════════════════
# 端点 3/6：创建 Agent  POST /api/agents/create
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/create", response_model=AgentConfigOut)
async def create_agent(
    request: AgentConfigCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    ============================================================
    创建新的 Agent 配置。

    请求格式（Request JSON — 完整示例）：
    ```json
    {
      "name": "客服助手",
      "description": "处理用户咨询和投诉",
      "system_prompt": "你是一个专业的客服代表。请用友好、耐心的语气回答用户问题。",
      "temperature": 0.7,
      "max_tokens": 4096,
      "enabled_tools": ["rag", "web_search"],
      "rag_top_k": 4,
      "rag_similarity_threshold": 0.5,
      "allow_delegation": true
    }
    ```

    最简请求（仅必填字段，其余使用默认值）：
    ```json
    {
      "name": "我的助手"
    }
    ```

    响应格式（Response JSON）：
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "客服助手",
      "description": "处理用户咨询和投诉",
      "system_prompt": "你是一个专业的客服代表...",
      "temperature": 0.7,
      "max_tokens": 4096,
      "enabled_tools": ["rag", "web_search"],
      "rag_top_k": 4,
      "rag_similarity_threshold": 0.5,
      "is_default": false,
      "is_protected": false,
      "allow_delegation": true
    }
    ```

    字段校验规则摘要：
      ┌────────────────────────────┬─────────────────────────────────────────────┐
      │  字段                      │  校验规则                                    │
      ├────────────────────────────┼─────────────────────────────────────────────┤
      │  name                      │  必填，1-100 字符                            │
      │  description               │  可选，0-500 字符，默认 ""                   │
      │  system_prompt             │  可选，1-5000 字符，默认通用提示词            │
      │  temperature               │  可选，0.0-2.0，默认 0.7                     │
      │  max_tokens                │  可选，1-131072，默认 4096                   │
      │  enabled_tools             │  可选，最多 50 个工具，默认 []               │
      │  rag_top_k                 │  可选，1-20，默认 4                          │
      │  rag_similarity_threshold  │  可选，0.0-1.0，默认 0.5                     │
      │  allow_delegation          │  可选，true/false，默认 true                 │
      └────────────────────────────┴─────────────────────────────────────────────┘

    is_default 和 is_protected 说明：
      - 创建时不可设置 is_default，新 Agent 的 is_default 始终为 false
      - 创建时不可设置 is_protected，新 Agent 的 is_protected 始终为 false
      - 如需将 Agent 设为默认，请使用更新接口
      - is_protected 只能由系统管理员在数据库中直接修改

    前端对接指南：
      1. 创建表单设计建议：
         ```
         ┌─────────────────────────────────────┐
         │  创建新 Agent                        │
         │                                      │
         │  名称 *          [_______________]  │
         │  描述             [_______________]  │
         │  系统提示词       [_______________]  │  ← 多行文本框
         │                                      │
         │  温度参数         0.7  [====o====]  │  ← 滑块
         │     保守 ←          → 创意           │
         │                                      │
         │  最大 Tokens      4096 [________]   │  ← 数字输入
         │                                      │
         │  工具选择：                           │
         │      ☑ 知识库检索 (rag)              │  ← 复选框列表
         │      ☑ 联网搜索 (web_search)         │
         │      ☐ 计算器 (calculator)           │
         │                                      │
         │  RAG 配置：                           │  ← 可折叠区域
         │      Top-K: [4]   阈值: [0.5]       │
         │                                      │
         │  ☑ 允许其他 Agent 委托任务            │  ← 开关
         │                                      │
         │  [取消]              [创建 Agent]    │
         └─────────────────────────────────────┘
         ```

      2. 创建成功后，前端应刷新 Agent 列表并将其置顶
         （因为列表按创建时间降序排列）

      3. 建议在 Agent 选择器中提供"从现有 Agent 复制配置"的功能
         （预填表单字段），提升用户体验
    ============================================================
    """
    agent = AgentConfig(
        id=str(uuid4()),
        name=request.name,
        description=request.description,
        system_prompt=request.system_prompt,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        enabled_tools=request.enabled_tools,
        rag_top_k=request.rag_top_k,
        rag_similarity_threshold=request.rag_similarity_threshold,
        allow_delegation=request.allow_delegation,
    )
    db.add(agent)
    await db.commit()

    result = await db.execute(select(AgentConfig).where(AgentConfig.id == agent.id))
    return result.scalar_one()


# ═══════════════════════════════════════════════════════════════════════════════
# 端点 4/6：获取 Agent 详情  POST /api/agents/get
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/get", response_model=AgentConfigOut)
async def get_agent(
    request: AgentGetRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    ============================================================
    获取单个 Agent 的完整配置信息。

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
      "name": "客服助手",
      "description": "处理用户咨询和投诉",
      "system_prompt": "你是一个专业的客服代表...",
      "temperature": 0.7,
      "max_tokens": 4096,
      "enabled_tools": ["rag", "web_search"],
      "rag_top_k": 4,
      "rag_similarity_threshold": 0.5,
      "is_default": true,
      "is_protected": true,
      "allow_delegation": true
    }
    ```

    可能的错误状态码：
      404 — Agent 不存在
      422 — id 格式不合法

    前端对接指南：
      1. 此接口通常在以下场景调用：
         - 用户点击编辑按钮，进入 Agent 编辑页面前加载当前配置
         - 用户在 Agent 列表中点击"查看详情"

      2. 获取到的数据可以用于：
         - 预填编辑表单的各个字段
         - 在详情页以只读方式展示 Agent 的完整配置
         - 在聊天界面中选择 Agent 时显示其描述和能力
    ============================================================
    """
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == request.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


# ═══════════════════════════════════════════════════════════════════════════════
# 端点 5/6：更新 Agent  POST /api/agents/update
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/update", response_model=AgentConfigOut)
async def update_agent(
    request: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    ============================================================
    更新指定 Agent 的配置。采用"部分更新"策略：只传需要修改的字段。

    请求格式（Request JSON）：
    ```json
    {
      "agent_id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "客服助手 v2",
      "temperature": 0.3
    }
    ```

    部分更新（Partial Update）说明：
      - 只有请求体中包含的字段会被更新
      - 未包含的字段保持原值不变
      - agent_id 是查找字段，不会被当作配置更新
      - 这意味着你可以只发一条 {"agent_id":"xxx","temperature":0.3} 来修改温度

    "设为默认"的特殊逻辑：
      当 is_default 设为 true 时，后端会自动：
      1. 查找当前所有 is_default=true 的 Agent
      2. 将它们全部设为 is_default=false
      3. 将当前 Agent 设为 is_default=true
      这保证了系统中同时只有一个默认 Agent。

    响应格式（Response JSON — 更新后的完整配置）：
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "客服助手 v2",
      "description": "处理用户咨询和投诉",
      "system_prompt": "你是一个专业的客服代表...",
      "temperature": 0.3,
      "max_tokens": 4096,
      "enabled_tools": ["rag", "web_search"],
      "rag_top_k": 4,
      "rag_similarity_threshold": 0.5,
      "is_default": false,
      "is_protected": true,
      "allow_delegation": true
    }
    ```

    前端对接指南：
      1. 编辑表单应该预填当前 Agent 的所有字段值：
         ```javascript
         // 加载 Agent 详情用于预填表单
         const { data: agent } = await apiPost('/api/agents/get', { id: agentId });

         // 预填表单
         setFormData({
           agent_id: agent.id,
           name: agent.name,
           description: agent.description,
           system_prompt: agent.system_prompt,
           temperature: agent.temperature,
           max_tokens: agent.max_tokens,
           enabled_tools: agent.enabled_tools,
           rag_top_k: agent.rag_top_k,
           rag_similarity_threshold: agent.rag_similarity_threshold,
           allow_delegation: agent.allow_delegation,
         });
         ```

      2. 提交时只发送变更的字段（脏检查）：
         ```javascript
         // 比对原始值和当前值，只发送变化的部分
         const changed = {};
         for (const [key, value] of Object.entries(formData)) {
           if (value !== originalData[key]) {
             changed[key] = value;
           }
         }
         // 必须包含 agent_id
         changed.agent_id = agentId;
         await apiPost('/api/agents/update', changed);
         ```

      3. 设为默认 Agent 的交互设计：
         - 提供一个"设为默认"按钮或开关
         - 切换前弹出提示："设为默认后，原有的默认 Agent 将被替换"
         - 列表中只有一个 Agent 显示为默认状态

      4. 受保护的 Agent：
         - is_protected=true 的 Agent 可以修改配置参数，
           但前端应提示"此 Agent 为系统默认配置，部分功能受限"
         - 不能删除受保护的 Agent（delete 接口会返回 400）

      5. enabled_tools 更新注意：
         此字段的值会完全替换原有列表（不是追加），
         所以前端提交时必须传递完整的工具名称数组，
         即使只新增/移除了一个工具。
    ============================================================
    """
    result = await db.execute(
        select(AgentConfig).where(AgentConfig.id == request.agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # model_dump(exclude_unset=True) 只获取请求体中实际传递的字段
    # 未传递的字段不会被包含在 update_data 中
    update_data = request.model_dump(exclude_unset=True)
    update_data.pop("agent_id", None)  # agent_id 是查找键，不是要更新的配置字段

    # 设为默认 Agent 的特殊处理：先将所有其他 Agent 的 is_default 设为 false
    if update_data.get("is_default") is True:
        all_agents = await db.execute(
            select(AgentConfig).where(AgentConfig.is_default == True)
        )
        for a in all_agents.scalars():
            a.is_default = False

    # 批量设置所有传递的字段到 Agent 对象
    for key, value in update_data.items():
        setattr(agent, key, value)

    await db.commit()

    result = await db.execute(select(AgentConfig).where(AgentConfig.id == request.agent_id))
    return result.scalar_one()


# ═══════════════════════════════════════════════════════════════════════════════
# 端点 6/6：删除 Agent  POST /api/agents/delete
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/delete")
async def delete_agent(
    request: AgentDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    ============================================================
    删除指定 Agent 配置。

    请求格式（Request JSON）：
    ```json
    {
      "id": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```

    响应格式（Response JSON — 删除成功）：
    ```json
    {
      "detail": "Agent deleted successfully"
    }
    ```

    无法删除的情况（返回 400 错误）：
      1. Agent 设置了 is_protected=true（受保护的系统 Agent）
         → {"detail": "Cannot delete a protected system agent"}
      2. Agent 是当前默认 Agent（is_default=true）
         → {"detail": "Cannot delete the default agent"}

    其他可能的错误：
      404 — Agent 不存在

    删除影响范围：
      - Agent 配置从数据库中永久删除（不可恢复）
      - 已关联到此 Agent 的会话（Conversation）的 agent_id 不会被
        自动清空（保留为历史引用的 ID），但该 Agent 配置已不存在

    前端对接指南：
      1. 删除前必须弹出确认对话框：
         ```javascript
         async function handleDelete(agentId) {
           // 二次确认
           const confirmed = await showConfirmDialog(
             '确定要删除此 Agent 吗？此操作不可恢复。'
           );
           if (!confirmed) return;

           try {
             await apiPost('/api/agents/delete', { id: agentId });
             // 从本地列表中移除
             setAgents(prev => prev.filter(a => a.id !== agentId));
             showToast('Agent 已删除', { type: 'success' });
           } catch (err) {
             if (err.status === 400) {
               showToast(err.detail, { type: 'error' });
               // 如果是受保护的 Agent，更新本地状态标记
               // 并隐藏删除按钮
             }
           }
         }
         ```

      2. 按钮禁用逻辑：
         ```javascript
         // 判断是否可删除
         function canDelete(agent) {
           return !agent.is_protected && !agent.is_default;
         }

         // 按钮渲染
         {canDelete(agent) ? (
           <Button onClick={() => handleDelete(agent.id)}>删除</Button>
         ) : (
           <Tooltip
             title={
               agent.is_protected
                 ? '系统受保护的 Agent，无法删除'
                 : '默认 Agent 无法删除，请先设置其他 Agent 为默认'
             }
           >
             <Button disabled>删除</Button>
           </Tooltip>
         )}
         ```

      3. 删除默认 Agent 的正确流程：
         如果用户想删除当前的默认 Agent，需要：
         a. 先将另一个 Agent 设为默认（调用 update 接口，设置 is_default=true）
         b. 确认新默认 Agent 设置成功后
         c. 再删除原来的 Agent

         前端可提供向导式操作：
         "此 Agent 是当前默认配置。请先选择另一个 Agent 作为默认配置，
          然后才能删除。"
    ============================================================
    """
    result = await db.execute(select(AgentConfig).where(AgentConfig.id == request.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # 安全门 1：不允许删除受保护的系统 Agent
    if agent.is_protected:
        raise HTTPException(status_code=400, detail="Cannot delete a protected system agent")

    # 安全门 2：不允许删除默认 Agent
    if agent.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete the default agent")

    await db.delete(agent)
    await db.commit()
    return {"detail": "Agent deleted successfully"}
