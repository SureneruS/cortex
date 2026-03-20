from __future__ import annotations

import asyncio
import hashlib
import random
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from cortex.mongo_state import MongoStateManager


EMBEDDING_DIMS = 768


class FakeEmbedder:
    def encode(self, text: str) -> list[float]:
        return self.encode_batch([text])[0]

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            rng = random.Random(hashlib.md5(text.encode()).hexdigest())
            vec = [rng.gauss(0, 1) for _ in range(EMBEDDING_DIMS)]
            norm = sum(x * x for x in vec) ** 0.5
            results.append([x / norm for x in vec])
        return results


@pytest.fixture(autouse=True)
def _mock_embedder():
    from cortex.embeddings import Embedder
    original = Embedder._instance
    Embedder._instance = FakeEmbedder()  # type: ignore[assignment]
    yield
    Embedder._instance = original


@pytest.fixture
def mongo_db():
    client = MongoClient("mongodb://localhost:27017")
    db = client["cortex_state_test"]
    yield db
    for name in db.list_collection_names():
        db.drop_collection(name)
    client.close()


@pytest.fixture
def state(tmp_path: Path, mongo_db) -> MongoStateManager:
    vec_path = tmp_path / "vec.db"
    sm = MongoStateManager(mongo_db, vec_path)
    sm.init_db()
    return sm


@pytest.fixture
def populated_state(state: MongoStateManager) -> MongoStateManager:
    stream = state.create_stream("Ralph Loop", ["suren-toolbox"])
    state.add_update(stream.id, "Implemented docker sandbox with volume mounts for .claude and workspace", "Docker sandbox setup")
    state.add_update(stream.id, "Fixed ralph loop workflow to use prd-driven iteration", "PRD-driven loop complete")
    state.add_decision(stream.id, "Use WAL mode for SQLite", "Better concurrent read performance")
    state.add_decision(stream.id, "Route /range declared before /{n} in FastAPI router", "Avoid path parameter collision")
    return state


@pytest.fixture
def api_client(state: MongoStateManager):
    from cortex import api
    with patch.object(api, "_state", state):
        yield TestClient(api.app)


@pytest.fixture
async def async_client(state: MongoStateManager):
    import asyncio as _asyncio
    from cortex import api, dashboard
    from httpx import ASGITransport, AsyncClient

    dashboard._sse_clients.clear()
    api._loop = _asyncio.get_running_loop()
    api._wire_sse_callback(state)
    with patch.object(api, "_state", state):
        transport = ASGITransport(app=api.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
def sse_queue():
    from cortex import dashboard

    q: asyncio.Queue = asyncio.Queue()
    dashboard._sse_clients.append(q)
    yield q
    if q in dashboard._sse_clients:
        dashboard._sse_clients.remove(q)
