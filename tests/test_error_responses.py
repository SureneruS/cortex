from cortex.mongo_state import MongoStateManager


def test_update_nonexistent_stream(api_client):
    resp = api_client.post("/api/streams/fake-id/updates", json={"content": "x", "summary": "x"})
    assert resp.status_code == 409


def test_decision_nonexistent_stream(api_client):
    resp = api_client.post("/api/streams/fake-id/decisions", json={"what": "x", "why": "x"})
    assert resp.status_code == 409


def test_duplicate_session_link(api_client, state: MongoStateManager):
    s = state.create_stream("Test", ["repo"])
    resp1 = api_client.post(f"/api/streams/{s.id}/sessions", json={"session_id": "sess-1"})
    assert resp1.status_code == 200
    resp2 = api_client.post(f"/api/streams/{s.id}/sessions", json={"session_id": "sess-1"})
    assert resp2.status_code == 200


def test_session_link_nonexistent_stream(api_client):
    resp = api_client.post("/api/streams/fake-id/sessions", json={"session_id": "sess-1"})
    assert resp.status_code == 409


def test_patch_nonexistent_update(api_client):
    resp = api_client.patch("/api/updates/fake-id", json={"content": "new"})
    assert resp.status_code == 404


def test_patch_nonexistent_decision(api_client):
    resp = api_client.patch("/api/decisions/fake-id", json={"what": "new"})
    assert resp.status_code == 404


def test_invalid_update_body(api_client, state: MongoStateManager):
    s = state.create_stream("Test", ["repo"])
    resp = api_client.post(f"/api/streams/{s.id}/updates", json={"summary": "missing content"})
    assert resp.status_code == 422


def test_invalid_decision_body(api_client, state: MongoStateManager):
    s = state.create_stream("Test", ["repo"])
    resp = api_client.post(f"/api/streams/{s.id}/decisions", json={"why": "missing what"})
    assert resp.status_code == 422


def test_delete_nonexistent_stream(api_client):
    resp = api_client.delete("/api/streams/fake-id")
    assert resp.status_code == 204
