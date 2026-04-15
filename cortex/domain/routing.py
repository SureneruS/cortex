from __future__ import annotations

import os

HUMAN_RECIPIENT = "suren"
LEGACY_HUMAN_RECIPIENT = "human"

RESERVED_NAMES: frozenset[str] = frozenset({HUMAN_RECIPIENT, LEGACY_HUMAN_RECIPIENT})

HUMAN_SENDER_TYPE = HUMAN_RECIPIENT
AGENT_SENDER_TYPE = "agent"
SYSTEM_SENDER_TYPE = "system"

DEPRECATED_HUMAN_WARNING = (
    f"to={LEGACY_HUMAN_RECIPIENT!r} is deprecated — use to={HUMAN_RECIPIENT!r}"
)

UNKNOWN_ACTOR = "unknown"


def canonical_recipient(recipient: str) -> tuple[str, str | None]:
    if recipient == LEGACY_HUMAN_RECIPIENT:
        return HUMAN_RECIPIENT, DEPRECATED_HUMAN_WARNING
    return recipient, None


def is_human_recipient(recipient: str) -> bool:
    return recipient in (HUMAN_RECIPIENT, LEGACY_HUMAN_RECIPIENT)


def resolve_actor() -> str:
    session_name = os.environ.get("CORTEX_SESSION_NAME")
    if session_name:
        return session_name
    actor = os.environ.get("CORTEX_ACTOR")
    if actor:
        return actor
    return UNKNOWN_ACTOR


def sender_type_for(actor: str) -> str:
    return HUMAN_SENDER_TYPE if actor == HUMAN_RECIPIENT else AGENT_SENDER_TYPE
