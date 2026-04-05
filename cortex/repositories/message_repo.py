from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pymongo.database import Database

from cortex.domain.models import Message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_msg_id() -> str:
    return "msg_" + uuid.uuid4().hex[:16]


class MongoMessageRepository:
    def __init__(self, db: Database) -> None:
        self._col = db["messages"]

    def create(
        self,
        sender: str,
        recipient: str,
        content: str,
        *,
        meta: dict | None = None,
    ) -> Message:
        msg_id = _new_msg_id()
        now = _now()
        doc = {
            "_id": msg_id,
            "from": sender,
            "to": recipient,
            "content": content,
            "meta": meta or {},
            "status": "pending",
            "created_at": now,
            "delivered_at": None,
        }
        self._col.insert_one(doc)
        return _doc_to_message(doc)

    def get_pending(self, recipient: str, limit: int = 10) -> list[Message]:
        docs = (
            self._col.find({"to": recipient, "status": "pending"})
            .sort("created_at", 1)
            .limit(limit)
        )
        return [_doc_to_message(d) for d in docs]

    def claim_and_deliver(self, message_id: str) -> Message | None:
        doc = self._col.find_one_and_update(
            {"_id": message_id, "status": "pending"},
            {"$set": {"status": "delivered", "delivered_at": _now()}},
        )
        if doc is None:
            return None
        doc["status"] = "delivered"
        return _doc_to_message(doc)

    def mark_delivered(self, message_id: str) -> None:
        self._col.update_one(
            {"_id": message_id},
            {"$set": {"status": "delivered", "delivered_at": _now()}},
        )

    def expire_for_session(self, session_name: str) -> int:
        now = _now()
        result = self._col.update_many(
            {"$or": [{"to": session_name}, {"from": session_name}], "status": "pending"},
            {"$set": {"status": "expired", "delivered_at": now}},
        )
        return result.modified_count

    def list_messages(
        self,
        *,
        session_name: str | None = None,
        to_filter: str | None = None,
        limit: int = 20,
    ) -> list[Message]:
        query: dict = {}
        if session_name:
            query["$or"] = [{"from": session_name}, {"to": session_name}]
        if to_filter:
            query["to"] = to_filter
        docs = list(self._col.find(query).sort("created_at", -1).limit(limit))
        return [_doc_to_message(d) for d in docs]

    def has_replies(self, *, from_session: str, to_session: str, after: str) -> bool:
        return self._col.count_documents(
            {"from": from_session, "to": to_session, "created_at": {"$gt": after}},
            limit=1,
        ) > 0

    def watch_messages(
        self,
        *,
        sessions: list[str] | None = None,
        after: str | None = None,
        limit: int = 100,
    ) -> list[Message]:
        query: dict = {}
        if sessions and len(sessions) == 2:
            a, b = sessions
            query["$or"] = [
                {"from": a, "to": b},
                {"from": b, "to": a},
            ]
        elif sessions and len(sessions) == 1:
            name = sessions[0]
            query["$or"] = [{"from": name}, {"to": name}]
        if after:
            query["created_at"] = {"$gt": after}
        docs = list(self._col.find(query).sort("created_at", 1).limit(limit))
        return [_doc_to_message(d) for d in docs]


def _doc_to_message(doc: dict) -> Message:
    return Message(
        id=doc["_id"],
        sender=doc["from"],
        recipient=doc["to"],
        content=doc.get("content", ""),
        status=doc.get("status", "pending"),
        created_at=doc.get("created_at", ""),
        meta=doc.get("meta", {}),
        delivered_at=doc.get("delivered_at"),
    )
