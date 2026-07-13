# AI Agent 平台 — 面试项目解释指南

> 写给前端同学看的版本。用最短的篇幅让你能跟面试官讲清楚这个项目。

---

## 一、一句话描述

一个**支持多个 AI 模型、可以上传文档做知识库问答、Agent 能调用真实工具（查天气、搜新闻、算数学）**的全栈聊天平台。

类比：ChatGPT + 知识库 + 插件商店，但一切你自己搭建。

---

## 二、整体架构（一张图看懂）

```
┌──────────────────────────────────────────────────────────┐
│                    用户浏览器                             │
│    React 前端 (localhost:80  线上)                        │
│    Vite 开发 (localhost:5173 本地)                        │
└──────────────┬───────────────────────────────────────────┘
               │  HTTP / SSE 流式
               ▼
┌──────────────────────────────────────────────────────────┐
│                   Nginx (80端口)                          │
│  把 /api/* 转发到后端   │   关掉缓冲 → 支持 SSE 流式       │
└──────────────┬───────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│              FastAPI 后端 (8000端口)                       │
│                        │                                  │
│     ┌──────────────────┼──────────────────┐              │
│     ▼                  ▼                  ▼              │
│  LangGraph         pgvector           Redis 缓存          │
│  (AI 调度引擎)     (知识库向量检索)    (限流/缓存)         │
│     │                                                     │
│     ▼                                                     │
│  通义千问 / OpenAI / Claude  (可切换)                     │
└──────────────────────────────────────────────────────────┘
```

**一句话总结**：前端发消息 → Nginx 转发 → 后端查知识库 → 调 AI 大模型 → 流式吐字 → 前端逐字显示。

---

## 三、前端技术栈（面试高频考点）

### 你用到的技术

| 技术 | 干什么的 |
|------|---------|
| **React 18** | 核心框架 |
| **TypeScript** | 类型安全 |
| **Vite 6** | 构建工具（比 Webpack 快） |
| **Tailwind CSS 3** | 原子化 CSS 写法 |
| **shadcn/ui** | 基于 Radix 的无障碍组件库 |
| **react-markdown** | AI 回复的 Markdown 渲染 |

### 前端组件树

```
App.tsx                         ← 全局状态：当前对话、模型选择
├── Sidebar.tsx                 ← 对话列表、Agent 切换、快捷入口
├── ChatInterface.tsx           ← 聊天主容器
│   ├── MessageList.tsx         ← 消息渲染（Markdown + 流式追加）
│   └── MessageInput.tsx        ← 输入框 + 图片粘贴 + RAG开关
├── DocumentUpload.tsx          ← 知识库文档上传
├── Settings.tsx                ← Agent 配置（提示词/温度/工具开关）
└── AdminPage.tsx               ← 管理后台（仪表盘/模型配置）
```

### 前端最值得讲的技术点

#### 1. SSE 流式输出（重点）

```typescript
// 不是 WebSocket，而是 fetch + ReadableStream | 更轻量、HTTP 原生
const response = await fetch('/api/v1/chat', {
  method: 'POST',
  body: JSON.stringify({ message: '你好', stream: true }),
})
const reader = response.body!.getReader()
const decoder = new TextDecoder()

while (true) {
  const { done, value } = await reader.read()
  if (done) break
  // 解析 SSE 格式: "data: {...}\n\n"
  const text = decoder.decode(value)
  // 逐 token 追加到 React 消息数组
}
```

**面试说**：用 SSE（Server-Sent Events）而不是 WebSocket，因为 AI 对话是单向推送（服务端→客户端），SSE 更简单，不需要心跳保活。

#### 2. Hook 驱动的聊天状态

