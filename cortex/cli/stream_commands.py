from __future__ import annotations

import json

import click

from cortex.cli import JsonGroup, _error_exit, _json_out, _output, get_container


def _svc():
    return get_container().stream_service


def _resolve_or_exit(ref: str):
    stream = _svc().resolve_stream(ref)
    if not stream:
        _error_exit(f"Stream '{ref}' not found")
    return stream


@click.group(cls=JsonGroup)
def stream() -> None:
    """Manage work streams, updates, and decisions."""
    pass


@stream.command("list")
@click.option("--status", default="active", help="Filter by status (active|completed|all)")
def stream_list(status: str) -> None:
    """List streams."""
    streams = _svc().list_streams(status=status)
    data = [
        {
            "id": s.id, "name": s.name, "title": s.title, "repos": s.repos,
            "status": s.status, "summary": s.summary,
            "metadata": s.metadata, "updated_at": s.updated_at.isoformat(),
        }
        for s in streams
    ]

    def _fmt(items: list[dict]) -> None:
        from cortex.cli.formatters import print_table, relative_time, styled_status, truncate, val
        if not items:
            click.echo("No streams found.")
            return
        cols = [
            ("Name", {}),
            ("Title", {}),
            ("Status", {}),
            ("Repos", {}),
            ("Updated", {"justify": "right"}),
        ]
        rows = []
        for s in items:
            rows.append([
                val(s.get("name")),
                truncate(s.get("title"), 40),
                styled_status(s.get("status")),
                ", ".join(s.get("repos", [])),
                relative_time(s.get("updated_at")),
            ])
        print_table(cols, rows, count=len(items))

    _output(data, _fmt)


@stream.command("get")
@click.argument("ref")
def stream_get(ref: str) -> None:
    """Get full stream context (updates, decisions, sessions)."""
    s = _resolve_or_exit(ref)
    ctx = _svc().get_stream_context(s.id)
    if not ctx:
        _error_exit(f"Stream '{ref}' not found")

    def _fmt(data: dict) -> None:
        from cortex.cli.formatters import get_console, print_detail, relative_time, styled_status, truncate, val
        console = get_console()
        si = data.get("stream", {})
        fields = [
            ("Name", val(si.get("name"))),
            ("Title", val(si.get("title"))),
            ("ID", val(si.get("id"))),
            ("Status", styled_status(si.get("status"))),
            ("Repos", ", ".join(si.get("repos", []))),
            ("Updated", relative_time(si.get("updated_at"))),
        ]
        if si.get("summary"):
            fields.append(("Summary", truncate(si["summary"], 100)))
        print_detail(fields, title=val(si.get("name"), "Stream"))

        decisions = data.get("decisions", [])
        if decisions:
            console.print(f"\n[bold]Decisions ({len(decisions)}):[/]")
            for d in decisions:
                age = relative_time(d.get("created_at"))
                console.print(f"  [bold]•[/] {truncate(d.get('what', ''), 80)}  [dim]{age}[/]")
                if d.get("why"):
                    console.print(f"    [dim]Why:[/] {truncate(d['why'], 80)}")

        updates = data.get("updates", [])
        if updates:
            console.print(f"\n[bold]Updates ({len(updates)}):[/]")
            for u in updates[-10:]:
                age = relative_time(u.get("created_at"))
                console.print(f"  [bold]•[/] {truncate(u.get('summary', ''), 80)}  [dim]{age}[/]")

        sessions = data.get("sessions", [])
        if sessions:
            console.print(f"\n[bold]Linked sessions ({len(sessions)}):[/]")
            for sess in sessions:
                console.print(f"  {val(sess.get('name', sess.get('session_id', '?')))}")

    _output(ctx, _fmt)


@stream.command("create")
@click.option("--title", required=True, help="Stream title")
@click.option("--repos", required=True, help="Comma-separated repo names")
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
def stream_create(title: str, repos: str, metadata_json: str | None) -> None:
    """Create a new stream."""
    metadata = json.loads(metadata_json) if metadata_json else None
    s = _svc().create_stream(title, repos.split(","), metadata=metadata)
    data = {"id": s.id, "name": s.name, "title": s.title}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Stream created: {d['name']} — {d['title']}")

    _output(data, _fmt)


@stream.command("update")
@click.argument("ref")
@click.option("--title", default=None)
@click.option("--status", "new_status", default=None)
@click.option("--repos", default=None, help="Comma-separated repo names")
@click.option("--summary", default=None)
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
@click.option("--replace-metadata", is_flag=True, help="Replace metadata instead of merging")
def stream_update(
    ref: str, title: str | None, new_status: str | None,
    repos: str | None, summary: str | None, metadata_json: str | None,
    replace_metadata: bool,
) -> None:
    """Update a stream."""
    resolved = _resolve_or_exit(ref)
    metadata = json.loads(metadata_json) if metadata_json else None
    repos_list = repos.split(",") if repos else None
    try:
        s = _svc().update_stream(
            resolved.id, title=title, status=new_status, repos=repos_list,
            summary=summary, metadata=metadata, merge_metadata=not replace_metadata,
        )
    except ValueError as e:
        _error_exit(str(e))
    if s is None:
        _error_exit(f"Stream '{ref}' not found")
    data = {"id": s.id, "name": s.name, "status": s.status, "updated_at": s.updated_at.isoformat()}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok, styled_status
        print_ok(f"Stream updated: {d['name']} [{styled_status(d['status'])}]")

    _output(data, _fmt)


