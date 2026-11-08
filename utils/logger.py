"""日志工具：详细堆栈写入本地文件，界面只展示友好提示。"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from utils.config import get_settings


_PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d)(\d{4})(\d{4})(?!\d)")
_URI_PASSWORD_PATTERN = re.compile(r"(mongodb(?:\+srv)?://[^:/@\s]+:)([^@\s]+)(@)")


class SensitiveFilter(logging.Filter):
    """脱敏手机号与 MongoDB 连接密码。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            message = _PHONE_PATTERN.sub(r"\1****\3", message)
            message = _URI_PASSWORD_PATTERN.sub(r"\1****\3", message)
            record.msg = message
            record.args = ()
        except Exception:
            pass
        return True


_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(name: str = "foodlink") -> logging.Logger:
    if name in _LOGGERS:
        return _LOGGERS[name]

    settings = get_settings()
    settings.ensure_directories()
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.propagate = False

    if not logger.handlers:
        handler = RotatingFileHandler(
            Path(settings.log_dir) / "foodlink.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        handler.addFilter(SensitiveFilter())
        logger.addHandler(handler)

    _LOGGERS[name] = logger
    return logger


def log_exception(exc: BaseException, *, context: str = "", logger: logging.Logger | None = None) -> None:
    log = logger or get_logger()
    log.exception("操作失败 | %s | %s", context, type(exc).__name__)


def log_action(action: str, detail: dict[str, Any] | None = None) -> None:
    logger = get_logger()
    logger.info("操作=%s | 详情=%s", action, detail or {})

