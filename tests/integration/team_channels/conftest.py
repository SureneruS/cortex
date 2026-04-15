from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pymongo import MongoClient
from pymongo.database import Database
from unittest.mock import patch

from cortex.session_registry import MongoSessionRepo

TEST_DB = "cortex_test_channels"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _minutes_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=n)).isoformat()


def _insert_message(
    db: Database,
    *,
    from_: str,
    to: str,
    content: str,
    status: str = "pending",
    created_at: str | None = None,
    meta: dict | None = None,
) -> dict:
    """Helper to directly write a message to MongoDB (simulates TS MCP send_message)."""
    msg_id = "msg_" + uuid.uuid4().hex[:16]
    now = created_at or _utc_now()
    doc = {
        "_id": msg_id,
        "from": from_,
        "to": to,
        "content": content,
        "meta": meta or {"type": "notification", "sender_type": "agent", "priority": "normal"},
        "status": status,
        "created_at": now,
        "delivered_at": None if status == "pending" else now,
    }
    db["messages"].insert_one(doc)
    return doc


def _claim_message(db: Database, msg_id: str) -> dict | None:
    """Atomic claim: status pending → delivered. Returns claimed doc or None."""
    return db["messages"].find_one_and_update(
        {"_id": msg_id, "status": "pending"},
        {"$set": {"status": "delivered", "delivered_at": _utc_now()}},
        return_document=True,
    )


def _get_pending(db: Database, session_name: str, limit: int = 10) -> list[dict]:
    return list(
        db["messages"]
        .find({"to": session_name, "status": "pending"})
        .sort("created_at", 1)
        .limit(limit)
    )


@pytest.fixture
def mongo_db() -> Database:
    client = MongoClient("mongodb://localhost:27017")
    db = client[TEST_DB]
    yield db
    for name in db.list_collection_names():
        db.drop_collection(name)
    client.close()


@pytest.fixture
def session_repo(mongo_db: Database) -> MongoSessionRepo:
    return MongoSessionRepo(mongo_db)


@pytest.fixture
def patch_db(mongo_db):
    """Route all CLI get_db() calls to the test database and simulate Suren running the CLI."""
    import os
    from cortex.container import reset_container
    reset_container()
    old_name = os.environ.pop("CORTEX_SESSION_NAME", None)
    old_id = os.environ.pop("CORTEX_SESSION_ID", None)
    old_actor = os.environ.get("CORTEX_ACTOR")
    os.environ["CORTEX_ACTOR"] = "suren"
    with patch("cortex.mongo.get_db", return_value=mongo_db):
        yield mongo_db
    reset_container()
    if old_name:
        os.environ["CORTEX_SESSION_NAME"] = old_name
    if old_id:
        os.environ["CORTEX_SESSION_ID"] = old_id
    if old_actor is None:
        os.environ.pop("CORTEX_ACTOR", None)
    else:
        os.environ["CORTEX_ACTOR"] = old_actor


@pytest.fixture
def team_session_factory(session_repo: MongoSessionRepo):
    """Create a team session in the registry."""

    def _make(
        name: str,
        task: str = "some task",
        status: str = "active",
        last_seen: str | None = _utc_now(),
        session_id: str | None = None,
    ) -> dict:
        sid = session_id or f"sess-{name}"
        return session_repo.register(
            sid,
            {
                "name": name,
                "task": task,
                "team": "default",
                "status": status,
                "last_seen": last_seen,
                "spawned_by": "cli",
            },
        )

    return _make
