#!/usr/bin/env python3
"""Generate fish completions from the cortex Click CLI tree.

Usage: uv run python scripts/gen-fish-completions.py > plugin/host/fish/cortex.fish
"""

from __future__ import annotations

import click

from cortex.cli import cli

# Known value suggestions for specific flags (flag_name → values or function call)
KNOWN_VALUES: dict[str, str | list[str]] = {
    "model": ["haiku", "sonnet", "opus"],
    "workspace": ["default", "background"],
    "permission-mode": ["plan", "full"],
    "effort": ["low", "medium", "high"],
    "color": ["blue", "green", "yellow", "purple", "orange", "pink", "cyan", "red"],
    "action": ["check-watches", "command"],
}

# Flags whose values come from dynamic functions
DYNAMIC_VALUES: dict[str, str] = {
    "repo": "(__cortex_repo_names)",
    "repos": "(__cortex_repo_names)",
    "beside": "(__cortex_session_names)",
    "below": "(__cortex_session_names)",
}

# Special: pr --repo uses github repos
PR_REPO_VALUES = "(__cortex_github_repos)"

# Commands that take a session ref as positional arg
SESSION_REF_CMDS = {
    "session": ["get", "close", "pause", "resume", "hide", "show", "restart",
                 "capture", "move", "paint", "auto-close", "update", "attach",
                 "message", "messages", "children", "link-cc", "watch"],
}

# Commands that take a stream ID as positional arg
STREAM_ID_CMDS = ["complete", "decide", "get", "log", "update"]

# Commands that take a cron job name as positional arg
CRON_NAME_CMDS = ["delete", "pause", "resume"]

# Status values per context
STATUS_VALUES = {
    ("session", "list"): ["active", "paused", "hidden", "dead", "completed"],
    ("stream", "list"): ["active", "completed", "all"],
    ("stream", "update"): ["active", "completed"],
    ("stream", "delete"): None,  # --type not --status
}

# --type values
TYPE_VALUES = {
    ("stream", "delete"): ["stream", "update", "decision"],
    ("stream", "edit"): ["update", "decision"],
}

# Paint colors (different from spawn colors)
PAINT_COLORS = ["green", "red", "amber", "blue", "purple", "gray"]

LAYOUT_VALUES = ["tiled", "even-horizontal", "even-vertical", "main-horizontal", "main-vertical"]


def get_groups_and_commands(group: click.Group) -> tuple[dict, dict]:
    """Walk the CLI tree and return groups (with subcommands) and leaf commands."""
    groups = {}
    leaves = {}
    for name, cmd in sorted(group.commands.items()):
        if isinstance(cmd, click.Group):
            groups[name] = cmd
        else:
            leaves[name] = cmd
    return groups, leaves


def get_params(cmd: click.Command) -> list[click.Parameter]:
    """Get non-help parameters."""
    return [p for p in cmd.params if p.name != "help" and not getattr(p, "hidden", False)]


def flag_name(param: click.Parameter) -> str:
    """Get the long flag name (e.g., --name)."""
    for opt in param.opts:
        if opt.startswith("--"):
            return opt[2:]
    return param.name or ""


def needs_value(param: click.Parameter) -> bool:
    """Does this flag take a value?"""
    return not isinstance(param, click.Argument) and param.is_flag is not True and param.nargs != 0


def get_values(flag: str, group_name: str | None, cmd_name: str | None) -> tuple[str, str]:
    """Return (values_str, flag_type) for a flag. flag_type is -x, -r, or empty."""
    # Special cases by context
    if flag == "repo" and group_name == "pr":
        return PR_REPO_VALUES, "-x"
    if flag == "status" and group_name and cmd_name:
        vals = STATUS_VALUES.get((group_name, cmd_name))
        if vals:
            return " ".join(vals), "-x"
    if flag == "type" and group_name and cmd_name:
        vals = TYPE_VALUES.get((group_name, cmd_name))
        if vals:
            return " ".join(vals), "-x"
    if flag == "color" and cmd_name == "paint":
        return " ".join(PAINT_COLORS), "-x"
    if flag == "layout":
        return " ".join(LAYOUT_VALUES), "-x"

    # Generic known values
    if flag in KNOWN_VALUES:
        v = KNOWN_VALUES[flag]
        return (" ".join(v) if isinstance(v, list) else v), "-x"
    if flag in DYNAMIC_VALUES:
        return DYNAMIC_VALUES[flag], "-x"

    return "", "-r"


def emit_line(condition: str, rest: str) -> str:
    return f'complete -c cortex -n "{condition}" {rest}'


