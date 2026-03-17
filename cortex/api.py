from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cortex.config import load_config
from cortex.dashboard import router as dashboard_router
from cortex.state import StateManager

app = FastAPI(title="Cortex API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_state: StateManager | None = None
_loop = None


def _wire_sse_callback(state: StateManager) -> None:
    """Wire StateManager.on_mutation to push SSE events to dashboard clients."""
    from cortex.dashboard import notify_sse

    def _on_mutation():
        if _loop is None:
            return
        _loop.call_soon_threadsafe(lambda: _loop.create_task(notify_sse()))

    state.on_mutation = _on_mutation


@app.on_event("startup")
async def _capture_loop():
    import asyncio

    global _loop
    _loop = asyncio.get_running_loop()
    # Wire callback now that we have the loop
    _get_state()


def _get_state() -> StateManager:
    global _state
    if _state is None:
        config = load_config()
        _state = StateManager(config.resolved_db_path)
        _state.init_db()
        _wire_sse_callback(_state)
    return _state


def _serialize_stream(s):
    return {
        "id": s.id,
        "title": s.title,
        "repos": s.repos,
        "status": s.status,
        "summary": s.summary,
        "metadata": s.metadata,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
    }


class CreateStreamRequest(BaseModel):
    title: str
    repos: list[str]
    metadata: dict | None = None


class PatchStreamRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    repos: list[str] | None = None
    summary: str | None = None
    metadata: dict | None = None


class CompleteStreamRequest(BaseModel):
    summary: str


@app.get("/api/streams")
def list_streams(status: str = "active"):
    state = _get_state()
    if status == "all":
        streams = state.list_streams(status="active") + state.list_streams(status="completed")
    else:
        streams = state.list_streams(status=status)
    return [_serialize_stream(s) for s in streams]


@app.post("/api/streams")
def create_stream(req: CreateStreamRequest):
    state = _get_state()
    s = state.create_stream(req.title, req.repos, metadata=req.metadata)
    return _serialize_stream(s)


@app.get("/api/streams/{stream_id}")
def get_stream(stream_id: str):
    state = _get_state()
    ctx = state.get_stream_context(stream_id)
    if not ctx:
        raise HTTPException(404, "Stream not found")
    return ctx


@app.patch("/api/streams/{stream_id}")
def patch_stream(stream_id: str, req: PatchStreamRequest):
    state = _get_state()
    try:
        updated = state.update_stream(
            stream_id,
            title=req.title,
            status=req.status,
            repos=req.repos,
            summary=req.summary,
            metadata=req.metadata,
        )
    except ValueError as e:
        raise HTTPException(409, str(e))
    if not updated:
        raise HTTPException(404, "Stream not found")
    return _serialize_stream(updated)


@app.delete("/api/streams/{stream_id}")
def delete_stream(stream_id: str):
    state = _get_state()
    state.delete_stream(stream_id)
    return Response(status_code=204)


@app.post("/api/streams/{stream_id}/complete")
def complete_stream(stream_id: str, req: CompleteStreamRequest):
    state = _get_state()
    stream = state.get_stream(stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")
    state.complete_stream(stream_id, req.summary)
    updated = state.get_stream(stream_id)
    return _serialize_stream(updated)


class CreateUpdateRequest(BaseModel):
    content: str
    summary: str
    metadata: dict | None = None


class PatchUpdateRequest(BaseModel):
    content: str | None = None
    summary: str | None = None
    metadata: dict | None = None


class CreateDecisionRequest(BaseModel):
    what: str
    why: str
    metadata: dict | None = None


class PatchDecisionRequest(BaseModel):
    what: str | None = None
    why: str | None = None
    metadata: dict | None = None


class LinkSessionRequest(BaseModel):
    session_id: str
    repo: str = ""
    branch: str = ""


class MoveSessionRequest(BaseModel):
    from_stream_id: str
    to_stream_id: str


# --- Updates ---


@app.post("/api/streams/{stream_id}/updates")
def create_update(stream_id: str, req: CreateUpdateRequest):
    state = _get_state()
    try:
        u = state.add_update(stream_id, req.content, req.summary, metadata=req.metadata)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {
        "id": u.id,
        "stream_id": u.stream_id,
        "content": u.content,
        "summary": u.summary,
        "created_at": u.created_at.isoformat(),
        "metadata": u.metadata,
    }


@app.patch("/api/updates/{update_id}")
def patch_update(update_id: str, req: PatchUpdateRequest):
    state = _get_state()
    u = state.edit_update(
        update_id, content=req.content, summary=req.summary, metadata=req.metadata
    )
    if not u:
        raise HTTPException(404, "Update not found")
    return {
        "id": u.id,
        "stream_id": u.stream_id,
        "content": u.content,
        "summary": u.summary,
        "created_at": u.created_at.isoformat(),
        "metadata": u.metadata,
    }


@app.delete("/api/updates/{update_id}")
def delete_update(update_id: str):
    state = _get_state()
    state.delete_update(update_id)
    return Response(status_code=204)


# --- Decisions ---


@app.post("/api/streams/{stream_id}/decisions")
def create_decision(stream_id: str, req: CreateDecisionRequest):
    state = _get_state()
    try:
        d = state.add_decision(stream_id, req.what, req.why, metadata=req.metadata)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {
        "id": d.id,
        "stream_id": d.stream_id,
        "what": d.what,
        "why": d.why,
        "created_at": d.created_at.isoformat(),
        "metadata": d.metadata,
    }


@app.patch("/api/decisions/{decision_id}")
def patch_decision(decision_id: str, req: PatchDecisionRequest):
    state = _get_state()
    d = state.edit_decision(decision_id, what=req.what, why=req.why, metadata=req.metadata)
    if not d:
        raise HTTPException(404, "Decision not found")
    return {
        "id": d.id,
        "stream_id": d.stream_id,
        "what": d.what,
        "why": d.why,
        "created_at": d.created_at.isoformat(),
        "metadata": d.metadata,
    }


@app.delete("/api/decisions/{decision_id}")
def delete_decision(decision_id: str):
    state = _get_state()
    state.delete_decision(decision_id)
    return Response(status_code=204)


# --- Sessions ---


@app.post("/api/streams/{stream_id}/sessions")
def link_session(stream_id: str, req: LinkSessionRequest):
    state = _get_state()
    try:
        state.link_session(req.session_id, stream_id, repo=req.repo, branch=req.branch)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"status": "linked"}


@app.delete("/api/sessions/{session_id}")
def unlink_session(session_id: str, stream_id: str):
    state = _get_state()
    state.unlink_session(session_id, stream_id)
    return Response(status_code=204)


@app.patch("/api/sessions/{session_id}")
def move_session(session_id: str, req: MoveSessionRequest):
    state = _get_state()
    state.move_session(session_id, req.from_stream_id, req.to_stream_id)
    return {"status": "moved"}


# --- Activity & Search ---


@app.get("/api/activity")
def activity(limit: int = 50, active_only: bool = False):
    state = _get_state()
    return state.get_recent_activity(limit=limit, active_only=active_only)


@app.get("/api/sessions")
def list_sessions(limit: int = 50, active_only: bool = False):
    state = _get_state()
    if active_only:
        rows = state._conn.execute(
            "SELECT s.session_id, s.stream_id, s.repo, s.branch, s.status, s.created_at "
            "FROM sessions s JOIN streams st ON s.stream_id = st.id "
            "WHERE st.status = 'active' ORDER BY s.created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = state._conn.execute(
            "SELECT session_id, stream_id, repo, branch, status, created_at FROM sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/search")
def search(q: str):
    state = _get_state()
    results = state.search(q)
    items = []
    for r in results:
        if hasattr(r, "summary"):  # Update
            items.append(
                {
                    "type": "update",
                    "id": r.id,
                    "stream_id": r.stream_id,
                    "content": r.content,
                    "summary": r.summary,
                    "created_at": r.created_at.isoformat(),
                }
            )
        elif hasattr(r, "what"):  # Decision
            items.append(
                {
                    "type": "decision",
                    "id": r.id,
                    "stream_id": r.stream_id,
                    "what": r.what,
                    "why": r.why,
                    "created_at": r.created_at.isoformat(),
                }
            )
        elif hasattr(r, "week_of"):  # Checkpoint
            items.append(
                {
                    "type": "checkpoint",
                    "id": r.id,
                    "week_of": r.week_of,
                    "content": r.content,
                    "created_at": r.created_at.isoformat(),
                }
            )
    return items


app.include_router(dashboard_router)

_web_out = Path(__file__).parent.parent / "web" / "out"
if _web_out.exists():
    app.mount("/", StaticFiles(directory=str(_web_out), html=True), name="static")
