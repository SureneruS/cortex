from __future__ import annotations

import sqlite3
from pathlib import Path

import structlog

log = structlog.get_logger("cortex.vector_store")

SIMILARITY_THRESHOLD = 0.5


class SqliteVectorStore:
    """SQLite-based vector index using sqlite-vec extension."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._conn: sqlite3.Connection | None = None
        self._has_vec = False
        if db_path is not None:
            self._init(db_path)

    @property
    def available(self) -> bool:
        return self._has_vec

    def _init(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
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

    def init_db(self) -> None:
        if self._has_vec and self._conn is not None:
            vec_count = self._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0]
            if vec_count == 0:
                return  # caller should rebuild

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

    def search(self, query: str, limit: int = 20) -> list[tuple[str, str, float]]:
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

    def index(self, entity_id: str, entity_type: str, stream_id: str, content: str) -> None:
        """Queue content for lazy embedding — no model loaded until search."""
        if not self._has_vec or self._conn is None:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO vec_pending(entity_id, entity_type, stream_id, content) VALUES (?, ?, ?, ?)",
            (entity_id, entity_type, stream_id, content),
        )

    def deindex(self, entity_id: str) -> None:
        if not self._has_vec or self._conn is None:
            return
        self._conn.execute("DELETE FROM vec_pending WHERE entity_id = ?", (entity_id,))
        row = self._conn.execute(
            "SELECT vec_rowid FROM vec_map WHERE entity_id = ?", (entity_id,)
        ).fetchone()
        if row:
            self._conn.execute("DELETE FROM vec_index WHERE rowid = ?", (row[0],))
            self._conn.execute("DELETE FROM vec_map WHERE entity_id = ?", (entity_id,))

    def clear(self) -> None:
        if self._has_vec and self._conn is not None:
            self._conn.execute("DELETE FROM vec_index")
            self._conn.execute("DELETE FROM vec_map")
            self._conn.execute("DELETE FROM vec_pending")

    def rebuild(self, entries: list[tuple[str, str, str, str]]) -> None:
        """Rebuild entire index. Each entry: (entity_id, entity_type, stream_id, text)."""
        if not self._has_vec or self._conn is None or not entries:
            return
        self._conn.execute("DELETE FROM vec_pending")
        from cortex.embeddings import Embedder, serialize_f32
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

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
