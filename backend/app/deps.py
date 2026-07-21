"""
FastAPI 共享依赖注入模块 — 安全优先设计。
FastAPI shared dependencies — security-first design.

================================================================================
  模块级说明（中文·前端开发者必读）
================================================================================

本模块定义了 API 的全局中间件依赖，包括：
  1. 三层速率限制（Rate Limiting）—— 按操作类型区分限制强度
  2. 客户端 IP 提取 —— 穿透代理/CDN 获取真实 IP
  3. 默认 Agent 获取 —— 查询数据库中标记为默认的智能体

════════════════════════════════════════════════════════════════════════════════
一、三层速率限制体系（3-Tier Rate Limiting）
════════════════════════════════════════════════════════════════════════════════

为什么需要分层限流？
  - 不同类型的 API 操作成本和风险不同
  - Chat（聊天）：每次请求调用 LLM API，消耗 Token 费用，最昂贵
  - Read（读取）：查询数据库，成本较低
  - Write（写入）：增删改数据，有安全和一致性风险

三层限流规则（每 IP 独立计数）：
┌───────────────┬──────────────────┬────────────────┬──────────────────────────┐
│  层级         │  限制             │  适用端点       │  原因                     │
├───────────────┼──────────────────┼────────────────┼──────────────────────────┤
│  Chat（聊天） │  20次 / 60秒     │  POST /api/chat │  LLM API 调用成本高       │
│  Read（读取） │  60次 / 60秒     │  list / get     │  查询频繁但成本低         │
│  Write（写入）│  10次 / 60秒     │  create/update/ │  防止数据被篡改/滥用      │
│               │                  │  delete         │                           │
└───────────────┴──────────────────┴────────────────┴──────────────────────────┘

技术实现：
  - 使用 Redis 滑动窗口计数器（Sliding Window Counter）
  - Key 格式：{前缀}:{IP地址}，例如 "chat:192.168.1.1"
  - 窗口过期后自动清理，不会无限占用 Redis 内存
  - Chat 层限流可通过环境变量 RATE_LIMIT_CHAT_MAX / RATE_LIMIT_CHAT_WINDOW 调整
  - 全局开关：RATE_LIMIT_ENABLED=false 可关闭所有限流（仅开发环境推荐）

════════════════════════════════════════════════════════════════════════════════
二、客户端 IP 提取机制
════════════════════════════════════════════════════════════════════════════════

IP 提取优先级链（从高到低）：
  1. X-Real-IP 请求头          — 最优先，通常由 Nginx/Caddy 直接设置
  2. X-Forwarded-For 请求头     — 取第一个 IP（客户端原始 IP），防止 IP 伪造
  3. request.client.host       — 直接连接的客户端地址（无代理时）
  4. "unknown"                 — 兜底值，以上全部为空时使用

安全防护：
  - 拒绝包含换行符（\n, \r）或空字节（\0）的 IP 字符串，防止 Header 注入攻击
  - IP 长度限制为 45 字符（IPv6 最大长度），超出自动截断
  - 去除首尾空白字符

════════════════════════════════════════════════════════════════════════════════
三、前端对接指南（Frontend Integration Tips）
════════════════════════════════════════════════════════════════════════════════

1. 处理 429 错误（Too Many Requests）：
   当 API 返回 HTTP 429 状态码时，表示触发频率限制。
   前端应实施以下处理策略：

   A. 即时提示用户：
      显示友好提示："请求过于频繁，请稍后再试"
      建议使用 Toast / Snackbar 组件，避免阻塞操作

   B. 实现指数退避重试（Exponential Backoff with Retry）：
      伪代码示例：
      ```javascript
      const MAX_RETRIES = 3;
      const BASE_DELAY = 1000; // 基础等待 1 秒

      async function apiWithRetry(url, body, retryCount = 0) {
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });

        if (response.status === 429 && retryCount < MAX_RETRIES) {
          // 指数退避：1秒 → 2秒 → 4秒
          const delay = BASE_DELAY * Math.pow(2, retryCount);
          await new Promise(resolve => setTimeout(resolve, delay));
          return apiWithRetry(url, body, retryCount + 1);
        }

        if (response.status === 429) {
          throw new Error('请求频率超限，请稍后再试');
        }

        return response.json();
      }
      ```

   C. 前端本地节流（Throttle）：
      在发送请求前做本地限制，避免频繁触发服务端 429：
      ```javascript
      // 聊天输入框节流：限制每 3 秒只能发送一次
      import { throttle } from 'lodash';  // 或手写节流函数

      const sendMessage = throttle(async (text) => {
        await apiPost('/api/chat', { message: text, conversation_id: currentConvId });
      }, 3000, { leading: true, trailing: false });
      ```

   D. 读取 Retry-After 响应头：
      虽然当前后端不直接返回 Retry-After 头，但建议前端预留逻辑：
      ```javascript
      const retryAfter = response.headers.get('Retry-After');
      if (retryAfter) {
        const waitSeconds = parseInt(retryAfter, 10);
        showToast(`请等待 ${waitSeconds} 秒后再试`);
      }
      ```

2. 不同操作类型的限流策略差异：
   - 聊天发送：最容易被限（20次/60秒），建议在输入框加入"发送冷却"提示
   - 列表刷新：几乎不会被限（60次/60秒），正常的 UI 操作不受影响
   - 编辑删除：限制较严（10次/60秒），批量操作时应注意频率

3. 调试/开发环境：
   后端可通过环境变量关闭限流：
   RATE_LIMIT_ENABLED=false
   开发时建议关闭，避免频繁触发限制影响调试效率。
================================================================================
"""
from typing import Optional

