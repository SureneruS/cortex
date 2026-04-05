from __future__ import annotations

from pymongo.database import Database

import structlog

from cortex.domain.utils import _new_id, _now, _slugify
from cortex.domain.converters import doc_to_decision, doc_to_stream, doc_to_update
from cortex.domain.models import Decision, Stream, Update
from cortex.observability import trace

log = structlog.get_logger("cortex.stream_repo")


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
        self._streams.create_index("name", unique=True, sparse=True)
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

        self._backfill_names()

    def _generate_unique_name(self, title: str) -> str:
        base = _slugify(title)
        if not base:
            base = "stream"
        candidate = base
        suffix = 2
        while self._streams.find_one({"name": candidate}):
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def _backfill_names(self) -> None:
        for doc in self._streams.find({"$or": [{"name": None}, {"name": {"$exists": False}}]}):
            name = self._generate_unique_name(doc["title"])
            self._streams.update_one({"_id": doc["_id"]}, {"$set": {"name": name}})
            log.info("Backfilled stream name", stream_id=doc["_id"], name=name)

    # ── Resolution ──────────────────────────────────────────

    @trace
    def resolve(self, ref: str) -> Stream | None:
        doc = self._streams.find_one({"_id": ref})
        if doc:
            return doc_to_stream(doc)

        doc = self._streams.find_one({"name": ref})
        if doc:
            return doc_to_stream(doc)

        by_prefix = list(self._streams.find({"_id": {"$regex": f"^{ref}"}}).limit(5))
        if len(by_prefix) == 1:
            return doc_to_stream(by_prefix[0])
        if len(by_prefix) > 1:
            options = ", ".join(f"{d['_id']} ({d.get('name', '?')})" for d in by_prefix)
            raise ValueError(f"Ambiguous prefix '{ref}' matches {len(by_prefix)} streams: {options}")

        return None

    # ── Stream CRUD ──────────────────────────────────────────

    @trace
    def create(self, title: str, repos: list[str], *, metadata: dict | None = None) -> Stream:
        now = _now()
        sid = _new_id()
        name = self._generate_unique_name(title)
        doc = {
            "_id": sid, "title": title, "name": name, "repos": repos, "status": "active",
            "summary": None, "metadata": metadata, "created_at": now, "updated_at": now,
        }
        self._streams.insert_one(doc)
        return doc_to_stream(doc)

    @trace
    def get(self, stream_id: str) -> Stream | None:
        doc = self._streams.find_one({"_id": stream_id})
        return doc_to_stream(doc) if doc else None

    def get_active(self) -> list[Stream]:
        return self.list(status="active")

    @trace
    def list(self, status: str = "active") -> list[Stream]:
        filt = {} if status == "all" else {"status": status}
        docs = self._streams.find(filt).sort("updated_at", -1)
        return [doc_to_stream(d) for d in docs]

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
            raise ValueError(f"Stream '{stream.name}' is {stream.status} — archived streams are immutable")
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
        return doc_to_update(doc)

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
            return doc_to_update(doc)
        self._updates.update_one({"_id": update_id}, {"$set": updates})
        return doc_to_update(self._updates.find_one({"_id": update_id}))

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
        return doc_to_decision(doc)

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
            return doc_to_decision(doc)
        self._decisions.update_one({"_id": decision_id}, {"$set": updates})
        return doc_to_decision(self._decisions.find_one({"_id": decision_id}))

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
                "id": stream.id, "name": stream.name, "title": stream.title, "repos": stream.repos,
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

    # ── Entity access (used by services) ──────────────────────

    def get_child_ids(self, stream_id: str) -> tuple[list[str], list[str]]:
        """Return (update_ids, decision_ids) for a stream."""
        update_ids = [d["_id"] for d in self._updates.find({"stream_id": stream_id}, {"_id": 1})]
        decision_ids = [d["_id"] for d in self._decisions.find({"stream_id": stream_id}, {"_id": 1})]
        return update_ids, decision_ids

    def get_update_by_id(self, update_id: str) -> Update | None:
        doc = self._updates.find_one({"_id": update_id})
        return doc_to_update(doc) if doc else None

    def get_decision_by_id(self, decision_id: str) -> Decision | None:
        doc = self._decisions.find_one({"_id": decision_id})
        return doc_to_decision(doc) if doc else None

    def iter_all_updates(self) -> list[Update]:
        return [doc_to_update(doc) for doc in self._updates.find()]

    def iter_all_decisions(self) -> list[Decision]:
        return [doc_to_decision(doc) for doc in self._decisions.find()]

    # ── Text search (used by SearchService) ──────────────────

    def text_search(self, query: str, limit: int = 20) -> list[Update | Decision]:
        results: list[Update | Decision] = []
        for col, converter in [
            (self._updates, doc_to_update),
            (self._decisions, doc_to_decision),
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
            results.append(doc_to_update(doc))
        for doc in self._decisions.find(_build_filter(["what", "why"])).sort("created_at", -1).limit(20):
            results.append(doc_to_decision(doc))

        def _match_count(item: Update | Decision) -> int:
            if isinstance(item, Update):
                text = f"{item.content} {item.summary}".lower()
            else:
                text = f"{item.what} {item.why}".lower()
            return sum(1 for t in tokens if t in text)

        results.sort(key=lambda x: (-_match_count(x), -x.created_at.timestamp()))
        return results
