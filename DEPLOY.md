# 服务器部署指南（Ubuntu Server 22.04）

## 前置要求

| 项目 | 要求 |
|------|------|
| 系统 | Ubuntu Server 22.04 LTS |
| 用户 | `ubuntu`（或具有 sudo 权限的用户） |
| 内存 | ≥ 2GB（推荐 4GB+） |
| 磁盘 | ≥ 10GB 可用空间 |
| 网络 | 已开放安全组端口 **80** 和 **8000** |
| API Key | Qwen API Key 已配置在 `backend/.env` 中 |

---

## 步骤 1：上传项目到服务器

在**本地电脑**执行：

```bash
# 打包项目（不含 node_modules、缓存等）
cd E:\fastload\myAiAgent
tar czf ai-agent.tar.gz --exclude='*/node_modules' --exclude='*/__pycache__' ai-agent-platform/

# 上传到服务器（替换为你的公网 IP）
scp ai-agent.tar.gz ubuntu@你的服务器IP:~/
```

## 步骤 2：SSH 登录服务器

```bash
ssh ubuntu@你的服务器IP
```

## 步骤 3：清理旧 apt 源（Ubuntu 22.04 常见坑）

Ubuntu 22.04 上可能残留过时的第三方 apt 源（如 Kubernetes），会导致 `apt-get update` 报错。先清理：

```bash
# 删除可能冲突的第三方源
sudo rm -f /etc/apt/sources.list.d/kubernetes.list 2>/dev/null
sudo rm -f /etc/apt/sources.list.d/apt.kubernetes.io.list 2>/dev/null

# 注释掉 sources.list 中的 kubernetes 行
sudo sed -i '/kubernetes/s/^/#/' /etc/apt/sources.list 2>/dev/null

# 更新 apt 索引
sudo apt-get update
```

如果 `apt-get update` 还有报错，把报错信息发给我。

## 步骤 4：安装 Docker

```bash
# 一键安装 Docker Engine + Docker Compose
curl -fsSL https://get.docker.com | sudo sh

# 启动 Docker 并设置开机自启
sudo systemctl start docker
sudo systemctl enable docker

# 把当前用户加入 docker 组（免 sudo 运行 docker 命令）
sudo usermod -aG docker $USER
newgrp docker

# 验证安装
docker --version
docker compose version
```

> 如果 `docker compose version` 正常输出，说明安装成功。如果提示权限不足，退出 SSH 重新登录再试。

## 步骤 5：解压并部署

```bash
# 解压项目
cd ~
tar xzf ai-agent.tar.gz
cd ai-agent-platform

# 确认 .env 存在且 API Key 已填入
cat backend/.env | grep DASHSCOPE_API_KEY
# 如果没有 .env，手动创建：
# cp .env.example backend/.env && nano backend/.env

# 一键部署
bash deploy.sh
```

`deploy.sh` 会自动完成：
- 构建 4 个 Docker 镜像（PostgreSQL+pgvector、Redis、后端、前端）
- 启动全部服务
- 健康检查确认就绪
- 打印公网访问地址

首次构建约 **3-5 分钟**（需下载依赖和镜像层）。

## 步骤 6：开放防火墙端口

### 6a. 云控制台安全组

在云服务器控制台（腾讯云/阿里云/华为云）→ 安全组 → 添加入站规则：

| 端口 | 协议 | 来源 | 说明 |
|------|------|------|------|
| 80   | TCP  | 0.0.0.0/0 | 前端 Web 界面 |
| 8000 | TCP  | 0.0.0.0/0 | API 后端 + Swagger 文档 |

### 6b. 服务器防火墙（ufw）

```bash
# 查看 ufw 状态
sudo ufw status

# 如果 ufw 是 active，开放端口
sudo ufw allow 80/tcp
sudo ufw allow 8000/tcp
sudo ufw allow 22/tcp     # SSH，确保不把自己锁外面
sudo ufw reload
```

## 步骤 7：访问验证

```bash
# 在服务器上测试
curl http://localhost/health
# 应返回 {"status":"ok",...}

# 获取公网 IP
curl ifconfig.me
```

浏览器访问：
- **前端界面**：http://你的服务器IP
- **API 文档**：http://你的服务器IP:8000/docs
- **健康检查**：http://你的服务器IP:8000/health