```typescript
// useChat.ts | 核心 hook
function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  
  async function sendMessage(text: string) {
    // 1. 先插入用户消息 + 空的 AI 占位
    setMessages(prev => [...prev, userMsg, emptyAIMsg])
    // 2. 调 API 获取 SSE 流
    for await (const event of api.streamChat(text)) {
      if (event.type === 'token') {
        // 逐字追加到占位消息
        setMessages(prev => /* 更新最后一条消息内容 */)
      }
    }
  }
}
```

**面试说**：把聊天状态封装成自定义 Hook，支持流式追字、工具调用状态、Agent 切换，UI 层只管渲染。

#### 3. 上下文窗口可视化

```
[████████░░] 68%   | 当前用了 2800 / 4096 tokens
```

**面试说**：前端通过字符数估算 token 用量，接近上限时进度条变红，提醒用户对话可能溢出。注意：前端只是估算（中文字符 ≈ 2 tokens，英文 ≈ 1.3），精确值服务端计算。

---

## 四、后端核心概念（前端能理解的版本）

### LangGraph 是什么？

把它理解为 **一个流程图引擎**。它定义 AI 的思考路径：

```
用户提问 → [查知识库] → AI 思考 → 需要查资料？→ [调用工具] → AI 再思考 → 回复
              ↑__________________________↓
                     循环（最多10轮）
```

**类比**：就像 React 的组件渲染循环——state 变化 → 重新 render → 可能触发新的 state 变化 → 再 render，直到稳定。LangGraph 就是这个循环，但跑的是 AI。

### RAG 是什么？

**R**etrieval-**A**ugmented **G**eneration = 检索增强生成。

简单说：用户上传一个 PDF，系统把它切成小段 → 每段转成数学向量 → 存到数据库。当用户问问题时，系统找到最相关的段落 → 塞给 AI 作为参考 → AI 基于这些资料回答。

**类比**：就像你考试前翻了课本 → 记住重点 → 答题时引用。RAG 就是 AI 的"课本"。

### 工具调用是什么？

AI 不是只会说话，它还能"做事"：

| 工具 | 比如 |
|------|------|
| `calculator` | "123 * 456 等于多少" |
| `get_weather` | "北京今天什么天气" |
| `web_search` | "搜索最新 Vue 3.5 更新" |
| `get_news` | "今天有什么热搜" |

**过程**：AI 说"我需要查天气" → 后端执行 `get_weather('北京')` → 拿到结果"26°C 晴" → AI 把结果组织成自然语言回复。

---

## 五、一次对话的完整流程

### 用"北京今天什么天气？"为例

```
1.  用户输入文字，点发送
2.  React 调用 fetch POST /api/v1/chat, stream: true
3.  Nginx 转发到 FastAPI 后端（关掉缓冲，保持长连接）
4.  后端查数据库，加载对话历史
5.  LangGraph 启动 AI 引擎：
    - 当前没有知识库需要查 → 跳过 RAG
    - AI 分析问题：这是天气查询，需要调用 get_weather 工具
    - 后端执行 get_weather("北京") → 26°C 晴
    - 结果返回给 AI
    - AI 组织语言："北京今天26°C，天气晴朗，适合户外活动"
6.  回复通过 SSE 流式推给前端：
    data: {"type":"token","content":"北"}
    data: {"type":"token","content":"京"}
    data: {"type":"token","content":"今"}
    ...
    data: {"type":"done"}
7.  前端逐字渲染，用户看到打字机效果
8.  对话保存到数据库
```

---

## 六、部署方式

```
GitHub 推送代码
  → GitHub Actions 自动构建 Docker 镜像
  → 推送到阿里云容器仓库 (ACR)
  → SSH 登录服务器
  → Docker Swarm 滚动更新（逐个替换容器，不停机）
```

**4 个 Docker 容器**：
- Nginx（前端静态文件 + 反向代理）
- FastAPI（后端 API）
- PostgreSQL（数据库 + 知识库向量存储）
- Redis（缓存 + 请求限流）

---

## 七、面试常见问题 & 回答模板

### Q1: 项目最大的技术挑战是什么？

