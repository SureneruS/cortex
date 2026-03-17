from cortex.state import StateManager


def test_list_streams_empty(api_client):
    resp = api_client.get("/api/streams")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_streams(api_client, state: StateManager):
    state.create_stream("Stream A", ["repo-a"])
    state.create_stream("Stream B", ["repo-b"])
    resp = api_client.get("/api/streams")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_list_streams_filter_completed(api_client, state: StateManager):
    s = state.create_stream("Done", ["repo"])
    state.complete_stream(s.id, "Finished")
    resp = api_client.get("/api/streams?status=completed")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["status"] == "completed"


def test_create_stream(api_client):
    resp = api_client.post("/api/streams", json={"title": "New", "repos": ["repo"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New"
    assert data["id"]


def test_get_stream_context(api_client, state: StateManager):
    s = state.create_stream("Test", ["repo"])
    state.add_update(s.id, "content", "summary")
    state.add_decision(s.id, "what", "why")
    resp = api_client.get(f"/api/streams/{s.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["stream"]["title"] == "Test"
    assert len(data["updates"]) == 1
    assert len(data["decisions"]) == 1


def test_get_stream_not_found(api_client):
    resp = api_client.get("/api/streams/nonexistent")
    assert resp.status_code == 404


def test_patch_stream(api_client, state: StateManager):
    s = state.create_stream("Old title", ["repo"])
    resp = api_client.patch(f"/api/streams/{s.id}", json={"title": "New title"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "New title"


def test_delete_stream(api_client, state: StateManager):
    s = state.create_stream("To delete", ["repo"])
    resp = api_client.delete(f"/api/streams/{s.id}")
    assert resp.status_code == 204
    assert api_client.get(f"/api/streams/{s.id}").status_code == 404


def test_complete_stream(api_client, state: StateManager):
    s = state.create_stream("To complete", ["repo"])
    resp = api_client.post(f"/api/streams/{s.id}/complete", json={"summary": "Done"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_create_update(api_client, state: StateManager):
    s = state.create_stream("Test", ["repo"])
    resp = api_client.post(
        f"/api/streams/{s.id}/updates", json={"content": "Full content", "summary": "Short"}
    )
    assert resp.status_code == 200
    assert resp.json()["summary"] == "Short"


def test_patch_update(api_client, state: StateManager):
    s = state.create_stream("Test", ["repo"])
    u = state.add_update(s.id, "old content", "old summary")
    resp = api_client.patch(f"/api/updates/{u.id}", json={"summary": "new summary"})
    assert resp.status_code == 200
    assert resp.json()["summary"] == "new summary"


def test_delete_update(api_client, state: StateManager):
    s = state.create_stream("Test", ["repo"])
    u = state.add_update(s.id, "content", "summary")
    resp = api_client.delete(f"/api/updates/{u.id}")
    assert resp.status_code == 204


def test_create_decision(api_client, state: StateManager):
    s = state.create_stream("Test", ["repo"])
    resp = api_client.post(
        f"/api/streams/{s.id}/decisions", json={"what": "Use X", "why": "Because Y"}
    )
    assert resp.status_code == 200
    assert resp.json()["what"] == "Use X"


def test_patch_decision(api_client, state: StateManager):
    s = state.create_stream("Test", ["repo"])
    d = state.add_decision(s.id, "old what", "old why")
    resp = api_client.patch(f"/api/decisions/{d.id}", json={"what": "new what"})
    assert resp.status_code == 200
    assert resp.json()["what"] == "new what"


def test_delete_decision(api_client, state: StateManager):
    s = state.create_stream("Test", ["repo"])
    d = state.add_decision(s.id, "what", "why")
    resp = api_client.delete(f"/api/decisions/{d.id}")
    assert resp.status_code == 204


def test_link_session(api_client, state: StateManager):
    s = state.create_stream("Test", ["repo"])
    resp = api_client.post(f"/api/streams/{s.id}/sessions", json={"session_id": "sess-001"})
    assert resp.status_code == 200


def test_unlink_session(api_client, state: StateManager):
    s = state.create_stream("Test", ["repo"])
    state.link_session("sess-001", s.id)
    resp = api_client.delete("/api/sessions/sess-001", params={"stream_id": s.id})
    assert resp.status_code == 204


def test_move_session(api_client, state: StateManager):
    s1 = state.create_stream("A", ["repo"])
    s2 = state.create_stream("B", ["repo"])
    state.link_session("sess-001", s1.id)
    resp = api_client.patch(
        "/api/sessions/sess-001", json={"from_stream_id": s1.id, "to_stream_id": s2.id}
    )
    assert resp.status_code == 200


def test_activity(api_client, state: StateManager):
    s = state.create_stream("Test", ["repo"])
    state.add_update(s.id, "content", "summary")
    state.add_decision(s.id, "what", "why")
    resp = api_client.get("/api/activity")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_search(api_client, state: StateManager):
    s = state.create_stream("Test", ["repo"])
    state.add_update(s.id, "Deployed auth module with OAuth2", "Auth deployed")
    resp = api_client.get("/api/search", params={"q": "auth"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
