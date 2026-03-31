from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from pymongo.database import Database

import structlog

from cortex.adapters.vector_store import SIMILARITY_THRESHOLD
from cortex.models import Checkpoint, Decision, Stream, Update
from cortex.observability import trace

log = structlog.get_logger("cortex.mongo_state")


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


class MongoStateManager:
    on_mutation: Callable[[], None] | None = None

    def __init__(self, db: Database, vec_db_path: Path | None = None) -> None:
        self._db = db
        self._streams = db["streams"]
        self._updates = db["updates"]
        self._decisions = db["decisions"]
        self._checkpoints = db["checkpoints"]
        self._sessions = db["stream_sessions"]
        self._blueprints = db["dashboard_blueprints"]
        self._snapshots = db["dashboard_snapshots"]

        self._conn: sqlite3.Connection | None = None
        self._has_vec = False

        if vec_db_path is not None:
            self._init_vec_db(vec_db_path)

        self._ensure_indexes()

    def _init_vec_db(self, vec_db_path: Path) -> None:
        vec_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(vec_db_path), isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        try:
            import sqlite_vec

            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)
            self._has_vec = True
            self._conn.executescript(
                "CREATE VIRTUAL TABLE IF NOT EXISTS vec_index USING vec0("
                "    embedding float[768] distance_metric=cosine,"
                "    entity_id text,"
                "    entity_type text,"
                "    stream_id text"
                ");"
            )
            self._conn.executescript(
                "CREATE TABLE IF NOT EXISTS vec_map ("
                "    entity_id TEXT PRIMARY KEY,"
                "    vec_rowid INTEGER NOT NULL"
                ");"
            )
            self._conn.executescript(
                "CREATE TABLE IF NOT EXISTS vec_pending ("
                "    entity_id TEXT PRIMARY KEY,"
                "    entity_type TEXT NOT NULL,"
                "    stream_id TEXT NOT NULL,"
                "    content TEXT NOT NULL"
                ");"
            )
        except Exception:
            log.warning("sqlite_vec not available — vector search disabled", exc_info=True)
            self._has_vec = False

    def _ensure_indexes(self) -> None:
        self._streams.create_index("status")
        self._updates.create_index("stream_id")
        self._decisions.create_index("stream_id")
        self._checkpoints.create_index("week_of", unique=True)
        self._sessions.create_index([("session_id", 1), ("stream_id", 1)], unique=True)
        self._sessions.create_index("stream_id")
        self._snapshots.create_index([("created_at", -1)])

        # $text indexes — one per collection (may already exist)
        for col, fields, name in [
            (self._updates, [("content", "text"), ("summary", "text")], "updates_text"),
            (self._decisions, [("what", "text"), ("why", "text")], "decisions_text"),
            (self._checkpoints, [("content", "text")], "checkpoints_text"),
        ]:
            try:
                col.create_index(fields, name=name)
            except Exception:
                log.debug("Text index already exists", index=name)

    def _notify(self) -> None:
        if self.on_mutation is not None:
            self.on_mutation()

    # ── Stream CRUD ──────────────────────────────────────────────

    @trace
    def create_stream(self, title: str, repos: list[str], *, metadata: dict | None = None) -> Stream:
        now = _now()
        sid = _new_id()
        doc = {
            "_id": sid,
            "title": title,
            "repos": repos,
            "status": "active",
            "summary": None,
            "metadata": metadata,
            "created_at": now,
            "updated_at": now,
        }
        self._streams.insert_one(doc)
        return _doc_to_stream(doc)

    @trace
    def get_stream(self, stream_id: str) -> Stream | None:
        doc = self._streams.find_one({"_id": stream_id})
        return _doc_to_stream(doc) if doc else None

    def get_active_streams(self) -> list[Stream]:
        return self.list_streams(status="active")

    @trace
    def list_streams(self, status: str = "active") -> list[Stream]:
        filt = {} if status == "all" else {"status": status}
        docs = self._streams.find(filt).sort("updated_at", -1)
        return [_doc_to_stream(d) for d in docs]

    @trace
    def update_stream(
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
        stream = self.get_stream(stream_id)
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
        return self.get_stream(stream_id)

    @trace
    def complete_stream(self, stream_id: str, summary: str) -> None:
        self._streams.update_one(
            {"_id": stream_id},
            {"$set": {"status": "completed", "summary": summary, "updated_at": _now()}},
        )
        self._notify()

    @trace
    def delete_stream(self, stream_id: str) -> None:
        # Deindex all child updates and decisions
        for doc in self._updates.find({"stream_id": stream_id}, {"_id": 1}):
            self._deindex_entity(doc["_id"])
        for doc in self._decisions.find({"stream_id": stream_id}, {"_id": 1}):
            self._deindex_entity(doc["_id"])
        self._updates.delete_many({"stream_id": stream_id})
        self._decisions.delete_many({"stream_id": stream_id})
        self._sessions.delete_many({"stream_id": stream_id})
        self._streams.delete_one({"_id": stream_id})

    def _require_active_stream(self, stream_id: str) -> Stream:
        stream = self.get_stream(stream_id)
        if not stream:
            raise ValueError(f"Stream {stream_id} not found")
        if stream.status != "active":
            raise ValueError(f"Stream {stream_id} is {stream.status} — archived streams are immutable")
        return stream

    # ── Update CRUD ──────────────────────────────────────────────

    @trace
    def add_update(self, stream_id: str, content: str, summary: str, *, metadata: dict | None = None) -> Update:
        self._require_active_stream(stream_id)
        now = _now()
        uid = _new_id()
        doc = {
            "_id": uid,
            "stream_id": stream_id,
            "content": content,
            "summary": summary,
            "metadata": metadata,
            "created_at": now,
        }
        self._updates.insert_one(doc)
        self._streams.update_one({"_id": stream_id}, {"$set": {"updated_at": now}})
        self._index_entity(uid, "update", stream_id, f"{summary} {content}")
        self._notify()
        return _doc_to_update(doc)

    @trace
    def edit_update(
        self,
        update_id: str,
        *,
        content: str | None = None,
        summary: str | None = None,
        metadata: dict | None = None,
    ) -> Update | None:
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
        new_doc = self._updates.find_one({"_id": update_id})
        u = _doc_to_update(new_doc)
        self._deindex_entity(update_id)
        self._index_entity(update_id, "update", u.stream_id, f"{u.summary} {u.content}")
        return u

    @trace
    def delete_update(self, update_id: str) -> None:
        self._deindex_entity(update_id)
        self._updates.delete_one({"_id": update_id})

    # ── Decision CRUD ────────────────────────────────────────────

    @trace
    def add_decision(self, stream_id: str, what: str, why: str, *, metadata: dict | None = None) -> Decision:
        self._require_active_stream(stream_id)
        now = _now()
        did = _new_id()
        doc = {
            "_id": did,
            "stream_id": stream_id,
            "what": what,
            "why": why,
            "metadata": metadata,
            "created_at": now,
        }
        self._decisions.insert_one(doc)
        self._streams.update_one({"_id": stream_id}, {"$set": {"updated_at": now}})
        self._index_entity(did, "decision", stream_id, f"{what} {why}")
        self._notify()
        return _doc_to_decision(doc)

    @trace
    def edit_decision(
        self,
        decision_id: str,
        *,
        what: str | None = None,
        why: str | None = None,
        metadata: dict | None = None,
    ) -> Decision | None:
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
        new_doc = self._decisions.find_one({"_id": decision_id})
        d = _doc_to_decision(new_doc)
        self._deindex_entity(decision_id)
        self._index_entity(decision_id, "decision", d.stream_id, f"{d.what} {d.why}")
        return d

    @trace
    def delete_decision(self, decision_id: str) -> None:
        self._deindex_entity(decision_id)
        self._decisions.delete_one({"_id": decision_id})

    # ── Checkpoint CRUD ──────────────────────────────────────────

    @trace
    def save_checkpoint(
        self,
        week_of: str,
        content: str,
        stream_ids: list[str] | None = None,
        metadata: dict | None = None,
    ) -> Checkpoint:
        if stream_ids is None:
            stream_ids = [s.id for s in self.get_active_streams()]
        now = _now()
        existing = self._checkpoints.find_one({"week_of": week_of})
        if existing:
            self._checkpoints.update_one(
                {"_id": existing["_id"]},
                {"$set": {"content": content, "stream_ids": stream_ids, "metadata": metadata, "updated_at": now}},
            )
            self._deindex_entity(existing["_id"])
            self._index_entity(existing["_id"], "checkpoint", "", content)
        else:
            cid = _new_id()
            doc = {
                "_id": cid,
                "week_of": week_of,
                "content": content,
                "stream_ids": stream_ids,
                "metadata": metadata,
                "created_at": now,
                "updated_at": now,
            }
            self._checkpoints.insert_one(doc)
            self._index_entity(cid, "checkpoint", "", content)
        return self.get_checkpoint(week_of)

    @trace
    def get_checkpoint(self, week_of: str | None = None) -> Checkpoint | None:
        if week_of:
            doc = self._checkpoints.find_one({"week_of": week_of})
        else:
            doc = self._checkpoints.find_one(sort=[("week_of", -1)])
        return _doc_to_checkpoint(doc) if doc else None

    # ── Session Links ────────────────────────────────────────────

    @trace
    def link_session(self, session_id: str, stream_id: str, repo: str = "", branch: str = "") -> None:
        self._require_active_stream(stream_id)
        existing = self._sessions.find_one({"session_id": session_id, "stream_id": stream_id})
        if existing:
            return
        self._sessions.insert_one({
            "_id": _new_id(),
            "session_id": session_id,
            "stream_id": stream_id,
            "repo": repo,
            "branch": branch,
            "status": "active",
            "last_summary": None,
            "created_at": _now(),
        })
        self._notify()

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
            active_ids = [s.id for s in self.get_active_streams()]
            filt = {"stream_id": {"$in": active_ids}}
        else:
            filt = {}
        docs = self._sessions.find(filt).sort("created_at", -1).limit(limit)
        return [
            {
                "session_id": d["session_id"],
                "stream_id": d["stream_id"],
                "repo": d.get("repo", ""),
                "branch": d.get("branch", ""),
                "status": d.get("status", "active"),
                "created_at": d["created_at"],
            }
            for d in docs
        ]

    # ── Search ───────────────────────────────────────────────────

    @trace
    def search(self, query: str) -> list[Update | Decision | Checkpoint]:
        if self._has_vec:
            results = self._semantic_search(query)
            if results:
                return results
        results = self._text_search(query)
        if results:
            return results
        return self._regex_search(query)

    def _flush_pending(self) -> None:
        """Compute embeddings for all pending entries and move them to vec_index."""
        if not self._has_vec or self._conn is None:
            return
        rows = self._conn.execute("SELECT entity_id, entity_type, stream_id, content FROM vec_pending").fetchall()
        if not rows:
            return
        from cortex.embeddings import Embedder, serialize_f32

        entries = [(r[0], r[1], r[2], r[3]) for r in rows]
        texts = [e[3] for e in entries]
        embeddings = Embedder.get().encode_batch(texts)
        for (entity_id, entity_type, stream_id, _), embedding in zip(entries, embeddings):
            self._conn.execute(
                "INSERT INTO vec_index(embedding, entity_id, entity_type, stream_id) VALUES (?, ?, ?, ?)",
                (serialize_f32(embedding), entity_id, entity_type, stream_id),
            )
            vec_rowid = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            self._conn.execute(
                "INSERT OR REPLACE INTO vec_map(entity_id, vec_rowid) VALUES (?, ?)",
                (entity_id, vec_rowid),
            )
        self._conn.execute("DELETE FROM vec_pending")

    def _vec_search(self, query: str, limit: int = 20) -> list[tuple[str, str, float]]:
        if not self._has_vec or self._conn is None:
            return []
        self._flush_pending()
        from cortex.embeddings import Embedder, serialize_f32

        query_embedding = Embedder.get().encode(query)
        rows = self._conn.execute(
            "SELECT entity_id, entity_type, distance FROM vec_index WHERE embedding MATCH ? AND k = ?",
            (serialize_f32(query_embedding), limit),
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    def _semantic_search(self, query: str) -> list[Update | Decision | Checkpoint]:
        vec_results = self._vec_search(query)
        if not vec_results or vec_results[0][2] > SIMILARITY_THRESHOLD:
            return []
        results: list[Update | Decision | Checkpoint] = []
        for entity_id, entity_type, distance in vec_results:
            if distance > SIMILARITY_THRESHOLD:
                break
            entity = self._hydrate_entity(entity_id, entity_type)
            if entity:
                results.append(entity)
        return results

    def _text_search(self, query: str) -> list[Update | Decision | Checkpoint]:
        results: list[Update | Decision | Checkpoint] = []
        for col, converter in [
            (self._updates, _doc_to_update),
            (self._decisions, _doc_to_decision),
            (self._checkpoints, _doc_to_checkpoint),
        ]:
            try:
                cursor = col.find(
                    {"$text": {"$search": query}},
                    {"score": {"$meta": "textScore"}},
                ).sort([("score", {"$meta": "textScore"})]).limit(20)
                for doc in cursor:
                    results.append(converter(doc))
            except Exception:
                log.warning("Text search failed on collection", collection=col.name, exc_info=True)
        return results[:20]

    def _regex_search(self, query: str) -> list[Update | Decision | Checkpoint]:
        tokens = query.lower().split()
        if not tokens:
            return []
        results = self._regex_query(tokens, require_all=True)
        if not results and len(tokens) > 1:
            results = self._regex_query(tokens, require_all=False)
        return results[:20]

    def _regex_query(self, tokens: list[str], *, require_all: bool) -> list[Update | Decision | Checkpoint]:
        op = "$and" if require_all else "$or"

        def _build_filter(fields: list[str]) -> dict:
            clauses = []
            for token in tokens:
                field_matches = [
                    {f: {"$regex": token, "$options": "i"}} for f in fields
                ]
                clauses.append({"$or": field_matches})
            return {op: clauses} if len(clauses) > 1 else clauses[0]

        update_filt = _build_filter(["content", "summary"])
        decision_filt = _build_filter(["what", "why"])
        checkpoint_filt = _build_filter(["content"])

        results: list[Update | Decision | Checkpoint] = []
        for doc in self._updates.find(update_filt).sort("created_at", -1).limit(20):
            results.append(_doc_to_update(doc))
        for doc in self._decisions.find(decision_filt).sort("created_at", -1).limit(20):
            results.append(_doc_to_decision(doc))
        for doc in self._checkpoints.find(checkpoint_filt).sort("created_at", -1).limit(20):
            results.append(_doc_to_checkpoint(doc))

        def _match_count(item: Update | Decision | Checkpoint) -> int:
            if isinstance(item, Update):
                text = f"{item.content} {item.summary}".lower()
            elif isinstance(item, Decision):
                text = f"{item.what} {item.why}".lower()
            else:
                text = item.content.lower()
            return sum(1 for t in tokens if t in text)

        results.sort(key=lambda x: (-_match_count(x), -x.created_at.timestamp()))
        return results

    def _hydrate_entity(self, entity_id: str, entity_type: str) -> Update | Decision | Checkpoint | None:
        if entity_type == "update":
            doc = self._updates.find_one({"_id": entity_id})
            return _doc_to_update(doc) if doc else None
        elif entity_type == "decision":
            doc = self._decisions.find_one({"_id": entity_id})
            return _doc_to_decision(doc) if doc else None
        elif entity_type == "checkpoint":
            doc = self._checkpoints.find_one({"_id": entity_id})
            return _doc_to_checkpoint(doc) if doc else None
        return None

    # ── Context & Activity ───────────────────────────────────────

    @trace
    def get_stream_context(self, stream_id: str) -> dict:
        stream = self.get_stream(stream_id)
        if not stream:
            return {}
        updates = list(self._updates.find({"stream_id": stream_id}).sort("created_at", -1))
        decisions = list(self._decisions.find({"stream_id": stream_id}).sort("created_at", -1))
        sessions = list(self._sessions.find({"stream_id": stream_id}).sort("created_at", -1))
        return {
            "stream": {
                "id": stream.id,
                "title": stream.title,
                "repos": stream.repos,
                "status": stream.status,
                "summary": stream.summary,
                "metadata": stream.metadata,
                "created_at": stream.created_at.isoformat(),
                "updated_at": stream.updated_at.isoformat(),
            },
            "updates": [
                {
                    "id": d["_id"],
                    "content": d["content"],
                    "summary": d["summary"],
                    "created_at": d["created_at"],
                    "metadata": d.get("metadata"),
                }
                for d in updates
            ],
            "decisions": [
                {
                    "id": d["_id"],
                    "what": d["what"],
                    "why": d["why"],
                    "created_at": d["created_at"],
                    "metadata": d.get("metadata"),
                }
                for d in decisions
            ],
            "sessions": [
                {
                    "session_id": d["session_id"],
                    "repo": d.get("repo", ""),
                    "branch": d.get("branch", ""),
                    "status": d.get("status", "active"),
                    "created_at": d["created_at"],
                }
                for d in sessions
            ],
        }

    @trace
    def get_recent_activity(self, limit: int = 50, active_only: bool = False) -> list[dict]:
        if active_only:
            active_ids = [s.id for s in self.get_active_streams()]
            filt = {"stream_id": {"$in": active_ids}}
        else:
            filt = {}

        update_docs = list(self._updates.find(filt).sort("created_at", -1).limit(limit))
        decision_docs = list(self._decisions.find(filt).sort("created_at", -1).limit(limit))

        results = []
        for d in update_docs:
            results.append({
                "type": "update",
                "id": d["_id"],
                "stream_id": d["stream_id"],
                "content": d["content"],
                "summary": d["summary"],
                "created_at": d["created_at"],
                "metadata": d.get("metadata"),
            })
        for d in decision_docs:
            results.append({
                "type": "decision",
                "id": d["_id"],
                "stream_id": d["stream_id"],
                "what": d["what"],
                "why": d["why"],
                "created_at": d["created_at"],
                "metadata": d.get("metadata"),
            })

        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results[:limit]

    # ── Dashboard ────────────────────────────────────────────────

    @trace
    def save_blueprint(self, blueprint: dict) -> dict:
        now = _now()
        row_id = _new_id()
        self._blueprints.delete_many({})
        doc = {
            "_id": row_id,
            "blueprint": blueprint,
            "resolved_data": None,
            "created_at": now,
            "updated_at": now,
        }
        self._blueprints.insert_one(doc)
        snap_id = _new_id()
        self._snapshots.insert_one({
            "_id": snap_id,
            "snapshot_type": "blueprint",
            "data": blueprint,
            "created_at": now,
        })
        return {"id": row_id, "blueprint": blueprint, "resolved_data": None, "created_at": now, "updated_at": now}

    @trace
    def get_blueprint(self) -> dict | None:
        doc = self._blueprints.find_one()
        if not doc:
            return None
        return {
            "id": doc["_id"],
            "blueprint": doc["blueprint"],
            "resolved_data": doc.get("resolved_data"),
            "created_at": doc["created_at"],
            "updated_at": doc["updated_at"],
        }

    @trace
    def update_resolved_data(self, resolved_data: dict) -> None:
        now = _now()
        self._blueprints.update_one({}, {"$set": {"resolved_data": resolved_data, "updated_at": now}})
        snap_id = _new_id()
        self._snapshots.insert_one({
            "_id": snap_id,
            "snapshot_type": "resolved",
            "data": resolved_data,
            "created_at": now,
        })

    @trace
    def get_dashboard_snapshots(self, limit: int = 20) -> list[dict]:
        docs = self._snapshots.find().sort("created_at", -1).limit(limit)
        return [
            {
                "id": d["_id"],
                "snapshot_type": d["snapshot_type"],
                "data": d["data"],
                "created_at": d["created_at"],
            }
            for d in docs
        ]

    # ── Index Management (SQLite vec only) ───────────────────────

    def init_db(self) -> None:
        if self._has_vec and self._conn is not None:
            vec_count = self._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0]
            if vec_count == 0:
                self._rebuild_vec_index()

    def clear_indexes(self) -> None:
        if self._has_vec and self._conn is not None:
            self._conn.execute("DELETE FROM vec_index")
            self._conn.execute("DELETE FROM vec_map")
            self._conn.execute("DELETE FROM vec_pending")

    def _rebuild_search_index(self) -> None:
        pass  # MongoDB $text indexes are automatic

    def _rebuild_vec_index(self) -> None:
        if not self._has_vec or self._conn is None:
            return
        self._conn.execute("DELETE FROM vec_pending")
        from cortex.embeddings import Embedder, serialize_f32

        entries: list[tuple[str, str, str, str]] = []
        for doc in self._updates.find():
            u = _doc_to_update(doc)
            entries.append((u.id, "update", u.stream_id, f"{u.summary} {u.content}"))
        for doc in self._decisions.find():
            d = _doc_to_decision(doc)
            entries.append((d.id, "decision", d.stream_id, f"{d.what} {d.why}"))
        for doc in self._checkpoints.find():
            c = _doc_to_checkpoint(doc)
            entries.append((c.id, "checkpoint", "", c.content))
        if not entries:
            return
        texts = [e[3] for e in entries]
        embeddings = Embedder.get().encode_batch(texts)
        for (entity_id, entity_type, stream_id, _), embedding in zip(entries, embeddings):
            self._conn.execute(
                "INSERT INTO vec_index(embedding, entity_id, entity_type, stream_id) VALUES (?, ?, ?, ?)",
                (serialize_f32(embedding), entity_id, entity_type, stream_id),
            )
            vec_rowid = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            self._conn.execute(
                "INSERT OR REPLACE INTO vec_map(entity_id, vec_rowid) VALUES (?, ?)",
                (entity_id, vec_rowid),
            )

    def _index_entity(self, entity_id: str, entity_type: str, stream_id: str, content: str) -> None:
        """Queue content for lazy embedding — no model loaded until search."""
        if self._has_vec and self._conn is not None:
            self._conn.execute(
                "INSERT OR REPLACE INTO vec_pending(entity_id, entity_type, stream_id, content) VALUES (?, ?, ?, ?)",
                (entity_id, entity_type, stream_id, content),
            )

    def _deindex_entity(self, entity_id: str) -> None:
        if self._has_vec and self._conn is not None:
            self._conn.execute("DELETE FROM vec_pending WHERE entity_id = ?", (entity_id,))
            row = self._conn.execute(
                "SELECT vec_rowid FROM vec_map WHERE entity_id = ?", (entity_id,)
            ).fetchone()
            if row:
                self._conn.execute("DELETE FROM vec_index WHERE rowid = ?", (row[0],))
                self._conn.execute("DELETE FROM vec_map WHERE entity_id = ?", (entity_id,))

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> MongoStateManager:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
