# AI Agent Platform

基于 **FastAPI + LangGraph + Qwen + PostgreSQL/pgvector + Redis** 构建的生产级 AI Agent 网站，支持流式对话、知识库问答 (RAG)、工具调用和 LangSmith 可观测性。

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| **流式对话** | SSE (Server-Sent Events) 实时流式输出，逐 token 显示 |
| **知识库问答 (RAG)** | 上传 PDF/DOCX/TXT/MD，自动分块、向量化、语义检索 |
| **工具调用** | 内置计算器、网络搜索、时间查询；支持 LangGraph 多步推理 |
| **多轮对话管理** | 会话历史持久化，侧边栏管理，自动生成标题 |
| **Agent 配置** | 可视化配置系统提示词、温度、工具开关、RAG 参数 |
| **多 LLM 支持** | Qwen (默认) / OpenAI / Claude，通过环境变量切换 |
| **LangSmith 追踪** | 可选开启，查看完整的 Agent 执行链路 |
| **Docker 一键部署** | `docker compose up -d` 启动全部服务 |

## 🏗️ 架构概览

```
┌─────────────────────────────────────────────────────┐
│                    用户浏览器                         │
│              React + Vite + Tailwind                 │
└────────────────────┬────────────────────────────────┘
                     │ HTTP / SSE
┌────────────────────▼────────────────────────────────┐
│              Nginx (端口 80)                         │
│         静态文件 + API 反向代理                       │
└────────┬───────────────────────────┬────────────────┘
         │ 静态文件                  │ /api/*
┌────────▼────────┐     ┌───────────▼──────────────────┐
│   React 静态文件  │     │   FastAPI Backend (端口 8000) │
│   dist/          │     │                              │
└─────────────────┘     │  ┌────────────────────────┐  │
                        │  │   LangGraph Agent      │  │
                        │  │   chat → RAG → tools   │  │
                        │  └──────────┬─────────────┘  │
                        └────────────┼────────────────┘
                    ┌────────────────┼────────────────┐
              ┌─────▼─────┐    ┌──────▼──────┐   ┌─────▼──────┐
              │ PostgreSQL │    │   Redis    │   │ LangSmith  │
              │ + pgvector │    │ 会话/限流   │   │  追踪(可选) │
              └────────────┘    └───────────┘   └────────────┘
```

## 📁 项目结构

```
ai-agent-platform/
├── backend/                    # Python 后端
│   ├── app/
│   │   ├── main.py             # FastAPI 入口 + 生命周期
│   │   ├── config.py           # Pydantic Settings 配置
│   │   ├── database.py         # SQLAlchemy async + pgvector
│   │   ├── models.py           # ORM 模型
│   │   ├── schemas.py          # Pydantic 请求/响应模型
│   │   ├── deps.py             # FastAPI 依赖注入
│   │   ├── api/                # API 路由
│   │   │   ├── chat.py         # SSE 流式对话端点
│   │   │   ├── rag.py          # 文档上传 + 向量检索
│   │   │   ├── conversations.py# 会话 CRUD
│   │   │   ├── agents.py       # Agent 配置 CRUD
│   │   │   └── health.py       # 健康检查
│   │   ├── agent/              # LangGraph Agent
│   │   │   ├── state.py        # Agent 状态定义
│   │   │   ├── llm.py          # LLM 工厂 (Qwen/OpenAI/Claude)
│   │   │   ├── tools.py        # 内置工具 (计算器/搜索/时间)
│   │   │   ├── nodes.py        # 图节点
│   │   │   └── graph.py        # LangGraph 编排
│   │   ├── rag/                # RAG 检索
│   │   │   ├── embeddings.py   # 向量嵌入
│   │   │   ├── chunker.py      # 文档分块 + 文本提取
│   │   │   └── retriever.py    # pgvector 语义搜索
│   │   └── core/
│   │       └── redis_client.py # Redis 客户端
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── App.tsx             # 主应用
│   │   ├── api/client.ts       # API 客户端 + SSE 解析
│   │   ├── hooks/useChat.ts    # 对话状态管理
│   │   ├── components/
│   │   │   ├── ChatInterface.tsx
│   │   │   ├── MessageList.tsx  # 消息列表 + Markdown 渲染
│   │   │   ├── MessageInput.tsx # 输入框 + RAG 开关
│   │   │   ├── Sidebar.tsx     # 会话侧边栏
│   │   │   ├── DocumentUpload.tsx # 知识库管理
│   │   │   └── Settings.tsx    # Agent 配置
│   │   └── types/index.ts
│   ├── Dockerfile              # 多阶段构建
│   ├── nginx.conf              # Nginx 配置
│   └── package.json
├── docker-compose.yml          # 一键部署
├── Makefile                    # 常用命令
├── .env.example
└── README.md
```

## 🚀 快速开始

### 前置条件

