from __future__ import annotations

from cortex.domain.models import SessionStatus


class InvalidTransition(ValueError):
    def __init__(self, current: SessionStatus, target: SessionStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Invalid session transition: {current.value} → {target.value}. "
            f"Allowed: {', '.join(s.value for s in TRANSITIONS.get(current, set()))}"
        )


TERMINAL = {SessionStatus.COMPLETED, SessionStatus.CLOSED, SessionStatus.DEAD}

TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.ACTIVE: {
        SessionStatus.IDLE,
        SessionStatus.PAUSED,
        SessionStatus.BLOCKED,
        SessionStatus.COMPLETED,
        SessionStatus.CLOSED,
        SessionStatus.DEAD,
    },
    SessionStatus.IDLE: {
        SessionStatus.ACTIVE,
        SessionStatus.PAUSED,
        SessionStatus.COMPLETED,
        SessionStatus.CLOSED,
        SessionStatus.DEAD,
    },
    SessionStatus.PAUSED: {
        SessionStatus.ACTIVE,
        SessionStatus.COMPLETED,
        SessionStatus.ARCHIVED,
        SessionStatus.CLOSED,
        SessionStatus.DEAD,
    },
    SessionStatus.BLOCKED: {
        SessionStatus.ACTIVE,
        SessionStatus.PAUSED,
        SessionStatus.COMPLETED,
        SessionStatus.ARCHIVED,
        SessionStatus.CLOSED,
        SessionStatus.DEAD,
    },
    SessionStatus.COMPLETED: set(),
    SessionStatus.ARCHIVED: {
        SessionStatus.ACTIVE,
        SessionStatus.COMPLETED,
        SessionStatus.CLOSED,
        SessionStatus.DEAD,
    },
    SessionStatus.CLOSED: set(),
    SessionStatus.DEAD: set(),
}


def validate_transition(current: SessionStatus, target: SessionStatus) -> None:
    allowed = TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidTransition(current, target)


def is_terminal(status: SessionStatus) -> bool:
    return status in TERMINAL


def is_alive(status: SessionStatus) -> bool:
    return status not in TERMINAL
