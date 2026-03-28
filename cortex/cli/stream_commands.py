from __future__ import annotations

import json

import click

from cortex.cli import _get_state, _error_exit, _json_out


@click.group()
def stream() -> None:
    """Manage work streams, updates, and decisions."""
    pass


@stream.command("list")
@click.option("--status", default="active", help="Filter by status (active|completed|all)")
def stream_list(status: str) -> None:
    """List streams."""
    with _get_state() as state:
        streams = state.list_streams(status=status)
    _json_out([
        {
            "id": s.id, "title": s.title, "repos": s.repos,
            "status": s.status, "summary": s.summary,
            "metadata": s.metadata, "updated_at": s.updated_at.isoformat(),
        }
        for s in streams
    ])


@stream.command("get")
@click.argument("stream_id")
def stream_get(stream_id: str) -> None:
    """Get full stream context (updates, decisions, sessions)."""
    with _get_state() as state:
        ctx = state.get_stream_context(stream_id)
    if not ctx:
        _error_exit(f"Stream {stream_id} not found")
    _json_out(ctx)


@stream.command("create")
@click.option("--title", required=True, help="Stream title")
@click.option("--repos", required=True, help="Comma-separated repo names")
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
def stream_create(title: str, repos: str, metadata_json: str | None) -> None:
    """Create a new stream."""
    metadata = json.loads(metadata_json) if metadata_json else None
    with _get_state() as state:
        s = state.create_stream(title, repos.split(","), metadata=metadata)
    _json_out({"id": s.id, "title": s.title})


@stream.command("update")
@click.argument("stream_id")
@click.option("--title", default=None)
@click.option("--status", "new_status", default=None)
@click.option("--repos", default=None, help="Comma-separated repo names")
@click.option("--summary", default=None)
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
@click.option("--replace-metadata", is_flag=True, help="Replace metadata instead of merging")
def stream_update(
    stream_id: str, title: str | None, new_status: str | None,
    repos: str | None, summary: str | None, metadata_json: str | None,
    replace_metadata: bool,
) -> None:
    """Update a stream."""
    metadata = json.loads(metadata_json) if metadata_json else None
    repos_list = repos.split(",") if repos else None
    with _get_state() as state:
        try:
            s = state.update_stream(
                stream_id, title=title, status=new_status, repos=repos_list,
                summary=summary, metadata=metadata, merge_metadata=not replace_metadata,
            )
        except ValueError as e:
            _error_exit(str(e))
    if s is None:
        _error_exit(f"Stream {stream_id} not found")
    _json_out({"id": s.id, "status": s.status, "updated_at": s.updated_at.isoformat()})


@stream.command("complete")
@click.argument("stream_id")
@click.option("--summary", required=True, help="Completion summary")
def stream_complete(stream_id: str, summary: str) -> None:
    """Mark a stream as completed."""
    with _get_state() as state:
        state.complete_stream(stream_id, summary)
    _json_out({"completed": stream_id, "summary": summary})


@stream.command("delete")
@click.argument("entry_id")
@click.option("--type", "entry_type", required=True, type=click.Choice(["stream", "update", "decision"]))
def stream_delete(entry_id: str, entry_type: str) -> None:
    """Delete a stream, update, or decision."""
    with _get_state() as state:
        if entry_type == "update":
            state.delete_update(entry_id)
        elif entry_type == "decision":
            state.delete_decision(entry_id)
        elif entry_type == "stream":
            state.delete_stream(entry_id)
    _json_out({"deleted": entry_id, "type": entry_type})


@stream.command("log")
@click.argument("stream_id")
@click.option("--content", required=True, help="Update content")
@click.option("--summary", required=True, help="Short summary")
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
def stream_log(stream_id: str, content: str, summary: str, metadata_json: str | None) -> None:
    """Log a progress update to a stream."""
    metadata = json.loads(metadata_json) if metadata_json else None
    with _get_state() as state:
        try:
            u = state.add_update(stream_id, content, summary, metadata=metadata)
        except ValueError as e:
            _error_exit(str(e))
    _json_out({"id": u.id, "summary": u.summary})


@stream.command("decide")
@click.argument("stream_id")
@click.option("--what", required=True, help="What was decided")
@click.option("--why", required=True, help="Why this decision")
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
def stream_decide(stream_id: str, what: str, why: str, metadata_json: str | None) -> None:
    """Log a decision to a stream."""
    metadata = json.loads(metadata_json) if metadata_json else None
    with _get_state() as state:
        try:
            d = state.add_decision(stream_id, what, why, metadata=metadata)
        except ValueError as e:
            _error_exit(str(e))
    _json_out({"id": d.id, "what": d.what})


@stream.command("edit")
@click.argument("entry_id")
@click.option("--type", "entry_type", required=True, type=click.Choice(["update", "decision"]))
@click.option("--content", default=None)
@click.option("--summary", default=None)
@click.option("--what", default=None)
@click.option("--why", default=None)
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
def stream_edit(
    entry_id: str, entry_type: str, content: str | None,
    summary: str | None, what: str | None, why: str | None,
    metadata_json: str | None,
) -> None:
    """Edit an existing update or decision."""
    metadata = json.loads(metadata_json) if metadata_json else None
    with _get_state() as state:
        if entry_type == "update":
            result = state.edit_update(entry_id, content=content, summary=summary, metadata=metadata)
        else:
            result = state.edit_decision(entry_id, what=what, why=why, metadata=metadata)
    if result is None:
        _error_exit(f"{entry_type} {entry_id} not found")
    _json_out({"id": result.id, "type": entry_type, "edited": True})


@stream.command("search")
@click.argument("query")
def stream_search(query: str) -> None:
    """Search across updates, decisions, and checkpoints."""
    from cortex.models import Checkpoint, Decision, Update

    with _get_state() as state:
        results = state.search(query)
    items = []
    for r in results:
        if isinstance(r, Update):
            items.append({"type": "update", "id": r.id, "stream_id": r.stream_id, "content": r.content, "summary": r.summary, "created_at": r.created_at.isoformat()})
        elif isinstance(r, Decision):
            items.append({"type": "decision", "id": r.id, "stream_id": r.stream_id, "what": r.what, "why": r.why, "created_at": r.created_at.isoformat()})
        elif isinstance(r, Checkpoint):
            items.append({"type": "checkpoint", "id": r.id, "week_of": r.week_of, "content": r.content[:200], "created_at": r.created_at.isoformat()})
    _json_out({"query": query, "results": items})


@stream.command("link")
@click.argument("session_id")
@click.argument("stream_id")
@click.option("--repo", default="", help="Repository name")
@click.option("--branch", default="", help="Branch name")
def stream_link(session_id: str, stream_id: str, repo: str, branch: str) -> None:
    """Link a session to a stream."""
    with _get_state() as state:
        try:
            state.link_session(session_id, stream_id, repo=repo, branch=branch)
        except ValueError as e:
            _error_exit(str(e))
    _json_out({"linked": True, "session_id": session_id, "stream_id": stream_id})
