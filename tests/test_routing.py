from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from cortex.domain.routing import (
    AGENT_SENDER_TYPE,
    HUMAN_RECIPIENT,
    HUMAN_SENDER_TYPE,
    LEGACY_HUMAN_RECIPIENT,
    RESERVED_NAMES,
    UNKNOWN_ACTOR,
    canonical_recipient,
    is_human_recipient,
    resolve_actor,
    sender_type_for,
)


class TestCanonicalRecipient:
    def test_suren_passes_through(self):
        canonical, warning = canonical_recipient("suren")
        assert canonical == "suren"
        assert warning is None

    def test_legacy_human_coerced_with_warning(self):
        canonical, warning = canonical_recipient("human")
        assert canonical == "suren"
        assert warning is not None
        assert "deprecated" in warning.lower()

    def test_regular_session_name_passes_through(self):
        canonical, warning = canonical_recipient("worker-1")
        assert canonical == "worker-1"
        assert warning is None


class TestIsHumanRecipient:
    def test_suren_is_human(self):
        assert is_human_recipient("suren") is True

    def test_legacy_human_is_human(self):
        assert is_human_recipient("human") is True

    def test_other_names_are_not_human(self):
        assert is_human_recipient("worker-1") is False
        assert is_human_recipient("") is False


class TestResolveActor:
    def test_session_name_wins(self):
        with patch.dict(os.environ, {
            "CORTEX_SESSION_NAME": "worker-42",
            "CORTEX_ACTOR": "suren",
        }):
            assert resolve_actor() == "worker-42"

    def test_actor_env_used_when_session_name_missing(self):
        env = {k: v for k, v in os.environ.items() if k != "CORTEX_SESSION_NAME"}
        env["CORTEX_ACTOR"] = "suren"
        with patch.dict(os.environ, env, clear=True):
            assert resolve_actor() == "suren"

    def test_unknown_when_neither_env_set(self):
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("CORTEX_SESSION_NAME", "CORTEX_ACTOR")
        }
        with patch.dict(os.environ, env, clear=True):
            assert resolve_actor() == UNKNOWN_ACTOR


class TestSenderTypeFor:
    def test_suren_is_human_sender_type(self):
        assert sender_type_for("suren") == HUMAN_SENDER_TYPE

    def test_agent_names_get_agent_sender_type(self):
        assert sender_type_for("worker-1") == AGENT_SENDER_TYPE
        assert sender_type_for(UNKNOWN_ACTOR) == AGENT_SENDER_TYPE


class TestReservedNames:
    def test_both_names_reserved(self):
        assert HUMAN_RECIPIENT in RESERVED_NAMES
        assert LEGACY_HUMAN_RECIPIENT in RESERVED_NAMES
