from __future__ import annotations

from pymongo.database import Database

from cortex.adapters.tmux import TmuxAdapter
from cortex.repositories.message_repo import MongoMessageRepository
from cortex.repositories.session_repo import MongoSessionRepository
from cortex.services.session_service import SessionService


class Container:
    """Composition root — wires repositories, adapters, and services."""

    def __init__(self, db: Database) -> None:
        self.db = db

        # Adapters
        self.terminal = TmuxAdapter()

        # Repositories
        self.sessions = MongoSessionRepository(db)
        self.messages = MongoMessageRepository(db)

        # Services
        self.session_service = SessionService(
            sessions=self.sessions,
            messages=self.messages,
            terminal=self.terminal,
        )


_container: Container | None = None


def get_container() -> Container:
    global _container
    if _container is None:
        from cortex.mongo import get_db

        _container = Container(get_db())
    return _container


def reset_container() -> None:
    """Reset the singleton — used by tests after patching get_db."""
    global _container
    _container = None
