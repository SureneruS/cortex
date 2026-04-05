from __future__ import annotations

import subprocess
import uuid

import pytest
from pymongo import MongoClient

from cortex.session_registry import MongoSessionRepo


@pytest.fixture(scope="session")
def e2e_mongo_db():
    client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
    except Exception:
        pytest.skip("MongoDB not reachable")
    db = client["cortex"]
    yield db
    client.close()


@pytest.fixture
def e2e_session_repo(e2e_mongo_db) -> MongoSessionRepo:
    return MongoSessionRepo(e2e_mongo_db)


MOCK_SHELL = "echo '❯ mock session ready'; sleep 3600"


@pytest.fixture
def spawn_mock_session(e2e_session_repo, e2e_mongo_db):
    """Spawns sessions with a mock shell instead of CC. No API calls."""
    spawned: list[dict] = []

    def _spawn(name: str | None = None, **kwargs) -> dict:
        if name is None:
            name = f"test-{uuid.uuid4().hex[:8]}"
        elif not name.startswith("test-"):
            name = f"test-{name}"

        kwargs.setdefault("command", MOCK_SHELL)

        cmd = ["cortex", "session", "spawn", "--name", name, "--goal", "E2E test session"]
        for k, v in kwargs.items():
            flag = f"--{k.replace('_', '-')}"
            cmd.extend([flag, str(v)])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            pytest.fail(f"Failed to spawn mock session {name}: {result.stderr}")

        import json
        doc = json.loads(result.stdout)
        spawned.append(doc)
        return doc

    yield _spawn

    for doc in spawned:
        session_id = doc.get("session_id")
        if session_id:
            subprocess.run(
                ["cortex", "session", "close", session_id, "--force"],
                capture_output=True, timeout=15,
            )

    remaining = e2e_session_repo.list({
        "name": {"$regex": "^test-"},
        "status": {"$nin": ["completed", "dead", "paused"]},
    })
    for doc in remaining:
        e2e_session_repo.close(doc["_id"], trigger="e2e-cleanup-sweep")
