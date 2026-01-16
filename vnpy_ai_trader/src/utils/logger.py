"""
Logging utilities for VNPy AI Trader.
日志工具模块
"""

import sys
from pathlib import Path
from loguru import logger


def setup_logger(
    level: str = "INFO",
    log_file: str | None = None,
    rotation: str = "1 day",
    retention: str = "30 days"
) -> None:
    """
    Setup logging configuration.
    配置日志系统

    Args:
        level: Log level (DEBUG/INFO/WARNING/ERROR)
        log_file: Path to log file, None for console only
        rotation: Log rotation interval
        retention: Log retention period
    """
    # Remove default handler
    logger.remove()

    # Console handler with colored output
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        colorize=True
    )

    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_file,
            level=level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation=rotation,
            retention=retention,
            encoding="utf-8"
        )


def get_logger(name: str = "ai_trader"):
    """
    Get a logger instance with the given name.
    获取指定名称的日志记录器

    Args:
        name: Logger name for identifying the source

    Returns:
        Logger instance
    """
    return logger.bind(name=name)


# Default logger instance
default_logger = get_logger()
