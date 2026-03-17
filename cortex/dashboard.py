from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from cortex.transforms import apply_transform

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_watcher_task: asyncio.Task | None = None
_sse_clients: list[asyncio.Queue] = []


def _get_state():
    from cortex.api import _get_state as api_get_state
    return api_get_state()


def _load_schema() -> dict | None:
    from pathlib import Path
    schema_path = Path(__file__).parent.parent / "web" / "canvas-schema.json"
    if not schema_path.exists():
        return None
    return json.loads(schema_path.read_text())


@router.post("/blueprint", status_code=201)
async def post_blueprint(request: Request):
    body = await request.json()
    schema = _load_schema()
    if schema:
        current_version = schema.get("version", 1)
        bp_version = body.get("schema_version")
        if bp_version != current_version:
            return JSONResponse(
                status_code=422,
                content={
                    "detail": f"schema_version mismatch: blueprint has {bp_version}, current is {current_version}. Fetch GET /api/dashboard/schema to get the latest schema and use schema_version: {current_version} in your blueprint.",
                    "current_version": current_version,
                    "schema": schema,
                },
            )
    state = _get_state()
    result = state.save_blueprint(body)
    resolved = _resolve_blueprint(body)
    state.update_resolved_data(resolved)
    _restart_watcher(state, body)
    await _notify_sse()
    return result


@router.get("/schema")
async def get_schema():
    schema = _load_schema()
    if not schema:
        return JSONResponse(status_code=404, content={"detail": "Schema not found"})
    return JSONResponse(content=schema)


@router.get("/blueprint")
async def get_blueprint():
    state = _get_state()
    result = state.get_blueprint()
    if not result:
        return JSONResponse(status_code=404, content={"detail": "No blueprint"})
    return result


@router.get("/resolved")
async def get_resolved():
    state = _get_state()
    bp = state.get_blueprint()
    if not bp:
        return JSONResponse(status_code=404, content={"detail": "No blueprint"})
    if bp["resolved_data"]:
        return bp["resolved_data"]
    return _resolve_blueprint(bp["blueprint"])


@router.get("/snapshots")
async def get_snapshots():
    state = _get_state()
    return state.get_dashboard_snapshots()


@router.get("/checkpoints")
async def get_checkpoint(week_of: str | None = None):
    state = _get_state()
    cp = state.get_checkpoint(week_of)
    if not cp:
        return JSONResponse(status_code=404, content={"detail": "No checkpoint"})
    return {
        "id": cp.id,
        "week_of": cp.week_of,
        "content": cp.content,
        "stream_ids": cp.stream_ids,
        "created_at": cp.created_at.isoformat(),
    }


@router.get("/events")
async def sse():
    queue: asyncio.Queue = asyncio.Queue()
    _sse_clients.append(queue)

    async def event_stream():
        try:
            while True:
                data = await queue.get()
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _sse_clients.remove(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


async def _notify_sse():
    for q in _sse_clients:
        await q.put("updated")


async def notify_sse():
    await _notify_sse()


@router.post("/notify", status_code=204)
async def notify():
    await _notify_sse()


@router.get("/open")
async def open_url(url: str):
    """Open a URL in the system default browser (bypasses iTerm2 embedded browser)."""
    if not url.startswith(("https://", "http://", "linear://", "notion://", "slack://", "figma://", "vscode://", "granola://")):
        return JSONResponse(status_code=400, content={"detail": "Invalid URL"})
    await asyncio.to_thread(subprocess.run, ["open", url])
    return JSONResponse(status_code=200, content={"status": "opened"})


def _resolve_blueprint(blueprint: dict) -> dict:
    resolved = {**blueprint, "resolved_at": datetime.now(timezone.utc).isoformat()}
    resolved_sections = []
    for section in blueprint.get("sections", []):
        resolved_section = {**section}
        if "source" in section:
            resolved_section["_status"] = "pending"
        resolved_sections.append(resolved_section)
    resolved["sections"] = resolved_sections
    return resolved


def _restart_watcher(state, blueprint: dict):
    global _watcher_task
    if _watcher_task and not _watcher_task.done():
        _watcher_task.cancel()
    try:
        loop = asyncio.get_running_loop()
        _watcher_task = loop.create_task(_run_watchers(state, blueprint))
    except RuntimeError:
        pass


async def _run_watchers(state, blueprint: dict):
    sources = []
    for section in blueprint.get("sections", []):
        if "source" in section:
            sources.append({"section_id": section["id"], **section["source"]})
        for idx, item in enumerate(section.get("items", [])):
            if "source" in item:
                sources.append({"section_id": section["id"], "item_index": idx, **item["source"]})

    if not sources:
        return

    while True:
        bp_record = state.get_blueprint()
        if not bp_record:
            return
        resolved = bp_record.get("resolved_data") or _resolve_blueprint(bp_record["blueprint"])

        changed = False
        for src in sources:
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    src["command"],
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0 and result.stdout.strip():
                    data = json.loads(result.stdout)
                    transformed = apply_transform(src.get("transform", "passthrough"), data)
                    for s in resolved.get("sections", []):
                        if s["id"] == src["section_id"]:
                            if "item_index" in src:
                                s.setdefault("items", [])
                                if src["item_index"] < len(s["items"]):
                                    s["items"][src["item_index"]]["_resolved"] = transformed
                            else:
                                s["_resolved"] = transformed
                                s["_status"] = "ok"
                            changed = True
            except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
                log.warning("Watcher %s failed: %s", src.get("section_id"), e)
                for s in resolved.get("sections", []):
                    if s["id"] == src["section_id"]:
                        s["_status"] = "error"
                        s["_error"] = str(e)
                        changed = True

        if changed:
            resolved["resolved_at"] = datetime.now(timezone.utc).isoformat()
            state.update_resolved_data(resolved)
            await _notify_sse()

        min_interval = min((s.get("interval", 60) for s in sources), default=60)
        await asyncio.sleep(min_interval)
