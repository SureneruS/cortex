from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pymongo.database import Database

import structlog

from cortex.models import Checkpoint, Decision, Stream, Update
from cortex.observability import trace

log = structlog.get_logger("cortex.stream_repo")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _doc_to_stream(doc: dict) -> Stream:
    return Stream(
        id=doc["_id"],
        title=doc["title"],
        repos=doc.get("repos", []),
        status=doc["status"],
        summary=doc.get("summary"),
        created_at=datetime.fromisoformat(doc["created_at"]),
        updated_at=datetime.fromisoformat(doc["updated_at"]),
        metadata=doc.get("metadata"),
    )


def _doc_to_update(doc: dict) -> Update:
    return Update(
        id=doc["_id"],
        stream_id=doc["stream_id"],
        content=doc["content"],
        summary=doc["summary"],
        created_at=datetime.fromisoformat(doc["created_at"]),
        metadata=doc.get("metadata"),
    )


def _doc_to_decision(doc: dict) -> Decision:
    return Decision(
        id=doc["_id"],
        stream_id=doc["stream_id"],
        what=doc["what"],
        why=doc["why"],
        created_at=datetime.fromisoformat(doc["created_at"]),
        metadata=doc.get("metadata"),
    )


def _doc_to_checkpoint(doc: dict) -> Checkpoint:
    return Checkpoint(
        id=doc["_id"],
        week_of=doc["week_of"],
        content=doc["content"],
        stream_ids=doc.get("stream_ids", []),
        created_at=datetime.fromisoformat(doc["created_at"]),
        updated_at=datetime.fromisoformat(doc["updated_at"]),
        metadata=doc.get("metadata"),
    )


