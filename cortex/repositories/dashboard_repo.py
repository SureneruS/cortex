from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pymongo.database import Database

from cortex.observability import trace


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class MongoDashboardRepository:
    def __init__(self, db: Database) -> None:
        self._blueprints = db["dashboard_blueprints"]
        self._snapshots = db["dashboard_snapshots"]
        self._snapshots.create_index([("created_at", -1)])

    @trace
    def save_blueprint(self, blueprint: dict) -> dict:
        now = _now()
        row_id = _new_id()
        self._blueprints.delete_many({})
        doc = {
            "_id": row_id, "blueprint": blueprint, "resolved_data": None,
            "created_at": now, "updated_at": now,
        }
        self._blueprints.insert_one(doc)
        self._snapshots.insert_one({
            "_id": _new_id(), "snapshot_type": "blueprint", "data": blueprint, "created_at": now,
        })
        return {"id": row_id, "blueprint": blueprint, "resolved_data": None, "created_at": now, "updated_at": now}

    @trace
    def get_blueprint(self) -> dict | None:
        doc = self._blueprints.find_one()
        if not doc:
            return None
        return {
            "id": doc["_id"], "blueprint": doc["blueprint"],
            "resolved_data": doc.get("resolved_data"),
            "created_at": doc["created_at"], "updated_at": doc["updated_at"],
        }

    @trace
    def update_resolved_data(self, resolved_data: dict) -> None:
        now = _now()
        self._blueprints.update_one({}, {"$set": {"resolved_data": resolved_data, "updated_at": now}})
        self._snapshots.insert_one({
            "_id": _new_id(), "snapshot_type": "resolved", "data": resolved_data, "created_at": now,
        })

    @trace
    def get_snapshots(self, limit: int = 20) -> list[dict]:
        docs = self._snapshots.find().sort("created_at", -1).limit(limit)
        return [
            {"id": d["_id"], "snapshot_type": d["snapshot_type"], "data": d["data"], "created_at": d["created_at"]}
            for d in docs
        ]
