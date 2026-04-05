from __future__ import annotations

from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Collapsible,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from textual.widget import Widget

from cortex.container import get_container
from cortex.domain.models import Stream


def _relative_time(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def _goal_priority(stream: Stream) -> int:
    goal = (stream.metadata or {}).get("goal", "")
    if goal == "daily":
        return 0
    if goal == "weekly":
        return 1
    return 2


class StreamListItem(ListItem):
    def __init__(self, stream: Stream) -> None:
        super().__init__()
        self.stream_id = stream.id
        self._stream = stream

    def compose(self) -> ComposeResult:
        meta = self._stream.metadata or {}
        goal = meta.get("goal", "")
        tags = meta.get("tags", [])

        indicator = {"daily": "\U0001f534 ", "weekly": "\U0001f7e1 "}.get(goal, "")
        title_line = f"{indicator}[bold]{self._stream.title}[/bold]"

        repos = ", ".join(self._stream.repos) if self._stream.repos else ""
        tags_str = ", ".join(tags) if tags else ""
        time_str = _relative_time(self._stream.updated_at)
        parts = [p for p in [repos, tags_str, time_str] if p]
        sep = " \u00b7 "
        info_line = f"[dim]{sep.join(parts)}[/dim]"

        yield Static(f"{title_line}\n   {info_line}")


class TagEditScreen(ModalScreen[list[str] | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    CSS = """
    TagEditScreen {
        align: center middle;
    }
    #tag-dialog {
        width: 60;
        height: auto;
        max-height: 12;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #tag-dialog Label {
        margin-bottom: 1;
    }
    #tag-input {
        width: 100%;
    }
    """

    def __init__(self, current_tags: list[str]) -> None:
        super().__init__()
        self._current_tags = current_tags

    def compose(self) -> ComposeResult:
        with Vertical(id="tag-dialog"):
            yield Label("Tags (comma-separated):")
            yield Input(
                value=", ".join(self._current_tags),
                id="tag-input",
                placeholder="e.g. api, frontend, urgent",
            )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        if not raw:
            self.dismiss([])
        else:
            self.dismiss([t.strip() for t in raw.split(",") if t.strip()])

    def action_cancel(self) -> None:
        self.dismiss(None)


class CortexApp(App):
    CSS = """
    #main {
        height: 1fr;
    }
    #stream-list {
        width: 1fr;
        max-width: 45%;
        border-right: solid $accent;
    }
    #detail-scroll {
        width: 1fr;
        padding: 1 2;
    }

    StreamListItem {
        padding: 1 1;
        border-left: solid $accent;
    }
    StreamListItem:hover {
        background: $boost;
    }
    StreamListItem.goal-daily {
        border-left: thick $error;
    }
    StreamListItem.goal-weekly {
        border-left: thick $warning;
    }

    #detail-header {
        padding: 0 0 1 0;
    }
    .decision-item {
        padding: 0 0 0 2;
    }
    .update-item {
        padding: 0 0 0 2;
    }
#empty-state {
        padding: 2 4;
        color: $text-muted;
    }
    Collapsible {
        padding: 0;
        margin: 0;
    }
    CollapsibleTitle {
        padding: 0;
        width: 1fr;
    }
    Contents {
        padding: 0 0 0 2;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("d", "toggle_daily", "Daily goal"),
        Binding("w", "toggle_weekly", "Weekly goal"),
        Binding("t", "edit_tags", "Tags"),
    ]

    TITLE = "Cortex"
    SUB_TITLE = "persistent context brain"

    def __init__(self) -> None:
        super().__init__()
        self._container = get_container()
        self._svc = self._container.stream_service
        self._streams: list[Stream] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            yield ListView(id="stream-list")
            with VerticalScroll(id="detail-scroll"):
                yield Static(id="detail-header")
        yield Footer()

    def on_mount(self) -> None:
        self._load_streams()

    def _load_streams(self) -> None:
        list_view = self.query_one("#stream-list", ListView)
        list_view.clear()
        self._streams = self._svc.get_active_streams()
        if not self._streams:
            self.query_one("#detail-header", Static).update("[dim]No active streams.[/dim]")
            return
        self._streams.sort(key=lambda s: (_goal_priority(s), -s.updated_at.timestamp()))
        for s in self._streams:
            item = StreamListItem(s)
            goal = (s.metadata or {}).get("goal", "")
            if goal:
                item.add_class(f"goal-{goal}")
            list_view.append(item)

    def _get_selected_stream(self) -> Stream | None:
        list_view = self.query_one("#stream-list", ListView)
        item = list_view.highlighted_child
        if not isinstance(item, StreamListItem):
            return None
        for s in self._streams:
            if s.id == item.stream_id:
                return s
        return None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if not isinstance(item, StreamListItem):
            return
        self._show_stream_detail(item.stream_id)

    def _show_stream_detail(self, stream_id: str) -> None:
        ctx = self._svc.get_stream_context(stream_id)
        if not ctx:
            return

        stream = ctx["stream"]
        meta = stream.get("metadata") or {}
        goal = meta.get("goal", "")
        tags = meta.get("tags", [])

        # --- Header ---
        goal_badge = ""
        if goal == "daily":
            goal_badge = " [$error bold]\U0001f534 DAILY GOAL[/]"
        elif goal == "weekly":
            goal_badge = " [$warning bold]\U0001f7e1 WEEKLY GOAL[/]"

        header_lines = [
            f"[bold underline]{stream['title']}[/bold underline]{goal_badge}",
            f"[dim]Repos: {', '.join(stream['repos'])} \u00b7 Status: {stream['status']}[/dim]",
        ]
        if tags:
            header_lines.append(f"[dim]Tags: {', '.join(tags)}[/dim]")
        # Collect session IDs from sessions table + update/decision metadata
        session_ids: set[str] = set()
        for s in ctx.get("sessions", []):
            session_ids.add(s["session_id"][:12])
        for entry in ctx.get("updates", []) + ctx.get("decisions", []):
            entry_meta = entry.get("metadata") or {}
            for key in ("session_id", "session"):
                if sid := entry_meta.get(key):
                    session_ids.add(str(sid)[:12])
        if session_ids:
            header_lines.append(f"[dim]Sessions: {', '.join(sorted(session_ids))}[/dim]")
        if stream.get("summary"):
            header_lines.append(f"\n[italic]{stream['summary']}[/italic]")

        self.query_one("#detail-header", Static).update("\n".join(header_lines))

        # --- Body sections ---
        scroll = self.query_one("#detail-scroll", VerticalScroll)
        for child in list(scroll.children):
            if child.id != "detail-header":
                child.remove()

        decisions = list(reversed(ctx.get("decisions", [])))
        updates = list(reversed(ctx.get("updates", [])))

        widgets_to_mount: list[Widget] = []

        # Decisions (collapsible, expanded by default)
        if decisions:
            decision_children: list[Widget] = []
            for d in decisions:
                ts = _relative_time(datetime.fromisoformat(d["created_at"])) if d.get("created_at") else ""
                ts_suffix = f" [dim]{ts}[/dim]" if ts else ""
                if d["why"]:
                    decision_children.append(
                        Collapsible(
                            Static(f"[dim]{d['why']}[/dim]"),
                            title=f"\u2192 {d['what']}{ts_suffix}",
                            collapsed=True,
                            collapsed_symbol="",
                            expanded_symbol="",
                        )
                    )
                else:
                    decision_children.append(Static(f"[yellow]\u2192[/yellow] {d['what']}{ts_suffix}", classes="decision-item"))
            widgets_to_mount.append(
                Collapsible(*decision_children, title=f"Decisions ({len(decisions)})", collapsed=False)
            )

        # Updates (collapsible, collapsed by default)
        if updates:
            update_children: list[Widget] = []
            for u in updates:
                ts = _relative_time(datetime.fromisoformat(u["created_at"])) if u.get("created_at") else ""
                ts_suffix = f" [dim]{ts}[/dim]" if ts else ""
                if u["content"] != u["summary"]:
                    update_children.append(
                        Collapsible(
                            Static(f"[dim]{u['content']}[/dim]"),
                            title=f"\u25cf {u['summary']}{ts_suffix}",
                            collapsed=True,
                            collapsed_symbol="",
                            expanded_symbol="",
                        )
                    )
                else:
                    update_children.append(Static(f"[cyan]\u25cf[/cyan] {u['summary']}{ts_suffix}", classes="update-item"))
            widgets_to_mount.append(
                Collapsible(*update_children, title=f"Updates ({len(updates)})", collapsed=True)
            )

        scroll.mount_all(widgets_to_mount)

    def action_refresh(self) -> None:
        self._load_streams()
        self.notify("Refreshed")

    def action_toggle_daily(self) -> None:
        self._toggle_goal("daily")

    def action_toggle_weekly(self) -> None:
        self._toggle_goal("weekly")

    def _toggle_goal(self, goal_type: str) -> None:
        stream = self._get_selected_stream()
        if not stream:
            self.notify("No stream selected", severity="warning")
            return
        current_goal = (stream.metadata or {}).get("goal", "")
        new_goal = "" if current_goal == goal_type else goal_type
        self._svc.update_stream(
            stream.id,
            metadata={"goal": new_goal if new_goal else None},
        )
        self._load_streams()
        self._show_stream_detail(stream.id)
        label = goal_type.capitalize()
        self.notify(f"{label} goal {'set' if new_goal else 'cleared'}")

    def action_edit_tags(self) -> None:
        stream = self._get_selected_stream()
        if not stream:
            self.notify("No stream selected", severity="warning")
            return
        current_tags = (stream.metadata or {}).get("tags", [])

        def on_tags_result(tags: list[str] | None) -> None:
            if tags is None:
                return
            self._svc.update_stream(stream.id, metadata={"tags": tags})
            self._load_streams()
            self._show_stream_detail(stream.id)
            self.notify("Tags updated")

        self.push_screen(TagEditScreen(current_tags), on_tags_result)


def main() -> None:
    CortexApp().run()


if __name__ == "__main__":
    main()
