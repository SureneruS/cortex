from __future__ import annotations

from collections.abc import Callable

from cortex.adapters.vector_store import SqliteVectorStore
from cortex.models import Checkpoint, Decision, Stream, Update
from cortex.repositories.checkpoint_repo import MongoCheckpointRepository
from cortex.repositories.stream_repo import MongoStreamRepository


class StreamService:
    """Coordinates stream operations with vector indexing."""

    def __init__(
        self,
        streams: MongoStreamRepository,
        checkpoints: MongoCheckpointRepository,
        vector_store: SqliteVectorStore,
        on_mutation: Callable[[], None] | None = None,
    ) -> None:
        self._streams = streams
        self._checkpoints = checkpoints
        self._vec = vector_store
        self._on_mutation = on_mutation

    def _notify(self) -> None:
        if self._on_mutation:
            self._on_mutation()

    # ── Stream CRUD (delegated) ──────────────────────────────

    def create_stream(self, title: str, repos: list[str], *, metadata: dict | None = None) -> Stream:
        return self._streams.create(title, repos, metadata=metadata)

    def get_stream(self, stream_id: str) -> Stream | None:
        return self._streams.get(stream_id)

    def get_active_streams(self) -> list[Stream]:
        return self._streams.get_active()

    def list_streams(self, status: str = "active") -> list[Stream]:
        return self._streams.list(status=status)

    def update_stream(self, stream_id: str, **kwargs) -> Stream | None:
        return self._streams.update(stream_id, **kwargs)

    def complete_stream(self, stream_id: str, summary: str) -> None:
        self._streams.complete(stream_id, summary)
        self._notify()

    def delete_stream(self, stream_id: str) -> None:
        # Deindex all child entities before deleting
        for doc in self._streams._updates.find({"stream_id": stream_id}, {"_id": 1}):
            self._vec.deindex(doc["_id"])
        for doc in self._streams._decisions.find({"stream_id": stream_id}, {"_id": 1}):
            self._vec.deindex(doc["_id"])
        self._streams.delete(stream_id)

    # ── Updates (with vec indexing) ──────────────────────────

    def add_update(self, stream_id: str, content: str, summary: str, *, metadata: dict | None = None) -> Update:
        u = self._streams.add_update(stream_id, content, summary, metadata=metadata)
        self._vec.index(u.id, "update", stream_id, f"{summary} {content}")
        self._notify()
        return u

    def edit_update(self, update_id: str, **kwargs) -> Update | None:
        u = self._streams.edit_update(update_id, **kwargs)
        if u:
            self._vec.deindex(update_id)
            self._vec.index(update_id, "update", u.stream_id, f"{u.summary} {u.content}")
        return u

    def delete_update(self, update_id: str) -> None:
        self._vec.deindex(update_id)
        self._streams.delete_update(update_id)

    # ── Decisions (with vec indexing) ─────────────────────────

    def add_decision(self, stream_id: str, what: str, why: str, *, metadata: dict | None = None) -> Decision:
        d = self._streams.add_decision(stream_id, what, why, metadata=metadata)
        self._vec.index(d.id, "decision", stream_id, f"{what} {why}")
        self._notify()
        return d

    def edit_decision(self, decision_id: str, **kwargs) -> Decision | None:
        d = self._streams.edit_decision(decision_id, **kwargs)
        if d:
            self._vec.deindex(decision_id)
            self._vec.index(decision_id, "decision", d.stream_id, f"{d.what} {d.why}")
        return d

    def delete_decision(self, decision_id: str) -> None:
        self._vec.deindex(decision_id)
        self._streams.delete_decision(decision_id)

    # ── Checkpoints (with vec indexing) ──────────────────────

    def save_checkpoint(
        self,
        week_of: str,
        content: str,
        stream_ids: list[str] | None = None,
        metadata: dict | None = None,
    ) -> Checkpoint:
        if stream_ids is None:
            stream_ids = [s.id for s in self.get_active_streams()]
        cp = self._checkpoints.save(week_of, content, stream_ids=stream_ids, metadata=metadata)
        self._vec.deindex(cp.id)
        self._vec.index(cp.id, "checkpoint", "", content)
        return cp

    def get_checkpoint(self, week_of: str | None = None) -> Checkpoint | None:
        return self._checkpoints.get(week_of)

    # ── Delegated methods ────────────────────────────────────

    def get_stream_context(self, stream_id: str) -> dict:
        return self._streams.get_context(stream_id)

    def get_recent_activity(self, limit: int = 50, active_only: bool = False) -> list[dict]:
        return self._streams.get_recent_activity(limit=limit, active_only=active_only)

    def link_session(self, session_id: str, stream_id: str, repo: str = "", branch: str = "") -> None:
        self._streams.link_session(session_id, stream_id, repo=repo, branch=branch)
        self._notify()

    def unlink_session(self, session_id: str, stream_id: str) -> None:
        self._streams.unlink_session(session_id, stream_id)

    def move_session(self, session_id: str, from_stream_id: str, to_stream_id: str) -> None:
        self._streams.move_session(session_id, from_stream_id, to_stream_id)

    def list_sessions(self, limit: int = 50, active_only: bool = False) -> list[dict]:
        return self._streams.list_sessions(limit=limit, active_only=active_only)

    def get_streams_for_session(self, session_id: str) -> list[str]:
        return self._streams.get_streams_for_session(session_id)

    # ── Index management ─────────────────────────────────────

    def clear_indexes(self) -> None:
        self._vec.clear()

    def rebuild_vec_index(self) -> None:
        from cortex.repositories.stream_repo import _doc_to_update, _doc_to_decision
        from cortex.repositories.checkpoint_repo import _doc_to_checkpoint

        entries: list[tuple[str, str, str, str]] = []
        for doc in self._streams._updates.find():
            u = _doc_to_update(doc)
            entries.append((u.id, "update", u.stream_id, f"{u.summary} {u.content}"))
        for doc in self._streams._decisions.find():
            d = _doc_to_decision(doc)
            entries.append((d.id, "decision", d.stream_id, f"{d.what} {d.why}"))
        for doc in self._checkpoints._col.find():
            c = _doc_to_checkpoint(doc)
            entries.append((c.id, "checkpoint", "", c.content))
        self._vec.rebuild(entries)