from fastapi import Depends, HTTPException, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import AgentConfig
from app.core.redis_client import rate_limit


async def get_client_ip(request: Request) -> str:
    """
    ============================================================
    从代理头部提取真实客户端 IP 地址。

    为什么不能直接用 request.client.host？
      - 生产环境中，应用通常部署在 Nginx / Caddy / Cloudflare 等反向代理后面
      - request.client.host 会返回代理服务器的 IP（如 127.0.0.1 或内网 IP）
      - 必须从代理服务器传递的 HTTP 头部中提取真实客户端 IP

    IP 提取优先级（从高到低）：
      1. X-Real-IP        — Nginx 等代理直接设置的单一 IP，最可靠
      2. X-Forwarded-For  — 取第一个 IP（逗号分隔列表的最左端），
                             这是原始客户端 IP，后续 IP 是经过的代理链
                             注意：取第一个而非最后一个，防止客户端伪造该头部
      3. request.client.host — 无代理时的直连 IP，作为兜底方案
      4. "unknown"         — 极端情况下（如 request.client 为 None）的兜底值

    安全校验（防止 Header 注入攻击）：
      - 长度截断：IP 字符串长度限制为 45 个字符（IPv6 标准最大长度）
      - 字符过滤：拒绝包含换行符（\\n, \\r）或空字节（\\0）的值
        攻击者可能通过注入换行符来伪造 HTTP 头部，此检查可有效防御
      - 空白去除：trim 首尾空白，防止空格导致的匹配/存储问题

    前端注意：
      此函数对前端透明（不可见），前端无需关心 IP 提取逻辑。
      速率限制和审计日志后端自动基于此函数返回的真实客户端 IP 进行计算。
    ============================================================
    """
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    x_real_ip = request.headers.get("X-Real-IP")

    # 优先级：X-Real-IP > X-Forwarded-For 第一个 > request.client.host > "unknown"
    # X-Forwarded-For 格式：client_ip, proxy1_ip, proxy2_ip, ...
    # 取第一个逗号前的内容（原始客户端 IP），并去除空白
    ip = x_real_ip or (x_forwarded_for.split(",")[0].strip() if x_forwarded_for else None)
    if not ip:
        ip = request.client.host if request.client else "unknown"

    # 安全清理：去除空白、限制长度、过滤危险字符
    ip = ip.strip()
    if len(ip) > 45:  # IPv6 标准最大长度为 45 个字符（如 fe80::1 共 45 字节）
        ip = ip[:45]
    if "\n" in ip or "\r" in ip or "\0" in ip:
        # 换行符可用于头部注入攻击（HTTP Header Injection），空字节用于绕过
        raise HTTPException(status_code=400, detail="Invalid client IP header")

    return ip


