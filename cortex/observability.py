from __future__ import annotations

import functools
import logging
import logging.handlers
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

LOG_DIR = Path.home() / ".cortex" / "logs"

_configured = False

ERRORS_TTL_DAYS = 7


class MongoErrorHandler(logging.Handler):
    """Logging handler that writes WARNING+ events to MongoDB `errors` collection."""

    def __init__(self, component: str, level: int = logging.WARNING) -> None:
        super().__init__(level)
        self._component = component
        self._col = None

    def _get_collection(self):
        if self._col is None:
            from cortex.mongo import get_db
            db = get_db()
            self._col = db["errors"]
            self._col.create_index("timestamp", expireAfterSeconds=ERRORS_TTL_DAYS * 86400)
        return self._col

    def emit(self, record: logging.LogRecord) -> None:
        try:
            col = self._get_collection()

            details = {}
            if hasattr(record, "msg") and isinstance(record.msg, str):
                details["message"] = record.getMessage()

            if record.exc_info and record.exc_info[1]:
                details["exception"] = str(record.exc_info[1])
                details["exception_type"] = type(record.exc_info[1]).__name__

            for key in ("correlation_id", "func", "duration_ms"):
                val = getattr(record, key, None)
                if val is not None:
                    details[key] = val

            col.insert_one({
                "component": self._component,
                "logger": record.name,
                "level": record.levelname,
                "event": getattr(record, "msg", ""),
                "details": details,
                "timestamp": datetime.now(timezone.utc),
            })
        except Exception:
            pass


def setup_logging(component: str = "cortex", *, force: bool = False) -> None:
    """Configure structlog + stdlib integration with two file handlers + console.

    Args:
        component: Identifies the process (e.g. "cli", "mcp", "daemon").
                   Used in log filenames and as a context field.
        force: Reconfigure even if already set up (e.g. daemon subprocess
               that was pre-configured as "cli" by the Click entry point).
    """
    global _configured
    if _configured and not force:
        return
    _configured = True

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_level_str = os.environ.get("CORTEX_LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_processors: list[Any] = [
        merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.stdlib.ExtraAdder(),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    json_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=shared_processors,
    )

    console_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        foreign_pre_chain=shared_processors,
    )

    # Info file — business events, 14-day retention
    info_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_DIR / f"cortex-{component}.log",
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(json_formatter)

    # Debug file — step tracing, 50MB cap with 3 backups (~200MB max)
    debug_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / f"cortex-{component}-debug.log",
        maxBytes=50 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(json_formatter)

    # Console — stderr only (stdout is reserved for MCP JSON-RPC and CLI JSON output)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.CRITICAL)
    console_handler.setFormatter(console_formatter)

    # MongoDB — error sink for dashboard visibility
    mongo_handler = MongoErrorHandler(component)
    mongo_handler.setLevel(logging.WARNING)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(info_handler)
    root.addHandler(debug_handler)
    root.addHandler(console_handler)
    root.addHandler(mongo_handler)
    root.setLevel(min(log_level, logging.DEBUG))

    # Quiet noisy libraries
    for name in ("httpx", "httpcore", "pymongo", "uvicorn", "asyncio", "markdown_it"):
        logging.getLogger(name).setLevel(logging.WARNING)


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:8]


def bind_correlation(correlation_id: str | None = None, **extra: Any) -> str:
    """Clear contextvars and bind a fresh correlation ID + any extra fields."""
    clear_contextvars()
    cid = correlation_id or new_correlation_id()
    bind_contextvars(correlation_id=cid, **extra)
    return cid


def _truncate(value: Any, max_len: int = 200) -> str:
    s = repr(value)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


def trace(fn=None, *, log_args: bool = True, log_result: bool = True):
    """Decorator that auto-logs ENTER/EXIT/ERROR for a function.

    Works with both sync and async functions.
    Logs at DEBUG level for ENTER/EXIT, ERROR level for exceptions.
    """
    if fn is None:
        return functools.partial(trace, log_args=log_args, log_result=log_result)

    logger = structlog.get_logger(fn.__module__)
    name = fn.__qualname__

    if _is_async(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            if log_args:
                logger.debug(
                    "ENTER", func=name, args=_truncate(args), kwargs=_truncate(kwargs)
                )
            else:
                logger.debug("ENTER", func=name)
            t0 = time.monotonic()
            try:
                result = await fn(*args, **kwargs)
            except Exception:
                logger.error("ERROR", func=name, duration_ms=_elapsed_ms(t0), exc_info=True)
                raise
            duration = _elapsed_ms(t0)
            if log_result:
                logger.debug("EXIT", func=name, result=_truncate(result), duration_ms=duration)
            else:
                logger.debug("EXIT", func=name, duration_ms=duration)
            return result

        return async_wrapper
    else:

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            if log_args:
                logger.debug(
                    "ENTER", func=name, args=_truncate(args), kwargs=_truncate(kwargs)
                )
            else:
                logger.debug("ENTER", func=name)
            t0 = time.monotonic()
            try:
                result = fn(*args, **kwargs)
            except Exception:
                logger.error("ERROR", func=name, duration_ms=_elapsed_ms(t0), exc_info=True)
                raise
            duration = _elapsed_ms(t0)
            if log_result:
                logger.debug("EXIT", func=name, result=_truncate(result), duration_ms=duration)
            else:
                logger.debug("EXIT", func=name, duration_ms=duration)
            return result

        return sync_wrapper


def _is_async(fn: Any) -> bool:
    import asyncio

    return asyncio.iscoroutinefunction(fn)


def _elapsed_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)
