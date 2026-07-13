# 生产环境部署指南（ACR + Docker Swarm 滚动更新）

## 概念

- **ACR**（阿里云容器镜像服务）= 存 Docker 镜像的地方，替代 Docker Hub，国内访问快
- **Docker Swarm** = Docker 内置集群管理，一句话 `docker swarm init` 就能开启
- **滚动更新** = 逐个替换容器实例，用户完全不感知，零停机

整个部署就是：**代码构建成镜像 → 存到 ACR → 服务器拉下来运行**

```
本地 git push → GitHub Actions 自动构建镜像 → 推送 ACR → SSH 服务器拉取 → Swarm 滚动更新
```

---

## 前置准备（一次性，已完成）

### 1. 阿里云 ACR

- 地址：https://cr.console.aliyun.com/
- 开通**个人版实例**（免费，无需企业认证）
- 创建命名空间：`ai_agent_platform`
- 创建两个镜像仓库：`backend`、`frontend`（类型选私有）
- 访问凭证 → 设置固定密码

你的配置：

| 项 | 值 |
|----|-----|
| 注册地址 | `crpi-tku91p701ehponrr.cn-hangzhou.personal.cr.aliyuncs.com` |
| 命名空间 | `ai_agent_platform` |
| 用户名 | `aliyun9908219536` |

### 2. GitHub Secrets

仓库 Settings → Secrets and variables → Actions，添加：

| Secret 名 | 值 |
|-----------|-----|
| `ACR_REGISTRY` | `crpi-tku91p701ehponrr.cn-hangzhou.personal.cr.aliyuncs.com/ai_agent_platform` |
| `ACR_USERNAME` | `aliyun9908219536` |
| `ACR_PASSWORD` | ACR 固定密码 |
| `SERVER_HOST` | `118.25.123.105` |
| `SERVER_USER` | `ubuntu` |
| `SERVER_PASSWORD` | SSH 密码 |
| `SERVER_PORT` | `22` |

### 3. 服务器 backend/.env

文件 `~/ai-agent-platform/backend/.env` 末尾添加 ACR 配置：

```bash
ACR_REGISTRY=crpi-tku91p701ehponrr.cn-hangzhou.personal.cr.aliyuncs.com/ai_agent_platform
ACR_USERNAME=aliyun9908219536
ACR_PASSWORD=你的ACR密码
```

同时在项目根目录创建软链接（Docker Compose 从这里读变量）：

```bash
cd ~/ai-agent-platform
ln -sf backend/.env .env
```

---

## 首次部署流程（本次操作）

### 步骤 1：上传文件到服务器

```powershell
# 本地 PowerShell 执行
scp E:\fastload\myAiAgent\ai-agent-platform\docker-compose.prod.yml ubuntu@118.25.123.105:~/ai-agent-platform/
scp E:\fastload\myAiAgent\ai-agent-platform\backend\.env ubuntu@118.25.123.105:~/ai-agent-platform/backend/
```

### 步骤 2：SSH 登录，创建 .env 软链接

```bash
ssh ubuntu@118.25.123.105
cd ~/ai-agent-platform
ln -sf backend/.env .env
```

### 步骤 3：本地构建镜像并推送到 ACR

> 核心原则：**服务器只拉取，不构建**。构建在你本地电脑完成（配置好，速度快）。

```powershell
# 本地 PowerShell 执行
cd E:\fastload\myAiAgent\ai-agent-platform

# 登录 ACR
docker login --username=aliyun9908219536 crpi-tku91p701ehponrr.cn-hangzhou.personal.cr.aliyuncs.com

# 构建后端镜像
docker compose -f docker-compose.yml build backend --no-cache

# 推送后端
docker tag ai-agent-platform-backend crpi-tku91p701ehponrr.cn-hangzhou.personal.cr.aliyuncs.com/ai_agent_platform/backend:latest
docker push crpi-tku91p701ehponrr.cn-hangzhou.personal.cr.aliyuncs.com/ai_agent_platform/backend:latest

# 构建前端镜像
docker compose -f docker-compose.yml build frontend --no-cache

# 推送前端
docker tag ai-agent-platform-frontend crpi-tku91p701ehponrr.cn-hangzhou.personal.cr.aliyuncs.com/ai_agent_platform/frontend:latest
docker push crpi-tku91p701ehponrr.cn-hangzhou.personal.cr.aliyuncs.com/ai_agent_platform/frontend:latest
```

### 步骤 4：服务器拉取镜像并部署

