"""Human-readable log viewer for structlog JSON logs."""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

from rich.console import Console
from rich.text import Text

LEVEL_STYLES = {
    "debug": "bright_black",
    "info": "bright_green",
    "warning": "bright_yellow bold",
    "error": "bright_red bold",
    "critical": "bright_red bold reverse",
}

# Keys handled specially — not dumped as extra fields
_META_KEYS = {"event", "level", "logger", "timestamp", "correlation_id", "positional_args"}


def _format_entry(entry: dict, *, source: str | None = None) -> Text:
    """Format a single JSON log entry as a rich Text object."""
    level = entry.get("level", "info")
    timestamp = entry.get("timestamp", "")
    event = entry.get("event", "")

    # Handle legacy %s-style formatting with positional_args
    positional = entry.get("positional_args")
    if positional and ("%s" in event or "%d" in event):
        try:
            event = event % tuple(positional)
        except (TypeError, ValueError):
            pass

    logger = entry.get("logger", "")

    text = Text()

    # Timestamp (dimmed, converted to local timezone)
    if timestamp and "T" in timestamp:
        from datetime import datetime, timezone
        try:
            dt = datetime.fromisoformat(timestamp.rstrip("Z") + "+00:00" if timestamp.endswith("Z") else timestamp)
            local_dt = dt.astimezone()
            time_part = local_dt.strftime("%H:%M:%S")
        except (ValueError, OSError):
            time_part = timestamp.split("T")[1][:8]
        text.append(time_part, style="grey70")
    else:
        text.append(timestamp[:8] if timestamp else "??:??:??", style="grey70")

    text.append(" ")

    # Source badge (for aggregated view)
    if source:
        text.append(f"[{source}]", style="magenta")
        text.append(" ")

    # Level badge
    level_style = LEVEL_STYLES.get(level, "")
    text.append(f"{level.upper():>7s}", style=level_style)
    text.append("  ")

    # Logger (shortened)
    short_logger = logger.replace("cortex.", "") if logger.startswith("cortex.") else logger
    if short_logger:
        text.append(f"{short_logger}", style="cyan")
        text.append("  ")

    # Event name
    text.append(event, style="bold")

    # Extra fields inline (anything not in _META_KEYS, skip empty values)
    extras = {k: v for k, v in entry.items() if k not in _META_KEYS and v != "" and v is not None}
    if extras:
        parts = []
        for key, value in extras.items():
            val_str = _format_value(value)
            if "\n" in val_str:
                # Multiline value — show on its own indented block
                indented = val_str.replace("\n", "\n" + " " * 20)
                parts.append(f"{key}={indented}")
            else:
                parts.append(f"{key}={val_str}")

        # Short extras go inline, long ones go on next line
        inline = "  " + "  ".join(parts)
        if len(inline) < 100 and "\n" not in inline:
            text.append(inline, style="grey70")
        else:
            for part in parts:
                text.append("\n")
                text.append(" " * 20, style="")
                text.append(part, style="grey70")

    text.append("\n")
    return text


