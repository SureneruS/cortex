from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
import structlog

from cortex.observability import (
    bind_correlation,
    setup_logging,
    trace,
)


@pytest.fixture(autouse=True)
def _reset_logging():
    """Reset logging state between tests."""
    import cortex.observability

    cortex.observability._configured = False
    root = logging.getLogger()
    root.handlers.clear()
    structlog.reset_defaults()
    yield
    cortex.observability._configured = False
    root.handlers.clear()


@pytest.fixture
def log_dir(tmp_path):
    with patch("cortex.observability.LOG_DIR", tmp_path):
        yield tmp_path


class TestSetupLogging:
    def test_creates_log_dir(self, log_dir):
        import shutil

        shutil.rmtree(log_dir)
        assert not log_dir.exists()
        setup_logging("test")
        assert log_dir.exists()

    def test_creates_handlers(self, log_dir):
        setup_logging("test")
        root = logging.getLogger()
        assert len(root.handlers) == 3  # info file, debug file, console

    def test_idempotent(self, log_dir):
        setup_logging("test")
        setup_logging("test")
        root = logging.getLogger()
        assert len(root.handlers) == 3

    def test_info_log_written_to_file(self, log_dir):
        setup_logging("test")
        logger = structlog.get_logger("cortex.test")
        logger.info("hello", key="value")
        info_log = log_dir / "cortex-test.log"
        assert info_log.exists()
        lines = info_log.read_text().strip().splitlines()
        assert len(lines) >= 1
        entry = json.loads(lines[-1])
        assert entry["event"] == "hello"
        assert entry["key"] == "value"
        assert entry["level"] == "info"

    def test_debug_log_written_to_debug_file(self, log_dir):
        setup_logging("test")
        logger = structlog.get_logger("cortex.test")
        logger.debug("step detail")
        debug_log = log_dir / "cortex-test-debug.log"
        assert debug_log.exists()
        lines = debug_log.read_text().strip().splitlines()
        assert any("step detail" in line for line in lines)

    def test_debug_not_in_info_file(self, log_dir):
        setup_logging("test")
        logger = structlog.get_logger("cortex.test")
        logger.debug("only-in-debug")
        info_log = log_dir / "cortex-test.log"
        content = info_log.read_text() if info_log.exists() else ""
        assert "only-in-debug" not in content


class TestCorrelation:
    def test_bind_generates_id(self, log_dir):
        setup_logging("test")
        cid = bind_correlation()
        assert len(cid) == 8

    def test_bind_uses_provided_id(self, log_dir):
        setup_logging("test")
        cid = bind_correlation(correlation_id="custom123")
        assert cid == "custom123"

    def test_correlation_in_logs(self, log_dir):
        setup_logging("test")
        bind_correlation(correlation_id="abc12345")
        logger = structlog.get_logger("cortex.test")
        logger.info("with correlation")
        info_log = log_dir / "cortex-test.log"
        lines = info_log.read_text().strip().splitlines()
        entry = json.loads(lines[-1])
        assert entry["correlation_id"] == "abc12345"


class TestTrace:
    def test_sync_trace_logs_enter_exit(self, log_dir):
        setup_logging("test")

        @trace
        def add(a: int, b: int) -> int:
            return a + b

        result = add(1, 2)
        assert result == 3

        debug_log = log_dir / "cortex-test-debug.log"
        content = debug_log.read_text()
        assert "ENTER" in content
        assert "EXIT" in content
        assert "duration_ms" in content

    def test_sync_trace_logs_error(self, log_dir):
        setup_logging("test")

        @trace
        def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            fail()

        debug_log = log_dir / "cortex-test-debug.log"
        content = debug_log.read_text()
        assert "ERROR" in content
        assert "boom" in content

    @pytest.mark.asyncio
    async def test_async_trace_logs_enter_exit(self, log_dir):
        setup_logging("test")

        @trace
        async def async_add(a: int, b: int) -> int:
            return a + b

        result = await async_add(1, 2)
        assert result == 3

        debug_log = log_dir / "cortex-test-debug.log"
        content = debug_log.read_text()
        assert "ENTER" in content
        assert "EXIT" in content

    @pytest.mark.asyncio
    async def test_async_trace_logs_error(self, log_dir):
        setup_logging("test")

        @trace
        async def async_fail():
            raise ValueError("async boom")

        with pytest.raises(ValueError, match="async boom"):
            await async_fail()

        debug_log = log_dir / "cortex-test-debug.log"
        content = debug_log.read_text()
        assert "ERROR" in content
        assert "async boom" in content

    def test_trace_no_args(self, log_dir):
        setup_logging("test")

        @trace(log_args=False)
        def secret(password: str) -> bool:
            return True

        secret("hunter2")
        debug_log = log_dir / "cortex-test-debug.log"
        content = debug_log.read_text()
        assert "hunter2" not in content
        assert "ENTER" in content

    def test_trace_preserves_function_name(self):
        @trace
        def my_function():
            pass

        assert my_function.__name__ == "my_function"