async def get_default_agent(db: AsyncSession) -> Optional[AgentConfig]:
    """
    ============================================================
    获取默认 Agent 配置。

    查找逻辑：
      1. 优先查找 is_default=True 的 AgentConfig 记录
      2. 如果没有标记为默认的，则取数据库中的第一条记录
      3. 如果数据库中没有任何 Agent 配置，返回 None

    前端关联：
      当用户发送消息时，如果不指定 agent_id，后端会调用此函数
      来获取默认 Agent 的系统提示词、温度参数、工具配置等。
      前端的 Agent 选择器中，标记为"默认"的选项对应此查询结果。
    ============================================================
    """
    result = await db.execute(
        select(AgentConfig)
        .where(AgentConfig.is_default == True)
        .limit(1)
    )
    agent = result.scalar_one_or_none()
    if agent:
        return agent
    result = await db.execute(select(AgentConfig).limit(1))
    return result.scalar_one_or_none()


async def verify_rate_limit(
    request: Request,
    max_requests: int = 30,
    window: int = 60,
    key_prefix: str = "api",
):
    """
    ============================================================
    速率限制中间件依赖 — 可应用于任何端点。

    实现方式：基于 Redis 的滑动窗口计数器（Sliding Window Counter）

    工作原理：
      1. 获取客户端真实 IP（调用上面的 get_client_ip）
      2. 生成 Redis Key：{key_prefix}:{IP地址}
         例如："chat:192.168.1.100"
      3. 在 Redis 中对该 Key 的计数器执行 INCR 操作
      4. 如果计数超过 max_requests，返回 429 Too Many Requests
      5. 窗口时间（window 秒）后 Key 自动过期，计数器重置

    与固定窗口（Fixed Window）的区别：
      - 固定窗口：00:00-00:59 是一个窗口，01:00-01:59 是下一个
        缺点：00:59 和 01:00 连续发送会被允许（跨窗口边界）
      - 滑动窗口：每个时间点向前看 window 秒
        优点：任何时间段的请求频率都会被正确限制，无边界逃逸问题

    参数说明（前端参考）：
      max_requests — 时间窗口内允许的最大请求次数
      window       — 时间窗口大小（秒）
      key_prefix   — Redis 键前缀，用于区分不同限流策略
                     "chat"  = 聊天限流（20次/60秒）
                     "read"  = 读取限流（60次/60秒）
                     "write" = 写入限流（10次/60秒）

    前端注意：
      触达限流时后端返回 HTTP 429 + JSON 响应体：
      { "detail": "Rate limit exceeded. Try again later." }
      前端应捕获 429 状态码并实施友好提示 + 重试策略。
      详见本文件顶部的"前端对接指南"章节。
    ============================================================
    """
    ip = await get_client_ip(request)
    key = f"{key_prefix}:{ip}"
    allowed = await rate_limit(key, max_requests=max_requests, window=window)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")


# ═══════════════════════════════════════════════════════════════════════════
# 便捷限流函数（Convenience Rate Limiters）
# 以下三个函数封装了 verify_rate_limit，为不同类型的端点预设了限流参数。
# 在路由定义中通过 FastAPI 的 Depends() 注入使用。
# ═══════════════════════════════════════════════════════════════════════════

