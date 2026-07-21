"""
================================================================================
结构化日志配置 — 基于 Loguru
================================================================================

【前端开发者必读】

本文件使用 Loguru 替换了 Python 默认的 Logging 模块，
为整个后端应用提供统一的结构化日志输出。

为什么使用 Loguru？
  - 比标准 logging 更简洁的 API（无需配置 Logger/Handler/Formatter）
  - 开箱即用的彩色输出（开发环境友好）
  - 支持 JSON 序列化输出（生产环境对接 ELK/Loki 等日志聚合系统）
  - 更好的异常追踪（自动显示变量值和调用栈）

日志级别（从低到高）：
  TRACE    — 最详细的调试信息，性能调优用
  DEBUG    — 开发调试信息，如"数据库查询完毕，耗时 45ms"
  INFO     — 正常运行信息，如"服务器启动成功，监听 0.0.0.0:8000"
  WARNING  — 警告信息，不影响运行的问题，如"Mem0 初始化跳过"
  ERROR    — 错误信息，需要关注但系统仍可运行，如"API 调用失败，使用缓存数据"
  CRITICAL — 严重错误，系统可能不可用，如"数据库连接失败"

日志格式说明：
  {time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}

  示例输出：
  2025-01-15 14:30:22.456 | INFO     | api.chat:send_message:42 | Agent response generated in 3.2s
  │                        │          │                          │
  │                        │          │                          └── 日志消息
  │                        │          └── 模块:函数:行号（精确定位代码位置）
  │                        └── 日志级别（左对齐，8 字符宽度）
  └── 精确到毫秒的时间戳

================================================================================
"""
import sys

from loguru import logger

# 移除 Loguru 的默认日志处理器
# Loguru 默认会输出到 stderr，我们移除它以便自定义输出格式
logger.remove()

# 添加结构化标准输出处理器（控制台输出）
logger.add(
    sys.stdout,
    format=(
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "{name}:{function}:{line} | {message}"
    ),
    level="DEBUG",    # 开发环境使用 DEBUG 级别，生产环境可改为 INFO
    colorize=True,    # 启用彩色输出（不同级别不同颜色，方便快速识别）
)

# ==============================================================================
# JSON 日志输出（生产环境可选）
# ==============================================================================
# 当设置环境变量 LOG_JSON=1 时，启用 JSON 格式输出。
# JSON 格式适合被日志聚合系统（如 ELK Stack、Grafana Loki）解析和索引。
#
# 启用方式：
#   - 开发环境：export LOG_JSON=1
#   - Docker Compose：在 environment 中添加 LOG_JSON=1
#
# 切换逻辑：
#   如果启用 JSON 模式，会先移除上面的彩色格式化处理器（index 0），
#   改为纯 JSON 行输出。
#
# 前端无需关注此配置，仅影响后端的日志输出格式。

import os
if os.environ.get("LOG_JSON") == "1":
    logger.add(
        sys.stdout,
        format="{message}",    # 在 serialize 模式下，Loguru 自动生成 JSON
        level="INFO",          # JSON 模式使用 INFO 级别（减少输出量）
        serialize=True,        # 核心标志：启用 JSON 序列化
    )
    logger.remove(0)  # 移除上面添加的彩色处理器（index 0）
