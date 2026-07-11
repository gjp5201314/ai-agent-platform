# 项目记忆

## 项目概述
AI Agent Platform — 基于 FastAPI + LangGraph + Qwen + PostgreSQL/pgvector + Redis + React 的 AI Agent SaaS 平台。支持流式对话、RAG 知识库、工具调用、多 LLM 切换。

## 关键约定
- 后端入口: backend/app/main.py
- 前端入口: frontend/src/App.tsx
- LLM 默认使用 Qwen (DashScope)，同时支持 OpenAI 和 Claude
- 部署方式: Docker Compose (4 个 service: frontend/backend/postgres/redis)
- CI/CD: GitHub Actions → tar + SCP → 服务器（绕过 GitHub 被墙问题）
- 无用户认证系统，仅 IP 级速率限制
- 前端无路由库，单页应用通过模态框切换视图

## 产出物
- 面试项目解析.md: 全面的项目技术分析文档，涵盖技术选型、架构设计、难点解决
