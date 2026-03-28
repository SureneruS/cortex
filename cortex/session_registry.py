"""Backward-compatible re-export. Use cortex.repositories.session_repo directly."""
from cortex.repositories.session_repo import (  # noqa: F401
    MongoSessionRepository as MongoSessionRepo,
    VALID_RUNTIME,
    VALID_STATUS,
    _make_event,
    _new_id,
    _now,
)

# Re-export MongoSessionRepository under its old name
MongoSessionRepo = MongoSessionRepo

__all__ = [
    "MongoSessionRepo",
    "VALID_STATUS",
    "VALID_RUNTIME",
    "_now",
    "_new_id",
    "_make_event",
]
