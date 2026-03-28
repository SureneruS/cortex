from __future__ import annotations

from pathlib import Path

from pymongo.database import Database

from cortex.adapters.tmux import TmuxAdapter
from cortex.adapters.vector_store import SqliteVectorStore
from cortex.repositories.checkpoint_repo import MongoCheckpointRepository
from cortex.repositories.dashboard_repo import MongoDashboardRepository
from cortex.repositories.message_repo import MongoMessageRepository
from cortex.repositories.session_repo import MongoSessionRepository
from cortex.repositories.stream_repo import MongoStreamRepository
from cortex.services.search_service import SearchService
from cortex.services.session_service import SessionService
from cortex.services.stream_service import StreamService


class Container:
    """Composition root — wires repositories, adapters, and services."""

    def __init__(self, db: Database, vec_db_path: Path | None = None) -> None:
        self.db = db

        # Adapters
        self.terminal = TmuxAdapter()
        self.vector_store = SqliteVectorStore(vec_db_path)

        # Repositories
        self.sessions = MongoSessionRepository(db)
        self.messages = MongoMessageRepository(db)
        self.streams = MongoStreamRepository(db)
        self.checkpoints = MongoCheckpointRepository(db)
        self.dashboards = MongoDashboardRepository(db)

        # Services
        self.session_service = SessionService(
            sessions=self.sessions,
            messages=self.messages,
            terminal=self.terminal,
        )
        self.stream_service = StreamService(
            streams=self.streams,
            checkpoints=self.checkpoints,
            vector_store=self.vector_store,
        )
        self.search_service = SearchService(
            streams=self.streams,
            checkpoints=self.checkpoints,
            vector_store=self.vector_store,
        )


_container: Container | None = None


def get_container() -> Container:
    global _container
    if _container is None:
        from cortex.config import load_config
        from cortex.mongo import get_db

        config = load_config()
        _container = Container(get_db(), config.resolved_vec_db_path)
    return _container


def reset_container() -> None:
    """Reset the singleton — used by tests after patching get_db."""
    global _container
    _container = None
