from __future__ import annotations

from datetime import datetime

from pymongo.database import Database

import structlog

from cortex.domain.utils import _new_id, _now
from cortex.domain.models import Checkpoint
from cortex.observability import trace

log = structlog.get_logger("cortex.checkpoint_repo")


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


class MongoCheckpointRepository:
    def __init__(self, db: Database) -> None:
        self._col = db["checkpoints"]
        self._col.create_index("week_of", unique=True)
        try:
            self._col.create_index([("content", "text")], name="checkpoints_text")
        except Exception:
            log.debug("Text index already exists", index="checkpoints_text")

    @trace
    def save(
        self,
        week_of: str,
        content: str,
        stream_ids: list[str] | None = None,
        metadata: dict | None = None,
    ) -> Checkpoint:
        now = _now()
        existing = self._col.find_one({"week_of": week_of})
        if existing:
            self._col.update_one(
                {"_id": existing["_id"]},
                {"$set": {"content": content, "stream_ids": stream_ids or [], "metadata": metadata, "updated_at": now}},
            )
        else:
            cid = _new_id()
            self._col.insert_one({
                "_id": cid, "week_of": week_of, "content": content,
                "stream_ids": stream_ids or [], "metadata": metadata,
                "created_at": now, "updated_at": now,
            })
        return self.get(week_of)

    @trace
    def get(self, week_of: str | None = None) -> Checkpoint | None:
        if week_of:
            doc = self._col.find_one({"week_of": week_of})
        else:
            doc = self._col.find_one(sort=[("week_of", -1)])
        return _doc_to_checkpoint(doc) if doc else None

    def text_search(self, query: str, limit: int = 20) -> list[Checkpoint]:
        results: list[Checkpoint] = []
        try:
            cursor = self._col.find(
                {"$text": {"$search": query}},
                {"score": {"$meta": "textScore"}},
            ).sort([("score", {"$meta": "textScore"})]).limit(limit)
            for doc in cursor:
                results.append(_doc_to_checkpoint(doc))
        except Exception:
            log.warning("Text search failed on checkpoints", exc_info=True)
        return results

    def regex_search(self, query: str, limit: int = 20) -> list[Checkpoint]:
        tokens = query.lower().split()
        if not tokens:
            return []
        op = "$and"
        clauses = [{f: {"$regex": t, "$options": "i"}} for t in tokens for f in ["content"]]
        filt = {op: clauses} if len(clauses) > 1 else clauses[0]
        results = []
        for doc in self._col.find(filt).sort("created_at", -1).limit(limit):
            results.append(_doc_to_checkpoint(doc))
        return results
