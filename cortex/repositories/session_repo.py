from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pymongo import ReturnDocument
from pymongo.database import Database

from cortex.domain.models import SessionStatus, RuntimeStatus

VALID_STATUS = {s.value for s in SessionStatus}
VALID_RUNTIME = {r.value for r in RuntimeStatus}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _make_event(
    field: str,
    from_val: str | None,
    to_val: str,
    trigger: str,
    reason: str | None = None,
    actor: str | None = None,
) -> dict:
    event = {
        "field": field,
        "from": from_val,
        "to": to_val,
        "at": _now(),
        "trigger": trigger,
    }
    if reason:
        event["reason"] = reason
    if actor:
        event["actor"] = actor
    return event


class MongoSessionRepository:
    def __init__(self, db: Database) -> None:
        self._col = db["session_registry"]

    def register(self, session_id: str | None, data: dict) -> dict:
        if session_id is None:
            session_id = _new_id()
        now = _now()
        doc = {"_id": session_id, "created_at": now, "status": "active", **data}
        doc.setdefault("runtime", "unknown")
        doc["events"] = [
            _make_event("status", None, doc["status"], "spawn", actor=doc.get("spawned_by")),
        ]
        if doc.get("cc_session_id"):
            doc.setdefault("cc_sessions", [
                {"cc_session_id": doc["cc_session_id"], "started_at": now},
            ])

        cc_session_id = data.get("cc_session_id")
        if cc_session_id:
            # Atomic find-or-create: if an active session with this cc_session_id
            # already exists, return it instead of creating a duplicate.
            result = self._col.find_one_and_update(
                {"cc_session_id": cc_session_id, "status": {"$nin": ["completed", "dead"]}},
                {"$setOnInsert": doc},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            return result

        self._col.insert_one(doc)
        return doc

    def get(self, session_id: str) -> dict | None:
        return self._col.find_one({"_id": session_id})

    def update(self, session_id: str, data: dict, *, trigger: str = "update", actor: str | None = None) -> dict | None:
        current = self.get(session_id)
        if current is None:
            return None

        events = []
        for field, valid_set in [("status", VALID_STATUS), ("runtime", VALID_RUNTIME)]:
            if field in data and data[field] != current.get(field):
                if data[field] not in valid_set:
                    raise ValueError(
                        f"Invalid {field}: {data[field]!r}. Must be one of {sorted(valid_set)}"
                    )
                events.append(_make_event(field, current.get(field), data[field], trigger, actor=actor))

        ops: dict = {"$set": data}
        if events:
            ops["$push"] = {"events": {"$each": events}}

        self._col.update_one({"_id": session_id}, ops)
        return self.get(session_id)

    def append_cc_session(
        self,
        session_id: str,
        cc_session_id: str,
        *,
        trigger: str = "session_start_hook",
        extra: dict | None = None,
    ) -> dict | None:
        current = self.get(session_id)
        if current is None:
            return None

        entry = {"cc_session_id": cc_session_id, "started_at": _now()}
        if extra:
            entry.update(extra)

        # Atomic: only push if this cc_session_id isn't already in the array
        result = self._col.update_one(
            {"_id": session_id, "cc_sessions.cc_session_id": {"$ne": cc_session_id}},
            {
                "$set": {"cc_session_id": cc_session_id},
                "$push": {"cc_sessions": entry},
            },
        )

        if result.matched_count == 0:
            # cc_session_id already in array — just ensure top-level field is set
            self._col.update_one(
                {"_id": session_id},
                {"$set": {"cc_session_id": cc_session_id}},
            )

        return self.get(session_id)

    def update_runtime(
        self, session_id: str, runtime: str, trigger: str = "health-check", actor: str | None = None
    ) -> dict | None:
        return self.update(session_id, {"runtime": runtime}, trigger=trigger, actor=actor)

    def list(
        self,
        filters: dict | None = None,
        *,
        brief: bool = False,
        limit: int | None = None,
    ) -> list[dict]:
        projection = {"events": 0, "watch.last_state": 0} if brief else None
        cursor = self._col.find(filters or {}, projection).sort("created_at", -1)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def resolve(self, ref: str) -> dict | None:
        doc = self.get(ref)
        if doc is not None:
            return doc

        active_filter = {"status": {"$nin": ["completed", "dead"]}}
        by_name = list(self._col.find({"name": ref, **active_filter}).sort("created_at", -1))
        if len(by_name) == 1:
            return by_name[0]
        if len(by_name) > 1:
            options = ", ".join(f"{d['_id']} ({d.get('status')})" for d in by_name)
            raise ValueError(f"Ambiguous name '{ref}' matches {len(by_name)} sessions: {options}")

        by_cc = self._col.find_one({
            "$or": [
                {"cc_session_id": ref},
                {"cc_sessions.cc_session_id": ref},
            ],
            **active_filter,
        })
        if by_cc is not None:
            return by_cc

        by_prefix = list(
            self._col.find({"_id": {"$regex": f"^{ref}"}}).sort("created_at", -1).limit(5)
        )
        if len(by_prefix) == 1:
            return by_prefix[0]
        if len(by_prefix) > 1:
            options = ", ".join(
                f"{d['_id']} ({d.get('name', '?')}, {d.get('status')})" for d in by_prefix
            )
            raise ValueError(
                f"Ambiguous prefix '{ref}' matches {len(by_prefix)} sessions: {options}"
            )

        return None

    def list_events(
        self,
        *,
        sessions: list[str] | None = None,
        after: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return session events (status/runtime changes) as flat dicts."""
        match: dict = {}
        if sessions:
            match["name"] = {"$in": sessions}

        pipeline: list[dict] = []
        if match:
            pipeline.append({"$match": match})
        pipeline.append({"$unwind": "$events"})
        if after:
            pipeline.append({"$match": {"events.at": {"$gt": after}}})
        pipeline.extend([
            {"$match": {"events.field": "status"}},
            {"$sort": {"events.at": 1}},
            {"$limit": limit},
            {"$project": {
                "_id": 0,
                "session_name": "$name",
                "field": "$events.field",
                "from": "$events.from",
                "to": "$events.to",
                "at": "$events.at",
                "trigger": "$events.trigger",
                "reason": "$events.reason",
                "actor": "$events.actor",
            }},
        ])
        return list(self._col.aggregate(pipeline))

    def close(self, session_id: str, trigger: str = "close", actor: str | None = None) -> dict | None:
        return self.update(
            session_id, {"status": "completed", "closed_at": _now()}, trigger=trigger, actor=actor
        )
