"""Human-friendly output formatters for the cortex CLI."""
from __future__ import annotations

from datetime import datetime, timezone

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

STATUS_STYLES = {
    "active": "green",
    "idle": "yellow",
    "paused": "yellow",
    "hidden": "dim",
    "completed": "dim",
    "closed": "dim",
    "dead": "dim red",
    "blocked": "red",
}

RUNTIME_STYLES = {
    "working": "green",
    "waiting_input": "yellow",
    "waiting_permission": "red",
    "error": "red",
    "unknown": "dim",
}

_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(highlight=False)
    return _console


def relative_time(iso_str: str | None) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(str(iso_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        secs = int((datetime.now(timezone.utc) - dt).total_seconds())
        if secs < 0:
            return "just now"
        if secs < 60:
            return f"{secs}s ago"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except (ValueError, TypeError):
        return "?"


def local_datetime(iso_str: str | None) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(str(iso_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%b %d %H:%M")
    except (ValueError, TypeError):
        return "?"


def styled_status(status: str | None) -> str:
    if not status:
        return "—"
    color = STATUS_STYLES.get(status, "white")
    return f"[{color}]{status}[/]"


def styled_runtime(runtime: str | None) -> str:
    if not runtime:
        return "—"
    color = RUNTIME_STYLES.get(runtime, "dim")
    return f"[{color}]{runtime}[/]"


def truncate(text: str | None, length: int = 60) -> str:
    if not text:
        return "—"
    text = str(text).replace("\n", " ")
    if len(text) <= length:
        return text
    return text[:length - 1] + "…"


def print_table(
    columns: list[tuple[str, dict]],
    rows: list[list[str]],
    title: str | None = None,
    count: int | None = None,
) -> None:
    console = get_console()
    table = Table(title=title, show_header=True, header_style="bold", show_lines=False, pad_edge=False)
    for col_name, col_kwargs in columns:
        table.add_column(col_name, **col_kwargs)
    for row in rows:
        table.add_row(*row)
    console.print(table)
    if count is not None:
        console.print(f"[dim]{count} item(s)[/]")


def print_detail(fields: list[tuple[str, str]], title: str | None = None) -> None:
    console = get_console()
    max_label = max((len(label) for label, _ in fields), default=0)
    lines = []
    for label, value in fields:
        lines.append(f"[bold]{label.rjust(max_label)}[/]  {value}")
    content = "\n".join(lines)
    if title:
        panel = Panel(content, title=f"[bold]{title}[/]", title_align="left", border_style="blue", padding=(0, 1))
        console.print(panel)
    else:
        console.print(content)


def print_ok(message: str) -> None:
    get_console().print(f"[green]✓[/] {message}")


def print_error(message: str) -> None:
    get_console().print(f"[red]Error:[/] {message}")


def print_list(items: list[str], title: str | None = None) -> None:
    console = get_console()
    if title:
        console.print(f"[bold]{title}[/]")
    for item in items:
        console.print(f"  {item}")


def val(v, default: str = "—") -> str:
    """Safe string conversion for display values."""
    if v is None:
        return default
    return str(v)
