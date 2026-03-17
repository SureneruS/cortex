from fastapi.testclient import TestClient


def test_post_blueprint(api_client: TestClient):
    bp = {"title": "Test", "sections": [{"id": "note", "type": "text", "content": "hi"}]}
    resp = api_client.post("/api/dashboard/blueprint", json=bp)
    assert resp.status_code == 201
    data = resp.json()
    assert data["blueprint"]["title"] == "Test"


def test_get_blueprint(api_client: TestClient):
    bp = {"title": "Test", "sections": []}
    api_client.post("/api/dashboard/blueprint", json=bp)
    resp = api_client.get("/api/dashboard/blueprint")
    assert resp.status_code == 200
    assert resp.json()["blueprint"]["title"] == "Test"


def test_get_blueprint_empty(api_client: TestClient):
    resp = api_client.get("/api/dashboard/blueprint")
    assert resp.status_code == 404


def test_get_resolved(api_client: TestClient):
    bp = {"title": "Test", "sections": [{"id": "note", "type": "text", "content": "hello"}]}
    api_client.post("/api/dashboard/blueprint", json=bp)
    resp = api_client.get("/api/dashboard/resolved")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sections"][0]["content"] == "hello"


def test_get_snapshots(api_client: TestClient):
    api_client.post("/api/dashboard/blueprint", json={"title": "T1", "sections": []})
    api_client.post("/api/dashboard/blueprint", json={"title": "T2", "sections": []})
    resp = api_client.get("/api/dashboard/snapshots")
    assert resp.status_code == 200
    snapshots = resp.json()
    assert len(snapshots) >= 2
    blueprint_snapshots = [s for s in snapshots if s["snapshot_type"] == "blueprint"]
    assert len(blueprint_snapshots) == 2
