# AI Agent 平台 - 简历项目内容

> 模板格式：项目概述 / 人员分工 / 我的分工 / 项目业绩

---

## 项目描述

**项目概述：**
AI Agent 平台是一个支持多 AI 大模型、集成知识库问答与工具调用的全栈智能对话系统。用户可以与 AI 对话，上传文档让 AI 基于资料回答，AI 还能自动调用工具（查天气、计算器、搜索网页等）。前端 React 18 + TypeScript + Vite 6 + Tailwind CSS，后端 FastAPI + LangGraph，PostgreSQL 做数据库和向量存储，Docker 容器化部署在阿里云。

**人员分工：**
独立开发，全栈一人完成。

**前端负责模块：**
- 聊天主界面：消息列表（用户气泡 + AI 卡片），AI 回复通过 SSE 流式逐字渲染（fetch + ReadableStream 解析），Markdown 格式渲染，滚动到底部
- 自定义 useChat Hook 管理聊天状态（消息数组、流式标志、对话 ID、知识库来源、工具调用状态），通过 AsyncGenerator 消费后端 SSE 事件
- 消息输入框：Textarea 自动增高、Enter 发送 / Shift+Enter 换行，支持剪贴板粘贴图片、点击上传文件附件，内置模型选择器切换 AI 模型
- 知识库模块：拖拽/点击上传文档（PDF/Word/TXT），展示文档列表（文件名、大小、处理状态），支持搜索和删除
- Agent 配置面板：可创建/编辑多个 Agent，配置温度参数、Token 上限、开启/关闭工具（开关网格布局）、开启委托、调整知识库检索阈值
- 管理后台仪表盘：统计卡片（总对话数、消息数、文档数、今日用量），LLM 模型配置，管理员素材库
- 侧边栏导航：对话列表（支持搜索/删除）、Agent 切换下拉（带默认标记）、新对话按钮
- 上下文窗口可视化：实时估算 Token 用量并用进度条显示（绿 < 65% / 黄 65~85% / 红 > 85%）
- 状态管理：React 内置 useState/useCallback，无第三方状态库；对话 ID 与 URL hash 同步实现刷新恢复
- UI 组件库：基于 shadcn/ui（Radix 无障碍基础）封装按钮、对话框、下拉菜单、滑块、开关、文本域等组件

**后端负责模块：**
- 基于 FastAPI 搭建 RESTful API，统一 POST + JSON body 设计（避免参数暴露 URL），添加请求 ID 追踪、CORS、安全响应头、请求体大小限制（10MB）等中间件
- LangGraph 编排 Agent 执行流程：用户提问 → 检索知识库 → AI 推理 → 判断是否需要工具 → 执行工具 → AI 组织最终回答；限制最多 10 轮循环防止死循环
- RAG 知识库管道：文档解析（PDF/Word/TXT/Markdown）→ 文本分块（500 字/块）→ 向量嵌入（DashScope 1024 维）→ 存储到 PostgreSQL pgvector
- 混合检索：语义搜索（pgvector cosine_distance）+ 关键词搜索（PostgreSQL 全文搜索 tsvector），通过 RRF 算法融合排序
- Redis 滑动窗口限流：读 60 次/分钟、写 10 次/分钟
- 支持通义千问 / OpenAI / Claude 三个大模型，统一用 ChatOpenAI 兼容接口切换

**部署：**
- 本地开发：Docker Compose 编排 4 个容器（Nginx + FastAPI + PostgreSQL + Redis），Vite 热更新代理到后端
- 前端 Dockerfile 多阶段构建：node:alpine 编译 → nginx:alpine 运行，产物仅几 MB
- 生产环境：GitHub Actions 自动构建镜像 → 推送到阿里云 ACR → SSH 到服务器 Docker Swarm 滚动更新
- Nginx 配置：关掉代理缓冲（proxy_buffering off）支持 SSE 长连接，gzip 压缩、静态资源缓存

---

## 项目业绩

1. 独立完成从零搭建到上线运行的全栈项目，前端 15+ 组件、后端 30+ API 端点，使用 6 个 Docker 文件编排部署。
2. 实现 SSE 流式聊天（非 WebSocket），通过 fetch + ReadableStream 逐 token 渲染，降低前端实现复杂度。
3. 搭建 RAG 知识库检索系统，支持文档上传 → 自动分块 → 向量存储 → 混合检索（语义+关键词融合排序），用户可上传 PDF/Word 让 AI 基于资料回答。
4. 通过 LangGraph 状态图编排实现 Agent 自动工具调用（计算器、天气查询、网络搜索等），LLM 自主决策何时调用工具，无需前端硬编码逻辑。
5. 设计上下文窗口自动压缩：Token 超过 70% 用 LLM 总结历史对话为摘要，保留最近 6 条完整消息，前端实时显示用量进度条。
6. 使用 Docker Swarm 部署到阿里云 2GB 内存服务器，优化后端 workers 数（4→1）和副本数（2→1），解决 OOM 问题，支持健康检查 + 失败自动回滚。
