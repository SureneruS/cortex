from __future__ import annotations

import functools
import logging
import logging.handlers
import os
import time
import uuid
from pathlib import Path
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

LOG_DIR = Path.home() / ".cortex" / "logs"

_configured = False


def setup_logging(component: str = "cortex") -> None:
    """Configure structlog + stdlib integration with two file handlers + console.

    Args:
        component: Identifies the process (e.g. "cli", "mcp", "daemon").
                   Used in log filenames and as a context field.
    """
    global _configured
    if _configured:
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

    # Debug file — step tracing, 3-day retention
    debug_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_DIR / f"cortex-{component}-debug.log",
        when="midnight",
        backupCount=3,
        encoding="utf-8",
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(json_formatter)

    # Console — stderr only (stdout is reserved for MCP JSON-RPC and CLI JSON output)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.CRITICAL)
    console_handler.setFormatter(console_formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(info_handler)
    root.addHandler(debug_handler)
    root.addHandler(console_handler)
    root.setLevel(min(log_level, logging.DEBUG))

    # Quiet noisy libraries
    for name in ("httpx", "httpcore", "pymongo", "uvicorn", "asyncio"):
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
