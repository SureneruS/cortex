from __future__ import annotations

from datetime import datetime, timezone

from croniter import croniter
from pymongo.database import Database


class CronManager:
    def __init__(self, db: Database) -> None:
        self._col = db["cron_jobs"]
        self._col.create_index("name", unique=True)

    def _validate_cron(self, expr: str) -> None:
        if not croniter.is_valid(expr):
            raise ValueError(f"Invalid cron expression: {expr!r}")

    def _next_run(self, cron_expr: str, base: datetime | None = None) -> datetime:
        base = base or datetime.now(timezone.utc)
        return croniter(cron_expr, base).get_next(datetime).replace(tzinfo=timezone.utc)

    def create(self, name: str, cron: str, action: str, action_args: dict | None = None) -> dict:
        self._validate_cron(cron)
        now = datetime.now(timezone.utc)
        doc = {
            "name": name,
            "cron": cron,
            "action": action,
            "action_args": action_args or {},
            "enabled": True,
            "last_run": None,
            "next_run": self._next_run(cron, now),
            "created_at": now,
        }
        try:
            self._col.insert_one({"_id": name, **doc})
        except Exception as e:
            if "duplicate key" in str(e).lower() or "E11000" in str(e):
                raise ValueError(f"Cron job {name!r} already exists") from e
            raise
        return doc

    def list(self) -> list[dict]:
        return [self._strip_id(d) for d in self._col.find().sort("created_at", -1)]

    def get(self, name: str) -> dict | None:
        doc = self._col.find_one({"_id": name})
        return self._strip_id(doc) if doc else None

    def delete(self, name: str) -> bool:
        result = self._col.delete_one({"_id": name})
        if result.deleted_count == 0:
            raise ValueError(f"Cron job {name!r} not found")
        return True

    def pause(self, name: str) -> dict:
        result = self._col.find_one_and_update(
            {"_id": name},
            {"$set": {"enabled": False}},
            return_document=True,
        )
        if result is None:
            raise ValueError(f"Cron job {name!r} not found")
        return self._strip_id(result)

    def resume(self, name: str) -> dict:
        doc = self._col.find_one({"_id": name})
        if doc is None:
            raise ValueError(f"Cron job {name!r} not found")
        now = datetime.now(timezone.utc)
        result = self._col.find_one_and_update(
            {"_id": name},
            {"$set": {"enabled": True, "next_run": self._next_run(doc["cron"], now)}},
            return_document=True,
        )
        return self._strip_id(result)

    def get_due_jobs(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        return [
            self._strip_id(d) for d in self._col.find({"enabled": True, "next_run": {"$lte": now}})
        ]

    def mark_run(self, name: str) -> None:
        doc = self._col.find_one({"_id": name})
        if doc is None:
            raise ValueError(f"Cron job {name!r} not found")
        now = datetime.now(timezone.utc)
        self._col.update_one(
            {"_id": name},
            {"$set": {"last_run": now, "next_run": self._next_run(doc["cron"], now)}},
        )

    @staticmethod
    def _strip_id(doc: dict) -> dict:
        doc.pop("_id", None)
        return doc
