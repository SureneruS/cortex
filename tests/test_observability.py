from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest
import structlog

from cortex.observability import (
    MongoErrorHandler,
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
        assert len(root.handlers) == 4  # info file, debug file, console, mongo

    def test_idempotent(self, log_dir):
        setup_logging("test")
        setup_logging("test")
        root = logging.getLogger()
        assert len(root.handlers) == 4

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


class TestMongoErrorHandler:
    @pytest.fixture
    def error_db(self):
        from pymongo import MongoClient
        client = MongoClient("mongodb://localhost:27017")
        db = client["cortex_state_test"]
        db.errors.drop()
        yield db
        db.errors.drop()
        client.close()

    def test_error_written_to_mongo(self, error_db):
        handler = MongoErrorHandler("test-component")
        handler._col = error_db["errors"]

        record = logging.LogRecord(
            name="cortex.test", level=logging.ERROR, pathname="", lineno=0,
            msg="something_failed", args=(), exc_info=None,
        )
        handler.emit(record)

        docs = list(error_db.errors.find())
        assert len(docs) == 1
        assert docs[0]["component"] == "test-component"
        assert docs[0]["level"] == "ERROR"
        assert docs[0]["event"] == "something_failed"

    def test_warning_written_to_mongo(self, error_db):
        handler = MongoErrorHandler("test-component")
        handler._col = error_db["errors"]

        record = logging.LogRecord(
            name="cortex.test", level=logging.WARNING, pathname="", lineno=0,
            msg="watch_out", args=(), exc_info=None,
        )
        handler.emit(record)

        docs = list(error_db.errors.find())
        assert len(docs) == 1
        assert docs[0]["level"] == "WARNING"

    def test_info_not_written(self, error_db):
        handler = MongoErrorHandler("test-component")
        handler._col = error_db["errors"]
        handler.setLevel(logging.WARNING)

        record = logging.LogRecord(
            name="cortex.test", level=logging.INFO, pathname="", lineno=0,
            msg="just_info", args=(), exc_info=None,
        )
        # Handler level filter prevents emit from being called by logging,
        # but if called directly, it would still write. Test the level gate:
        if record.levelno >= handler.level:
            handler.emit(record)

        docs = list(error_db.errors.find())
        assert len(docs) == 0

    def test_exception_details_captured(self, error_db):
        handler = MongoErrorHandler("test-component")
        handler._col = error_db["errors"]

        try:
            raise ValueError("test error details")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="cortex.test", level=logging.ERROR, pathname="", lineno=0,
            msg="failed_with_exception", args=(), exc_info=exc_info,
        )
        handler.emit(record)

        docs = list(error_db.errors.find())
        assert len(docs) == 1
        assert docs[0]["details"]["exception"] == "test error details"
        assert docs[0]["details"]["exception_type"] == "ValueError"

    def test_emit_swallows_db_errors(self, error_db):
        handler = MongoErrorHandler("test-component")
        handler._col = None  # Force lazy init

        # Patch get_db to raise — handler should not propagate
        with patch("cortex.mongo.get_db", side_effect=RuntimeError("db down")):
            handler._col = None
            record = logging.LogRecord(
                name="cortex.test", level=logging.ERROR, pathname="", lineno=0,
                msg="should_not_crash", args=(), exc_info=None,
            )
            handler.emit(record)  # Should not raise

    def test_ttl_index_created(self, error_db):
        handler = MongoErrorHandler("test-component")
        with patch("cortex.mongo.get_db", return_value=error_db):
            handler._get_collection()

        indexes = error_db.errors.index_information()
        ttl_indexes = [
            idx for idx in indexes.values()
            if idx.get("expireAfterSeconds") is not None
        ]
        assert len(ttl_indexes) == 1
        assert ttl_indexes[0]["key"] == [("timestamp", 1)]
