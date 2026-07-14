"""
Structured logging via loguru.
Replaces all scattered print() calls with JSON-formatted, timestamped logs.
"""
import sys

from loguru import logger

# Remove default handler and add structured stdout handler
logger.remove()
logger.add(
    sys.stdout,
    format=(
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "{name}:{function}:{line} | {message}"
    ),
    level="DEBUG",
    colorize=True,
)

# Also add a JSON handler for production (disabled by default, set LOG_JSON=1 to enable)
# When enabled, emits JSON lines for log aggregation systems (ELK, Loki, etc.)
import os
if os.environ.get("LOG_JSON") == "1":
    logger.add(
        sys.stdout,
        format="{message}",
        level="INFO",
        serialize=True,  # JSON output
    )
    logger.remove(0)  # Remove the colored handler above
