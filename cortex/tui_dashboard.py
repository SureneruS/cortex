"""Cortex TUI Dashboard — Textual app with Rich chat bubbles from session watch."""
from __future__ import annotations

from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Header, Footer, DataTable, Static

from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.style import Style
from rich.text import Text

from cortex.mongo import get_db


# ── Data ─────────────────────────────────────────────────────

def _fetch_sessions() -> list[dict]:
    db = get_db()
    return list(db.session_registry.find(
        {"status": {"$nin": ["completed", "dead"]}},
    ).sort("created_at", -1))


def _fetch_timeline(limit: int = 40) -> list[dict]:
    db = get_db()
    msgs = list(db.messages.find().sort("created_at", -1).limit(limit))
    events_raw = list(db.session_registry.aggregate([
        {"$match": {"events": {"$exists": True, "$ne": []}}},
        {"$unwind": "$events"},
        {"$sort": {"events.at": -1}},
        {"$limit": limit},
        {"$project": {"name": 1, "event": "$events"}},
    ]))

    items: list[dict] = []
    for m in msgs:
        items.append({"kind": "msg", "ts": m.get("created_at", ""), "data": m})
    for e in events_raw:
        ev = e["event"]
        ev["session_name"] = e["name"]
        items.append({"kind": "event", "ts": ev.get("at", ""), "data": ev})

    items.sort(key=lambda x: x["ts"])
    return items[-limit:]


# ── Rich rendering (same palette as cortex session watch) ────

SESSION_COLOR_MAP = {
    "blue":    {"color": "#58a6ff", "bg": "#0d1a2d"},
    "green":   {"color": "#3fb950", "bg": "#0a1a0d"},
    "yellow":  {"color": "#d29922", "bg": "#1a1506"},
    "purple":  {"color": "#bc8cff", "bg": "#170d2e"},
    "orange":  {"color": "#d29922", "bg": "#1a1506"},
    "pink":    {"color": "#f778ba", "bg": "#1f0d18"},
    "cyan":    {"color": "#58a6ff", "bg": "#0d1a2d"},
    "red":     {"color": "#f85149", "bg": "#1f0a0a"},
}

FALLBACK_THEMES = [
    {"color": "#58a6ff", "bg": "#0d1a2d"},
    {"color": "#d29922", "bg": "#1a1506"},
    {"color": "#bc8cff", "bg": "#170d2e"},
    {"color": "#f85149", "bg": "#1f0a0a"},
    {"color": "#3fb950", "bg": "#0a1a0d"},
]

_color_map: dict[str, dict[str, str]] = {}

EVENT_ICONS = {"spawn": "+", "close": "x", "stale-sweep": "~", "stale_sweep": "x", "health-check": "~"}
EVENT_COLORS = {
    "active": "green", "completed": "dim", "dead": "red", "working": "green",
    "waiting_input": "cyan", "error": "red", "unknown": "dim",
}


def _get_theme(name: str) -> dict[str, str]:
    if name not in _color_map:
        _color_map[name] = FALLBACK_THEMES[len(_color_map) % len(FALLBACK_THEMES)]
    return _color_map[name]


def _fmt_time(iso: str) -> str:
    try:
        utc_dt = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
        return utc_dt.astimezone().strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return iso[11:19] if len(iso) >= 19 else iso


def _render_message(msg: dict) -> Panel:
    theme = _get_theme(msg.get("from", ""))
    color, bg = theme["color"], theme["bg"]

    ts = _fmt_time(msg.get("created_at", ""))
    meta = msg.get("meta") or {}
    msg_type = meta.get("type", "")
    priority = meta.get("priority", "")

    badge_parts: list[str] = []
    if msg_type:
        badge_parts.append(msg_type)
    if priority and priority != "normal":
        badge_parts.append(f"[bold red]{priority}[/]")
    badge = f" ({', '.join(badge_parts)})" if badge_parts else ""

    header = Text.from_markup(
        f"[bold {color}]{msg.get('from', '')}[/] [dim]→[/] [bold]{msg.get('to', '')}[/]"
        f"  [dim]{ts}[/]{badge}"
    )

    content = (msg.get("content") or "").strip()
    try:
        body: RenderableType = Markdown(content)
    except Exception:
        body = Text(content)

    return Panel(
        body,
        title=header,
        title_align="left",
        border_style=Style(color=color),
        style=Style(bgcolor=bg),
        padding=(0, 1),
    )


def _render_event(ev: dict) -> Text:
    ts = _fmt_time(ev.get("at", ""))
    name = ev.get("session_name", "?")
    to_val = ev.get("to", "?")
    from_val = ev.get("from")
    trigger = ev.get("trigger", "")
    actor = ev.get("actor", "")

    icon = EVENT_ICONS.get(trigger, "~")
    sc = EVENT_COLORS.get(to_val, "white")

    if from_val:
        label = f"{name} {from_val} → [{sc}]{to_val}[/]"
    else:
        label = f"{name} [{sc}]{to_val}[/]"

    suffix = f"  [dim]by {actor}[/]" if actor else ""
    return Text.from_markup(f"[dim]{ts}[/]  {icon} {label}{suffix}")


# ── Widgets ──────────────────────────────────────────────────

class TimelineWidget(VerticalScroll):
    def populate(self, items: list[dict]) -> None:
        was_at_bottom = self.scroll_offset.y >= self.max_scroll_y - 2
        self.remove_children()
        for item in items:
            if item["kind"] == "msg":
                self.mount(Static(_render_message(item["data"])))
            else:
                self.mount(Static(_render_event(item["data"])))
        if was_at_bottom:
            self.scroll_end(animate=False)


# ── App ──────────────────────────────────────────────────────

class DashboardApp(App):
    CSS = """
    Screen { layout: horizontal; }
    #left { width: 45%; border-right: solid $secondary; }
    #right { width: 55%; }
    #session-table { height: 1fr; }
    .panel-title { text-style: bold; padding: 0 1; }
    #sess-title { color: $accent; }
    Footer { dock: bottom; }
    Header { dock: top; }
    """

    TITLE = "Cortex Dashboard"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("tab", "focus_next", "Switch Panel"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with VerticalScroll(id="left"):
                yield Static("▸ Sessions", classes="panel-title", id="sess-title")
                yield DataTable(id="session-table")
            yield TimelineWidget(id="right")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#session-table", DataTable)
        table.add_columns("Name", "Status", "Runtime", "Pane", "Repos")
        table.cursor_type = "row"
        self._refresh_data()
        self.set_interval(3.0, self._refresh_data)

    def _refresh_data(self) -> None:
        table = self.query_one("#session-table", DataTable)
        table.clear()
        for s in _fetch_sessions():
            name = s.get("name", "")
            cc_color = s.get("color", "")
            if cc_color in SESSION_COLOR_MAP:
                _color_map[name] = SESSION_COLOR_MAP[cc_color]
            table.add_row(
                name,
                s.get("status", ""),
                s.get("runtime", ""),
                s.get("pane_id", ""),
                ", ".join(s.get("repos", [])),
            )

        timeline = self.query_one("#right", TimelineWidget)
        timeline.populate(_fetch_timeline(40))

    def action_refresh(self) -> None:
        self._refresh_data()


def main() -> None:
    DashboardApp().run()
