#!/usr/bin/env python3
"""Weekly dashboard — Textual-based goal-centric control plane.

Usage:
    python dashboard.py          # Live mode (scrollable, auto-refreshes)
    python dashboard.py --once   # Single render and exit
"""

import json
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from rich.console import Console, Group
from rich.table import Table
from rich.text import Text
from rich import box

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll, Horizontal, Container
from textual.widgets import Static, Footer, DataTable, Collapsible, Sparkline
from textual import work

# --- Paths ---
DATA_DIR = Path(__file__).parent.parent / "data"
WEEK_FILE = DATA_DIR / "week.json"

# --- Symbols ---
SYM = {
    "done": "\u2713",
    "active": "\u25ba",
    "pending": "\u25cb",
    "blocked": "\u2717",
    "draft": "\u25c7",
    "review": "\u25c8",
    "ci_pass": "\u25cf",
    "ci_fail": "\u2717",
    "ci_mixed": "\u25d1",
    "ci_none": "\u25cb",
    "unplanned": "*",
    "wip": "~",
    "backlog": "\u00b7",
}

FEEDBACK_TICKETS = {"ATS-949", "ATS-992", "ATS-950", "ATS-828", "ATS-832"}
CORTEX_BASE = "http://localhost:9400/api/dashboard"

CI_STYLE = {"pass": "green", "fail": "red bold", "mixed": "yellow", "pending": "dim"}
CI_SYM = {
    "pass": SYM["ci_pass"],
    "fail": SYM["ci_fail"],
    "mixed": SYM["ci_mixed"],
    "pending": SYM["ci_none"],
}
REV_STYLE = {
    "approved": "green",
    "changes_requested": "red bold",
    "needs_review": "yellow",
    "draft": "dim",
}
REV_SYM = {
    "approved": SYM["done"],
    "changes_requested": SYM["blocked"],
    "needs_review": SYM["review"],
    "draft": SYM["draft"],
}


# ============================================================
#  URL builders
# ============================================================


def linear_url(tid: str) -> str:
    return f"linear://cercli/issue/{tid}"


def pr_url(repo_full: str, number: int) -> str:
    return f"https://github.com/{repo_full}/pull/{number}"


def focus_pane_url(pane_id: int) -> str:
    return f"{CORTEX_BASE}/focus-pane?pane_id={pane_id}"


def app_uri(url: str, rtype: str) -> str:
    if rtype == "linear" and url.startswith("https://linear.app/"):
        return "linear://" + url.removeprefix("https://linear.app/")
    if rtype == "notion" and "notion.so/" in url:
        return url.replace("https://www.notion.so/", "notion://www.notion.so/").replace(
            "https://notion.so/", "notion://notion.so/"
        )
    return url


# ============================================================
#  Textual markup helpers
# ============================================================


def _esc(text: str) -> str:
    return text.replace("[", "\\[")


def _link(text: str, url: str, style: str = "") -> str:
    escaped = _esc(text)
    url_escaped = url.replace("'", "\\'")
    if style:
        return f"[{style}][@click=app.open_link('{url_escaped}')]{escaped}[/][/{style}]"
    return f"[@click=app.open_link('{url_escaped}')]{escaped}[/]"


def _s(symbol: str, style: str = "") -> str:
    return f"[{style}]{symbol}[/{style}]" if style else symbol


# ============================================================
#  Data fetching (unchanged)
# ============================================================


def load_week():
    with open(WEEK_FILE) as f:
        return json.load(f)


def fetch_prs(repos):
    prs = []
    for repo in repos:
        try:
            r = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--author",
                    "@me",
                    "--state",
                    "open",
                    "--json",
                    "number,title,isDraft,reviewDecision,statusCheckRollup,url,createdAt",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if r.returncode == 0:
                for pr in json.loads(r.stdout):
                    pr["repo"] = repo.split("/")[-1]
                    pr["repo_full"] = repo
                    prs.append(pr)
        except Exception:
            pass
    return prs


