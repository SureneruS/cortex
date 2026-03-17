"""Tests that StateManager mutations fire SSE via the on_mutation callback.

This was the root cause of the dashboard staleness bug: MCP tools call
StateManager directly (not HTTP endpoints), so SSE never fired.
The fix: StateManager.on_mutation callback, wired in api._wire_sse_callback().
"""

from __future__ import annotations

import asyncio

from cortex.state import StateManager


class TestOnMutationCallback:
    def test_add_update_fires_callback(self, state: StateManager):
        fired = []
        state.on_mutation = lambda: fired.append(True)
        stream = state.create_stream("Test", ["repo"])
        state.add_update(stream.id, "content", "summary")
        assert len(fired) == 1

    def test_add_decision_fires_callback(self, state: StateManager):
        fired = []
        state.on_mutation = lambda: fired.append(True)
        stream = state.create_stream("Test", ["repo"])
        state.add_decision(stream.id, "what", "why")
        assert len(fired) == 1

    def test_link_session_fires_callback(self, state: StateManager):
        fired = []
        state.on_mutation = lambda: fired.append(True)
        stream = state.create_stream("Test", ["repo"])
        state.link_session("sess-1", stream.id)
        assert len(fired) == 1

    def test_complete_stream_fires_callback(self, state: StateManager):
        fired = []
        state.on_mutation = lambda: fired.append(True)
        stream = state.create_stream("Test", ["repo"])
        state.complete_stream(stream.id, "done")
        assert len(fired) == 1

    def test_no_callback_when_none(self, state: StateManager):
        """Verify no error when on_mutation is not set."""
        assert state.on_mutation is None
        stream = state.create_stream("Test", ["repo"])
        state.add_update(stream.id, "content", "summary")

    def test_create_stream_does_not_fire(self, state: StateManager):
        """Stream creation is not a mutation that needs live dashboard update."""
        fired = []
        state.on_mutation = lambda: fired.append(True)
        state.create_stream("Test", ["repo"])
        assert len(fired) == 0


class TestMCPPathFiresSSE:
    """Simulate the MCP tool path: direct StateManager calls with SSE queue wired."""

    async def test_mcp_log_update_fires_sse(self, state: StateManager, sse_queue: asyncio.Queue):
        from cortex import api

        api._loop = asyncio.get_running_loop()
        api._wire_sse_callback(state)

        stream = state.create_stream("Test", ["repo"])
        state.add_update(stream.id, "content", "summary")

        await asyncio.sleep(0.05)
        assert sse_queue.qsize() >= 1

    async def test_mcp_log_decision_fires_sse(self, state: StateManager, sse_queue: asyncio.Queue):
        from cortex import api

        api._loop = asyncio.get_running_loop()
        api._wire_sse_callback(state)

        stream = state.create_stream("Test", ["repo"])
        state.add_decision(stream.id, "what", "why")

        await asyncio.sleep(0.05)
        assert sse_queue.qsize() >= 1

    async def test_mcp_link_session_fires_sse(self, state: StateManager, sse_queue: asyncio.Queue):
        from cortex import api

        api._loop = asyncio.get_running_loop()
        api._wire_sse_callback(state)

        stream = state.create_stream("Test", ["repo"])
        state.link_session("sess-1", stream.id)

        await asyncio.sleep(0.05)
        assert sse_queue.qsize() >= 1

    async def test_mcp_complete_stream_fires_sse(
        self, state: StateManager, sse_queue: asyncio.Queue
    ):
        from cortex import api

        api._loop = asyncio.get_running_loop()
        api._wire_sse_callback(state)

        stream = state.create_stream("Test", ["repo"])
        state.complete_stream(stream.id, "done")

        await asyncio.sleep(0.05)
        assert sse_queue.qsize() >= 1