def _format_value(value) -> str:
    """Format a value for display, handling nested dicts/lists gracefully."""
    if isinstance(value, str):
        if not value:
            return '""'
        if len(value) > 120:
            if "\n" in value:
                return value
            return value[:120] + "..."
        return value
    if isinstance(value, (dict, list)):
        try:
            formatted = json.dumps(value, indent=2)
            return formatted
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _parse_line(line: str) -> dict | None:
    """Parse a JSON log line, returning None for non-JSON lines."""
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _read_last_n_lines(path: Path, n: int) -> list[str]:
    """Read last N lines from a file efficiently."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return []

            # Read from end in chunks
            chunk_size = min(size, n * 512)
            f.seek(max(0, size - chunk_size))
            data = f.read().decode("utf-8", errors="replace")

        lines = data.splitlines()
        return lines[-n:]
    except OSError:
        return []


def tail_logs(
    log_file: Path,
    *,
    lines: int = 50,
    follow: bool = False,
    level_filter: str | None = None,
) -> None:
    """Display log entries from a structlog JSON file."""
    console = Console(highlight=False)

    level_priority = {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}
    min_level = level_priority.get(level_filter, 0) if level_filter else 0

    # Show recent history
    recent_lines = _read_last_n_lines(log_file, lines * 3)  # read extra since some may be filtered
    shown = 0
    buffer: deque[Text] = deque()
    for raw_line in recent_lines:
        entry = _parse_line(raw_line)
        if not entry:
            continue
        entry_level = level_priority.get(entry.get("level", "info"), 1)
        if entry_level < min_level:
            continue
        buffer.append(_format_entry(entry))
        if len(buffer) > lines:
            buffer.popleft()

    for text in buffer:
        console.print(text, end="")
        shown += 1

    if shown == 0:
        console.print("[dim]No log entries found.[/]")

    if not follow:
        return

    # Follow mode — tail the file
    console.print("[dim]--- following (Ctrl+C to stop) ---[/]")

    try:
        with open(log_file) as f:
            f.seek(0, 2)  # EOF
            while True:
                line = f.readline()
                if line:
                    entry = _parse_line(line)
                    if not entry:
                        continue
                    entry_level = level_priority.get(entry.get("level", "info"), 1)
                    if entry_level < min_level:
                        continue
                    console.print(_format_entry(entry), end="")
                else:
                    time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("\n[dim]stopped[/]")


# ── Aggregated multi-file log viewer ────────────────────────


def _derive_source(filename: str) -> str:
    """Derive a short source label from a log filename."""
    name = filename.removesuffix(".log")
    if name.startswith("cortex-"):
        name = name[7:]
    elif name.startswith("channels-mcp-"):
        name = "ch:" + name[13:]
    return name


def _collect_log_files(log_dir: Path) -> list[Path]:
    """Collect current (non-rotated) log files from the log directory."""
    return sorted(
        f for f in log_dir.iterdir()
        if f.is_file() and f.name.endswith(".log")
    )


def aggregate_tail_logs(
    log_dir: Path,
    *,
    lines: int = 50,
    follow: bool = False,
    level_filter: str | None = None,
) -> None:
    """Aggregate and display log entries from all current log files."""
    console = Console(highlight=False)

    log_files = _collect_log_files(log_dir)
    if not log_files:
        console.print("[dim]No log files found.[/]")
        return

    level_priority = {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}
    min_level = level_priority.get(level_filter, 0) if level_filter else 0

    # Collect recent entries from all files
    all_entries: list[tuple[str, dict]] = []
    for log_file in log_files:
        source = _derive_source(log_file.name)
        recent = _read_last_n_lines(log_file, lines * 3)
        for raw_line in recent:
            entry = _parse_line(raw_line)
            if not entry:
                continue
            entry_level = level_priority.get(entry.get("level", "info"), 1)
            if entry_level < min_level:
                continue
            all_entries.append((source, entry))

    # Sort by timestamp across all files, show last N
    all_entries.sort(key=lambda x: x[1].get("timestamp", ""))
    for source, entry in all_entries[-lines:]:
        console.print(_format_entry(entry, source=source), end="")

    if not all_entries:
        console.print("[dim]No log entries found.[/]")

    if not follow:
        return

    # Follow mode — tail all files simultaneously
    console.print("[dim]--- following (Ctrl+C to stop) ---[/]")

    handles: list[tuple[str, object]] = []
    try:
        for log_file in log_files:
            f = open(log_file)
            f.seek(0, 2)
            handles.append((_derive_source(log_file.name), f))

        while True:
            new_entries: list[tuple[str, dict]] = []
            for source, f in handles:
                while True:
                    line = f.readline()
                    if not line:
                        break
                    entry = _parse_line(line)
                    if not entry:
                        continue
                    entry_level = level_priority.get(entry.get("level", "info"), 1)
                    if entry_level < min_level:
                        continue
                    new_entries.append((source, entry))

            if new_entries:
                new_entries.sort(key=lambda x: x[1].get("timestamp", ""))
                for source, entry in new_entries:
                    console.print(_format_entry(entry, source=source), end="")
            else:
                time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("\n[dim]stopped[/]")
    finally:
        for _, f in handles:
            f.close()
