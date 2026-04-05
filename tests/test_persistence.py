from __future__ import annotations

from pathlib import Path

from cortex.container import Container


def _make_container(mongo_db, vec_path: Path) -> Container:
    return Container(mongo_db, vec_path)


def test_streams_persist(tmp_path: Path, mongo_db):
    vec_path = tmp_path / "vec.db"
    c1 = _make_container(mongo_db, vec_path)
    stream = c1.stream_service.create_stream("My Stream", ["repo-a"])

    c2 = _make_container(mongo_db, vec_path)
    streams = c2.stream_service.list_streams(status="all")
    assert len(streams) == 1
    assert streams[0].id == stream.id
    assert streams[0].title == "My Stream"
    assert streams[0].repos == ["repo-a"]


def test_updates_persist(tmp_path: Path, mongo_db):
    vec_path = tmp_path / "vec.db"
    c1 = _make_container(mongo_db, vec_path)
    stream = c1.stream_service.create_stream("Stream", ["repo"])
    c1.stream_service.add_update(stream.id, "Did something important", "Important update")

    c2 = _make_container(mongo_db, vec_path)
    ctx = c2.stream_service.get_stream_context(stream.id)
    assert len(ctx["updates"]) == 1
    assert ctx["updates"][0]["content"] == "Did something important"
    assert ctx["updates"][0]["summary"] == "Important update"


def test_decisions_persist(tmp_path: Path, mongo_db):
    vec_path = tmp_path / "vec.db"
    c1 = _make_container(mongo_db, vec_path)
    stream = c1.stream_service.create_stream("Stream", ["repo"])
    c1.stream_service.add_decision(stream.id, "Use WAL mode", "Better concurrency")

    c2 = _make_container(mongo_db, vec_path)
    ctx = c2.stream_service.get_stream_context(stream.id)
    assert len(ctx["decisions"]) == 1
    assert ctx["decisions"][0]["what"] == "Use WAL mode"
    assert ctx["decisions"][0]["why"] == "Better concurrency"


def test_blueprint_persists(tmp_path: Path, mongo_db):
    vec_path = tmp_path / "vec.db"
    blueprint = {"sections": [{"title": "Overview", "widgets": []}]}

    c1 = _make_container(mongo_db, vec_path)
    c1.dashboards.save_blueprint(blueprint)

    c2 = _make_container(mongo_db, vec_path)
    result = c2.dashboards.get_blueprint()
    assert result is not None
    assert result["blueprint"] == blueprint


def test_resolved_data_persists(tmp_path: Path, mongo_db):
    vec_path = tmp_path / "vec.db"
    blueprint = {"sections": []}
    resolved = {"metrics": {"active_streams": 3}}

    c1 = _make_container(mongo_db, vec_path)
    c1.dashboards.save_blueprint(blueprint)
    c1.dashboards.update_resolved_data(resolved)

    c2 = _make_container(mongo_db, vec_path)
    result = c2.dashboards.get_blueprint()
    assert result is not None
    assert result["resolved_data"] == resolved


def test_text_search_survives(tmp_path: Path, mongo_db):
    vec_path = tmp_path / "vec.db"
    c1 = _make_container(mongo_db, vec_path)
    stream = c1.stream_service.create_stream("Stream", ["repo"])
    c1.stream_service.add_update(stream.id, "Implemented xylophone orchestration layer", "Xylophone update")

    c2 = _make_container(mongo_db, vec_path)
    results = c2.search_service.search("xylophone")
    assert len(results) >= 1
    assert any("xylophone" in r.content.lower() or "xylophone" in r.summary.lower() for r in results)


def test_checkpoint_persists(tmp_path: Path, mongo_db):
    vec_path = tmp_path / "vec.db"
    c1 = _make_container(mongo_db, vec_path)
    c1.stream_service.save_checkpoint("2026-W11", "Weekly summary content", stream_ids=["abc123"])

    c2 = _make_container(mongo_db, vec_path)
    cp = c2.stream_service.get_checkpoint("2026-W11")
    assert cp is not None
    assert cp.week_of == "2026-W11"
    assert cp.content == "Weekly summary content"
    assert cp.stream_ids == ["abc123"]