```bash
# SSH 登录服务器
ssh ubuntu@118.25.123.105
cd ~/ai-agent-platform

# 登录 ACR 并拉取镜像
docker login --username=aliyun9908219536 crpi-tku91p701ehponrr.cn-hangzhou.personal.cr.aliyuncs.com
docker pull crpi-tku91p701ehponrr.cn-hangzhou.personal.cr.aliyuncs.com/ai_agent_platform/backend:latest
docker pull crpi-tku91p701ehponrr.cn-hangzhou.personal.cr.aliyuncs.com/ai_agent_platform/frontend:latest

# 初始化 Swarm（只需一次）
docker swarm init

# 加载环境变量并部署
set -a; source .env; set +a
docker stack deploy -c docker-compose.prod.yml ai-agent

# 强制启动（确保镜像被使用）
docker service update --force ai-agent_backend
docker service update --force ai-agent_frontend
```

> 注意：不要用 `docker compose config | docker stack deploy` 的方式，会导致端口格式被转义成字符串。直接用 `docker stack deploy -c` 配合 shell 变量。

### 步骤 5：强制拉取镜像并启动

首次部署时镜像标记为 `latest`，Swarm 可能不会自动拉取。强制更新：

```bash
docker service update --force --image crpi-tku91p701ehponrr.cn-hangzhou.personal.cr.aliyuncs.com/ai_agent_platform/backend:latest ai-agent_backend
docker service update --force --image crpi-tku91p701ehponrr.cn-hangzhou.personal.cr.aliyuncs.com/ai_agent_platform/frontend:latest ai-agent_frontend
```

### 步骤 6：验证

```bash
# 查看服务状态（都应该是 1/1 或 2/2）
docker service ls

# 后端健康检查
curl -s -X POST http://localhost:8000/api/v1/health

# 前端验证
curl -s -o /dev/null -w "%{http_code}" http://localhost:80/
```

浏览器访问：`http://118.25.123.105`

---

## 日常更新流程（以后只需 git push）

配好 GitHub Secrets 后，只需要：

```bash
git add .
git commit -m "更新说明"
git push origin main
```

GitHub Actions 自动完成：
1. 检出代码
2. 构建后端镜像 → 推送到 ACR
3. 构建前端镜像 → 推送到 ACR
4. SSH 到服务器，拉取新镜像并滚动更新
5. 健康检查验证

全程自动化，零停机。

---

## 常用运维命令

```bash
# 查看所有服务
docker service ls

# 查看服务详情（滚动更新进度）
docker service ps ai-agent_backend

# 查看日志
docker service logs -f ai-agent_backend

# 手动滚动更新到指定版本
docker service update --image crpi-tku91p701ehponrr.cn-hangzhou.personal.cr.aliyuncs.com/ai_agent_platform/backend:v1.2.3 ai-agent_backend

# 强制重建所有容器
docker service update --force ai-agent_backend

# 回滚到上一版本
docker service rollback ai-agent_backend

# 扩容/缩容
docker service scale ai-agent_backend=3

# 停止整个 Stack
docker stack rm ai-agent

# 清理旧镜像
docker image prune -f
```

---

## 踩坑记录

### 1. `docker compose config` 管道部署失败

**现象**：`services.backend.ports.0.published must be a integer`

**原因**：`docker compose config` 输出时把端口号转成了字符串 `"8000"`，Docker Swarm 要求整数。

**解决**：不要管道。用 `set -a; source .env; set +a` 导出变量，然后直接 `docker stack deploy -c compose.prod.yml`。

### 2. `The "ACR_REGISTRY" variable is not set`

**原因**：`docker-compose.prod.yml` 不会自动读取 `backend/.env`，需要项目根目录有 `.env` 文件。

**解决**：在项目根目录创建软链接 `ln -sf backend/.env .env`。

### 3. Swarm 服务 REPLICAS 显示 0/2

**原因**：镜像还没推送到 ACR，或者 ACR 未登录。

**解决**：先 `docker push` 镜像，再 `docker service update --force`。

### 4. SSH 长时间空闲后 `client_loop: send disconnect`

**原因**：SSH 空闲超时断开。

**解决**：这是正常的，不影响正在运行的命令。重新 SSH 连接即可。如果要避免，加 `-o ServerAliveInterval=60`。

### 5. 服务器 2G 内存卡顿

**原因**：postgres + redis + 2个 backend + frontend 5个容器跑在 2G 内存上。

**解决**：
```bash
# 添加交换内存
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```
