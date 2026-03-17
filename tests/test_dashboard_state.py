from cortex.state import StateManager


def test_save_blueprint(state: StateManager):
    bp = {"title": "Test", "sections": []}
    result = state.save_blueprint(bp)
    assert result["blueprint"] == bp
    assert result["resolved_data"] is None
    assert "id" in result
    assert "created_at" in result


def test_get_blueprint(state: StateManager):
    state.save_blueprint({"title": "Test", "sections": []})
    result = state.get_blueprint()
    assert result is not None
    assert result["blueprint"]["title"] == "Test"


def test_get_blueprint_empty(state: StateManager):
    result = state.get_blueprint()
    assert result is None


def test_save_blueprint_overwrites(state: StateManager):
    state.save_blueprint({"title": "First", "sections": []})
    state.save_blueprint({"title": "Second", "sections": []})
    result = state.get_blueprint()
    assert result["blueprint"]["title"] == "Second"


def test_update_resolved_data(state: StateManager):
    state.save_blueprint({"title": "Test", "sections": []})
    resolved = {"title": "Test", "sections": [{"id": "x", "data": [1, 2]}]}
    state.update_resolved_data(resolved)
    result = state.get_blueprint()
    assert result["resolved_data"] == resolved


def test_save_blueprint_creates_snapshot(state: StateManager):
    state.save_blueprint({"title": "Test", "sections": []})
    snapshots = state.get_dashboard_snapshots(limit=10)
    assert len(snapshots) == 1
    assert snapshots[0]["snapshot_type"] == "blueprint"


def test_update_resolved_creates_snapshot(state: StateManager):
    state.save_blueprint({"title": "Test", "sections": []})
    state.update_resolved_data({"title": "Test", "sections": []})
    snapshots = state.get_dashboard_snapshots(limit=10)
    assert len(snapshots) == 2
    assert snapshots[0]["snapshot_type"] == "resolved"
