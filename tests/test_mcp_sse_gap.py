"""Tests that mutations fire SSE via the on_mutation callback.

This was the root cause of the dashboard staleness bug: MCP tools call
state directly (not HTTP endpoints), so SSE never fired.
The fix: on_mutation callback on StreamService, wired in api._wire_sse_callback().
"""

from __future__ import annotations

import asyncio

from cortex.container import Container
from cortex.services.stream_service import StreamService


class TestOnMutationCallback:
    def test_add_update_fires_callback(self, stream_svc: StreamService):
        fired = []
        stream_svc._on_mutation = lambda: fired.append(True)
        stream = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_update(stream.id, "content", "summary")
        assert len(fired) == 1

    def test_add_decision_fires_callback(self, stream_svc: StreamService):
        fired = []
        stream_svc._on_mutation = lambda: fired.append(True)
        stream = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_decision(stream.id, "what", "why")
        assert len(fired) == 1

    def test_link_session_fires_callback(self, stream_svc: StreamService):
        fired = []
        stream_svc._on_mutation = lambda: fired.append(True)
        stream = stream_svc.create_stream("Test", ["repo"])
        stream_svc.link_session("sess-1", stream.id)
        assert len(fired) == 1

    def test_complete_stream_fires_callback(self, stream_svc: StreamService):
        fired = []
        stream_svc._on_mutation = lambda: fired.append(True)
        stream = stream_svc.create_stream("Test", ["repo"])
        stream_svc.complete_stream(stream.id, "done")
        assert len(fired) == 1

    def test_no_callback_when_none(self, stream_svc: StreamService):
        """Verify no error when on_mutation is not set."""
        assert stream_svc._on_mutation is None
        stream = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_update(stream.id, "content", "summary")

    def test_create_stream_does_not_fire(self, stream_svc: StreamService):
        """Stream creation is not a mutation that needs live dashboard update."""
        fired = []
        stream_svc._on_mutation = lambda: fired.append(True)
        stream_svc.create_stream("Test", ["repo"])
        assert len(fired) == 0


class TestStreamServiceSSE:
    """Simulate the direct StreamService call path with SSE queue wired."""

    async def test_add_update_fires_sse(self, container: Container, sse_queue: asyncio.Queue):
        from cortex import api

        api._loop = asyncio.get_running_loop()
        svc = container.stream_service

        from cortex.dashboard import notify_sse

        def _on_mutation():
            if api._loop:
                api._loop.call_soon_threadsafe(lambda: api._loop.create_task(notify_sse()))
        svc._on_mutation = _on_mutation

        stream = svc.create_stream("Test", ["repo"])
        svc.add_update(stream.id, "content", "summary")

        await asyncio.sleep(0.05)
        assert sse_queue.qsize() >= 1

    async def test_add_decision_fires_sse(self, container: Container, sse_queue: asyncio.Queue):
        from cortex import api

        api._loop = asyncio.get_running_loop()
        svc = container.stream_service

        from cortex.dashboard import notify_sse

        def _on_mutation():
            if api._loop:
                api._loop.call_soon_threadsafe(lambda: api._loop.create_task(notify_sse()))
        svc._on_mutation = _on_mutation

        stream = svc.create_stream("Test", ["repo"])
        svc.add_decision(stream.id, "what", "why")

        await asyncio.sleep(0.05)
        assert sse_queue.qsize() >= 1

    async def test_complete_stream_fires_sse(self, container: Container, sse_queue: asyncio.Queue):
        from cortex import api

        api._loop = asyncio.get_running_loop()
        svc = container.stream_service

        from cortex.dashboard import notify_sse

        def _on_mutation():
            if api._loop:
                api._loop.call_soon_threadsafe(lambda: api._loop.create_task(notify_sse()))
        svc._on_mutation = _on_mutation

        stream = svc.create_stream("Test", ["repo"])
        svc.complete_stream(stream.id, "done")

        await asyncio.sleep(0.05)
        assert sse_queue.qsize() >= 1
