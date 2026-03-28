from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# ── Session Domain ───────────────────────────────────────────


class SessionStatus(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    PAUSED = "paused"
    BLOCKED = "blocked"
    WATCHING = "watching"
    HIDDEN = "hidden"
    COMPLETED = "completed"
    DEAD = "dead"


class RuntimeStatus(str, Enum):
    WORKING = "working"
    WAITING_INPUT = "waiting_input"
    WAITING_PERMISSION = "waiting_permission"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SessionEvent:
    field: str
    from_val: str | None
    to_val: str
    trigger: str
    at: str
    reason: str | None = None


@dataclass(frozen=True)
class Session:
    id: str
    name: str
    status: SessionStatus
    runtime: RuntimeStatus
    role: str
    workspace: str
    spawned_by: str
    created_at: str
    pane_id: str | None = None
    goal: str | None = None
    model: str | None = None
    color: str | None = None
    repos: list[str] = field(default_factory=list)
    cc_session_id: str | None = None
    cc_sessions: list[dict] = field(default_factory=list)
    events: list[SessionEvent] = field(default_factory=list)


# ── Stream Domain ────────────────────────────────────────────


@dataclass(frozen=True)
class Stream:
    id: str
    title: str
    repos: list[str]
    status: str
    summary: str | None
    created_at: datetime
    updated_at: datetime
    metadata: dict | None = None


@dataclass(frozen=True)
class Update:
    id: str
    stream_id: str
    content: str
    summary: str
    created_at: datetime
    metadata: dict | None = None


@dataclass(frozen=True)
class Decision:
    id: str
    stream_id: str
    what: str
    why: str
    created_at: datetime
    metadata: dict | None = None


@dataclass(frozen=True)
class Checkpoint:
    id: str
    week_of: str
    content: str
    stream_ids: list[str]
    created_at: datetime
    updated_at: datetime
    metadata: dict | None = None


# ── Message Domain ───────────────────────────────────────────


@dataclass(frozen=True)
class Message:
    id: str
    sender: str
    recipient: str
    content: str
    status: str
    created_at: str
    meta: dict = field(default_factory=dict)
    delivered_at: str | None = None
