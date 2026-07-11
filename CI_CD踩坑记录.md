# CI/CD 踩坑记录

> 项目：AI Agent Platform
> 时间：2026-07-10 ~ 2026-07-11
> 范围：GitHub Actions 自动部署 + 工具扩展

---

## 问题 1：DuckDuckGo Instant Answer API 中文搜索返回空

**现象**

用户问天气相关问题，Agent 调用 `web_search` 工具后返回"未找到相关结果"或空内容。

**原因**

`tools.py` 中使用的是 DuckDuckGo 的 **Instant Answer API**（`api.duckduckgo.com`），该 API 对中文查询支持极差，经常返回空 JSON。

**解决**

改用 `duckduckgo_search` Python 库，通过 HTML 抓取 DuckDuckGo 搜索结果：

```python
# 之前：API 调用，中文查询不可靠
resp = await client.get("https://api.duckduckgo.com/", params={...})

# 之后：HTML 抓取，结果稳定
from duckduckgo_search import DDGS
with DDGS() as ddgs:
    results = list(ddgs.text(query, max_results=5))
```

同时更新 `requirements.txt` 添加 `duckduckgo-search>=7.0.0`。

---

## 问题 2：缺少天气查询工具

**现象**

用户问天气时，Agent 只能通过 `web_search` 间接查询，结果不稳定且 LLM 容易误判为"网络搜索不可用"。

**解决**

新增 `get_weather(city)` 工具，使用 **wttr.in** 免费 API（无需 Key）：

```python
@tool
def get_weather(city: str) -> str:
    url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1"
    # 返回：天气描述、温度、体感、湿度、风速等
```

注册到 `ALL_TOOLS` 字典即可在前端 Settings 页面出现。

---

## 问题 3：GitHub Actions `git pull` 分支名不匹配

**现象**

```text
fatal: couldn't find remote ref main
Error: Process completed with exit code 1.
```

**原因**

`deploy.yml` 中写的是 `git pull origin main`，但仓库实际主分支叫 `master`。

**解决**

```yaml
# 修改前
git pull origin main

# 修改后
git checkout master
git pull origin master
```

> **教训**：分支名要与实际仓库一致，不确定时用 `git branch -a` 确认。

---

## 问题 4：服务器访问 GitHub TLS 连接被墙

**现象**

```text
fatal: unable to access 'https://github.com/...':
  GnuTLS recv error (-110): The TLS connection was non-properly terminated.
```

**原因**

国内服务器（腾讯云）访问 GitHub 极其不稳定，TLS 握手频繁被重置。之前设计是 Actions → SSH → 服务器 → `git pull` GitHub，中间这步必挂。

**解决**

改架构：不让服务器访问 GitHub，由 Actions 直接传代码到服务器。

```
之前: GitHub Runner → SSH → 服务器 git pull GitHub  ❌ 被墙
现在: GitHub Runner → tar → SCP → 服务器解压 → 构建  ✅ 绕过墙
```

核心流程：

```yaml
# 1. 打包代码
tar czf /tmp/code.tar.gz --exclude='.git' --exclude='__pycache__' .

# 2. SCP 传到服务器
sshpass -e scp /tmp/code.tar.gz user@host:/tmp/

# 3. SSH 解压并构建
sshpass -e ssh user@host bash -s << 'ENDSCRIPT'
  cd ~/ai-agent-platform
  tar xzf /tmp/code.tar.gz
  docker compose build backend --no-cache
  docker compose build frontend
  docker compose up -d
ENDSCRIPT
```

> **关键点**：用 `SSHPASS` 环境变量传递密码，`sshpass -e` 安全可靠。

---

## 问题 5：`appleboy/scp-action@v0` 版本不存在

**现象**

```text
Error: Unable to resolve action `appleboy/scp-action@v0`,
  unable to find version `v0`
```

**原因**

GitHub Actions 的第三方 Action 需要明确版本号，`v0` 不是有效 tag。

**解决**

放弃第三方 Action，直接用标准命令行工具：

```bash
sudo apt-get install -y sshpass        # 安装密码认证工具
sshpass -e scp ...                     # 传文件
sshpass -e ssh ...                     # 执行命令
```

> **原则**：能不依赖第三方 Action 就不依赖。标准工具（git、scp、ssh、tar）比 Action 稳定得多。

---

## 问题 6：阿里云容器镜像拉取需要认证

**现象**

```text
FROM registry.aliyuncs.com/library/node:22-alpine AS builder
failed to solve: pull access denied, repository does not exist
  or may require authorization
```

**原因**

Dockerfile 中硬编码了 `registry.aliyuncs.com`，但阿里云容器镜像服务改了策略，公共拉取需要登录认证。

**解决**

改用标准 Docker Hub 镜像名，让服务器 Docker daemon 的镜像加速器自动代理：

```dockerfile
# 之前
FROM registry.aliyuncs.com/library/node:22-alpine AS builder
FROM registry.aliyuncs.com/library/nginx:alpine

# 之后
FROM node:22-alpine AS builder
FROM nginx:alpine
```

服务器之前已配置 `docker.m.daocloud.io` 镜像加速器（见 `daemon.json`），标准镜像名会自动走加速通道。

---

## 问题 7：密码泄露风险

**现象**

在聊天中直接发送服务器 SSH 密码和 IP 地址。

**解决**

1. **立即修改服务器密码**：`ssh ubuntu@IP` → `passwd`
2. 敏感信息只能通过 **GitHub Secrets** 传递：
   - Settings → Secrets and variables → Actions
   - `SERVER_HOST`、`SERVER_USER`、`SERVER_PASSWORD`、`SERVER_PORT`
3. 撤销 `.env.example` 中暴露的 API Key（`sk-71364233b04d4e4fb7ff11db3b8994f9`）

---

## 总结

| # | 问题 | 根因 | 解决 |
|---|------|------|------|
| 1 | 网络搜索返回空 | DuckDuckGo API 不支持中文 | 改用 HTML 抓取库 |
| 2 | 无天气工具 | 未实现 | wttr.in 免费 API |
| 3 | git pull 报错 | 分支名 main vs master | 改为主分支实际名称 |
| 4 | TLS 连接被墙 | 国内服务器访问 GitHub 不稳定 | tar+SCP 绕开，服务器不访问 GitHub |
| 5 | scp-action 版本不存在 | v0 不是有效 tag | 改用标准 sshpass 命令 |
| 6 | 阿里云镜像拉取失败 | registry 需要认证 | 改回 Docker Hub，走 daemon 加速 |
| 7 | 密码泄露 | 明文发送 | 改密码 + GitHub Secrets |

### 核心经验

1. **国内服务器部署**：代码由海外 Runner 推过来，别让服务器去拉 GitHub
2. **镜像源**：Docker Hub + daemon 加速，别硬编码国内 Registry（策略经常变）
3. **GitHub Actions**：优先用标准命令行工具，第三方 Action 版本号要精确
4. **免费 API 选型**：DuckDuckGo 用搜索库而非 API、wttr.in 做天气、ip-api.com 做 IP 查询
5. **安全**：所有敏感信息走 GitHub Secrets，绝不硬编码或明文传输
