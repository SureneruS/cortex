"""Cortex Mission Control — Textual TUI dashboard."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Static, Input

from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.text import Text

from cortex.container import get_container
from cortex.mongo import get_db


# ── Color Palette ───────────────────────────────────────────────

SESSION_COLORS = {
    "blue":   {"fg": "#58a6ff", "bg": "#0d1a2d"},
    "green":  {"fg": "#3fb950", "bg": "#0a1a0d"},
    "yellow": {"fg": "#d29922", "bg": "#1a1506"},
    "purple": {"fg": "#bc8cff", "bg": "#170d2e"},
    "orange": {"fg": "#d2883e", "bg": "#1a1208"},
    "pink":   {"fg": "#f778ba", "bg": "#1f0d18"},
    "cyan":   {"fg": "#39c5cf", "bg": "#0d1a1e"},
    "red":    {"fg": "#f85149", "bg": "#1f0a0a"},
}

CYCLE_COLORS = [
    {"fg": "#58a6ff", "bg": "#0d1a2d"},
    {"fg": "#d29922", "bg": "#1a1506"},
    {"fg": "#bc8cff", "bg": "#170d2e"},
    {"fg": "#3fb950", "bg": "#0a1a0d"},
    {"fg": "#f778ba", "bg": "#1f0d18"},
    {"fg": "#39c5cf", "bg": "#0d1a1e"},
]

_sender_colors: dict[str, dict[str, str]] = {}

STATUS_DOTS = {
    "active": ("●", "#3fb950"),
    "idle": ("◐", "#d29922"),
    "paused": ("◼", "#6e7681"),
    "blocked": ("◆", "#f85149"),
    "completed": ("✓", "#484f58"),
    "archived": ("○", "#484f58"),
    "closed": ("✕", "#f85149"),
    "dead": ("☠", "#6e7681"),
}

RUNTIME_INDICATORS = {
    "working": ("~", "#58a6ff"),
    "waiting_input": ("<", "#d29922"),
    "waiting_permission": ("!", "#d29922"),
    "error": ("!", "#f85149"),
    "unknown": ("", ""),
}

EVENT_GLYPHS = {
    # Lifecycle
    "spawn": ("+", "#3fb950"),
    "close": ("x", "#f85149"),
    "close-force": ("x", "#f85149"),
    "auto-close": ("x", "#d29922"),
    "manual-close-dead-pane": ("x", "#f85149"),
    "team-kill": ("x", "#f85149"),
    "cleanup": ("x", "#6e7681"),
    "shutdown": ("x", "#6e7681"),
    # Session end
    "session_end_exit": ("~", "#6e7681"),
    "session_end_prompt_input_exit": ("~", "#6e7681"),
    "session_end_other": ("~", "#6e7681"),
    "session-wrapup": ("v", "#3fb950"),
    # Pause / resume
    "pause": ("=", "#d29922"),
    "resume": (">", "#3fb950"),
    "resume-link": (">", "#3fb950"),
    "stop_hook": ("=", "#d29922"),
    "stop_failure": ("!", "#f85149"),
    # Visibility
    "hide": ("_", "#6e7681"),
    "show": ("^", "#58a6ff"),
    "manual-reactivate": ("^", "#3fb950"),
    # Maintenance
    "health-check": ("-", "#484f58"),
    "stale-sweep": ("X", "#d29922"),
    "stale_sweep": ("X", "#d29922"),
    "control-stale": ("X", "#d29922"),
    # Operations
    "update": ("^", "#58a6ff"),
    "cron": ("@", "#bc8cff"),
    "pr-watch": ("@", "#bc8cff"),
    "user_prompt": (">", "#58a6ff"),
    "scatter": ("*", "#58a6ff"),
    "remove-watch": ("-", "#6e7681"),
    # Test (dim)
    "e2e-cleanup": (".", "#484f58"),
    "e2e-cleanup-sweep": (".", "#484f58"),
    "test-cleanup": (".", "#484f58"),
}


def _sender_theme(name: str) -> dict[str, str]:
    if name not in _sender_colors:
        _sender_colors[name] = CYCLE_COLORS[len(_sender_colors) % len(CYCLE_COLORS)]
    return _sender_colors[name]


def _fmt_ts(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%H:%M")
    except (ValueError, TypeError):
        return iso[11:16] if len(iso) >= 16 else str(iso)[:5]


def _fmt_ago(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60}m"
        if secs < 86400:
            return f"{secs // 3600}h"
        return f"{secs // 86400}d"
    except (ValueError, TypeError):
        return "?"


def _truncate(s: str, n: int) -> str:
    return s[:n - 1] + "…" if len(s) > n else s


# ── Data Layer ──────────────────────────────────────────────────

def _fetch_sessions(include_done: bool = False) -> list[dict]:
    db = get_db()
    if include_done:
        filt = {"status": {"$nin": ["dead"]}}
    else:
        filt = {"status": {"$nin": ["completed", "closed", "dead"]}}
    return list(db.session_registry.find(filt).sort("created_at", -1))


def _fetch_session_detail(session_id: str) -> dict | None:
    db = get_db()
    return db.session_registry.find_one({"_id": session_id})


def _fetch_messages(limit: int = 60) -> list[dict]:
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    docs = list(
        db.messages.find({"created_at": {"$gt": cutoff}})
        .sort("created_at", -1)
        .limit(limit)
    )
    docs.reverse()
    return docs


def _fetch_events(limit: int = 30) -> list[dict]:
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    pipeline = [
        {"$match": {"events": {"$exists": True, "$ne": []}}},
        {"$unwind": "$events"},
        {"$match": {"events.at": {"$gt": cutoff}, "events.field": "status"}},
        {"$sort": {"events.at": -1}},
        {"$limit": limit},
        {"$project": {
            "_id": 0, "session_name": "$name",
            "field": "$events.field", "from": "$events.from",
            "to": "$events.to", "at": "$events.at",
            "trigger": "$events.trigger", "actor": "$events.actor",
        }},
    ]
    results = list(db.session_registry.aggregate(pipeline))
    results.reverse()
    return results


def _fetch_streams() -> list[dict]:
    db = get_db()
    return list(db.streams.find({"status": "active"}).sort("updated_at", -1).limit(10))


def _fetch_stream_entries(stream_id: str, limit: int = 5) -> list[dict]:
    db = get_db()
    updates = list(db.updates.find({"stream_id": stream_id}).sort("created_at", -1).limit(limit))
    decisions = list(db.decisions.find({"stream_id": stream_id}).sort("created_at", -1).limit(limit))
    items = []
    for u in updates:
        items.append({"type": "update", "summary": u.get("summary", ""), "at": u["created_at"]})
    for d in decisions:
        items.append({"type": "decision", "summary": d.get("what", ""), "at": d["created_at"]})
    items.sort(key=lambda x: x["at"], reverse=True)
    return items[:limit]


def _fetch_cron_jobs() -> list[dict]:
    db = get_db()
    return list(db.cron_jobs.find().sort("created_at", -1))


def _fetch_daemon_status() -> str:
    import subprocess
    try:
        result = subprocess.run(
            ["launchctl", "list", "com.cortex.daemon"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return "stopped"
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[2] == "com.cortex.daemon":
                return "stopped" if parts[0].strip() == "-" else "running"
        return "running"
    except Exception:
        return "unknown"


def _fetch_watch_count() -> int:
    db = get_db()
    return db.session_registry.count_documents({"watch_active": True})


def _fetch_recent_errors(limit: int = 5) -> list[dict]:
    db = get_db()
    return list(
        db.errors.find()
        .sort("timestamp", -1)
        .limit(limit)
    )


def _fetch_error_count_24h() -> int:
    db = get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    return db.errors.count_documents({"timestamp": {"$gte": cutoff}})


def _message_rate() -> float:
    db = get_db()
    five_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    count = db.messages.count_documents({"created_at": {"$gt": five_min_ago}})
    return count / 5.0


def _fetch_activity(limit: int = 30) -> list[dict]:
    db = get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    return list(
        db.activity.find({"timestamp": {"$gte": cutoff}})
        .sort("timestamp", -1)
        .limit(limit)
    )


def _fetch_errors_for_timeline(limit: int = 20) -> list[dict]:
    db = get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    return list(
        db.errors.find({"timestamp": {"$gte": cutoff}})
        .sort("timestamp", -1)
        .limit(limit)
    )


def _merge_timeline(
    messages: list[dict],
    events: list[dict],
    activity: list[dict] | None = None,
    errors: list[dict] | None = None,
) -> list[dict]:
    items = []
    for m in messages:
        items.append({"kind": "msg", "ts": m.get("created_at", ""), "data": m})
    for e in events:
        items.append({"kind": "event", "ts": e.get("at", ""), "data": e})
    for a in (activity or []):
        ts = a.get("timestamp")
        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        items.append({"kind": "activity", "ts": ts_str, "data": a})
    for err in (errors or []):
        ts = err.get("timestamp")
        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        items.append({"kind": "error", "ts": ts_str, "data": err})
    items.sort(key=lambda x: x["ts"])
    return items


# ── Rich Renderables ────────────────────────────────────────────

def _render_session_row(s: dict, selected: bool = False) -> RenderableType:
    name = s.get("name", s.get("_id", "?"))
    status = s.get("status", "unknown")
    runtime = s.get("runtime", "unknown")
    dot_char, dot_color = STATUS_DOTS.get(status, ("?", "#484f58"))
    rt_char, rt_color = RUNTIME_INDICATORS.get(runtime, ("", ""))

    cc_color = s.get("color", "")
    if cc_color and cc_color in SESSION_COLORS:
        _sender_colors[name] = SESSION_COLORS[cc_color]

    theme = _sender_theme(name)
    name_color = theme["fg"]

    repos = s.get("repos", [])
    repo_short = ", ".join(r.split("/")[-1] if "/" in r else r for r in repos[:2])

    sel_marker = "▸ " if selected else "  "
    rt_part = f"  [{rt_color}]{rt_char}[/]" if rt_char else ""
    line1 = Text.from_markup(
        f"{sel_marker}[{dot_color}]{dot_char}[/] [{name_color} bold]{_truncate(name, 18)}[/]"
        f"{rt_part}"
    )
    line2 = Text.from_markup(
        f"    [dim]{repo_short}[/]" if repo_short else f"    [dim]{_fmt_ago(s.get('created_at', ''))} ago[/]"
    )
    result = Text()
    result.append_text(line1)
    result.append("\n")
    result.append_text(line2)
    return result


def _render_msg_bubble(msg: dict) -> Panel:
    sender = msg.get("from", "?")
    theme = _sender_theme(sender)
    fg, bg = theme["fg"], theme["bg"]

    ts = _fmt_ts(msg.get("created_at", ""))
    recipient = msg.get("to", "?")
    meta = msg.get("meta") or {}
    msg_type = meta.get("type", "")
    priority = meta.get("priority", "")

    badges = []
    if msg_type:
        badges.append(msg_type)
    if priority and priority != "normal":
        badges.append(f"[bold #f85149]{priority}[/]")
    badge_str = f" ({', '.join(badges)})" if badges else ""

    title = Text.from_markup(
        f"[bold {fg}]{sender}[/] [#484f58]→[/] [bold]{recipient}[/]"
        f"  [#484f58]{ts}[/]{badge_str}"
    )

    content = (msg.get("content") or "").strip()

    try:
        body: RenderableType = Markdown(content)
    except Exception:
        body = Text(content)

    return Panel(
        body,
        title=title,
        title_align="left",
        border_style=Style(color=fg),
        style=Style(bgcolor=bg),
        padding=(0, 1),
    )


def _render_event_line(ev: dict) -> Text:
    ts = _fmt_ts(ev.get("at", ""))
    name = ev.get("session_name", "?")
    to_val = ev.get("to", "?")
    from_val = ev.get("from")
    trigger = ev.get("trigger", "")

    glyph, glyph_color = EVENT_GLYPHS.get(trigger, ("·", "#484f58"))
    status_color = STATUS_DOTS.get(to_val, ("?", "#6e7681"))[1]

    if from_val:
        transition = f"[#6e7681]{from_val}[/] → [{status_color}]{to_val}[/]"
    else:
        transition = f"[{status_color}]{to_val}[/]"

    return Text.from_markup(
        f"  [#484f58]{ts}[/]  [{glyph_color}]{glyph}[/]  "
        f"[#6e7681]{_truncate(name, 16)}[/]  {transition}"
    )


def _render_activity_line(activity: dict) -> RenderableType:
    ts = activity.get("timestamp")
    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    ts_fmt = _fmt_ts(ts_str)
    summary = activity.get("summary", "?")
    details = activity.get("details", {})
    is_error = details.get("error", False)
    has_changes = "changes" in details
    changes_text = details.get("changes", "")

    if is_error:
        glyph, color = "!", "#f85149"
    elif has_changes:
        glyph, color = "▲", "#d29922"
    else:
        glyph, color = "◇", "#484f58"

    header = Text.from_markup(
        f"  [#484f58]{ts_fmt}[/]  [{color}]{glyph}[/]  [{color}]{summary}[/]"
    )
    if changes_text:
        header.append_text(Text.from_markup(f"\n        [dim]{changes_text}[/]"))
    return header


def _render_error_line(error: dict) -> RenderableType:
    ts = error.get("timestamp")
    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    ts_fmt = _fmt_ts(ts_str)
    component = error.get("component", "?")
    event = str(error.get("event", ""))
    level = error.get("level", "ERROR")
    details = error.get("details", {})
    exc_type = details.get("exception_type", "")
    exc_msg = details.get("exception", "")
    message = details.get("message", "")

    level_color = "#f85149" if level == "ERROR" else "#d29922"

    header = Text.from_markup(
        f"  [#484f58]{ts_fmt}[/]  [{level_color}]▲[/]  "
        f"[dim]{component}[/]  [{level_color}]{event}[/]"
    )
    detail_parts = []
    if exc_type:
        detail_parts.append(f"[{level_color}]{exc_type}[/]")
    if exc_msg:
        detail_parts.append(f"[dim]{exc_msg}[/]")
    elif message and message != event:
        detail_parts.append(f"[dim]{message}[/]")
    if detail_parts:
        header.append_text(Text.from_markup("\n        " + "  ".join(detail_parts)))
    return header


def _render_stream_card(stream: dict, entries: list[dict]) -> RenderableType:
    title = stream.get("title", "untitled")
    repos = stream.get("repos", [])
    repo_str = ", ".join(r.split("/")[-1] for r in repos[:2]) if repos else ""
    updated = _fmt_ago(stream.get("updated_at", stream.get("created_at", "")))

    lines = Text.from_markup(
        f"[bold #d29922]{_truncate(title, 28)}[/]\n"
        f"[dim]{repo_str}[/]  [dim]↻ {updated}[/]"
    )

    if entries:
        lines.append("\n")
        for e in entries[:3]:
            icon = "△" if e["type"] == "update" else "◇"
            lines.append_text(Text.from_markup(
                f"[#484f58]{icon}[/] [dim]{_truncate(e['summary'], 24)}[/]\n"
            ))

    return lines


# ── Widgets ─────────────────────────────────────────────────────

class SessionListWidget(VerticalScroll):
    selected_index: reactive[int] = reactive(0)
    sessions: reactive[list[dict]] = reactive(list, init=False)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.sessions = []

    def set_sessions(self, sessions: list[dict]) -> None:
        self.sessions = sessions
        if self.selected_index >= len(sessions):
            self.selected_index = max(0, len(sessions) - 1)
        self._rebuild()

    def _rebuild(self) -> None:
        self.remove_children()
        for i, s in enumerate(self.sessions):
            widget = Static(
                _render_session_row(s, selected=(i == self.selected_index)),
                classes="session-item",
            )
            if i == self.selected_index:
                widget.add_class("-selected")
            self.mount(widget)

    def move_selection(self, delta: int) -> None:
        if not self.sessions:
            return
        self.selected_index = max(0, min(len(self.sessions) - 1, self.selected_index + delta))
        self._rebuild()

    def get_selected(self) -> dict | None:
        if 0 <= self.selected_index < len(self.sessions):
            return self.sessions[self.selected_index]
        return None


class TimelineScroll(VerticalScroll):
    def populate(self, items: list[dict]) -> None:
        was_at_bottom = self.scroll_offset.y >= self.max_scroll_y - 2
        self.remove_children()
        for item in items:
            kind = item["kind"]
            if kind == "msg":
                self.mount(Static(_render_msg_bubble(item["data"]), classes="msg-bubble"))
            elif kind == "activity":
                self.mount(Static(_render_activity_line(item["data"]), classes="activity-line"))
            elif kind == "error":
                self.mount(Static(_render_error_line(item["data"]), classes="error-line"))
            else:
                self.mount(Static(_render_event_line(item["data"]), classes="event-line"))
        if was_at_bottom:
            self.scroll_end(animate=False)


class StreamsPanel(VerticalScroll):
    def populate(self, streams: list[dict]) -> None:
        self.remove_children()
        for s in streams:
            entries = _fetch_stream_entries(s["_id"], limit=3)
            self.mount(Static(_render_stream_card(s, entries), classes="stream-item"))


class HealthPanel(Widget):
    def render(self) -> RenderableType:
        try:
            db = get_db()
            mongo_ok = True
            db.command("ping")
        except Exception:
            mongo_ok = False

        crons = _fetch_cron_jobs()
        enabled = sum(1 for c in crons if c.get("enabled"))
        total_crons = len(crons)

        daemon_status = _fetch_daemon_status()
        watch_count = _fetch_watch_count()
        error_count = _fetch_error_count_24h()
        recent_errors = _fetch_recent_errors(3)

        lines = Text()

        # Daemon
        if daemon_status == "running":
            lines.append_text(Text.from_markup("  [#3fb950]●[/] Daemon     [#3fb950]running[/]\n"))
        elif daemon_status == "stopped":
            lines.append_text(Text.from_markup("  [#f85149]●[/] Daemon     [#f85149]stopped[/]\n"))
        else:
            lines.append_text(Text.from_markup("  [#d29922]●[/] Daemon     [#d29922]unknown[/]\n"))

        # MongoDB
        if mongo_ok:
            lines.append_text(Text.from_markup("  [#3fb950]●[/] MongoDB    [#3fb950]connected[/]\n"))
        else:
            lines.append_text(Text.from_markup("  [#f85149]●[/] MongoDB    [#f85149]disconnected[/]\n"))

        # Cron
        lines.append_text(Text.from_markup(
            f"  [#58a6ff]●[/] Cron jobs  [dim]{enabled}/{total_crons} enabled[/]\n"
        ))

        # PR Watches
        if watch_count > 0:
            lines.append_text(Text.from_markup(
                f"  [#bc8cff]●[/] Watches    [#bc8cff]{watch_count} active[/]\n"
            ))
        else:
            lines.append_text(Text.from_markup(
                "  [#484f58]○[/] Watches    [dim]none[/]\n"
            ))

        # Errors
        if error_count > 0:
            lines.append_text(Text.from_markup(
                f"\n  [#f85149 bold]▲ {error_count} error{'s' if error_count != 1 else ''} (24h)[/]\n"
            ))
            for err in recent_errors:
                ts = _fmt_ago(err.get("timestamp", "").isoformat() if hasattr(err.get("timestamp", ""), "isoformat") else str(err.get("timestamp", "")))
                component = err.get("component", "?")
                event = _truncate(str(err.get("event", "")), 22)
                lines.append_text(Text.from_markup(
                    f"  [#484f58]{ts}[/] [dim]{component}[/] [#f85149]{event}[/]\n"
                ))
        else:
            lines.append_text(Text.from_markup(
                "\n  [#3fb950]✓[/] [dim]No errors (24h)[/]\n"
            ))

        return lines


# ── Session Detail Modal ────────────────────────────────────────

class SessionDetailScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss_modal", "Back", show=True),
        Binding("q", "dismiss_modal", "Back", show=False),
        Binding("d", "dismiss_modal", "Close", show=False),
    ]

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-overlay"):
            yield Static(id="detail-header")
            yield VerticalScroll(id="detail-body")

    def on_mount(self) -> None:
        self._load_detail()

    @work(thread=True)
    def _load_detail(self) -> None:
        doc = _fetch_session_detail(self.session_id)
        if not doc:
            self.app.call_from_thread(self._show_not_found)
            return
        self.app.call_from_thread(self._render_detail, doc)

    def _show_not_found(self) -> None:
        header = self.query_one("#detail-header", Static)
        header.update(Text.from_markup("[bold #f85149]Session not found[/]"))

    def _render_detail(self, doc: dict) -> None:
        name = doc.get("name", doc["_id"])
        status = doc.get("status", "?")
        runtime = doc.get("runtime", "?")
        dot_char, dot_color = STATUS_DOTS.get(status, ("?", "#484f58"))

        theme = _sender_theme(name)
        fg = theme["fg"]

        header = self.query_one("#detail-header", Static)
        header.update(Text.from_markup(
            f"[bold {fg}]{name}[/]  [{dot_color}]{dot_char} {status}[/]"
            f"  [dim]runtime:[/] {runtime}"
            f"  [dim]id:[/] [dim]{doc['_id']}[/]"
        ))

        body = self.query_one("#detail-body", VerticalScroll)
        body.remove_children()

        # Info table
        info = Table.grid(padding=(0, 2))
        info.add_column(style="bold #6e7681", width=14)
        info.add_column()

        info.add_row("Role", doc.get("role", "?"))
        info.add_row("Pane", doc.get("pane_id") or "—")
        info.add_row("Model", doc.get("model") or "—")
        info.add_row("Color", doc.get("color") or "—")
        info.add_row("Spawned by", doc.get("spawned_by") or "—")
        info.add_row("Created", _fmt_ts(doc.get("created_at", "")))
        if doc.get("closed_at"):
            info.add_row("Closed", _fmt_ts(doc["closed_at"]))

        repos = doc.get("repos", [])
        if repos:
            info.add_row("Repos", ", ".join(repos))

        goal = doc.get("goal")
        if goal:
            info.add_row("Goal", _truncate(goal, 60))

        cc_sessions = doc.get("cc_sessions", [])
        if cc_sessions:
            info.add_row("CC sessions", str(len(cc_sessions)))

        body.mount(Static(Panel(
            info,
            title="[bold]Info[/]",
            title_align="left",
            border_style="#2a3544",
            padding=(0, 1),
        )))

        # Goal (full)
        if goal and len(goal) > 60:
            body.mount(Static(Panel(
                Text(goal, style="#c9d1d9"),
                title="[bold]Goal[/]",
                title_align="left",
                border_style="#2a3544",
                padding=(0, 1),
            )))

        # Events timeline
        events = doc.get("events", [])
        if events:
            event_lines = Text()
            for ev in reversed(events[-20:]):
                ts = _fmt_ts(ev.get("at", ""))
                field = ev.get("field", "?")
                from_v = ev.get("from", "—")
                to_v = ev.get("to", "?")
                trigger = ev.get("trigger", "")
                actor = ev.get("actor", "")
                glyph, gc = EVENT_GLYPHS.get(trigger, ("·", "#484f58"))

                event_lines.append_text(Text.from_markup(
                    f"[#484f58]{ts}[/]  [{gc}]{glyph}[/]  "
                    f"[#6e7681]{field}[/] {from_v} → [{dot_color}]{to_v}[/]"
                ))
                if actor:
                    event_lines.append_text(Text.from_markup(f"  [dim]by {actor}[/]"))
                event_lines.append("\n")

            body.mount(Static(Panel(
                event_lines,
                title=f"[bold]Events[/] [dim]({len(events)})[/]",
                title_align="left",
                border_style="#2a3544",
                padding=(0, 1),
            )))

    def action_dismiss_modal(self) -> None:
        self.dismiss()


# ── Main Dashboard App ──────────────────────────────────────────

class CortexDashboard(App):
    CSS_PATH = "dashboard.tcss"
    TITLE = "Cortex"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=False, priority=True),
        Binding("R", "refresh", "Refresh", show=False),
        Binding("j", "move_down", "↓", show=False),
        Binding("k", "move_up", "↑", show=False),
        Binding("enter", "drill_down", "Detail", show=False),
        Binding("d", "drill_down", "Detail", show=False),
        Binding("p", "pause_session", "Pause", show=False),
        Binding("r", "resume_session", "Resume", show=False),
        Binding("c", "close_session", "Close", show=False),
        Binding("slash", "toggle_filter", "Filter", show=False),
        Binding("escape", "close_filter", "Back", show=False),
        Binding("tab", "focus_next", "Next Panel", show=False),
        Binding("shift+tab", "focus_previous", "Prev Panel", show=False),
        Binding("a", "toggle_all", "All sessions", show=False),
        Binding("g", "scroll_top", "Top", show=False),
        Binding("G", "scroll_bottom", "Bottom", show=False),
        Binding("left_square_bracket", "toggle_left_panel", "[  Sessions", show=False),
        Binding("right_square_bracket", "toggle_right_panel", "]  Streams", show=False),
    ]

    show_all: reactive[bool] = reactive(False)
    filter_text: reactive[str] = reactive("")
    _refresh_count: int = 0
    _all_sessions: list[dict] = []

    def compose(self) -> ComposeResult:
        # Header
        with Horizontal(id="header-bar"):
            yield Static("⬡ CORTEX", id="logo")
            yield Static("", id="header-stats")

        # Main 3-column layout
        with Horizontal(id="main-area"):
            # Left: Sessions
            with Vertical(id="sessions-panel"):
                yield Static("▸ Sessions", id="sessions-title")
                yield SessionListWidget(id="sessions-list")

            # Center: Timeline
            with Vertical(id="timeline-panel"):
                yield Static("▸ Timeline", id="timeline-title")
                yield TimelineScroll(id="timeline-scroll")

            # Right: Streams + Health
            with Vertical(id="right-panel"):
                with Vertical(id="streams-section"):
                    yield Static("▸ Streams", id="streams-title")
                    yield StreamsPanel(id="streams-list")
                with Vertical(id="health-section"):
                    yield Static("▸ System", id="health-title")
                    yield HealthPanel()

        # Filter bar (hidden by default)
        yield Input(placeholder="Filter sessions...", id="filter-bar")

        # Bottom bar: action hints (left) + stats (right)
        with Horizontal(id="bottom-bar"):
            yield Static("", id="action-bar")
            yield Static("", id="status-right")

    def on_mount(self) -> None:
        self._refresh_data()
        self.set_interval(3.0, self._refresh_data)
        self.query_one("#sessions-list", SessionListWidget).focus()
        self._update_action_bar()

    # ── Data refresh ────────────────────────────────────────────

    @work(thread=True)
    def _refresh_data(self) -> None:
        sessions = _fetch_sessions(include_done=self.show_all)
        messages = _fetch_messages(60)
        events = _fetch_events(30)
        activity = _fetch_activity(30)
        errors = _fetch_errors_for_timeline(20)
        timeline = _merge_timeline(messages, events, activity, errors)
        streams = _fetch_streams()
        rate = _message_rate()

        self._all_sessions = sessions
        self._refresh_count += 1

        self.app.call_from_thread(self._apply_data, sessions, timeline, streams, rate)

    def _apply_data(
        self,
        sessions: list[dict],
        timeline: list[dict],
        streams: list[dict],
        rate: float,
    ) -> None:
        # Filter sessions
        if self.filter_text:
            ft = self.filter_text.lower()
            sessions = [s for s in sessions if ft in (s.get("name") or "").lower()
                        or ft in (s.get("status") or "").lower()
                        or any(ft in r.lower() for r in s.get("repos", []))]

        # Sessions
        sess_list = self.query_one("#sessions-list", SessionListWidget)
        sess_list.set_sessions(sessions)

        active_count = sum(1 for s in sessions if s.get("status") not in ("completed", "closed", "dead"))
        working_count = sum(1 for s in sessions if s.get("runtime") == "working")
        total_label = "all" if self.show_all else "active"
        self.query_one("#sessions-title", Static).update(
            Text.from_markup(
                f"[bold #58a6ff]▸ Sessions[/]  "
                f"[dim]{active_count} {total_label}[/]  "
                f"[#3fb950]{working_count} working[/]"
            )
        )

        # Timeline
        tl = self.query_one("#timeline-scroll", TimelineScroll)
        tl.populate(timeline)

        msg_count = sum(1 for t in timeline if t["kind"] == "msg")
        self.query_one("#timeline-title", Static).update(
            Text.from_markup(
                f"[bold #bc8cff]▸ Timeline[/]  [dim]{msg_count} messages (24h)[/]"
            )
        )

        # Streams
        sp = self.query_one("#streams-list", StreamsPanel)
        sp.populate(streams)
        self.query_one("#streams-title", Static).update(
            Text.from_markup(
                f"[bold #d29922]▸ Streams[/]  [dim]{len(streams)} active[/]"
            )
        )

        # Header stats
        now = datetime.now().strftime("%H:%M:%S")
        self.query_one("#header-stats", Static).update(
            Text.from_markup(
                f"[dim]↻ {now}[/]  "
                f"[#3fb950]{working_count}[/] working  "
                f"[#d29922]{rate:.1f}[/] msg/min"
            )
        )

        # Status (right side of bottom bar)
        self.query_one("#status-right", Static).update(
            Text.from_markup(
                f"[#58a6ff]●[/] {active_count}  "
                f"[#bc8cff]●[/] {msg_count} msgs  "
                f"[#d29922]●[/] {len(streams)} streams  "
                f"[dim]#{self._refresh_count}[/]"
            )
        )

        self._update_action_bar()

    # ── Action bar ──────────────────────────────────────────────

    def _update_action_bar(self) -> None:
        sess = self.query_one("#sessions-list", SessionListWidget).get_selected()
        status = sess.get("status", "") if sess else ""

        parts: list[str] = []

        def _key(k: str, label: str, color: str = "#58a6ff") -> str:
            return f"[bold {color}]{k}[/] [#c9d1d9]{label}[/]"

        if status in ("active", "idle", "blocked", "hidden"):
            parts.append(_key("p", "Pause", "#d29922"))
        if status in ("paused",):
            parts.append(_key("r", "Resume", "#3fb950"))
        if status in ("active", "idle", "blocked", "hidden", "paused"):
            parts.append(_key("c", "Close", "#f85149"))
        if sess:
            parts.append(_key("Enter", "Detail"))
        parts.append(_key("/", "Filter", "#6e7681"))
        parts.append(_key("a", "All", "#6e7681"))
        parts.append(_key("R", "Refresh", "#6e7681"))
        parts.append(_key("q", "Quit", "#6e7681"))

        bar = self.query_one("#action-bar", Static)
        bar.update(Text.from_markup("  " + "    ".join(parts)))

    # ── Actions ─────────────────────────────────────────────────

    def action_refresh(self) -> None:
        self._refresh_data()

    def action_move_down(self) -> None:
        sl = self.query_one("#sessions-list", SessionListWidget)
        sl.move_selection(1)
        self._update_action_bar()

    def action_move_up(self) -> None:
        sl = self.query_one("#sessions-list", SessionListWidget)
        sl.move_selection(-1)
        self._update_action_bar()

    def action_drill_down(self) -> None:
        sess = self.query_one("#sessions-list", SessionListWidget).get_selected()
        if sess:
            self.push_screen(SessionDetailScreen(sess["_id"]))

    def action_pause_session(self) -> None:
        sess = self.query_one("#sessions-list", SessionListWidget).get_selected()
        if not sess or sess.get("status") not in ("active", "idle", "blocked", "hidden"):
            self.notify("No pausable session selected", severity="warning")
            return
        self._do_pause(sess["_id"], sess.get("name", sess["_id"]))

    @work(thread=True)
    def _do_pause(self, session_id: str, name: str) -> None:
        try:
            svc = get_container().session_service
            svc.pause(session_id)
            self.app.call_from_thread(self.notify, f"Paused {name}", severity="information")
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Pause failed: {e}", severity="error")
        self._refresh_data()

    def action_resume_session(self) -> None:
        sess = self.query_one("#sessions-list", SessionListWidget).get_selected()
        if not sess or sess.get("status") != "paused":
            self.notify("No paused session selected", severity="warning")
            return
        self._do_resume(sess["_id"], sess.get("name", sess["_id"]))

    @work(thread=True)
    def _do_resume(self, session_id: str, name: str) -> None:
        try:
            svc = get_container().session_service
            svc.resume(session_id)
            self.app.call_from_thread(self.notify, f"Resumed {name}", severity="information")
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Resume failed: {e}", severity="error")
        self._refresh_data()

    def action_close_session(self) -> None:
        sess = self.query_one("#sessions-list", SessionListWidget).get_selected()
        if not sess or sess.get("status") in ("completed", "closed", "dead"):
            self.notify("No closable session selected", severity="warning")
            return
        self._do_close(sess["_id"], sess.get("name", sess["_id"]))

    @work(thread=True)
    def _do_close(self, session_id: str, name: str) -> None:
        try:
            svc = get_container().session_service
            svc.close(session_id)
            self.app.call_from_thread(self.notify, f"Closed {name}", severity="information")
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Close failed: {e}", severity="error")
        self._refresh_data()

    def action_toggle_filter(self) -> None:
        fbar = self.query_one("#filter-bar", Input)
        if fbar.has_class("-visible"):
            fbar.remove_class("-visible")
            self.query_one("#sessions-list", SessionListWidget).focus()
        else:
            fbar.add_class("-visible")
            fbar.focus()

    def action_close_filter(self) -> None:
        fbar = self.query_one("#filter-bar", Input)
        if fbar.has_class("-visible"):
            fbar.remove_class("-visible")
            fbar.value = ""
            self.filter_text = ""
            self.query_one("#sessions-list", SessionListWidget).focus()
            self._refresh_data()

    def action_toggle_all(self) -> None:
        self.show_all = not self.show_all
        self._refresh_data()
        self._update_action_bar()

    def action_scroll_top(self) -> None:
        tl = self.query_one("#timeline-scroll", TimelineScroll)
        tl.scroll_home(animate=False)

    def action_scroll_bottom(self) -> None:
        tl = self.query_one("#timeline-scroll", TimelineScroll)
        tl.scroll_end(animate=False)

    def action_toggle_left_panel(self) -> None:
        panel = self.query_one("#sessions-panel")
        panel.toggle_class("-collapsed")

    def action_toggle_right_panel(self) -> None:
        panel = self.query_one("#right-panel")
        panel.toggle_class("-collapsed")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-bar":
            self.filter_text = event.value
            self._refresh_data()


def main() -> None:
    CortexDashboard().run()
