from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Stream:
    id: str
    title: str
    repos: list[str]
    status: str  # "active" | "completed"
    summary: str | None
    created_at: datetime
    updated_at: datetime
    metadata: dict | None = field(default=None)


@dataclass(frozen=True)
class Update:
    id: str
    stream_id: str
    content: str
    summary: str
    created_at: datetime
    metadata: dict | None = field(default=None)


@dataclass(frozen=True)
class Decision:
    id: str
    stream_id: str
    what: str
    why: str
    created_at: datetime
    metadata: dict | None = field(default=None)


@dataclass(frozen=True)
class Checkpoint:
    id: str
    week_of: str
    content: str
    stream_ids: list[str]
    created_at: datetime
    updated_at: datetime
    metadata: dict | None = field(default=None)


@dataclass(frozen=True)
class Session:
    id: str
    session_id: str
    stream_id: str
    repo: str
    branch: str
    status: str  # "active" | "ended"
    last_summary: str | None
    created_at: datetime
