"""SSE integration tests — verify that mutating HTTP endpoints fire SSE events."""
from __future__ import annotations

import asyncio

from cortex import dashboard
from cortex.mongo_state import MongoStateManager

TICK = 0.01


class TestSSEFiresOnMutation:
    async def test_update_post(self, async_client, state: MongoStateManager, sse_queue: asyncio.Queue):
        stream = state.create_stream("Test", ["repo"])
        resp = await async_client.post(
            f"/api/streams/{stream.id}/updates",
            json={"content": "hello", "summary": "test"},
        )
        await asyncio.sleep(TICK)
        assert resp.status_code == 200
        assert sse_queue.qsize() >= 1
        assert sse_queue.get_nowait() == "updated"

    async def test_decision_post(self, async_client, state: MongoStateManager, sse_queue: asyncio.Queue):
        stream = state.create_stream("Test", ["repo"])
        resp = await async_client.post(
            f"/api/streams/{stream.id}/decisions",
            json={"what": "chose X", "why": "because Y"},
        )
        await asyncio.sleep(TICK)
        assert resp.status_code == 200
        assert sse_queue.qsize() >= 1

    async def test_session_link(self, async_client, state: MongoStateManager, sse_queue: asyncio.Queue):
        stream = state.create_stream("Test", ["repo"])
        resp = await async_client.post(
            f"/api/streams/{stream.id}/sessions",
            json={"session_id": "sess-123"},
        )
        await asyncio.sleep(TICK)
        assert resp.status_code == 200
        assert sse_queue.qsize() >= 1

    async def test_blueprint_post(self, async_client, sse_queue: asyncio.Queue):
        bp = {"title": "Dash", "sections": [{"id": "s1", "type": "text", "content": "hi"}]}
        resp = await async_client.post("/api/dashboard/blueprint", json=bp)
        await asyncio.sleep(TICK)
        assert resp.status_code == 201
        assert sse_queue.qsize() >= 1


class TestSSEMultipleClients:
    async def test_all_clients_receive(self, async_client, state: MongoStateManager):
        queues = []
        for _ in range(3):
            q: asyncio.Queue = asyncio.Queue()
            dashboard._sse_clients.append(q)
            queues.append(q)

        stream = state.create_stream("Test", ["repo"])
        await async_client.post(
            f"/api/streams/{stream.id}/updates",
            json={"content": "hello", "summary": "test"},
        )
        await asyncio.sleep(TICK)

        for q in queues:
            assert q.qsize() >= 1
            assert q.get_nowait() == "updated"

        for q in queues:
            dashboard._sse_clients.remove(q)


class TestNoSSEOnReadOrSyncMutations:
    async def test_patch_update_no_sse(self, async_client, state: MongoStateManager, sse_queue: asyncio.Queue):
        stream = state.create_stream("Test", ["repo"])
        update = state.add_update(stream.id, "content", "summary")
        await asyncio.sleep(TICK)
        while not sse_queue.empty():
            sse_queue.get_nowait()

        resp = await async_client.patch(
            f"/api/updates/{update.id}",
            json={"summary": "new summary"},
        )
        await asyncio.sleep(TICK)
        assert resp.status_code == 200
        assert sse_queue.empty()

    async def test_delete_decision_no_sse(self, async_client, state: MongoStateManager, sse_queue: asyncio.Queue):
        stream = state.create_stream("Test", ["repo"])
        decision = state.add_decision(stream.id, "what", "why")
        await asyncio.sleep(TICK)
        while not sse_queue.empty():
            sse_queue.get_nowait()

        resp = await async_client.delete(f"/api/decisions/{decision.id}")
        await asyncio.sleep(TICK)
        assert resp.status_code == 204
        assert sse_queue.empty()

    async def test_get_endpoints_no_sse(self, async_client, state: MongoStateManager, sse_queue: asyncio.Queue):
        state.create_stream("Test", ["repo"])
        await asyncio.sleep(TICK)
        while not sse_queue.empty():
            sse_queue.get_nowait()

        await async_client.get("/api/streams")
        await async_client.get("/api/activity")
        await asyncio.sleep(TICK)
        assert sse_queue.empty()
