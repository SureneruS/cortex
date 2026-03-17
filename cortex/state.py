from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from cortex.models import Checkpoint, Decision, Stream, Update

SQL_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS streams (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    repos TEXT NOT NULL,  -- JSON array
    status TEXT NOT NULL DEFAULT 'active',
    summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS updates (
    id TEXT PRIMARY KEY,
    stream_id TEXT NOT NULL REFERENCES streams(id),
    content TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    stream_id TEXT NOT NULL REFERENCES streams(id),
    what TEXT NOT NULL,
    why TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY,
    week_of TEXT NOT NULL UNIQUE,
    content TEXT NOT NULL,
    stream_ids TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    stream_id TEXT NOT NULL REFERENCES streams(id),
    repo TEXT NOT NULL,
    branch TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    last_summary TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dashboard_blueprints (
    id TEXT PRIMARY KEY,
    blueprint TEXT NOT NULL,
    resolved_data TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dashboard_snapshots (
    id TEXT PRIMARY KEY,
    snapshot_type TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

SQL_MIGRATE_METADATA = [
    "ALTER TABLE streams ADD COLUMN metadata TEXT",
    "ALTER TABLE updates ADD COLUMN metadata TEXT",
    "ALTER TABLE decisions ADD COLUMN metadata TEXT",
]

SQL_CREATE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
    entity_id,
    entity_type,
    stream_id,
    content,
    tokenize="unicode61 tokenchars '-_'"
);
"""

SQL_CREATE_VEC = """
CREATE VIRTUAL TABLE IF NOT EXISTS vec_index USING vec0(
    embedding float[768] distance_metric=cosine,
    entity_id text,
    entity_type text,
    stream_id text
);
"""

SQL_CREATE_VEC_MAP = """
CREATE TABLE IF NOT EXISTS vec_map (
    entity_id TEXT PRIMARY KEY,
    vec_rowid INTEGER NOT NULL
);
"""

SIMILARITY_THRESHOLD = 0.7


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _parse_metadata(raw: str | None) -> dict | None:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _row_to_stream(row: sqlite3.Row) -> Stream:
    return Stream(
        id=row["id"],
        title=row["title"],
        repos=json.loads(row["repos"]),
        status=row["status"],
        summary=row["summary"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        metadata=_parse_metadata(row["metadata"]) if "metadata" in row.keys() else None,
    )


def _row_to_update(row: sqlite3.Row) -> Update:
    return Update(
        id=row["id"],
        stream_id=row["stream_id"],
        content=row["content"],
        summary=row["summary"],
        created_at=datetime.fromisoformat(row["created_at"]),
        metadata=_parse_metadata(row["metadata"]) if "metadata" in row.keys() else None,
    )


def _row_to_decision(row: sqlite3.Row) -> Decision:
    return Decision(
        id=row["id"],
        stream_id=row["stream_id"],
        what=row["what"],
        why=row["why"],
        created_at=datetime.fromisoformat(row["created_at"]),
        metadata=_parse_metadata(row["metadata"]) if "metadata" in row.keys() else None,
    )


def _row_to_checkpoint(row: sqlite3.Row) -> Checkpoint:
    return Checkpoint(
        id=row["id"],
        week_of=row["week_of"],
        content=row["content"],
        stream_ids=json.loads(row["stream_ids"]) if row["stream_ids"] else [],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        metadata=_parse_metadata(row["metadata"]) if "metadata" in row.keys() else None,
    )


class StateManager:
    on_mutation: Callable[[], None] | None = None

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._has_fts = False
        self._has_vec = False
        try:
            import sqlite_vec
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)
            self._has_vec = True
        except Exception:
            self._has_vec = False

    def _notify(self) -> None:
        if self.on_mutation is not None:
            self.on_mutation()

    def init_db(self) -> None:
        self._conn.executescript(SQL_CREATE_TABLES)
        for stmt in SQL_MIGRATE_METADATA:
            try:
                self._conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists
        # FTS setup with tokenizer migration
        try:
            row = self._conn.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'search_index'"
            ).fetchone()
            if row and "porter" in row[0]:
                self._conn.execute("DROP TABLE search_index")
            self._conn.executescript(SQL_CREATE_FTS)
            self._has_fts = True
            count = self._conn.execute("SELECT COUNT(*) FROM search_index").fetchone()[0]
            if count == 0:
                self._rebuild_search_index()
        except sqlite3.OperationalError:
            self._has_fts = False
        # Vec setup
        if self._has_vec:
            try:
                self._conn.execute(SQL_CREATE_VEC)
                self._conn.execute(SQL_CREATE_VEC_MAP)
                vec_count = self._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0]
                if vec_count == 0:
                    self._rebuild_vec_index()
            except sqlite3.OperationalError:
                self._has_vec = False

    def _require_active_stream(self, stream_id: str) -> Stream:
        stream = self.get_stream(stream_id)
        if not stream:
            raise ValueError(f"Stream {stream_id} not found")
        if stream.status != "active":
            raise ValueError(f"Stream {stream_id} is {stream.status} — archived streams are immutable")
        return stream

    def _rebuild_search_index(self) -> None:
        if not self._has_fts:
            return
        for row in self._conn.execute("SELECT * FROM updates").fetchall():
            u = _row_to_update(row)
            self._index_entity(u.id, "update", u.stream_id, f"{u.summary} {u.content}")
        for row in self._conn.execute("SELECT * FROM decisions").fetchall():
            d = _row_to_decision(row)
            self._index_entity(d.id, "decision", d.stream_id, f"{d.what} {d.why}")
        for row in self._conn.execute("SELECT * FROM checkpoints").fetchall():
            c = _row_to_checkpoint(row)
            self._index_entity(c.id, "checkpoint", "", c.content)

    def _rebuild_vec_index(self) -> None:
        if not self._has_vec:
            return
        from cortex.embeddings import Embedder, serialize_f32

        entries: list[tuple[str, str, str, str]] = []
        for row in self._conn.execute("SELECT * FROM updates").fetchall():
            u = _row_to_update(row)
            entries.append((u.id, "update", u.stream_id, f"{u.summary} {u.content}"))
        for row in self._conn.execute("SELECT * FROM decisions").fetchall():
            d = _row_to_decision(row)
            entries.append((d.id, "decision", d.stream_id, f"{d.what} {d.why}"))
        for row in self._conn.execute("SELECT * FROM checkpoints").fetchall():
            c = _row_to_checkpoint(row)
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

    def clear_indexes(self) -> None:
        if self._has_fts:
            self._conn.execute("DELETE FROM search_index")
        if self._has_vec:
            self._conn.execute("DELETE FROM vec_index")
            self._conn.execute("DELETE FROM vec_map")

    def _index_entity(self, entity_id: str, entity_type: str, stream_id: str, content: str) -> None:
        if self._has_fts:
            self._conn.execute(
                "INSERT INTO search_index (entity_id, entity_type, stream_id, content) VALUES (?, ?, ?, ?)",
                (entity_id, entity_type, stream_id, content),
            )
        if self._has_vec:
            from cortex.embeddings import Embedder, serialize_f32
            embedding = Embedder.get().encode(content)
            self._conn.execute(
                "INSERT INTO vec_index(embedding, entity_id, entity_type, stream_id) VALUES (?, ?, ?, ?)",
                (serialize_f32(embedding), entity_id, entity_type, stream_id),
            )
            vec_rowid = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            self._conn.execute(
                "INSERT OR REPLACE INTO vec_map(entity_id, vec_rowid) VALUES (?, ?)",
                (entity_id, vec_rowid),
            )

    def _deindex_entity(self, entity_id: str) -> None:
        if self._has_fts:
            self._conn.execute("DELETE FROM search_index WHERE entity_id = ?", (entity_id,))
        if self._has_vec:
            row = self._conn.execute(
                "SELECT vec_rowid FROM vec_map WHERE entity_id = ?", (entity_id,)
            ).fetchone()
            if row:
                self._conn.execute("DELETE FROM vec_index WHERE rowid = ?", (row[0],))
                self._conn.execute("DELETE FROM vec_map WHERE entity_id = ?", (entity_id,))

    def create_stream(self, title: str, repos: list[str], *, metadata: dict | None = None) -> Stream:
        now = _now()
        sid = _new_id()
        self._conn.execute(
            "INSERT INTO streams (id, title, repos, status, metadata, created_at, updated_at) VALUES (?, ?, ?, 'active', ?, ?, ?)",
            (sid, title, json.dumps(repos), json.dumps(metadata) if metadata else None, now, now),
        )
        return self.get_stream(sid)

    def get_stream(self, stream_id: str) -> Stream | None:
        row = self._conn.execute(
            "SELECT * FROM streams WHERE id = ?", (stream_id,)
        ).fetchone()
        return _row_to_stream(row) if row else None

    def get_active_streams(self) -> list[Stream]:
        return self.list_streams(status="active")

    def list_streams(self, status: str = "active") -> list[Stream]:
        if status == "all":
            rows = self._conn.execute(
                "SELECT * FROM streams ORDER BY updated_at DESC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM streams WHERE status = ? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
        return [_row_to_stream(r) for r in rows]

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
            raise ValueError(f"Stream {stream_id} is {stream.status} — archived streams are immutable (set status='active' to unarchive first)")
        sets: list[str] = []
        params: list = []
        if title is not None:
            sets.append("title = ?")
            params.append(title)
        if status is not None:
            sets.append("status = ?")
            params.append(status)
        if repos is not None:
            sets.append("repos = ?")
            params.append(json.dumps(repos))
        if summary is not None:
            sets.append("summary = ?")
            params.append(summary)
        if metadata is not None:
            if merge_metadata and stream.metadata:
                merged = {**stream.metadata, **metadata}
                merged = {k: v for k, v in merged.items() if v is not None}
            else:
                merged = metadata
            sets.append("metadata = ?")
            params.append(json.dumps(merged))
        if not sets:
            return stream
        sets.append("updated_at = ?")
        params.append(_now())
        params.append(stream_id)
        self._conn.execute(
            f"UPDATE streams SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        return self.get_stream(stream_id)

    def complete_stream(self, stream_id: str, summary: str) -> None:
        self._conn.execute(
            "UPDATE streams SET status = 'completed', summary = ?, updated_at = ? WHERE id = ?",
            (summary, _now(), stream_id),
        )
        self._notify()

    def add_update(self, stream_id: str, content: str, summary: str, *, metadata: dict | None = None) -> Update:
        self._require_active_stream(stream_id)
        now = _now()
        uid = _new_id()
        self._conn.execute("BEGIN")
        self._conn.execute(
            "INSERT INTO updates (id, stream_id, content, summary, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, stream_id, content, summary, json.dumps(metadata) if metadata else None, now),
        )
        self._conn.execute(
            "UPDATE streams SET updated_at = ? WHERE id = ?",
            (now, stream_id),
        )
        self._conn.execute("COMMIT")
        self._index_entity(uid, "update", stream_id, f"{summary} {content}")
        row = self._conn.execute(
            "SELECT * FROM updates WHERE id = ?", (uid,)
        ).fetchone()
        self._notify()
        return _row_to_update(row)

    def add_decision(self, stream_id: str, what: str, why: str, *, metadata: dict | None = None) -> Decision:
        self._require_active_stream(stream_id)
        now = _now()
        did = _new_id()
        self._conn.execute("BEGIN")
        self._conn.execute(
            "INSERT INTO decisions (id, stream_id, what, why, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (did, stream_id, what, why, json.dumps(metadata) if metadata else None, now),
        )
        self._conn.execute(
            "UPDATE streams SET updated_at = ? WHERE id = ?",
            (now, stream_id),
        )
        self._conn.execute("COMMIT")
        self._index_entity(did, "decision", stream_id, f"{what} {why}")
        row = self._conn.execute(
            "SELECT * FROM decisions WHERE id = ?", (did,)
        ).fetchone()
        self._notify()
        return _row_to_decision(row)

    def edit_update(
        self,
        update_id: str,
        *,
        content: str | None = None,
        summary: str | None = None,
        metadata: dict | None = None,
    ) -> Update | None:
        row = self._conn.execute("SELECT * FROM updates WHERE id = ?", (update_id,)).fetchone()
        if not row:
            return None
        sets: list[str] = []
        params: list = []
        if content is not None:
            sets.append("content = ?")
            params.append(content)
        if summary is not None:
            sets.append("summary = ?")
            params.append(summary)
        if metadata is not None:
            sets.append("metadata = ?")
            params.append(json.dumps(metadata))
        if not sets:
            return _row_to_update(row)
        params.append(update_id)
        self._conn.execute(f"UPDATE updates SET {', '.join(sets)} WHERE id = ?", params)
        new_row = self._conn.execute("SELECT * FROM updates WHERE id = ?", (update_id,)).fetchone()
        u = _row_to_update(new_row)
        self._deindex_entity(update_id)
        self._index_entity(update_id, "update", u.stream_id, f"{u.summary} {u.content}")
        return u

    def edit_decision(
        self,
        decision_id: str,
        *,
        what: str | None = None,
        why: str | None = None,
        metadata: dict | None = None,
    ) -> Decision | None:
        row = self._conn.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
        if not row:
            return None
        sets: list[str] = []
        params: list = []
        if what is not None:
            sets.append("what = ?")
            params.append(what)
        if why is not None:
            sets.append("why = ?")
            params.append(why)
        if metadata is not None:
            sets.append("metadata = ?")
            params.append(json.dumps(metadata))
        if not sets:
            return _row_to_decision(row)
        params.append(decision_id)
        self._conn.execute(f"UPDATE decisions SET {', '.join(sets)} WHERE id = ?", params)
        new_row = self._conn.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
        d = _row_to_decision(new_row)
        self._deindex_entity(decision_id)
        self._index_entity(decision_id, "decision", d.stream_id, f"{d.what} {d.why}")
        return d

    def delete_update(self, update_id: str) -> None:
        self._deindex_entity(update_id)
        self._conn.execute("DELETE FROM updates WHERE id = ?", (update_id,))

    def delete_decision(self, decision_id: str) -> None:
        self._deindex_entity(decision_id)
        self._conn.execute("DELETE FROM decisions WHERE id = ?", (decision_id,))

    def delete_stream(self, stream_id: str) -> None:
        updates = self._conn.execute("SELECT id FROM updates WHERE stream_id = ?", (stream_id,)).fetchall()
        decisions = self._conn.execute("SELECT id FROM decisions WHERE stream_id = ?", (stream_id,)).fetchall()
        for row in updates:
            self._deindex_entity(row["id"])
        for row in decisions:
            self._deindex_entity(row["id"])
        self._conn.execute("DELETE FROM updates WHERE stream_id = ?", (stream_id,))
        self._conn.execute("DELETE FROM decisions WHERE stream_id = ?", (stream_id,))
        self._conn.execute("DELETE FROM sessions WHERE stream_id = ?", (stream_id,))
        self._conn.execute("DELETE FROM streams WHERE id = ?", (stream_id,))

    def search(self, query: str) -> list[Update | Decision | Checkpoint]:
        if self._has_vec:
            results = self._semantic_search(query)
            if results:
                return results
        if self._has_fts:
            return self._fts_search(query)
        return self._like_search(query)

    def _vec_search(self, query: str, limit: int = 20) -> list[tuple[str, str, float]]:
        if not self._has_vec:
            return []
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

    def _hydrate_entity(self, entity_id: str, entity_type: str) -> Update | Decision | Checkpoint | None:
        if entity_type == "update":
            row = self._conn.execute("SELECT * FROM updates WHERE id = ?", (entity_id,)).fetchone()
            return _row_to_update(row) if row else None
        elif entity_type == "decision":
            row = self._conn.execute("SELECT * FROM decisions WHERE id = ?", (entity_id,)).fetchone()
            return _row_to_decision(row) if row else None
        elif entity_type == "checkpoint":
            row = self._conn.execute("SELECT * FROM checkpoints WHERE id = ?", (entity_id,)).fetchone()
            return _row_to_checkpoint(row) if row else None
        return None

    def _fts_search(self, query: str) -> list[Update | Decision | Checkpoint]:
        tokens = query.split()
        if not tokens:
            return []
        fts_query = " ".join(tokens)
        rows = self._conn.execute(
            "SELECT entity_id, entity_type FROM search_index WHERE content MATCH ? ORDER BY rank LIMIT 20",
            (fts_query,),
        ).fetchall()
        if not rows and len(tokens) > 1:
            fts_query = " OR ".join(tokens)
            rows = self._conn.execute(
                "SELECT entity_id, entity_type FROM search_index WHERE content MATCH ? ORDER BY rank LIMIT 20",
                (fts_query,),
            ).fetchall()
        results: list[Update | Decision | Checkpoint] = []
        for row in rows:
            entity = self._hydrate_entity(row["entity_id"], row["entity_type"])
            if entity:
                results.append(entity)
        return results

    def _like_search(self, query: str) -> list[Update | Decision | Checkpoint]:
        tokens = query.lower().split()
        if not tokens:
            return []

        # Try AND first, fall back to OR if no results
        results = self._like_query(tokens, require_all=True)
        if not results and len(tokens) > 1:
            results = self._like_query(tokens, require_all=False)
        return results[:20]

    def _like_query(self, tokens: list[str], *, require_all: bool) -> list[Update | Decision | Checkpoint]:
        joiner = " AND " if require_all else " OR "

        def _build_clauses(fields: list[str]) -> tuple[str, list[str]]:
            clauses = []
            params: list[str] = []
            for token in tokens:
                pattern = f"%{token}%"
                field_checks = " OR ".join(f"{f} LIKE ?" for f in fields)
                clauses.append(f"({field_checks})")
                params.extend([pattern] * len(fields))
            return joiner.join(clauses), params

        update_where, update_params = _build_clauses(["content", "summary", "COALESCE(metadata, '')"])
        decision_where, decision_params = _build_clauses(["what", "why", "COALESCE(metadata, '')"])
        checkpoint_where, checkpoint_params = _build_clauses(["content", "COALESCE(metadata, '')"])

        updates = self._conn.execute(
            f"SELECT * FROM updates WHERE {update_where} ORDER BY created_at DESC LIMIT 20",
            update_params,
        ).fetchall()
        decisions = self._conn.execute(
            f"SELECT * FROM decisions WHERE {decision_where} ORDER BY created_at DESC LIMIT 20",
            decision_params,
        ).fetchall()
        checkpoints = self._conn.execute(
            f"SELECT * FROM checkpoints WHERE {checkpoint_where} ORDER BY created_at DESC LIMIT 20",
            checkpoint_params,
        ).fetchall()

        results: list[Update | Decision | Checkpoint] = [_row_to_update(r) for r in updates]
        results.extend(_row_to_decision(r) for r in decisions)
        results.extend(_row_to_checkpoint(r) for r in checkpoints)

        # Rank by number of matching tokens (most matches first)
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

    def get_stream_context(self, stream_id: str) -> dict:
        stream = self.get_stream(stream_id)
        if not stream:
            return {}
        updates = self._conn.execute(
            "SELECT * FROM updates WHERE stream_id = ? ORDER BY created_at DESC",
            (stream_id,),
        ).fetchall()
        decisions = self._conn.execute(
            "SELECT * FROM decisions WHERE stream_id = ? ORDER BY created_at DESC",
            (stream_id,),
        ).fetchall()
        sessions = self._conn.execute(
            "SELECT * FROM sessions WHERE stream_id = ? ORDER BY created_at DESC",
            (stream_id,),
        ).fetchall()
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
                {"id": r["id"], "content": r["content"], "summary": r["summary"], "created_at": r["created_at"], "metadata": _parse_metadata(r["metadata"]) if "metadata" in r.keys() else None}
                for r in updates
            ],
            "decisions": [
                {"id": r["id"], "what": r["what"], "why": r["why"], "created_at": r["created_at"], "metadata": _parse_metadata(r["metadata"]) if "metadata" in r.keys() else None}
                for r in decisions
            ],
            "sessions": [
                {"session_id": r["session_id"], "repo": r["repo"], "branch": r["branch"], "status": r["status"], "created_at": r["created_at"]}
                for r in sessions
            ],
        }

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
        existing = self._conn.execute(
            "SELECT id FROM checkpoints WHERE week_of = ?", (week_of,)
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE checkpoints SET content = ?, stream_ids = ?, metadata = ?, updated_at = ? WHERE week_of = ?",
                (content, json.dumps(stream_ids), json.dumps(metadata) if metadata else None, now, week_of),
            )
            self._deindex_entity(existing["id"])
            self._index_entity(existing["id"], "checkpoint", "", content)
        else:
            cid = _new_id()
            self._conn.execute(
                "INSERT INTO checkpoints (id, week_of, content, stream_ids, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cid, week_of, content, json.dumps(stream_ids), json.dumps(metadata) if metadata else None, now, now),
            )
            self._index_entity(cid, "checkpoint", "", content)
        return self.get_checkpoint(week_of)

    def get_checkpoint(self, week_of: str | None = None) -> Checkpoint | None:
        if week_of:
            row = self._conn.execute(
                "SELECT * FROM checkpoints WHERE week_of = ?", (week_of,)
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM checkpoints ORDER BY week_of DESC LIMIT 1"
            ).fetchone()
        return _row_to_checkpoint(row) if row else None

    def link_session(self, session_id: str, stream_id: str, repo: str = "", branch: str = "") -> None:
        self._require_active_stream(stream_id)
        existing = self._conn.execute(
            "SELECT id FROM sessions WHERE session_id = ? AND stream_id = ?",
            (session_id, stream_id),
        ).fetchone()
        if existing:
            return
        self._conn.execute(
            "INSERT INTO sessions (id, session_id, stream_id, repo, branch, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (_new_id(), session_id, stream_id, repo, branch, _now()),
        )
        self._notify()

    def unlink_session(self, session_id: str, stream_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM sessions WHERE session_id = ? AND stream_id = ?",
                (session_id, stream_id),
            )

    def move_session(self, session_id: str, from_stream_id: str, to_stream_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE sessions SET stream_id = ? WHERE session_id = ? AND stream_id = ?",
                (to_stream_id, session_id, from_stream_id),
            )

    def get_streams_for_session(self, session_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT stream_id FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        return [r["stream_id"] for r in rows]

    def get_recent_activity(self, limit: int = 50, active_only: bool = False) -> list[dict]:
        if active_only:
            rows = self._conn.execute(
                """
                SELECT 'update' as type, u.id, u.stream_id, u.content, u.summary, NULL as what, NULL as why, u.metadata, u.created_at as created_at
                FROM updates u JOIN streams s ON u.stream_id = s.id
                WHERE s.status = 'active'
                UNION ALL
                SELECT 'decision' as type, d.id, d.stream_id, NULL, NULL, d.what, d.why, d.metadata, d.created_at as created_at
                FROM decisions d JOIN streams s ON d.stream_id = s.id
                WHERE s.status = 'active'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT 'update' as type, id, stream_id, content, summary, NULL as what, NULL as why, metadata, created_at
                FROM updates
                UNION ALL
                SELECT 'decision' as type, id, stream_id, NULL, NULL, what, why, metadata, created_at
                FROM decisions
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        results = []
        for r in rows:
            item = {
                "type": r["type"],
                "id": r["id"],
                "stream_id": r["stream_id"],
                "created_at": r["created_at"],
                "metadata": _parse_metadata(r["metadata"]),
            }
            if r["type"] == "update":
                item["content"] = r["content"]
                item["summary"] = r["summary"]
            else:
                item["what"] = r["what"]
                item["why"] = r["why"]
            results.append(item)
        return results

    def save_blueprint(self, blueprint: dict) -> dict:
        now = _now()
        row_id = _new_id()
        self._conn.execute("DELETE FROM dashboard_blueprints")
        self._conn.execute(
            "INSERT INTO dashboard_blueprints (id, blueprint, resolved_data, created_at, updated_at) VALUES (?, ?, NULL, ?, ?)",
            (row_id, json.dumps(blueprint), now, now),
        )
        snap_id = _new_id()
        self._conn.execute(
            "INSERT INTO dashboard_snapshots (id, snapshot_type, data, created_at) VALUES (?, 'blueprint', ?, ?)",
            (snap_id, json.dumps(blueprint), now),
        )
        return {"id": row_id, "blueprint": blueprint, "resolved_data": None, "created_at": now, "updated_at": now}

    def get_blueprint(self) -> dict | None:
        row = self._conn.execute("SELECT * FROM dashboard_blueprints LIMIT 1").fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "blueprint": json.loads(row["blueprint"]),
            "resolved_data": json.loads(row["resolved_data"]) if row["resolved_data"] else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def update_resolved_data(self, resolved_data: dict) -> None:
        now = _now()
        self._conn.execute(
            "UPDATE dashboard_blueprints SET resolved_data = ?, updated_at = ?",
            (json.dumps(resolved_data), now),
        )
        snap_id = _new_id()
        self._conn.execute(
            "INSERT INTO dashboard_snapshots (id, snapshot_type, data, created_at) VALUES (?, 'resolved', ?, ?)",
            (snap_id, json.dumps(resolved_data), now),
        )

    def get_dashboard_snapshots(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM dashboard_snapshots ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {"id": r["id"], "snapshot_type": r["snapshot_type"], "data": json.loads(r["data"]), "created_at": r["created_at"]}
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()
