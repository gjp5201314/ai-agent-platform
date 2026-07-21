"""
================================================================================
健康检查 API 模块
================================================================================

【模块职责】
  提供系统健康状态检查端点，用于：
  1. 负载均衡器/反向代理的健康探测（如 Nginx upstream check）
  2. 容器编排平台的存活探针（Kubernetes liveness/readiness probe）
  3. 前端监控面板/状态页的实时状态展示
  4. 告警系统的数据源（结合 Prometheus/Grafana 等）

【API 设计规范】
  - 企业级安全设计：使用 POST 方法，不含 URL 查询参数。
  - 健康检查端点通常为 GET（如 Kubernetes probe），这里改为 POST 是为了
    统一项目的 API 风格，避免敏感信息出现在 URL 中。
  - 如果您需要对接 Kubernetes，可以在 ingress/nginx 层添加 GET→POST 代理，
    或新增一个轻量级的 GET /healthz 端点。

【端点说明】
  POST /api/health/health
  请求：无需参数（POST Body 可为空）
  响应：HealthCheck 对象

================================================================================

【响应格式详解】

  HealthCheck 结构体包含以下字段：

  {
    "status": "ok",             // 整体状态。
                                //   "ok"       — 所有关键服务正常
                                //   "degraded" — 部分服务异常，但系统仍可部分工作
                                //   （当前实现不会返回"error"，因为健康检查本身
                                //   不依赖所有服务都正常）

    "database": "ok",           // PostgreSQL 数据库连接状态。
                                //   "ok"       — 数据库连接正常，可以执行查询
                                //   "error"    — 数据库连接失败
                                //   "unknown"  — 未检测（初始值，正常情况下不会出现）

    "redis": "ok",              // Redis 缓存服务连接状态。
                                //   "ok"       — Redis 连接正常，可以 ping 通
                                //   "error"    — Redis 连接失败
                                //   "unknown"  — 未检测（初始值）

    "memory": {                 // Mem0 长期记忆服务状态（JSON 对象）。
                                //   具体字段由 get_memory_status() 返回，
                                //   通常包含 enabled, status 等字段。
                                //   如果 Mem0 未配置，status 可能为 "disabled"
    },

    "llm_provider": "qwen"      // 当前使用的 LLM 提供商标识符。
                                //   可能值: "qwen", "openai", "claude"
                                //   用于判断当前 AI 对话使用的是哪家服务
                                //   注意：此字段返回的是提供商名称，不包含 API Key
  }

================================================================================

【状态字段完整说明】

  ┌──────────────┬──────────────────────────────────────────────────────────┐
  │ 字段          │ 说明                                                      │
  ├──────────────┼──────────────────────────────────────────────────────────┤
  │ status        │ 系统整体健康状态。逻辑：仅当 database 和 redis 均为       │
  │               │ "ok" 时才为 "ok"，否则为 "degraded"。                     │
  │               │ memory 和 llm_provider 的状态不影响 overall 判断。        │
  ├──────────────┼──────────────────────────────────────────────────────────┤
  │ database      │ PostgreSQL + pgvector 数据库连接状态。                    │
  │               │ 通过执行 "SELECT 1" 来验证连接可用性和查询功能。           │
  │               │ 如果此字段为 "error"，知识库功能和对话历史将不可用。       │
  ├──────────────┼──────────────────────────────────────────────────────────┤
  │ redis         │ Redis 缓存服务状态。用于会话缓存、对话上下文存储等。       │
  │               │ 如果此字段为 "error"，会话管理功能会降级（可能丢失上下文）。│
  │               │ 通过 redis.ping() 检测连接。                              │
  ├──────────────┼──────────────────────────────────────────────────────────┤
  │ memory        │ Mem0 长期记忆服务状态。                                   │
  │               │ 类型为对象（JSON），包含子字段如 enabled, status 等。       │
  │               │ 如果未配置 Mem0，status 会显示相关提示。                   │
  │               │ 长期记忆不可用时，AI 无法记住跨对话的历史信息。             │
  ├──────────────┼──────────────────────────────────────────────────────────┤
  │ llm_provider  │ 当前激活的 LLM 提供商。                                  │
  │               │ 可能值: "qwen"（通义千问）, "openai", "claude"            │
  │               │ 用于前端的服务状态指示（如显示"当前使用: 通义千问"）        │
  │               │ 此字段不涉及 API Key 等敏感信息，可安全展示。              │
  │               │ 注意：此字段仅表示"配置"的提供商，不验证 API Key 是否有效。 │
  └──────────────┴──────────────────────────────────────────────────────────┘

================================================================================

【前端监控/状态页面使用指南】

  1. 基础状态展示
     前端可定时轮询此端点（建议间隔：15-30 秒），展示实时状态面板：

     ┌─────────────────────────────────────────────┐
     │  🟢 系统运行正常                               │
     │                                              │
     │  🟢 数据库    PostgreSQL 连接正常              │
     │  🟢 缓存      Redis 连接正常                   │
     │  🟢 长期记忆  Mem0 服务可用                    │
     │  📡 LLM服务   通义千问 (DashScope)             │
     └─────────────────────────────────────────────┘

     当服务降级时：
     ┌─────────────────────────────────────────────┐
     │  🟡 系统部分降级                               │
     │                                              │
     │  🟢 数据库    PostgreSQL 连接正常              │
     │  🔴 缓存      Redis 连接异常                   │
     │  ⚪ 长期记忆  Mem0 未配置                       │
     │  📡 LLM服务   通义千问 (DashScope)             │
     └─────────────────────────────────────────────┘

  2. 状态图标映射建议
     "ok"      → 🟢 绿色圆点 / 绿色状态标签
     "error"   → 🔴 红色圆点 / 红色警告
     "unknown" → ⚪ 灰色圆点 / 加载中动画
     "disabled"→ ⚫ 黑色圆点 / "未配置"标签

  3. 监控告警集成
     - 配合 setInterval 定时轮询（如每 30 秒）
     - status === "degraded" 时触发前端通知/弹窗
     - database === "error" 时禁用知识库相关功能
     - redis === "error" 时显示"会话缓存异常"提示
     - 可记录状态变更历史用于趋势分析

  4. Kubernetes 探针配置参考
     如果需要在 K8s 中使用此端点：
     livenessProbe:
       httpGet:
         path: /api/health/health
         port: 8000
       initialDelaySeconds: 30
       periodSeconds: 30

     注意：K8s 默认使用 GET 请求，而此端点是 POST。
     可考虑添加一个轻量级的 GET /healthz 端点用于 K8s 探针，
     /healthz 只需返回 200 OK + 简单的 JSON {"status":"ok"}。

  5. 错误处理建议
     - 网络请求失败（非 200 响应）→ 视为整个服务不可用
     - 响应解析失败 → 显示"获取状态失败"并重试
     - 超时 → 设置合理的 timeout（如 5 秒），超时视为不可用
     - 接入超时重试机制（最多重试 3 次，指数退避）

================================================================================

【依赖的组件状态检测方式】

  组件      检测方式                  检测失败时的处理
  ─────────────────────────────────────────────────────────
  数据库    SELECT 1                 捕获异常，设为 "error"
  Redis     redis.ping()            捕获异常，设为 "error"
  长期记忆  get_memory_status()     返回配置状态（不会抛异常）
  LLM       读取 settings 配置       始终返回（无需网络检测）

================================================================================
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.core.redis_client import get_redis
from app.core.memory import get_memory_status
from app.schemas import HealthCheck

router = APIRouter()


# ============================================================================
# 健康检查端点
# ============================================================================
# POST /api/health/health
#
# 【检测逻辑】
#   1. 数据库检测：执行 "SELECT 1" 验证 PostgreSQL 连接
#      - 成功 → database = "ok"
#      - 失败 → database = "error"（不影响整体流程继续执行）
#   2. Redis 检测：执行 redis.ping() 验证连接
#      - 成功 → redis = "ok"
#      - 失败 → redis = "error"
#   3. Mem0 检测：调用 get_memory_status() 获取长期记忆服务状态
#      - 该函数不抛异常，始终返回状态对象
#   4. LLM 提供商：读取 settings.llm_provider（纯配置读取，无网络检测）
#
# 【整体状态判定】
#   - status = "ok"       当 database == "ok" 且 redis == "ok"
#   - status = "degraded" 当 database 或 redis 任一为 "error"
#   - 注意：memory 和 llm_provider 的状态不影响 overall 判断
#          因为这两项不是系统运行的关键依赖

@router.post("/health", response_model=HealthCheck)
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    服务健康检查（POST — 无敏感数据出现在 URL 中）。

    检测数据库、Redis、Mem0 长期记忆服务的连接状态，
    并返回当前使用的 LLM 提供商信息。
    """
    db_status = "unknown"
    redis_status = "unknown"

    try:
        # 执行简单的查询验证数据库连接
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    try:
        # Ping Redis 验证缓存服务连接
        redis = await get_redis()
        await redis.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"

    # 获取 Mem0 长期记忆服务状态（不会抛异常）
    memory_status = get_memory_status()

    # 整体状态判定：仅当数据库和 Redis 都正常时才算 ok
    overall = "ok"
    if db_status != "ok" or redis_status != "ok":
        overall = "degraded"

    return HealthCheck(
        status=overall,
        database=db_status,
        redis=redis_status,
        memory=memory_status,
        llm_provider=settings.llm_provider,
    )