def fetch_threads(prs):
    threads = {}
    for pr in prs:
        if pr.get("isDraft"):
            continue
        try:
            owner, name = pr["repo_full"].split("/")
            num = pr["number"]
            q = (
                f'query{{repository(owner:"{owner}",name:"{name}")'
                f"{{pullRequest(number:{num})"
                f"{{reviewThreads(first:30){{nodes{{isResolved}}}}}}}}}}"
            )
            r = subprocess.run(
                ["gh", "api", "graphql", "-f", f"query={q}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0:
                data = json.loads(r.stdout)
                nodes = data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
                resolved = sum(1 for t in nodes if t["isResolved"])
                unresolved = sum(1 for t in nodes if not t["isResolved"])
                threads[f"{pr['repo']}#{num}"] = (resolved, unresolved)
        except Exception:
            pass
    return threads


def classify_ci(pr):
    checks = pr.get("statusCheckRollup") or []
    if not checks:
        return "pending", "no CI"
    conclusions = [c.get("conclusion") for c in checks]
    passed = sum(1 for c in conclusions if c == "SUCCESS")
    total = len(conclusions)
    if all(c == "SUCCESS" for c in conclusions):
        return "pass", f"{passed}/{total}"
    if any(c == "FAILURE" for c in conclusions):
        failed = sum(1 for c in conclusions if c == "FAILURE")
        return "fail", f"{failed} fail"
    return "mixed", f"{passed}/{total}"


def classify_review(pr):
    if pr.get("isDraft"):
        return "draft", "draft"
    d = pr.get("reviewDecision", "")
    if d == "APPROVED":
        return "approved", "approved"
    if d == "CHANGES_REQUESTED":
        return "changes_requested", "changes req"
    return "needs_review", "needs review"


def _is_feedback_goal(g):
    return g.get("linear", "") in FEEDBACK_TICKETS


def _short_title(title):
    return title.split(": ", 1)[1] if ": " in title else title


# ============================================================
#  Markup builders
# ============================================================


def _pr_inline(pr, threads):
    parts = []
    num = pr["number"]
    parts.append(_link(f"#{num}", pr_url(pr["repo_full"], num), "underline"))
    ci_s, ci_d = classify_ci(pr)
    parts.append(f"[{CI_STYLE[ci_s]}]{CI_SYM[ci_s]} {_esc(ci_d)}[/{CI_STYLE[ci_s]}]")
    rev_s, rev_d = classify_review(pr)
    parts.append(f"[{REV_STYLE[rev_s]}]{REV_SYM[rev_s]} {_esc(rev_d)}[/{REV_STYLE[rev_s]}]")
    key = f"{pr['repo']}#{num}"
    resolved, unresolved = threads.get(key, (0, 0))
    if unresolved > 0:
        parts.append(f"[red]{SYM['blocked']} {unresolved} open[/red]")
    elif resolved > 0:
        parts.append(f"[green]{SYM['done']} ok[/green]")
    return " ".join(parts)


def _goal_line(g, pr_map, threads, session_map):
    s = g["status"]
    linear = g.get("linear", "")
    is_fb = _is_feedback_goal(g)
    sym = SYM.get(s, SYM["pending"])

    # Determine styles
    if s == "done":
        sym_st, txt_st = "dim", "dim"
    elif s == "active":
        sym_st, txt_st = "bold green", "bold"
    elif is_fb:
        sym_st, txt_st = "bold cyan", "bold cyan"
    else:
        sym_st, txt_st = "bold", "bold"

    # Goal text with Linear link
    if linear and linear in g["text"]:
        before, after = g["text"].split(linear, 1)
        text = _esc(before) + _link(linear, linear_url(linear), "underline") + _esc(after)
    elif linear:
        text = _link(g["text"], linear_url(linear))
    else:
        text = _esc(g["text"])

    # Right-side context
    ctx = []
    pr_num = g.get("pr", "").lstrip("#")
    if pr_num and pr_num in pr_map:
        ctx.append(_pr_inline(pr_map[pr_num], threads))
    if linear:
        session = session_map.get(linear.lower())
        if session:
            pane_id = session.get("pane")
            if pane_id:
                ctx.append(f"[green]{_link(f'pane:{pane_id}', focus_pane_url(pane_id))}[/green]")
            else:
                ctx.append(f"[green]{SYM['active']}[/green]")
    note = g.get("note", "")
    if note and "block" in note.lower():
        ctx.append(f"[red]{_esc(note)}[/red]")
    elif note and not ctx:
        ctx.append(f"[dim]{_esc(note)}[/dim]")

    right = f"  [dim]\u2502[/dim] {'  '.join(ctx)}" if ctx else ""
    return f"{_s(sym, sym_st)} [{txt_st}]{text}[/{txt_st}]{right}"


# ============================================================
#  Textual App
# ============================================================


class DashboardApp(App):
    CSS = """
    Screen { background: #0d1117; }

    #scroll { scrollbar-size-vertical: 1; }

    .panel {
        border: solid #30363d;
        padding: 0 1;
        margin: 0 1 1 1;
        height: auto;
    }
    .panel-content { padding: 0; }

    #progress-panel {
        border: solid #30363d;
        margin: 1 1 0 1;
        padding: 0 1;
        height: 3;
    }
    #progress-bar { height: 1; }
    #sparkline-row {
        height: 1;
        margin: 0;
        padding: 0;
    }
    #goal-spark {
        width: 1fr;
        height: 1;
        margin: 0;
    }

    #goals-panel { border: solid #58a6ff; }

    #completed-section {
        height: auto;
        margin: 0;
        padding: 0;
    }
    #completed-section CollapsibleTitle {
        color: #6e7681;
        padding: 0;
    }

    #bottom-row {
        height: auto;
        margin: 0;
    }
    #prs-panel { width: 3fr; }
    #pr-table {
        height: auto;
        max-height: 14;
        scrollbar-size-vertical: 1;
    }
    #pr-table > .datatable--header { color: #6e7681; }
    #pr-table > .datatable--cursor { background: #1a1f2b; }

    #side-col { width: 2fr; }
    #sessions-panel, #wip-panel, #resources-panel {
        height: auto;
    }

    Footer { background: #0d1117; }
    """

    BINDINGS = [("q", "quit", "Quit"), ("r", "force_refresh", "Refresh")]

    def __init__(self):
        super().__init__()
        self._data = load_week()
        self._repos = self._data.get("repos_to_track", ["cercli/recruitment-backend"])
        self._prs: list = []
        self._threads: dict = {}
        self._pr_row_urls: dict = {}  # row_key -> url

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="scroll"):
            with Container(id="progress-panel"):
                yield Static(id="progress-bar")
                with Horizontal(id="sparkline-row"):
                    yield Sparkline([], id="goal-spark")
            with Container(id="goals-panel", classes="panel"):
                yield Static(id="goals-content", classes="panel-content")
                with Collapsible(title="Completed", collapsed=True, id="completed-section"):
                    yield Static(id="completed-content")
            with Horizontal(id="bottom-row"):
                with Container(id="prs-panel", classes="panel"):
                    yield DataTable(id="pr-table", cursor_type="row", zebra_stripes=True)
                with Container(id="side-col"):
                    with Container(id="sessions-panel", classes="panel"):
                        yield Static(id="sessions-content", classes="panel-content")
                    with Container(id="wip-panel", classes="panel"):
                        yield Static(id="wip-content", classes="panel-content")
                    with Container(id="resources-panel", classes="panel"):
                        yield Static(id="resources-content", classes="panel-content")
        yield Footer()

    def on_mount(self) -> None:
        self._update_display()
        self._fetch_prs_bg()
        self.set_interval(1, self._tick_data)
        self.set_interval(120, self._fetch_prs_bg)

    def _tick_data(self) -> None:
        try:
            self._data = load_week()
        except Exception:
            pass
        self._update_display()

    @work(thread=True, group="fetch", exclusive=True)
    def _fetch_prs_bg(self) -> None:
        prs = fetch_prs(self._repos)
        threads = fetch_threads(prs)
        self.call_from_thread(self._apply_pr_data, prs, threads)

    def _apply_pr_data(self, prs: list, threads: dict) -> None:
        self._prs = prs
        self._threads = threads
        self._update_display()

    def action_force_refresh(self) -> None:
        self._fetch_prs_bg()

    def action_open_link(self, url: str) -> None:
        if url.startswith(("http://", "https://")):
            webbrowser.open(url)
        else:
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        url = self._pr_row_urls.get(event.row_key)
        if url:
            self.action_open_link(url)

    def _update_display(self) -> None:
        data = self._data
        prs = self._prs
        threads = self._threads

        # --- Indexes ---
        pr_map = {str(pr["number"]): pr for pr in prs}
        session_map = {}
        for s in data.get("sessions", []):
            parts = s["name"].split("-")
            if len(parts) >= 2:
                session_map["-".join(parts[:2])] = s

        goals = data.get("goals", [])
        unplanned = data.get("unplanned", [])
        done_count = sum(1 for g in goals if g["status"] == "done")
        total = len(goals)
        ts = datetime.now().strftime("%H:%M")
        sessions_active = len(data.get("sessions", []))

        # === PROGRESS PANEL ===
        bar_w = max(self.size.width - 45, 20)
        filled = int(bar_w * done_count / total) if total else 0
        bar = f"[green]{'█' * filled}[/green][#30363d]{'░' * (bar_w - filled)}[/#30363d]"
        self.query_one("#progress-panel").border_title = f"Week of {data.get('week_of', '?')}"
        sess_info = (
            f"  {_s(SYM['active'], 'green')} [bold]{sessions_active}[/bold] [dim]session{'s' if sessions_active != 1 else ''}[/dim]"
            if sessions_active
            else ""
        )
        self.query_one("#progress-bar", Static).update(
            f" {bar} [bold]{done_count}[/bold][dim]/{total}[/dim]{sess_info}  [dim]{ts}[/dim]"
        )

        # Sparkline: only show when real history exists
        history = data.get("history", [])
        spark = self.query_one("#goal-spark", Sparkline)
        sparkline_row = self.query_one("#sparkline-row")
        if len(history) >= 2:
            spark.data = history
            sparkline_row.display = True
        else:
            sparkline_row.display = False

        # === GOALS PANEL ===
        feedback_pending = [g for g in goals if g["status"] != "done" and _is_feedback_goal(g)]
        other_pending = [g for g in goals if g["status"] != "done" and not _is_feedback_goal(g)]
        completed = [g for g in goals if g["status"] == "done"]
        done_unplanned = [u for u in unplanned if u.get("status") == "done"]
        active_unplanned = [u for u in unplanned if u.get("status") != "done"]

        lines = []
        if feedback_pending:
            lines.append(
                f"[bold cyan]{'\u2500' * 3} Feedback Management {'\u2500' * 3}[/bold cyan]"
            )
            for g in feedback_pending:
                lines.append(_goal_line(g, pr_map, threads, session_map))

        if other_pending:
            lines.append(f"\n[bold]{'\u2500' * 3} Other {'\u2500' * 3}[/bold]")
            for g in other_pending:
                lines.append(_goal_line(g, pr_map, threads, session_map))

        total_done = len(completed) + len(done_unplanned)

        if active_unplanned:
            lines.append(
                f"\n[magenta bold]{'\u2500' * 3} * Unplanned {'\u2500' * 3}[/magenta bold]"
            )
            for g in active_unplanned:
                lines.append(_goal_line(g, pr_map, threads, session_map))

        self.query_one("#goals-panel").border_title = f"GOALS  {done_count}/{total}"
        self.query_one("#goals-content", Static).update("\n".join(lines))

        # Completed in collapsible
        completed_section = self.query_one("#completed-section", Collapsible)
        if total_done:
            completed_section.title = (
                f"{SYM['done']} {total_done} completed (incl. {len(done_unplanned)} unplanned)"
            )
            done_lines = []
            for g in completed + done_unplanned:
                done_lines.append(f"[dim]{SYM['done']} {_esc(g['text'])}[/dim]")
            self.query_one("#completed-content", Static).update("\n".join(done_lines))
            completed_section.display = True
        else:
            completed_section.display = False

        # === PRs TABLE ===
        goal_pr_nums = {g["pr"].lstrip("#") for g in goals + unplanned if g.get("pr")}
        all_active = sorted(
            [p for p in prs if not p.get("isDraft")], key=lambda p: p["number"], reverse=True
        )
        all_drafts = sorted(
            [p for p in prs if p.get("isDraft")], key=lambda p: p["number"], reverse=True
        )

        table = self.query_one("#pr-table", DataTable)
        table.clear(columns=True)
        self._pr_row_urls = {}

        table.add_columns("PR", "Title", "CI", "Review", "Threads")

        for pr in all_active:
            ci_s, ci_d = classify_ci(pr)
            rev_s, rev_d = classify_review(pr)
            key = f"{pr['repo']}#{pr['number']}"
            _, unresolved = threads.get(key, (0, 0))
            thr = f"{SYM['blocked']} {unresolved}" if unresolved else ""
            tied = str(pr["number"]) in goal_pr_nums

            pr_num = Text(f"{'*' if tied else ' '}#{pr['number']}")
            ci_cell = Text(f"{CI_SYM[ci_s]} {ci_d}", style=CI_STYLE[ci_s])
            rev_cell = Text(f"{REV_SYM[rev_s]} {rev_d}", style=REV_STYLE[rev_s])
            thr_cell = Text(thr, style="red") if thr else Text("")

            row_key = table.add_row(pr_num, _short_title(pr["title"]), ci_cell, rev_cell, thr_cell)
            self._pr_row_urls[row_key] = pr_url(pr["repo_full"], pr["number"])

        for pr in all_drafts[:2]:
            pr_num = Text(f" #{pr['number']}", style="dim")
            row_key = table.add_row(
                pr_num,
                Text(_short_title(pr["title"]), style="dim"),
                Text(f"{SYM['draft']} draft", style="dim"),
                Text(""),
                Text(""),
            )
            self._pr_row_urls[row_key] = pr_url(pr["repo_full"], pr["number"])

        extra = len(all_drafts) - 2
        if extra > 0:
            table.add_row(
                Text(""), Text(f"+{extra} more drafts", style="dim"), Text(""), Text(""), Text("")
            )

        self.query_one(
            "#prs-panel"
        ).border_title = f"PRs  {len(all_active)} active  {len(all_drafts)} draft"

        # === SESSIONS PANEL ===
        sessions = data.get("sessions", [])
        sess_lines = []
        for s in sessions:
            pane_id = s.get("pane")
            name = _esc(s["name"])
            task = _esc(s.get("task", ""))
            if pane_id:
                sess_lines.append(
                    f"{_s(SYM['active'], 'green')} "
                    f"[green]{_link(name, focus_pane_url(pane_id))}[/green]"
                    f" [dim]{task}[/dim]"
                )
            else:
                sess_lines.append(
                    f"{_s(SYM['active'], 'green')} [green]{name}[/green] [dim]{task}[/dim]"
                )

        self.query_one("#sessions-panel").border_title = f"Sessions  {len(sessions)}"
        self.query_one("#sessions-content", Static).update(
            "\n".join(sess_lines) if sess_lines else "[dim]No active sessions[/dim]"
        )

        # === WIP PANEL ===
        wip = data.get("wip", [])
        blockers = data.get("blockers", [])
        wip_lines = []
        for item in wip:
            linear = item.get("linear", "")
            text = item["text"]
            note = item.get("note", "")
            if linear and linear in text:
                before, after = text.split(linear, 1)
                display = (
                    _esc(before) + _link(linear, linear_url(linear), "underline") + _esc(after)
                )
            elif linear:
                display = _link(text, linear_url(linear))
            else:
                display = _esc(text)
            note_m = f" [dim]{_esc(note)}[/dim]" if note else ""
            wip_lines.append(f"{_s(SYM['wip'], 'yellow')} {display}{note_m}")

        if blockers:
            wip_lines.append("")
            for b in blockers:
                linear = b.get("linear", "")
                if linear:
                    display = _link(b["text"], linear_url(linear), "red")
                else:
                    display = f"[red]{_esc(b['text'])}[/red]"
                wip_lines.append(f"{_s(SYM['blocked'], 'red')} {display}")

        backlog = data.get("backlog", [])
        if backlog:
            wip_lines.append(f"\n[dim]{SYM['backlog']} {len(backlog)} parked[/dim]")

        self.query_one("#wip-panel").border_title = "WIP"
        self.query_one("#wip-content", Static).update(
            "\n".join(wip_lines) if wip_lines else "[dim]Clear[/dim]"
        )

        # === RESOURCES PANEL ===
        resources = data.get("resources", [])
        type_sym = {
            "linear": ("\u25c6", "blue"),
            "slack": ("#", "green"),
            "notion": ("\u25a3", ""),
            "figma": ("\u25c8", "magenta"),
            "github": ("\u2299", ""),
        }
        res_lines = []
        for r in resources:
            sym_ch, color = type_sym.get(r.get("type", ""), ("\u00b7", ""))
            url = r.get("url", "")
            label = _esc(r["label"])
            if url and url != "#":
                display = _link(label, app_uri(url, r.get("type", "")), color)
            else:
                display = f"[{color}]{label}[/{color}]" if color else label
            res_lines.append(f"{_s(sym_ch, color)} {display}")

        self.query_one("#resources-panel").border_title = "Resources"
        self.query_one("#resources-content", Static).update(
            "\n".join(res_lines) if res_lines else "[dim]None[/dim]"
        )


# ============================================================
#  --once mode (Rich Console)
# ============================================================


def _once_render():
    console = Console(emoji=False)
    data = load_week()
    repos = data.get("repos_to_track", ["cercli/recruitment-backend"])
    prs = fetch_prs(repos)  # noqa: F841 — used by dashboard sections not yet wired
    session_map = {}
    for s in data.get("sessions", []):
        parts = s["name"].split("-")
        if len(parts) >= 2:
            session_map["-".join(parts[:2])] = s

    goals = data.get("goals", [])
    unplanned = data.get("unplanned", [])
    done_count = sum(1 for g in goals if g["status"] == "done")
    total = len(goals)
    w = console.width

    def _lr(text, url, style=""):
        t = Text(text, style=style)
        t.stylize(f"link {url}")
        return t

    parts = []
    bar_w = min(20, w // 4)
    filled = int(bar_w * done_count / total) if total else 0
    bar = f"[green]{'\u2501' * filled}[/][bright_black]{'\u2500' * (bar_w - filled)}[/]"
    parts.append(
        Text.from_markup(
            f"[bold underline]WEEKLY GOALS[/]  [bright_black]Week of {data.get('week_of', '?')}[/]  "
            f"{bar} [bold]{done_count}[/]/{total}"
        )
    )
    parts.append(Text())

    for label, goal_list, skey in [
        (
            " [bold cyan underline]Feedback Management[/]",
            [g for g in goals if g["status"] != "done" and _is_feedback_goal(g)],
            "feedback",
        ),
        (
            " [underline]Other[/]",
            [g for g in goals if g["status"] != "done" and not _is_feedback_goal(g)],
            "default",
        ),
    ]:
        if not goal_list:
            continue
        parts.append(Text.from_markup(label))
        table = Table(
            box=box.SIMPLE, show_header=False, padding=(0, 1), expand=True, show_edge=False
        )
        table.add_column("S", width=2, no_wrap=True)
        table.add_column("Goal", ratio=2, no_wrap=True, overflow="ellipsis")
        table.add_column("Notes", ratio=1, no_wrap=True, style="bright_black", overflow="ellipsis")
        for g in goal_list:
            s = g["status"]
            sym = SYM.get(s, SYM["pending"])
            ss = "bold green" if s == "active" else ("bold cyan" if skey == "feedback" else "bold")
            cell = Text(g["text"])
            cell.stylize(ss)
            n = []
            if g.get("pr"):
                n.append(f"PR {g['pr']}")
            if g.get("note"):
                n.append(g["note"])
            table.add_row(Text(sym, style=ss), cell, Text("  ".join(n), style="bright_black"))
        parts.append(table)

    done_unplanned = [u for u in unplanned if u.get("status") == "done"]
    total_done = sum(1 for g in goals if g["status"] == "done") + len(done_unplanned)
    if total_done:
        parts.append(
            Text.from_markup(
                f" [bright_black]{SYM['done']} {total_done} completed (incl. {len(done_unplanned)} unplanned)[/]"
            )
        )

    parts.append(
        Text.from_markup(f"\n[bright_black] \u21bb {datetime.now().strftime('%H:%M:%S')}[/]")
    )
    console.print(Group(*parts))


def main():
    if "--once" in sys.argv:
        _once_render()
        return
    DashboardApp().run()


if __name__ == "__main__":
    main()
