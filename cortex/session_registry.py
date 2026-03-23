from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pymongo.database import Database

VALID_STATUS = {"active", "idle", "paused", "blocked", "watching", "completed", "dead"}
VALID_RUNTIME = {"working", "waiting_input", "waiting_permission", "error", "unknown"}


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
    return event


class MongoSessionRepo:
    def __init__(self, db: Database) -> None:
        self._col = db["session_registry"]

    def register(self, session_id: str | None, data: dict) -> dict:
        if session_id is None:
            session_id = _new_id()
        now = _now()
        doc = {"_id": session_id, "created_at": now, "status": "active", **data}
        doc.setdefault("runtime", "unknown")
        doc["events"] = [
            _make_event("status", None, doc["status"], "spawn"),
        ]
        self._col.insert_one(doc)
        return doc

    def get(self, session_id: str) -> dict | None:
        return self._col.find_one({"_id": session_id})

    def update(self, session_id: str, data: dict, *, trigger: str = "update") -> dict | None:
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
                events.append(_make_event(field, current.get(field), data[field], trigger))

        ops: dict = {"$set": data}
        if events:
            ops["$push"] = {"events": {"$each": events}}

        self._col.update_one({"_id": session_id}, ops)
        return self.get(session_id)

    def update_runtime(
        self, session_id: str, runtime: str, trigger: str = "health-check"
    ) -> dict | None:
        return self.update(session_id, {"runtime": runtime}, trigger=trigger)

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
        """Resolve a session by _id, name (among non-terminal), or _id prefix.

        Returns the session doc, or raises ValueError if ambiguous/not found.
        """
        # 1. Exact _id
        doc = self.get(ref)
        if doc is not None:
            return doc

        # 2. Name match among non-terminal sessions
        active_filter = {"status": {"$nin": ["completed", "dead"]}}
        by_name = list(self._col.find({"name": ref, **active_filter}).sort("created_at", -1))
        if len(by_name) == 1:
            return by_name[0]
        if len(by_name) > 1:
            options = ", ".join(f"{d['_id']} ({d.get('status')})" for d in by_name)
            raise ValueError(f"Ambiguous name '{ref}' matches {len(by_name)} sessions: {options}")

        # 3. cc_session_id match (CC UUID from hooks)
        by_cc = self._col.find_one({"cc_session_id": ref, **active_filter})
        if by_cc is not None:
            return by_cc

        # 4. _id prefix match
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

    def close(self, session_id: str, trigger: str = "close") -> dict | None:
        return self.update(
            session_id, {"status": "completed", "closed_at": _now()}, trigger=trigger
        )