async def verify_write_rate_limit(request: Request):
    """
    ============================================================
    写入操作限流：10次 / 60秒 per IP

    适用端点（示例）：
      POST /api/agents/create     — 创建 Agent
      POST /api/agents/update     — 更新 Agent
      POST /api/agents/delete     — 删除 Agent
      POST /api/conversations/create     — 创建会话
      POST /api/conversations/delete     — 删除会话
      POST /api/conversations/update-title — 更新标题

    为什么最严格？
      - 写入操作修改数据库状态，误操作或恶意攻击影响大
      - 批量创建/删除可能导致数据库压力
      - 防止脚本批量注册/篡改数据

    前端最佳实践：
      - 删除操作必须弹出二次确认对话框（Modal Confirm）
      - 避免提供"一键全部删除"类的高危批量操作
      - 编辑表单应加入防抖（debounce），避免快速点击提交
      - 创建成功后建议短暂禁用提交按钮（如 500ms），防止双击
    ============================================================
    """
    await verify_rate_limit(request, max_requests=10, window=60, key_prefix="write")


async def verify_read_rate_limit(request: Request):
    """
    ============================================================
    读取操作限流：60次 / 60秒 per IP

    适用端点（示例）：
      POST /api/agents/list        — 获取 Agent 列表
      POST /api/agents/get         — 获取 Agent 详情
      POST /api/conversations/list — 获取会话列表
      POST /api/conversations/get  — 获取会话详情
      POST /api/documents/list     — 获取文档列表

    为什么相对宽松？
      - 查询操作不修改数据，误操作影响小且易恢复
      - 正常 UI 浏览行为会产生大量查询请求（滚动列表、切换页面）
      - 60次/分钟基本等于每秒1次，能满足正常用户操作需求

    前端注意：
      正常使用基本不会触发此限制。如果触发了，说明：
      - 前端存在轮询逻辑且轮询间隔过短（建议不低于2秒）
      - 存在 Bug 导致死循环请求（请检查 useEffect 依赖项）
      - 多人共享同一出口 IP（如公司内网），此为正常现象
    ============================================================
    """
    await verify_rate_limit(request, max_requests=60, window=60, key_prefix="read")


async def verify_chat_rate_limit(request: Request):
    """
    ============================================================
    聊天端点限流：20次 / 60秒 per IP（可通过环境变量调整）

    适用端点：
      POST /api/chat  — 发送聊天消息（唯一触发点）

    为什么是最严格的限流策略？
      1. 每次聊天请求都会调用 LLM API（通义千问/OpenAI/Claude）
      2. LLM API 按 Token 计费，请求频率直接影响运营成本
      3. 流式响应（SSE）占用的连接时间较长，高并发可能导致资源耗尽

    区别于上述两个限流函数：
      - 支持全局开关：RATE_LIMIT_ENABLED=false 可（仅开发环境）关闭
      - 参数可配置：
          RATE_LIMIT_CHAT_MAX=20     （环境变量，窗口内最大次数）
          RATE_LIMIT_CHAT_WINDOW=60  （环境变量，窗口秒数）
      - 默认值：20次/60秒 ≈ 每3秒可发送1条消息

    前端最佳实践：
      1. 发送按钮冷却（推荐）：
         发送消息后禁用输入框/按钮 2-3 秒，既防止快速重复发送，
         也自然避免了触发限流。同时给出视觉反馈（按钮变灰）。

      2. 防止重复提交：
         发送请求期间设置 loading 状态，禁止再次点击发送：
         ```javascript
         const [sending, setSending] = useState(false);

         async function handleSend(text) {
           if (sending) return;  // 防重复提交
           setSending(true);
           try {
             await apiPost('/api/chat', { message: text, ... });
           } finally {
             setSending(false);  // 请求完成后恢复
           }
         }
         ```

      3. 错误反馈（429 处理）：
         捕获 429 状态码后显示友好提示。
         因为窗口只有60秒，用户只需等待最多60秒即可恢复。
         ```javascript
         if (response.status === 429) {
           showToast('消息发送太频繁，请稍等几秒后再试', { type: 'warning' });
         }
         ```
    ============================================================
    """
    if not settings.rate_limit_enabled:
        return
    await verify_rate_limit(
        request,
        max_requests=settings.rate_limit_chat_max,
        window=settings.rate_limit_chat_window,
        key_prefix="chat",
    )
