from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cortex.container import get_container
from cortex.dashboard import router as dashboard_router

app = FastAPI(title="Cortex API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_loop = None


@app.on_event("startup")
async def _capture_loop():
    import asyncio

    global _loop
    _loop = asyncio.get_running_loop()
    _wire_sse_callback()


def _wire_sse_callback() -> None:
    """Wire StreamService.on_mutation to push SSE events to dashboard clients."""
    from cortex.dashboard import notify_sse

    def _on_mutation():
        if _loop is None:
            return
        _loop.call_soon_threadsafe(lambda: _loop.create_task(notify_sse()))

    get_container().stream_service._on_mutation = _on_mutation


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
    svc = get_container().stream_service
    if status == "all":
        streams = svc.list_streams(status="active") + svc.list_streams(status="completed")
    else:
        streams = svc.list_streams(status=status)
    return [_serialize_stream(s) for s in streams]


@app.post("/api/streams")
def create_stream(req: CreateStreamRequest):
    svc = get_container().stream_service
    s = svc.create_stream(req.title, req.repos, metadata=req.metadata)
    return _serialize_stream(s)


@app.get("/api/streams/{stream_id}")
def get_stream(stream_id: str):
    svc = get_container().stream_service
    ctx = svc.get_stream_context(stream_id)
    if not ctx:
        raise HTTPException(404, "Stream not found")
    return ctx


@app.patch("/api/streams/{stream_id}")
def patch_stream(stream_id: str, req: PatchStreamRequest):
    svc = get_container().stream_service
    try:
        updated = svc.update_stream(
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
    svc = get_container().stream_service
    svc.delete_stream(stream_id)
    return Response(status_code=204)


@app.post("/api/streams/{stream_id}/complete")
def complete_stream(stream_id: str, req: CompleteStreamRequest):
    svc = get_container().stream_service
    stream = svc.get_stream(stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")
    svc.complete_stream(stream_id, req.summary)
    updated = svc.get_stream(stream_id)
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
    svc = get_container().stream_service
    try:
        u = svc.add_update(stream_id, req.content, req.summary, metadata=req.metadata)
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
    svc = get_container().stream_service
    u = svc.edit_update(
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
    svc = get_container().stream_service
    svc.delete_update(update_id)
    return Response(status_code=204)


# --- Decisions ---


@app.post("/api/streams/{stream_id}/decisions")
def create_decision(stream_id: str, req: CreateDecisionRequest):
    svc = get_container().stream_service
    try:
        d = svc.add_decision(stream_id, req.what, req.why, metadata=req.metadata)
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
    svc = get_container().stream_service
    d = svc.edit_decision(decision_id, what=req.what, why=req.why, metadata=req.metadata)
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
    svc = get_container().stream_service
    svc.delete_decision(decision_id)
    return Response(status_code=204)


# --- Sessions ---


@app.post("/api/streams/{stream_id}/sessions")
def link_session(stream_id: str, req: LinkSessionRequest):
    svc = get_container().stream_service
    try:
        svc.link_session(req.session_id, stream_id, repo=req.repo, branch=req.branch)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"status": "linked"}


@app.delete("/api/sessions/{session_id}")
def unlink_session(session_id: str, stream_id: str):
    svc = get_container().stream_service
    svc.unlink_session(session_id, stream_id)
    return Response(status_code=204)


@app.patch("/api/sessions/{session_id}")
def move_session(session_id: str, req: MoveSessionRequest):
    svc = get_container().stream_service
    svc.move_session(session_id, req.from_stream_id, req.to_stream_id)
    return {"status": "moved"}


# --- Activity & Search ---


@app.get("/api/activity")
def activity(limit: int = 50, active_only: bool = False):
    svc = get_container().stream_service
    return svc.get_recent_activity(limit=limit, active_only=active_only)


@app.get("/api/sessions")
def list_sessions(limit: int = 50, active_only: bool = False):
    svc = get_container().stream_service
    return svc.list_sessions(limit=limit, active_only=active_only)


@app.get("/api/search")
def search(q: str):
    svc = get_container().search_service
    results = svc.search(q)
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
