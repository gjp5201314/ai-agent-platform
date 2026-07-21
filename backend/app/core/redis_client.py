"""
================================================================================
Redis 异步客户端 — 会话状态、速率限制和缓存的中央存储
================================================================================

【前端开发者必读】

Redis 是什么？
  Redis 是一个高性能的内存键值存储数据库。可以把它想象成一个
  超级快的大字典（key-value store），数据全在内存中，读写速度极快。

本项目中 Redis 的三大用途：

  1. 速率限制（Rate Limiting）
     记录每个 IP 地址的请求频率，防止 API 滥用。
     - 每个用户（按 IP 识别）每分钟最多 N 次聊天请求
     - 超过限制返回 HTTP 429 (Too Many Requests)
     - 前端应捕获 429 并显示友好提示

  2. 数据缓存（Caching）
     缓存频繁访问的数据，避免重复查询 PostgreSQL。
     - 例如：Agent 配置列表、热门的知识库搜索结果
     - 缓存有过期时间 TTL（Time To Live），到期自动删除

  3. 会话状态（Session State）
     存储对话过程中的临时状态。
     - 例如：用户当前选择的 Agent、正在进行的操作标记

================================================================================
缓存键（Cache Key）命名规范
================================================================================

所有缓存键采用层级前缀结构，便于管理和调试：

  agent:{agent_id}            — Agent 配置缓存
  agent:list                  — 所有 Agent 列表缓存
  conversation:{conv_id}      — 对话缓存
  conversation:{conv_id}:messages — 对话消息缓存
  document:{doc_id}           — 文档元数据缓存
  rate_limit:{ip_address}     — 速率限制计数器
  search:{query_hash}         — 搜索结果缓存

TTL（过期时间）说明：
  - 默认 TTL: 3600 秒（1 小时）
  - 用户数据缓存 TTL 较短（避免数据不一致）
  - 速率限制窗口: 60 秒

================================================================================
技术细节：protocol=2 兼容性问题
================================================================================

redis-py 5.x 版本默认使用 RESP3 协议（Redis 序列化协议第 3 版），
但与密码保护的 Redis 7 存在一个 bug：使用 HELLO 命令切换协议时，
AUTH 选项会导致连接失败。

解决方法：强制使用 RESP2 协议（protocol=2），这是兼容性最广的版本。
这个参数不影响任何功能，只是改变了底层通信协议的版本。

详细说明：
  - RESP2: 简单文本协议，所有 Redis 版本都支持
  - RESP3: 新版二进制协议，支持更丰富的数据类型（但客户端兼容性差）
  - 这个 bug 在 redis-py 和 Redis 7 之间，指定 protocol=2 是标准解决方法
================================================================================
"""
from typing import Optional, Any
import json

import redis.asyncio as redis

from app.config import settings

# 连接池 — 懒加载初始化的单例模式
# 全局变量存储 Redis 连接实例，避免每次请求都创建新连接
# 初始值为 None，首次调用 get_redis() 时创建
_redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """
    获取或创建 Redis 连接（懒加载单例模式）。

    【设计说明】
    使用懒加载单例模式的原因：
      1. 连接只在需要时创建（节省资源）
      2. 全局只有一个连接实例（连接池管理）
      3. 避免在模块导入时创建连接（可能在事件循环准备好之前）

    【连接配置说明】
    - decode_responses=True: 自动将 Redis 返回的 bytes 解码为 str，
      这样缓存的值读取后直接是 Python 字符串，前端 API 可以直接使用。
    - max_connections=20: 连接池大小，20 个并发连接足够中等规模使用。
    - protocol=2: 强制使用 RESP2 协议（见文件头部注释的详细说明）。
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
            # Force RESP2 protocol — newer redis-py defaults to HELLO 3 (RESP3)
            # which is incompatible with password-protected Redis 7 (HELLO AUTH option bug)
            protocol=2,
        )
    return _redis_client


async def close_redis():
    """
    关闭 Redis 连接（应用关闭时调用）。

    在 FastAPI 的 lifespan/shutdown 事件中调用此函数，
    确保资源被正确释放，避免连接泄漏。
    """
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


# ==============================================================================
# 缓存辅助函数
# ==============================================================================
# 以下函数提供了对 Redis 缓存的简单封装，
# 值和 key 之间有清晰的命名约定，方便调试和监控。

async def cache_set(key: str, value: Any, ttl: int = 3600) -> bool:
    """
    设置缓存键值对，带 TTL（过期时间）。

    参数：
      key:   缓存键名，建议使用 "category:id" 格式
      value: 缓存值，任意 Python 对象（会被 JSON 序列化）
      ttl:   过期时间（秒），默认 3600 秒（1 小时）

    返回：True 表示设置成功

    【前端关联】
    缓存的 Agent 配置可以通过 cache_get("agent:list") 获取。
    """
    r = await get_redis()
    # json.dumps 将 Python 对象转为 JSON 字符串存储
    # default=str 处理 JSON 不支持的类型（如 datetime）
    return await r.set(key, json.dumps(value, default=str), ex=ttl)


async def cache_get(key: str) -> Any:
    """
    获取缓存值。如果键不存在或已过期，返回 None。

    参数：
      key: 缓存键名

    返回：缓存的值（Python 对象），或 None

    使用示例：
      agent_config = await cache_get("agent:abc123")
      if agent_config is None:
          # 缓存未命中，需要从数据库加载
          pass
    """
    r = await get_redis()
    data = await r.get(key)
    # json.loads 将 JSON 字符串还原为 Python 对象
    return json.loads(data) if data else None


async def cache_delete(key: str) -> bool:
    """
    删除缓存项。在数据更新后调用，使缓存失效。

    参数：
      key: 缓存键名

    返回：True 表示成功删除了至少一个键
    """
    r = await get_redis()
    return await r.delete(key) > 0


# ==============================================================================
# 速率限制辅助函数
# ==============================================================================

async def rate_limit(identifier: str, max_requests: int = 20, window: int = 60) -> bool:
    """
    简单的滑动窗口速率限制器。

    【工作原理】
    1. 使用 Redis 的 INCR 命令原子地递增计数器
    2. 如果是第一次请求（counter==1），设置过期时间（TTL）
    3. TTL 到期后计数器自动归零，窗口重置

    类比：一个漏水桶，每秒漏一点水；如果水倒得太快就会溢出。

    【前端如何使用】
    后端会在请求处理前调用此函数：
      POST /api/chat  → rate_limit(ip_address, 20, 60)
    如果返回 False，后端返回 HTTP 429 状态码。
    前端需要：
      1. 捕获 429 状态码
      2. 显示友好提示："请求太频繁，请稍等片刻"
      3. 可选：显示倒计时

    参数：
      identifier:    用户标识符（通常是客户端 IP 地址）
      max_requests:  窗口内允许的最大请求数（默认 20）
      window:        时间窗口大小（秒，默认 60）

    返回：
      True:  允许通过
      False: 速率限制触发，应返回 429
    """
    r = await get_redis()
    # 缓存键格式：rate_limit:{identifier}
    # 例如：rate_limit:192.168.1.100
    key = f"rate_limit:{identifier}"

    # Redis INCR 是原子操作，天然的线程安全
    # 多个并发请求不会导致计数错误
    current = await r.incr(key)

    # 只在首次设置时指定过期时间（后续 INCR 不影响 TTL）
    if current == 1:
        await r.expire(key, window)

    # 判断是否在限制内
    return current <= max_requests
