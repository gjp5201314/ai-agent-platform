# 服务器部署指南

## 前置要求

- Linux 云服务器（Ubuntu / CentOS / Debian 均可）
- 服务器已开放安全组端口：**80**、**8000**
- 你的 Qwen API Key（已配置在 `backend/.env` 中）

---

## 方式一：SCP 直传 + 一键脚本（最快）

### 步骤 1：本地打包项目

```bash
# 在本地执行
cd E:\fastload\myAiAgent
tar czf ai-agent.tar.gz ai-agent-platform/
```

### 步骤 2：上传到服务器

```bash
# 把 your-server-ip 换成你的服务器公网 IP
scp ai-agent.tar.gz root@your-server-ip:/opt/
```

### 步骤 3：服务器上解压并部署

```bash
# SSH 登录服务器
ssh root@your-server-ip

# 解压
cd /opt
tar xzf ai-agent.tar.gz
cd ai-agent-platform

# 一键部署（自动安装 Docker + 构建镜像 + 启动）
bash deploy.sh
```

脚本会自动完成：安装 Docker → 构建 4 个镜像 → 启动服务 → 健康检查。

### 步骤 4：开放安全组端口

在云服务器控制台 → 安全组/防火墙规则，添加：

| 端口 | 协议 | 说明 |
|------|------|------|
| 80   | TCP  | 前端 Web 界面 |
| 8000 | TCP  | FastAPI 后端 + API 文档 |

### 步骤 5：访问

- **前端界面**：http://你的服务器IP
- **API 文档**：http://你的服务器IP:8000/docs
- **健康检查**：http://你的服务器IP:8000/health

---

## 方式二：Git 部署（适合后续更新）

```bash
# 1. 本地推送到 Git
cd E:\fastload\myAiAgent\ai-agent-platform
git init
git add .
git commit -m "AI Agent Platform"
git remote add origin https://github.com/你的用户名/ai-agent-platform.git
git push -u origin main

# 2. 服务器上拉取并部署
ssh root@your-server-ip
git clone https://github.com/你的用户名/ai-agent-platform.git /opt/ai-agent-platform
cd /opt/ai-agent-platform

# 3. 创建 .env（.env 不会被 Git 跟踪）
cp .env.example backend/.env
nano backend/.env    # 填入 API Key

# 4. 部署
bash deploy.sh
```

后续更新代码只需：
```bash
git pull && docker compose build && docker compose up -d
```

---

## 常用运维命令

```bash
# 查看服务状态
docker compose ps

# 查看实时日志
docker compose logs -f

# 只看后端日志
docker compose logs -f backend

# 重启所有服务
docker compose restart

# 停止所有服务
docker compose down

# 停止并删除数据（慎用！会清空数据库）
docker compose down -v

# 更新代码后重建
docker compose build && docker compose up -d
```

---

## 数据备份

```bash
# 备份数据库
docker exec ai-agent-platform-postgres-1 \
  pg_dump -U agent aiagent > backup_$(date +%Y%m%d).sql

# 恢复数据库
cat backup_20250710.sql | docker exec -i ai-agent-platform-postgres-1 \
  psql -U agent aiagent
```

---

## 常见问题

### Q: 访问不了 http://服务器IP ？

1. 检查服务是否在运行：`docker compose ps`
2. 检查端口是否开放：`curl http://localhost` （在服务器上执行）
3. 检查安全组规则是否开放了 80 端口

### Q: 后端启动失败？

```bash
# 查看后端日志
docker compose logs backend

# 常见原因：
# 1. API Key 无效 → 检查 backend/.env 中的 DASHSCOPE_API_KEY
# 2. 数据库连接失败 → 检查 DATABASE_URL 中的密码
```

### Q: 文档上传失败？

Nginx 默认限制 50MB。如需更大，编辑 `frontend/nginx.conf` 中的 `client_max_body_size`，然后：
```bash
docker compose build frontend && docker compose up -d frontend
```

### Q: 如何修改 LLM 模型？

编辑 `backend/.env`：
```bash
QWEN_MODEL=qwen-plus      # 或 qwen-turbo / qwen-max
```
然后重启：`docker compose restart backend`