- Docker 24+ 和 Docker Compose v2
- Qwen API Key（免费申请）：[https://dashscope.console.aliyun.com/](https://dashscope.console.aliyun.com/)

### 步骤 1：配置环境变量

```bash
cd ai-agent-platform
cp .env.example backend/.env
```

编辑 `backend/.env`，填入你的 API Key：

```bash
# Qwen API Key (必填)
DASHSCOPE_API_KEY=sk-your-actual-api-key
EMBEDDING_API_KEY=sk-your-actual-api-key

# 数据库密码 (建议修改)
POSTGRES_PASSWORD=your_strong_password
DATABASE_URL=postgresql+asyncpg://agent:your_strong_password@postgres:5432/aiagent

# LangSmith 追踪 (可选)
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_your_langsmith_key
```

### 步骤 2：启动服务

```bash
docker compose up -d
```

首次启动会自动构建镜像并初始化数据库。等待 30-60 秒后检查状态：

```bash
docker compose ps
```

所有服务应为 `running` / `healthy` 状态。

### 步骤 3：访问应用

- **前端界面**：http://localhost
- **API 文档**：http://localhost:8000/docs (Swagger UI)
- **健康检查**：http://localhost:8000/health

## 📖 使用指南

### 基础对话

1. 打开 http://localhost，点击 "新对话"
2. 在输入框输入消息，按 Enter 发送
3. AI 回复会逐字流式显示

### 知识库问答 (RAG)

1. 点击侧边栏 "知识库管理"
2. 上传 PDF / DOCX / TXT / MD 文件（系统自动分块 + 向量化）
3. 等待状态变为 "就绪" ✓
4. 在对话中确保 📚 RAG 按钮为绿色（已开启）
5. 提问时 AI 会优先检索知识库内容回答

### Agent 配置

1. 点击侧边栏 "Agent 设置"
2. 可创建多个 Agent，各有不同系统提示词和工具
3. 可调节：温度、最大 token、RAG 检索数量、相似度阈值
4. 可启用/禁用工具：RAG、计算器、网络搜索、时间查询

### 切换 LLM

编辑 `backend/.env`，修改 `LLM_PROVIDER`：

```bash
LLM_PROVIDER=qwen      # 通义千问 (国内推荐)
LLM_PROVIDER=openai    # OpenAI GPT
LLM_PROVIDER=claude    # Claude (Anthropic)
```

修改后重启：`docker compose restart backend`

## 🔧 开发模式

### 后端开发 (热重载)

```bash
cd backend
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 前端开发 (热重载)

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173 (自动代理 /api 到 8000)
```

> 开发时仍需 PostgreSQL 和 Redis 运行。可单独启动：
> `docker compose up -d postgres redis`

## 🚢 服务器部署

### 部署到远程服务器

```bash
# 1. 将项目传到服务器
scp -r ai-agent-platform/ user@your-server:/opt/

# 或用 Git:
# git clone <your-repo> /opt/ai-agent-platform

# 2. 在服务器上配置
cd /opt/ai-agent-platform
cp .env.example backend/.env
nano backend/.env    # 填入 API Key 和密码

# 3. 启动
docker compose up -d

# 4. 检查
curl http://localhost:8000/health
```

### 配置 HTTPS (推荐)

使用 Caddy 或 Nginx + Certbot：

```bash
# 示例：修改 docker-compose.yml 添加 Caddy
# 或在前面再加一层 Nginx 反代
```

### Kubernetes 部署

K8s 清单模板见 `k8s/` 目录（按需生成）。核心资源：

- `Deployment` (backend, frontend)
- `StatefulSet` (postgres, redis) + PersistentVolume
- `Service` + `Ingress`
- `Secret` (API Keys)

## 🛠️ 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| 前端 | React 18 + Vite 6 + TypeScript | SPA 用户界面 |
| 样式 | Tailwind CSS 3 | 原子化 CSS |
| 后端 | FastAPI + Uvicorn | 异步 API 服务 |
| Agent | LangGraph | 多步推理状态图 |
| LLM | Qwen / OpenAI / Claude | 对话与推理 |
| 向量库 | PostgreSQL 16 + pgvector | 向量存储与检索 |
| 缓存 | Redis 7 | 会话状态、限流 |
| 追踪 | LangSmith | Agent 执行可视化 |
| 部署 | Docker + Docker Compose | 容器化部署 |

## ❓ 常见问题

**Q: 如何获取 Qwen API Key？**
A: 访问 [阿里云百炼](https://dashscope.console.aliyun.com/)，开通 DashScope 服务，创建 API Key。新用户有免费额度。

**Q: 支持哪些文档格式？**
A: PDF、DOCX、TXT、Markdown。如需更多格式，可在 `app/rag/chunker.py` 中扩展。

**Q: 数据存储在哪里？**
A: PostgreSQL 数据存储在 Docker volume `postgres_data` 中。删除容器不会丢失数据，除非执行 `docker compose down -v`。

**Q: 如何备份数据库？**
A: `docker exec ai-agent-platform-postgres-1 pg_dump -U agent aiagent > backup.sql`

**Q: LangSmith 是必须的吗？**
A: 不是。`LANGSMITH_TRACING=false` 即可关闭。开启后可在 [LangSmith](https://smith.langchain.com) 查看 Agent 的完整执行链路。

**Q: 如何添加自定义工具？**
A: 在 `backend/app/agent/tools.py` 中用 `@tool` 装饰器定义新工具，然后在 Agent 设置中启用。

## 📄 License

MIT
