from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

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


@pytest.fixture
def test_session_name() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def spawn_test_session(e2e_session_repo, e2e_mongo_db):
    """Factory fixture that spawns real CC sessions and tracks them for cleanup.

    Returns a callable: spawn(name) -> session doc dict.
    On teardown: kills tmux panes, closes registry entries, removes prompt files.
    """
    spawned: list[dict] = []

    def _spawn(name: str | None = None, **kwargs) -> dict:
        if name is None:
            name = f"test-{uuid.uuid4().hex[:8]}"
        elif not name.startswith("test-"):
            name = f"test-{name}"

        cmd = ["cortex", "session", "spawn", "--name", name, "--goal", "E2E test session"]
        for k, v in kwargs.items():
            flag = f"--{k.replace('_', '-')}"
            cmd.extend([flag, str(v)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            pytest.fail(f"Failed to spawn session {name}: {result.stderr}")

        import json
        doc = json.loads(result.stdout)
        spawned.append(doc)
        return doc

    yield _spawn

    # Cleanup: close session (--force skips /memorize, kills pane, closes registry)
    for doc in spawned:
        session_id = doc.get("session_id")
        if session_id:
            subprocess.run(
                ["cortex", "session", "close", session_id, "--force"],
                capture_output=True,
                timeout=15,
            )

    # Final verification: no test-* sessions left active
    remaining = e2e_session_repo.list({
        "name": {"$regex": "^test-"},
        "status": {"$nin": ["completed", "dead"]},
    })
    for doc in remaining:
        e2e_session_repo.close(doc["_id"], trigger="e2e-cleanup-sweep")


MOCK_SHELL = "echo '❯ mock session ready'; sleep 3600"


@pytest.fixture
def spawn_mock_session(e2e_session_repo, e2e_mongo_db):
    """Like spawn_test_session but uses a mock shell instead of CC.

    Use for tests that only need a tmux pane (layout, spatial, hide/show).
    Does NOT start claude — no API calls, no rate limits.
    """
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