---

## Git 方式部署（适合后续更新）

```bash
# === 本地：推送到 GitHub ===
cd E:\fastload\myAiAgent\ai-agent-platform
git init && git add . && git commit -m "AI Agent Platform"
git remote add origin https://github.com/你的用户名/ai-agent-platform.git
git push -u origin main

# === 服务器：拉取并部署 ===
git clone https://github.com/你的用户名/ai-agent-platform.git ~/ai-agent-platform
cd ~/ai-agent-platform

# .env 不会被 Git 跟踪，需要手动创建
cp .env.example backend/.env
nano backend/.env    # 填入 DASHSCOPE_API_KEY 和 EMBEDDING_API_KEY

bash deploy.sh
```

后续更新代码：
```bash
cd ~/ai-agent-platform
git pull
docker compose build && docker compose up -d
```

---

## 常用运维命令

```bash
cd ~/ai-agent-platform

# 查看服务状态
docker compose ps

# 查看所有服务实时日志
docker compose logs -f

# 只看后端日志
docker compose logs -f backend

# 重启所有服务
docker compose restart

# 停止所有服务
docker compose down

# 更新代码后重新构建并启动
docker compose build && docker compose up -d

# 停止并删除数据（慎用！会清空数据库）
docker compose down -v
```

---

## 数据备份与恢复

```bash
# 备份数据库
docker exec ai-agent-platform-postgres-1 \
  pg_dump -U agent aiagent > backup_$(date +%Y%m%d).sql

# 恢复数据库
cat backup_20250710.sql | docker exec -i ai-agent-platform-postgres-1 \
  psql -U agent aiagent

# 查看备份文件大小
ls -lh backup_*.sql
```

---

## 常见问题

### Q: `apt-get update` 报错 "does not have a Release file"

Ubuntu 22.04 上残留的旧源导致的。执行步骤 3 的清理命令，删除 `/etc/apt/sources.list.d/` 下的冲突源。

### Q: `docker compose` 提示 permission denied

当前用户没有 docker 组权限。执行：
```bash
sudo usermod -aG docker $USER
newgrp docker
# 或退出 SSH 重新登录
```

### Q: 访问不了 http://服务器IP

按顺序排查：
```bash
# 1. 服务是否在运行
docker compose ps

# 2. 服务器本地能否访问
curl http://localhost
curl http://localhost:8000/health

# 3. 端口是否被监听
sudo ss -tlnp | grep -E '80|8000'

# 4. 安全组是否开放了 80 和 8000 端口
# 5. ufw 防火墙是否放行
sudo ufw status
```

### Q: 后端启动失败

```bash
docker compose logs backend

# 常见原因：
# 1. DASHSCOPE_API_KEY 无效 → 检查 backend/.env
# 2. 数据库未就绪 → 等待 30 秒后重启: docker compose restart backend
# 3. 依赖安装失败 → 重新构建: docker compose build --no-cache backend
```

### Q: 文档上传失败 (413 Request Entity Too Large)

Nginx 默认限制 50MB。如需更大，编辑 `frontend/nginx.conf` 中的 `client_max_body_size`，然后：
```bash
docker compose build frontend && docker compose up -d frontend
```

### Q: 如何切换 LLM 模型

编辑 `backend/.env`，修改后重启后端：
```bash
# Qwen 模型可选: qwen-turbo (快/便宜) / qwen-plus (均衡) / qwen-max (最强)
nano backend/.env
# 修改 QWEN_MODEL=qwen-max

docker compose restart backend
```

### Q: 如何切换 LLM 提供商

编辑 `backend/.env`：
```bash
LLM_PROVIDER=openai     # 或 claude
OPENAI_API_KEY=sk-xxx   # 填入对应 Key
```
然后 `docker compose restart backend`。

### Q: 服务器内存不足 (OOM)

2GB 内存服务器可能在构建时 OOM。解决：
```bash
# 添加 swap 虚拟内存
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Q: 如何更新到最新代码

```bash
cd ~/ai-agent-platform
# 如果用 SCP 上传的，重新上传 tar 包并解压覆盖
# 如果用 Git，直接 pull
git pull

# 重新构建并启动
docker compose build && docker compose up -d
```
