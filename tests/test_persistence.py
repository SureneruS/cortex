from __future__ import annotations

from pathlib import Path

from cortex.state import StateManager


def make_state(db_path: Path) -> StateManager:
    sm = StateManager(db_path)
    sm.init_db()
    return sm


def test_streams_persist(tmp_path: Path):
    db_path = tmp_path / "test.db"
    s1 = make_state(db_path)
    stream = s1.create_stream("My Stream", ["repo-a"])
    s1.close()

    s2 = make_state(db_path)
    streams = s2.list_streams(status="all")
    assert len(streams) == 1
    assert streams[0].id == stream.id
    assert streams[0].title == "My Stream"
    assert streams[0].repos == ["repo-a"]
    s2.close()


def test_updates_persist(tmp_path: Path):
    db_path = tmp_path / "test.db"
    s1 = make_state(db_path)
    stream = s1.create_stream("Stream", ["repo"])
    s1.add_update(stream.id, "Did something important", "Important update")
    s1.close()

    s2 = make_state(db_path)
    ctx = s2.get_stream_context(stream.id)
    assert len(ctx["updates"]) == 1
    assert ctx["updates"][0]["content"] == "Did something important"
    assert ctx["updates"][0]["summary"] == "Important update"
    s2.close()


def test_decisions_persist(tmp_path: Path):
    db_path = tmp_path / "test.db"
    s1 = make_state(db_path)
    stream = s1.create_stream("Stream", ["repo"])
    s1.add_decision(stream.id, "Use WAL mode", "Better concurrency")
    s1.close()

    s2 = make_state(db_path)
    ctx = s2.get_stream_context(stream.id)
    assert len(ctx["decisions"]) == 1
    assert ctx["decisions"][0]["what"] == "Use WAL mode"
    assert ctx["decisions"][0]["why"] == "Better concurrency"
    s2.close()


def test_blueprint_persists(tmp_path: Path):
    db_path = tmp_path / "test.db"
    blueprint = {"sections": [{"title": "Overview", "widgets": []}]}

    s1 = make_state(db_path)
    s1.save_blueprint(blueprint)
    s1.close()

    s2 = make_state(db_path)
    result = s2.get_blueprint()
    assert result is not None
    assert result["blueprint"] == blueprint
    s2.close()


def test_resolved_data_persists(tmp_path: Path):
    db_path = tmp_path / "test.db"
    blueprint = {"sections": []}
    resolved = {"metrics": {"active_streams": 3}}

    s1 = make_state(db_path)
    s1.save_blueprint(blueprint)
    s1.update_resolved_data(resolved)
    s1.close()

    s2 = make_state(db_path)
    result = s2.get_blueprint()
    assert result is not None
    assert result["resolved_data"] == resolved
    s2.close()


def test_fts_index_survives(tmp_path: Path):
    db_path = tmp_path / "test.db"
    s1 = make_state(db_path)
    stream = s1.create_stream("Stream", ["repo"])
    s1.add_update(stream.id, "Implemented xylophone orchestration layer", "Xylophone update")
    s1.close()

    s2 = make_state(db_path)
    results = s2.search("xylophone")
    assert len(results) >= 1
    assert any("xylophone" in r.content.lower() or "xylophone" in r.summary.lower() for r in results)
    s2.close()


def test_checkpoint_persists(tmp_path: Path):
    db_path = tmp_path / "test.db"
    s1 = make_state(db_path)
    s1.save_checkpoint("2026-W11", "Weekly summary content", stream_ids=["abc123"])
    s1.close()

    s2 = make_state(db_path)
    cp = s2.get_checkpoint("2026-W11")
    assert cp is not None
    assert cp.week_of == "2026-W11"
    assert cp.content == "Weekly summary content"
    assert cp.stream_ids == ["abc123"]
    s2.close()
