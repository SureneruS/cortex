import pytest

from cortex.domain.utils import _slugify
from cortex.services.stream_service import StreamService


class TestSlugify:
    def test_basic(self):
        assert _slugify("Auth Middleware Rewrite") == "auth-middleware-rewrite"

    def test_special_chars(self):
        assert _slugify("Fix: N+1 query (users)") == "fix-n-1-query-users"

    def test_leading_trailing(self):
        assert _slugify("  --hello world--  ") == "hello-world"

    def test_consecutive_hyphens(self):
        assert _slugify("foo---bar") == "foo-bar"

    def test_truncation(self):
        long_title = "a" * 60
        result = _slugify(long_title)
        assert len(result) <= 50

    def test_truncation_no_trailing_hyphen(self):
        title = "a" * 49 + " b"
        result = _slugify(title, max_length=50)
        assert not result.endswith("-")

    def test_empty(self):
        assert _slugify("") == ""

    def test_only_special_chars(self):
        assert _slugify("!!!") == ""


class TestStreamNameGeneration:
    def test_create_generates_name(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Auth Middleware", ["backend"])
        assert s.name == "auth-middleware"

    def test_name_uniqueness_with_suffix(self, stream_svc: StreamService):
        s1 = stream_svc.create_stream("Auth Middleware", ["backend"])
        s2 = stream_svc.create_stream("Auth Middleware", ["backend"])
        assert s1.name == "auth-middleware"
        assert s2.name == "auth-middleware-2"

    def test_name_uniqueness_triple(self, stream_svc: StreamService):
        stream_svc.create_stream("Auth Middleware", ["backend"])
        stream_svc.create_stream("Auth Middleware", ["backend"])
        s3 = stream_svc.create_stream("Auth Middleware", ["backend"])
        assert s3.name == "auth-middleware-3"


class TestStreamResolve:
    def test_resolve_by_id(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test Stream", ["repo"])
        resolved = stream_svc.resolve_stream(s.id)
        assert resolved is not None
        assert resolved.id == s.id

    def test_resolve_by_name(self, stream_svc: StreamService):
        s = stream_svc.create_stream("My Feature", ["repo"])
        resolved = stream_svc.resolve_stream("my-feature")
        assert resolved is not None
        assert resolved.id == s.id

    def test_resolve_by_prefix(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test Stream", ["repo"])
        prefix = s.id[:6]
        resolved = stream_svc.resolve_stream(prefix)
        assert resolved is not None
        assert resolved.id == s.id

    def test_resolve_not_found(self, stream_svc: StreamService):
        assert stream_svc.resolve_stream("nonexistent") is None

    def test_resolve_completed_stream_by_name(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Old Feature", ["repo"])
        stream_svc.complete_stream(s.id, "done")
        resolved = stream_svc.resolve_stream("old-feature")
        assert resolved is not None
        assert resolved.id == s.id

    def test_resolve_ambiguous_prefix_raises(self, stream_svc: StreamService):
        stream_svc.create_stream("Stream A", ["repo"])
        stream_svc.create_stream("Stream B", ["repo"])
        # Both IDs are 12 hex chars — unlikely to share a prefix, but test the error path
        # by using an empty prefix that matches all
        # We need at least 2 streams for this test
        with pytest.raises(ValueError, match="Ambiguous prefix"):
            # Use a very short prefix to trigger ambiguity
            stream_svc.resolve_stream("")  # empty matches nothing via regex ^


class TestStreamNameInOutput:
    def test_stream_context_includes_name(self, stream_svc: StreamService):
        s = stream_svc.create_stream("My Stream", ["repo"])
        ctx = stream_svc.get_stream_context(s.id)
        assert ctx["stream"]["name"] == "my-stream"

    def test_list_streams_have_names(self, stream_svc: StreamService):
        stream_svc.create_stream("First Stream", ["repo"])
        stream_svc.create_stream("Second Stream", ["repo"])
        streams = stream_svc.list_streams()
        assert all(s.name for s in streams)
        names = {s.name for s in streams}
        assert "first-stream" in names
        assert "second-stream" in names