@stream.command("complete")
@click.argument("ref")
@click.option("--summary", required=True, help="Completion summary")
def stream_complete(ref: str, summary: str) -> None:
    """Mark a stream as completed."""
    resolved = _resolve_or_exit(ref)
    _svc().complete_stream(resolved.id, summary)
    data = {"completed": resolved.id, "name": resolved.name, "summary": summary}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Stream completed: {d['name']}")

    _output(data, _fmt)


@stream.command("delete")
@click.argument("entry_id")
@click.option("--type", "entry_type", required=True, type=click.Choice(["stream", "update", "decision"]))
def stream_delete(entry_id: str, entry_type: str) -> None:
    """Delete a stream, update, or decision."""
    svc = _svc()
    if entry_type == "update":
        svc.delete_update(entry_id)
    elif entry_type == "decision":
        svc.delete_decision(entry_id)
    elif entry_type == "stream":
        svc.delete_stream(entry_id)
    data = {"deleted": entry_id, "type": entry_type}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Deleted {d['type']}: {d['deleted']}")

    _output(data, _fmt)


@stream.command("log")
@click.argument("ref")
@click.option("--content", required=True, help="Update content")
@click.option("--summary", required=True, help="Short summary")
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
def stream_log(ref: str, content: str, summary: str, metadata_json: str | None) -> None:
    """Log a progress update to a stream."""
    resolved = _resolve_or_exit(ref)
    metadata = json.loads(metadata_json) if metadata_json else None
    try:
        u = _svc().add_update(resolved.id, content, summary, metadata=metadata)
    except ValueError as e:
        _error_exit(str(e))
    data = {"id": u.id, "summary": u.summary}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Logged: {d['summary']}")

    _output(data, _fmt)


@stream.command("decide")
@click.argument("ref")
@click.option("--what", required=True, help="What was decided")
@click.option("--why", required=True, help="Why this decision")
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
def stream_decide(ref: str, what: str, why: str, metadata_json: str | None) -> None:
    """Log a decision to a stream."""
    resolved = _resolve_or_exit(ref)
    metadata = json.loads(metadata_json) if metadata_json else None
    try:
        d = _svc().add_decision(resolved.id, what, why, metadata=metadata)
    except ValueError as e:
        _error_exit(str(e))
    data = {"id": d.id, "what": d.what}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Decision: {d['what']}")

    _output(data, _fmt)


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
    svc = _svc()
    if entry_type == "update":
        result = svc.edit_update(entry_id, content=content, summary=summary, metadata=metadata)
    else:
        result = svc.edit_decision(entry_id, what=what, why=why, metadata=metadata)
    if result is None:
        _error_exit(f"{entry_type} {entry_id} not found")
    data = {"id": result.id, "type": entry_type, "edited": True}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Edited {d['type']}: {d['id']}")

    _output(data, _fmt)


@stream.command("search")
@click.argument("query")
def stream_search(query: str) -> None:
    """Search across updates, decisions, and checkpoints."""
    from cortex.domain.models import Checkpoint, Decision, Update

    results = get_container().search_service.search(query)
    items = []
    for r in results:
        if isinstance(r, Update):
            items.append({"type": "update", "id": r.id, "stream_id": r.stream_id, "content": r.content, "summary": r.summary, "created_at": r.created_at.isoformat()})
        elif isinstance(r, Decision):
            items.append({"type": "decision", "id": r.id, "stream_id": r.stream_id, "what": r.what, "why": r.why, "created_at": r.created_at.isoformat()})
        elif isinstance(r, Checkpoint):
            items.append({"type": "checkpoint", "id": r.id, "week_of": r.week_of, "content": r.content[:200], "created_at": r.created_at.isoformat()})
    data = {"query": query, "results": items}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import get_console, relative_time, truncate
        console = get_console()
        results = d.get("results", [])
        if not results:
            console.print(f"No results for '{d['query']}'.")
            return
        console.print(f"[bold]Search:[/] {d['query']}  [dim]({len(results)} result(s))[/]\n")
        for item in results:
            itype = item["type"]
            age = relative_time(item.get("created_at"))
            if itype == "update":
                console.print(f"  [blue]update[/]  {truncate(item.get('summary', ''), 70)}  [dim]{age}[/]")
            elif itype == "decision":
                console.print(f"  [green]decision[/]  {truncate(item.get('what', ''), 70)}  [dim]{age}[/]")
            elif itype == "checkpoint":
                console.print(f"  [yellow]checkpoint[/]  {item.get('week_of', '?')}  [dim]{age}[/]")

    _output(data, _fmt)


@stream.command("link")
@click.argument("session_id")
@click.argument("stream_ref")
@click.option("--repo", default="", help="Repository name")
@click.option("--branch", default="", help="Branch name")
def stream_link(session_id: str, stream_ref: str, repo: str, branch: str) -> None:
    """Link a session to a stream."""
    resolved = _resolve_or_exit(stream_ref)
    try:
        _svc().link_session(session_id, resolved.id, repo=repo, branch=branch)
    except ValueError as e:
        _error_exit(str(e))
    data = {"linked": True, "session_id": session_id, "stream_id": resolved.id, "stream_name": resolved.name}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Linked session → {d['stream_name']}")

    _output(data, _fmt)