def generate() -> list[str]:
    lines: list[str] = []
    a = lines.append

    a("# Fish completions for cortex CLI — auto-generated")
    a("# Run: uv run python scripts/gen-fish-completions.py > plugin/host/fish/cortex.fish")
    a("")
    a("complete -c cortex -f")
    a("")

    # Helpers
    a("# ── Helpers ──────────────────────────────────────────────────")
    a("function __cortex_session_names")
    a('    cortex session list --brief 2>/dev/null | python3 -c "import json,sys; [print(s[\'name\']) for s in json.load(sys.stdin) if s.get(\'status\') not in (\'completed\',\'dead\')]" 2>/dev/null')
    a("end")
    a("")
    a("function __cortex_repo_names")
    a("    ls ~/workspace/cercli/ 2>/dev/null")
    a("end")
    a("")
    a("function __cortex_stream_ids")
    a('    uv run python3 -c "')
    a("from pymongo import MongoClient")
    a("for s in MongoClient('mongodb://localhost:27017').cortex.streams.find({'status':'active'},{'_id':1,'title':1}):")
    a("    print(s['_id'] + '\\t' + s.get('title',''))")
    a('" 2>/dev/null')
    a("end")
    a("")
    a("function __cortex_cron_names")
    a('    cortex cron list 2>/dev/null | python3 -c "import json,sys; [print(j[\'name\']) for j in json.load(sys.stdin)]" 2>/dev/null')
    a("end")
    a("")
    a("function __cortex_github_repos")
    a('    printf "cercli/recruitment-backend\\ncercli/cercli-backend\\ncercli/frontend\\ncercli/workflows-backend\\ncercli/storage-service\\n"')
    a("end")
    a("")

    # Top-level commands
    groups, top_leaves = get_groups_and_commands(cli)
    all_cmds = sorted(list(groups.keys()) + list(top_leaves.keys()))
    cmd_list = " ".join(all_cmds)

    a("# ── Top-level commands ────────────────────────────────────────")
    a(f"set -l __cortex_cmds {cmd_list}")
    a("")

    for name in all_cmds:
        cmd = groups.get(name) or top_leaves.get(name)
        desc = (cmd.help or "").split("\n")[0].split("—")[0].strip().rstrip(".")
        a(emit_line(f"not __fish_seen_subcommand_from $__cortex_cmds", f'-a {name} -d "{desc}"'))

    a("")

    # Top-level leaf commands with flags
    for name, cmd in sorted(top_leaves.items()):
        params = get_params(cmd)
        if not params:
            continue
        a(f"# ── {name} ──")
        for p in params:
            fn = flag_name(p)
            if isinstance(p, click.Argument):
                continue
            vals, ftype = get_values(fn, None, name) if needs_value(p) else ("", "")
            parts = f"-l {fn}"
            if ftype:
                parts += f" {ftype}"
            if vals:
                parts += f' -a "{vals}"'
            parts += f' -d "{p.help or fn}"'
            a(emit_line(f"__fish_seen_subcommand_from {name}", parts))
        a("")

    # Groups with subcommands
    for group_name, group_cmd in sorted(groups.items()):
        sub_groups, sub_leaves = get_groups_and_commands(group_cmd)
        sub_cmds = sorted(list(sub_leaves.keys()) + list(sub_groups.keys()))
        if not sub_cmds:
            continue

        sub_list = " ".join(sub_cmds)
        a(f"# ── {group_name} ──────────────────────────────────────────────")
        a(f"set -l __{group_name}_cmds {sub_list}")

        # Subcommand completions
        for sub_name in sub_cmds:
            sub_cmd = sub_leaves.get(sub_name) or sub_groups.get(sub_name)
            desc = (sub_cmd.help or "").split("\n")[0].split("—")[0].strip().rstrip(".")
            if len(desc) > 40:
                desc = desc[:37] + "..."
            a(emit_line(
                f"__fish_seen_subcommand_from {group_name}; and not __fish_seen_subcommand_from ${_v(group_name)}",
                f'-a {sub_name} -d "{desc}"',
            ))

        a("")

        # Flags for each subcommand
        for sub_name in sub_cmds:
            sub_cmd = sub_leaves.get(sub_name) or sub_groups.get(sub_name)
            params = get_params(sub_cmd)
            if not params:
                continue

            for p in params:
                if isinstance(p, click.Argument):
                    continue
                fn = flag_name(p)
                vals, ftype = get_values(fn, group_name, sub_name) if needs_value(p) else ("", "")
                parts = f"-l {fn}"
                if ftype:
                    parts += f" {ftype}"
                if vals:
                    parts += f' -a "{vals}"'
                help_text = (p.help or fn).split("\n")[0]
                if len(help_text) > 40:
                    help_text = help_text[:37] + "..."
                parts += f' -d "{help_text}"'
                a(emit_line(
                    f"__fish_seen_subcommand_from {group_name}; and __fish_seen_subcommand_from {sub_name}",
                    parts,
                ))

        a("")

        # Dynamic positional args
        if group_name in SESSION_REF_CMDS:
            cmds = SESSION_REF_CMDS[group_name]
            a(f"# {group_name} commands that take session name as positional arg")
            a(f"for cmd in {' '.join(cmds)}")
            a(f'    complete -c cortex -n "__fish_seen_subcommand_from {group_name}; and __fish_seen_subcommand_from $cmd" -x -a "(__cortex_session_names)"')
            a("end")
            a("")

        if group_name == "stream":
            a("# stream commands that take STREAM_ID as positional arg")
            a(f"for cmd in {' '.join(STREAM_ID_CMDS)}")
            a('    complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from $cmd" -x -a "(__cortex_stream_ids)"')
            a("end")
            a("")

        if group_name == "cron":
            a("# cron commands that take job name as positional arg")
            a(f"for cmd in {' '.join(CRON_NAME_CMDS)}")
            a('    complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from $cmd" -x -a "(__cortex_cron_names)"')
            a("end")
            a("")

    return lines


def _v(group_name: str) -> str:
    return f"__{group_name}_cmds"


if __name__ == "__main__":
    for line in generate():
        print(line)
