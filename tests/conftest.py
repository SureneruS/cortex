from __future__ import annotations

import asyncio
import hashlib
import os
import random
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

# Disable the production MongoDB error sink for the entire test session,
# including any `cortex` CLI subprocess that inherits this environment.
# See cortex/observability.py::setup_logging.
os.environ["CORTEX_DISABLE_ERROR_SINK"] = "1"

# Treat the session as non-paused regardless of ~/.cortex/paused — tests
# exercise spawn/message commands that would otherwise refuse to run while
# the user's real cortex is paused. See cortex/cli/toggle_commands.py.
os.environ["CORTEX_TESTING"] = "1"

from cortex.container import Container, reset_container  # noqa: E402


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
def container(tmp_path: Path, mongo_db) -> Container:
    reset_container()
    vec_path = tmp_path / "vec.db"
    c = Container(mongo_db, vec_path)
    yield c  # type: ignore[misc]
    reset_container()


@pytest.fixture
def stream_svc(container: Container):
    return container.stream_service


@pytest.fixture
def search_svc(container: Container):
    return container.search_service


@pytest.fixture
def dashboards(container: Container):
    return container.dashboards


@pytest.fixture
def vec_store(container: Container):
    return container.vector_store


@pytest.fixture
def populated_container(container: Container) -> Container:
    svc = container.stream_service
    stream = svc.create_stream("Ralph Loop", ["suren-toolbox"])
    svc.add_update(stream.id, "Implemented docker sandbox with volume mounts for .claude and workspace", "Docker sandbox setup")
    svc.add_update(stream.id, "Fixed ralph loop workflow to use prd-driven iteration", "PRD-driven loop complete")
    svc.add_decision(stream.id, "Use WAL mode for SQLite", "Better concurrent read performance")
    svc.add_decision(stream.id, "Route /range declared before /{n} in FastAPI router", "Avoid path parameter collision")
    return container


@pytest.fixture
def api_client(container: Container):
    from cortex import api
    with patch("cortex.api.get_container", return_value=container), \
         patch("cortex.container.get_container", return_value=container):
        yield TestClient(api.app)


@pytest.fixture
async def async_client(container: Container):
    import asyncio as _asyncio
    from cortex import api, dashboard
    from httpx import ASGITransport, AsyncClient

    dashboard._sse_clients.clear()
    api._loop = _asyncio.get_running_loop()

    def _on_mutation():
        if api._loop:
            api._loop.call_soon_threadsafe(lambda: api._loop.create_task(dashboard.notify_sse()))
    container.stream_service._on_mutation = _on_mutation

    with patch("cortex.api.get_container", return_value=container), \
         patch("cortex.container.get_container", return_value=container):
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