> **答**：流式输出。AI 回复一个字一个字地返回，前端要实时渲染，还要处理 Markdown 格式。我们用 SSE 而不是 WebSocket，因为 SSE 更轻量；前端用 ReadableStream 解析，用了 React 函数式更新避免闭包问题。另外后端 LangGraph 的 tool-calling 循环要限制迭代次数防止死循环，我们设了 10 轮上限。

### Q2: 为什么选 LangGraph 而不是直接用 API？

> **答**：直接用 API 只能一问一答。LangGraph 让我们能编排复杂流程：先查知识库 → 再让 AI 决定要不要调工具 → 调完工具再让 AI 组织回答。这是一个有状态的图执行引擎，支持循环和条件分支。

### Q3: 知识库怎么实现的？

> **答**：混合检索。上传的文档先切成 500 字的小段，用阿里云的 embedding 模型把每段转成 1024 维向量存到 PostgreSQL。查询时同时做两种搜索：语义相似度（用向量余弦距离）+ 关键词匹配（用 PostgreSQL 全文搜索），然后用 RRF 算法融合排序取最优结果。

### Q4: 怎么支持多个大模型？

> **答**：统一用 OpenAI 的接口格式。通义千问、OpenAI、Claude 都兼容 ChatOpenAI 的调用方式，只是换一下 API key 和 base_url。前端有个模型选择器，用户点切换就行，后端按选择的提供商创建对应的 LLM 实例。

### Q5: 上下文窗口满了怎么办？

> **答**：自动压缩。当估算的 token 用量超过最大窗口的 70%，后端会用 LLM 把较早的对话总结成一段 200 字的摘要，只保留最近 6 条完整消息。前端有个进度条实时显示用量。

### Q6: 前端有哪些性能优化？

> **答**：
> - 流式渲染用 `requestAnimationFrame` 控制更新频率，避免每来一个 token 就重渲染一次
> - react-markdown 按需加载插件（只加载 gfm）
> - Vite 构建 + code splitting
> - Nginx 层 gzip 压缩 + 静态文件缓存

---

## 八、关键技术词汇中英文对照

| 中文 | 英文 | 一句话解释 |
|------|------|----------|
| 流式输出 | Streaming / SSE | 一个字一个字返回，不回等全部生成完 |
| 知识库 | RAG | 给 AI 读文档，它按文档内容回答 |
| 工具调用 | Tool Calling / Function Calling | AI 能"用"计算器、查天气、搜网页 |
| 向量 | Embedding / Vector | 把文字转成一串数字，数学上近似的=语义上近似的 |
| Agent 引擎 | LangGraph | 编排 AI 思考流程的框架 |
| 混合检索 | Hybrid Search | 语义搜索 + 关键词搜索，取各自最好的结果融合 |
| 滚动更新 | Rolling Update | 一台台换容器，服务不中断 |
| 上下文窗口 | Context Window | AI 一次能"记住"多少对话 |
| 提示词 | System Prompt | 给 AI 的角色设定，比如"你是一个前端专家" |

---

## 九、项目中的文件对应关系（快速查代码）

| 你想看… | 打开这个文件 |
|---------|-------------|
| 全局状态 + 路由 | `frontend/src/App.tsx` |
| 聊天消息渲染 | `frontend/src/components/MessageList.tsx` |
| 输入框 + 发送逻辑 | `frontend/src/components/MessageInput.tsx` |
| SSE 流式消费 | `frontend/src/hooks/useChat.ts` |
| API 调用封装 | `frontend/src/api/client.ts` |
| TypeScript 类型 | `frontend/src/types/index.ts` |
| 后端聊天入口 | `backend/app/api/chat.py` |
| Agent 编排逻辑 | `backend/app/agent/graph.py` |
| 知识库检索 | `backend/app/rag/retriever.py` |
| 工具定义 | `backend/app/agent/tools.py` |
| 数据库模型 | `backend/app/models.py` |