class MongoStreamRepository:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._streams = db["streams"]
        self._updates = db["updates"]
        self._decisions = db["decisions"]
        self._sessions = db["stream_sessions"]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self._streams.create_index("status")
        self._updates.create_index("stream_id")
        self._decisions.create_index("stream_id")
        self._sessions.create_index([("session_id", 1), ("stream_id", 1)], unique=True)
        self._sessions.create_index("stream_id")

        for col, fields, name in [
            (self._updates, [("content", "text"), ("summary", "text")], "updates_text"),
            (self._decisions, [("what", "text"), ("why", "text")], "decisions_text"),
        ]:
            try:
                col.create_index(fields, name=name)
            except Exception:
                log.debug("Text index already exists", index=name)

    # ── Stream CRUD ──────────────────────────────────────────

    @trace
    def create(self, title: str, repos: list[str], *, metadata: dict | None = None) -> Stream:
        now = _now()
        sid = _new_id()
        doc = {
            "_id": sid, "title": title, "repos": repos, "status": "active",
            "summary": None, "metadata": metadata, "created_at": now, "updated_at": now,
        }
        self._streams.insert_one(doc)
        return _doc_to_stream(doc)

    @trace
    def get(self, stream_id: str) -> Stream | None:
        doc = self._streams.find_one({"_id": stream_id})
        return _doc_to_stream(doc) if doc else None

    def get_active(self) -> list[Stream]:
        return self.list(status="active")

    @trace
    def list(self, status: str = "active") -> list[Stream]:
        filt = {} if status == "all" else {"status": status}
        docs = self._streams.find(filt).sort("updated_at", -1)
        return [_doc_to_stream(d) for d in docs]

    @trace
    def update(
        self,
        stream_id: str,
        *,
        title: str | None = None,
        status: str | None = None,
        repos: list[str] | None = None,
        summary: str | None = None,
        metadata: dict | None = None,
        merge_metadata: bool = True,
    ) -> Stream | None:
        stream = self.get(stream_id)
        if not stream:
            return None
        if stream.status != "active" and status != "active":
            raise ValueError(
                f"Stream {stream_id} is {stream.status} — archived streams are immutable "
                "(set status='active' to unarchive first)"
            )
        updates: dict = {}
        if title is not None:
            updates["title"] = title
        if status is not None:
            updates["status"] = status
        if repos is not None:
            updates["repos"] = repos
        if summary is not None:
            updates["summary"] = summary
        if metadata is not None:
            if merge_metadata and stream.metadata:
                merged = {**stream.metadata, **metadata}
                merged = {k: v for k, v in merged.items() if v is not None}
            else:
                merged = metadata
            updates["metadata"] = merged
        if not updates:
            return stream
        updates["updated_at"] = _now()
        self._streams.update_one({"_id": stream_id}, {"$set": updates})
        return self.get(stream_id)

    @trace
    def complete(self, stream_id: str, summary: str) -> None:
        self._streams.update_one(
            {"_id": stream_id},
            {"$set": {"status": "completed", "summary": summary, "updated_at": _now()}},
        )

    @trace
    def delete(self, stream_id: str) -> None:
        self._updates.delete_many({"stream_id": stream_id})
        self._decisions.delete_many({"stream_id": stream_id})
        self._sessions.delete_many({"stream_id": stream_id})
        self._streams.delete_one({"_id": stream_id})

    def require_active(self, stream_id: str) -> Stream:
        stream = self.get(stream_id)
        if not stream:
            raise ValueError(f"Stream {stream_id} not found")
        if stream.status != "active":
            raise ValueError(f"Stream {stream_id} is {stream.status} — archived streams are immutable")
        return stream

    # ── Update CRUD ──────────────────────────────────────────

    @trace
    def add_update(self, stream_id: str, content: str, summary: str, *, metadata: dict | None = None) -> Update:
        self.require_active(stream_id)
        now = _now()
        uid = _new_id()
        doc = {
            "_id": uid, "stream_id": stream_id, "content": content,
            "summary": summary, "metadata": metadata, "created_at": now,
        }
        self._updates.insert_one(doc)
        self._streams.update_one({"_id": stream_id}, {"$set": {"updated_at": now}})
        return _doc_to_update(doc)

    @trace
    def edit_update(self, update_id: str, *, content: str | None = None, summary: str | None = None, metadata: dict | None = None) -> Update | None:
        doc = self._updates.find_one({"_id": update_id})
        if not doc:
            return None
        updates: dict = {}
        if content is not None:
            updates["content"] = content
        if summary is not None:
            updates["summary"] = summary
        if metadata is not None:
            updates["metadata"] = metadata
        if not updates:
            return _doc_to_update(doc)
        self._updates.update_one({"_id": update_id}, {"$set": updates})
        return _doc_to_update(self._updates.find_one({"_id": update_id}))

    @trace
    def delete_update(self, update_id: str) -> None:
        self._updates.delete_one({"_id": update_id})

    # ── Decision CRUD ────────────────────────────────────────

    @trace
    def add_decision(self, stream_id: str, what: str, why: str, *, metadata: dict | None = None) -> Decision:
        self.require_active(stream_id)
        now = _now()
        did = _new_id()
        doc = {
            "_id": did, "stream_id": stream_id, "what": what,
            "why": why, "metadata": metadata, "created_at": now,
        }
        self._decisions.insert_one(doc)
        self._streams.update_one({"_id": stream_id}, {"$set": {"updated_at": now}})
        return _doc_to_decision(doc)

    @trace
    def edit_decision(self, decision_id: str, *, what: str | None = None, why: str | None = None, metadata: dict | None = None) -> Decision | None:
        doc = self._decisions.find_one({"_id": decision_id})
        if not doc:
            return None
        updates: dict = {}
        if what is not None:
            updates["what"] = what
        if why is not None:
            updates["why"] = why
        if metadata is not None:
            updates["metadata"] = metadata
        if not updates:
            return _doc_to_decision(doc)
        self._decisions.update_one({"_id": decision_id}, {"$set": updates})
        return _doc_to_decision(self._decisions.find_one({"_id": decision_id}))

    @trace
    def delete_decision(self, decision_id: str) -> None:
        self._decisions.delete_one({"_id": decision_id})

    # ── Session Links ────────────────────────────────────────

    @trace
    def link_session(self, session_id: str, stream_id: str, repo: str = "", branch: str = "") -> None:
        self.require_active(stream_id)
        existing = self._sessions.find_one({"session_id": session_id, "stream_id": stream_id})
        if existing:
            return
        self._sessions.insert_one({
            "_id": _new_id(), "session_id": session_id, "stream_id": stream_id,
            "repo": repo, "branch": branch, "status": "active",
            "last_summary": None, "created_at": _now(),
        })

    @trace
    def unlink_session(self, session_id: str, stream_id: str) -> None:
        self._sessions.delete_one({"session_id": session_id, "stream_id": stream_id})

    @trace
    def move_session(self, session_id: str, from_stream_id: str, to_stream_id: str) -> None:
        self._sessions.update_one(
            {"session_id": session_id, "stream_id": from_stream_id},
            {"$set": {"stream_id": to_stream_id}},
        )

    @trace
    def get_streams_for_session(self, session_id: str) -> list[str]:
        return self._sessions.distinct("stream_id", {"session_id": session_id})

    @trace
    def list_sessions(self, limit: int = 50, active_only: bool = False) -> list[dict]:
        if active_only:
            active_ids = [s.id for s in self.get_active()]
            filt = {"stream_id": {"$in": active_ids}}
        else:
            filt = {}
        docs = self._sessions.find(filt).sort("created_at", -1).limit(limit)
        return [
            {
                "session_id": d["session_id"], "stream_id": d["stream_id"],
                "repo": d.get("repo", ""), "branch": d.get("branch", ""),
                "status": d.get("status", "active"), "created_at": d["created_at"],
            }
            for d in docs
        ]

    # ── Context & Activity ───────────────────────────────────

    @trace
    def get_context(self, stream_id: str) -> dict:
        stream = self.get(stream_id)
        if not stream:
            return {}
        updates = list(self._updates.find({"stream_id": stream_id}).sort("created_at", -1))
        decisions = list(self._decisions.find({"stream_id": stream_id}).sort("created_at", -1))
        sessions = list(self._sessions.find({"stream_id": stream_id}).sort("created_at", -1))
        return {
            "stream": {
                "id": stream.id, "title": stream.title, "repos": stream.repos,
                "status": stream.status, "summary": stream.summary, "metadata": stream.metadata,
                "created_at": stream.created_at.isoformat(), "updated_at": stream.updated_at.isoformat(),
            },
            "updates": [
                {"id": d["_id"], "content": d["content"], "summary": d["summary"],
                 "created_at": d["created_at"], "metadata": d.get("metadata")}
                for d in updates
            ],
            "decisions": [
                {"id": d["_id"], "what": d["what"], "why": d["why"],
                 "created_at": d["created_at"], "metadata": d.get("metadata")}
                for d in decisions
            ],
            "sessions": [
                {"session_id": d["session_id"], "repo": d.get("repo", ""),
                 "branch": d.get("branch", ""), "status": d.get("status", "active"),
                 "created_at": d["created_at"]}
                for d in sessions
            ],
        }

    @trace
    def get_recent_activity(self, limit: int = 50, active_only: bool = False) -> list[dict]:
        if active_only:
            active_ids = [s.id for s in self.get_active()]
            filt = {"stream_id": {"$in": active_ids}}
        else:
            filt = {}
        update_docs = list(self._updates.find(filt).sort("created_at", -1).limit(limit))
        decision_docs = list(self._decisions.find(filt).sort("created_at", -1).limit(limit))
        results = []
        for d in update_docs:
            results.append({
                "type": "update", "id": d["_id"], "stream_id": d["stream_id"],
                "content": d["content"], "summary": d["summary"],
                "created_at": d["created_at"], "metadata": d.get("metadata"),
            })
        for d in decision_docs:
            results.append({
                "type": "decision", "id": d["_id"], "stream_id": d["stream_id"],
                "what": d["what"], "why": d["why"],
                "created_at": d["created_at"], "metadata": d.get("metadata"),
            })
        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results[:limit]

    # ── Text search (used by SearchService) ──────────────────

    def text_search(self, query: str, limit: int = 20) -> list[Update | Decision]:
        results: list[Update | Decision] = []
        for col, converter in [
            (self._updates, _doc_to_update),
            (self._decisions, _doc_to_decision),
        ]:
            try:
                cursor = col.find(
                    {"$text": {"$search": query}},
                    {"score": {"$meta": "textScore"}},
                ).sort([("score", {"$meta": "textScore"})]).limit(limit)
                for doc in cursor:
                    results.append(converter(doc))
            except Exception:
                log.warning("Text search failed", collection=col.name, exc_info=True)
        return results[:limit]

    def regex_search(self, query: str, limit: int = 20) -> list[Update | Decision]:
        tokens = query.lower().split()
        if not tokens:
            return []
        results = self._regex_query(tokens, require_all=True)
        if not results and len(tokens) > 1:
            results = self._regex_query(tokens, require_all=False)
        return results[:limit]

    def _regex_query(self, tokens: list[str], *, require_all: bool) -> list[Update | Decision]:
        op = "$and" if require_all else "$or"

        def _build_filter(fields: list[str]) -> dict:
            clauses = []
            for token in tokens:
                field_matches = [{f: {"$regex": token, "$options": "i"}} for f in fields]
                clauses.append({"$or": field_matches})
            return {op: clauses} if len(clauses) > 1 else clauses[0]

        results: list[Update | Decision] = []
        for doc in self._updates.find(_build_filter(["content", "summary"])).sort("created_at", -1).limit(20):
            results.append(_doc_to_update(doc))
        for doc in self._decisions.find(_build_filter(["what", "why"])).sort("created_at", -1).limit(20):
            results.append(_doc_to_decision(doc))

        def _match_count(item: Update | Decision) -> int:
            if isinstance(item, Update):
                text = f"{item.content} {item.summary}".lower()
            else:
                text = f"{item.what} {item.why}".lower()
            return sum(1 for t in tokens if t in text)

        results.sort(key=lambda x: (-_match_count(x), -x.created_at.timestamp()))
        return results
