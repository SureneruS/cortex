from cortex.repositories.dashboard_repo import MongoDashboardRepository


def test_save_blueprint(dashboards: MongoDashboardRepository):
    bp = {"title": "Test", "sections": []}
    result = dashboards.save_blueprint(bp)
    assert result["blueprint"] == bp
    assert result["resolved_data"] is None
    assert "id" in result
    assert "created_at" in result


def test_get_blueprint(dashboards: MongoDashboardRepository):
    dashboards.save_blueprint({"title": "Test", "sections": []})
    result = dashboards.get_blueprint()
    assert result is not None
    assert result["blueprint"]["title"] == "Test"


def test_get_blueprint_empty(dashboards: MongoDashboardRepository):
    result = dashboards.get_blueprint()
    assert result is None


def test_save_blueprint_overwrites(dashboards: MongoDashboardRepository):
    dashboards.save_blueprint({"title": "First", "sections": []})
    dashboards.save_blueprint({"title": "Second", "sections": []})
    result = dashboards.get_blueprint()
    assert result["blueprint"]["title"] == "Second"


def test_update_resolved_data(dashboards: MongoDashboardRepository):
    dashboards.save_blueprint({"title": "Test", "sections": []})
    resolved = {"title": "Test", "sections": [{"id": "x", "data": [1, 2]}]}
    dashboards.update_resolved_data(resolved)
    result = dashboards.get_blueprint()
    assert result["resolved_data"] == resolved


def test_save_blueprint_creates_snapshot(dashboards: MongoDashboardRepository):
    dashboards.save_blueprint({"title": "Test", "sections": []})
    snapshots = dashboards.get_snapshots(limit=10)
    assert len(snapshots) == 1
    assert snapshots[0]["snapshot_type"] == "blueprint"


def test_update_resolved_creates_snapshot(dashboards: MongoDashboardRepository):
    dashboards.save_blueprint({"title": "Test", "sections": []})
    dashboards.update_resolved_data({"title": "Test", "sections": []})
    snapshots = dashboards.get_snapshots(limit=10)
    assert len(snapshots) == 2
    assert snapshots[0]["snapshot_type"] == "resolved"
