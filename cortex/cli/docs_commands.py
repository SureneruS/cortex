"""Auto-generate CLI reference docs from Click introspection."""
from __future__ import annotations

from pathlib import Path

import click

from cortex.cli import JsonCommand

SKILL_PATH = Path(__file__).resolve().parent.parent.parent / "plugin" / "skills" / "cortex-cli" / "SKILL.md"

AUTO_START = "<!-- AUTO-START -->"
AUTO_END = "<!-- AUTO-END -->"

FRONTMATTER = """\
---
name: cortex-cli
description: Use when you need to interact with Cortex — logging updates/decisions, managing streams, PR operations, session orchestration, checkpoints, cron jobs, or searching history. Complete CLI reference for all cortex commands.
---

# Cortex CLI Reference

Output defaults to human-friendly Rich format on TTY, JSON when piped (non-TTY). Use `--json` flag to force JSON. CC sessions get JSON automatically since Bash tool output is piped. Errors return `{"error": "..."}` with exit code 1 in JSON mode.
"""

# Hand-written sections injected after auto-generated command groups
SECTION_NOTES: dict[str, str] = {
    "stream": """\
### Logging guidelines
- **Log as you go** — if you make a decision or complete a milestone, log it immediately
- `stream log` for progress: milestones, blockers, phase completions
- `stream decide` for choices: architecture, tradeoffs, "we chose X because Y"
- Check `cortex stream list` at session start for active work context
""",
    "session": """\
### Session spawn notes
- `--goal` is metadata only (shows in list/get)
- `--prompt` is what gets typed into the session via channels
- `--beside`/`--below` resolve by session name, ID prefix, or %pane_id
- `--color` auto-cycles (blue/green/yellow/purple/orange/pink/cyan/red) if omitted
- Don't use both `--prompt` and `session message` — pick one
""",
}

# Commands to exclude from docs (internal/deprecated)
EXCLUDE_COMMANDS = {"team", "docs"}
EXCLUDE_SUBCOMMANDS: dict[str, set[str]] = {
    "session": {"auto-close", "register", "paint"},
    "daemon": {"run"},
}

# Section titles for top-level groups
SECTION_TITLES: dict[str, str] = {
    "stream": "Streams",
    "checkpoint": "Checkpoints",
    "pr": "PR Operations",
    "session": "Sessions",
    "cron": "Cron Jobs",
    "daemon": "Daemon",
    "test": "Testing",
}

# Order for sections in the generated doc
SECTION_ORDER = ["stream", "checkpoint", "pr", "session", "cron", "daemon", "test"]


def _is_skippable(param: click.Parameter) -> bool:
    """Skip --json flags and hidden options."""
    if param.name in ("json_output",):
        return True
    if isinstance(param, click.Option) and param.hidden:
        return True
    if isinstance(param, click.Option) and "--json" in param.opts:
        return True
    return False


def _format_param(param: click.Parameter) -> str | None:
    """Format a Click parameter as a CLI usage string."""
    if _is_skippable(param):
        return None

    if isinstance(param, click.Argument):
        name = param.human_readable_name.upper()
        if not param.required:
            return f"[{name}]"
        if param.nargs == -1:
            return f"{name}..."
        return f"<{name.lower()}>"

    if isinstance(param, click.Option):
        flag = param.opts[0]
        if param.is_flag:
            return flag
        type_name = ""
        if param.type and param.type.name not in ("TEXT", "text"):
            type_name = f" {param.type.name.upper()}"
        return f"{flag}{type_name}"

    return None


def _format_command_line(group_name: str, cmd_name: str, cmd: click.Command) -> str:
    """Build a single command usage line like: cortex stream list [--status active|completed|all]"""
    parts = [f"cortex {group_name} {cmd_name}"]

    # Arguments first
    for param in cmd.params:
        if isinstance(param, click.Argument):
            formatted = _format_param(param)
            if formatted:
                parts.append(formatted)

    # Then options
    opts = []
    for param in cmd.params:
        if isinstance(param, click.Option):
            formatted = _format_param(param)
            if formatted:
                help_text = param.help or ""
                # Show choices inline
                if isinstance(param.type, click.Choice):
                    choices = "|".join(param.type.choices)
                    formatted = f"{param.opts[0]} {choices}"
                elif param.default is not None and param.default != "" and not param.is_flag:
                    pass  # Don't show defaults in the command line

                if param.required:
                    opts.append(formatted)
                else:
                    opts.append(f"[{formatted}]")

    parts.extend(opts)
    return " ".join(parts)


def _format_option_help(param: click.Option) -> str | None:
    """Format an option's help text for the detail block."""
    if param.name in ("json_output",):
        return None
    if not param.help:
        return None

    flag = param.opts[0]
    help_text = param.help

    if isinstance(param.type, click.Choice):
        choices = "|".join(param.type.choices)
        return f"  - `{flag}` — {help_text} ({choices})"
    if param.is_flag:
        return f"  - `{flag}` — {help_text}"
    return f"  - `{flag}` — {help_text}"


def _generate_group_section(group_name: str, group: click.Group) -> str:
    """Generate markdown for a command group."""
    title = SECTION_TITLES.get(group_name, group_name.title())
    help_text = group.help or ""

    lines = [f"## {title}", ""]
    if help_text and help_text != f"Manage {group_name}.":
        lines.append(help_text)
        lines.append("")

    lines.append("```bash")

    exclude = EXCLUDE_SUBCOMMANDS.get(group_name, set())
    commands = sorted(group.commands.items())

    for cmd_name, cmd in commands:
        if cmd_name in exclude:
            continue
        if getattr(cmd, "hidden", False):
            continue

        usage = _format_command_line(group_name, cmd_name, cmd)
        short_help = cmd.help.split("\n")[0] if cmd.help else ""
        lines.append(f"# {short_help}")
        lines.append(usage)
        lines.append("")

    # Remove trailing blank line inside code block
    if lines and lines[-1] == "":
        lines.pop()
    lines.append("```")

    # Add hand-written notes if any
    notes = SECTION_NOTES.get(group_name)
    if notes:
        lines.append("")
        lines.append(notes.rstrip())

    return "\n".join(lines)


def _generate_misc_section(cli_group: click.Group) -> str:
    """Generate the 'Other' section for top-level non-group commands."""
    lines = ["## Other", "", "```bash"]

    group_names = set(SECTION_ORDER) | EXCLUDE_COMMANDS
    for name, cmd in sorted(cli_group.commands.items()):
        if name in group_names:
            continue
        if isinstance(cmd, click.Group):
            continue
        if getattr(cmd, "hidden", False):
            continue

        short_help = cmd.help.split("\n")[0] if cmd.help else ""
        # Build simple usage
        parts = [f"cortex {name}"]
        for param in cmd.params:
            formatted = _format_param(param)
            if formatted:
                if isinstance(param, click.Option) and not param.required:
                    parts.append(f"[{formatted}]")
                else:
                    parts.append(formatted)
        usage = " ".join(parts)
        lines.append(f"# {short_help}")
        lines.append(usage)
        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()
    lines.append("```")
    return "\n".join(lines)


def generate_skill_doc(cli_group: click.Group) -> str:
    """Generate the full SKILL.md content."""
    sections = [FRONTMATTER.rstrip(), "", AUTO_START, ""]

    for group_name in SECTION_ORDER:
        cmd = cli_group.commands.get(group_name)
        if cmd and isinstance(cmd, click.Group):
            sections.append(_generate_group_section(group_name, cmd))
            sections.append("")

    sections.append(_generate_misc_section(cli_group))
    sections.append("")
    sections.append(AUTO_END)

    return "\n".join(sections) + "\n"


@click.group(cls=click.Group)
def docs() -> None:
    """Generate CLI documentation."""
    pass


@docs.command("generate")
@click.option("--check", is_flag=True, help="Check if docs are up-to-date (exit 1 if stale)")
@click.option("--output", "output_path", default=None, help="Output path (default: SKILL.md)")
def docs_generate(check: bool, output_path: str | None) -> None:
    """Generate SKILL.md from Click command definitions."""
    from cortex.cli import cli as root_cli

    content = generate_skill_doc(root_cli)
    target = Path(output_path) if output_path else SKILL_PATH

    if check:
        if not target.exists():
            click.echo(f"SKILL.md not found at {target}")
            raise SystemExit(1)
        existing = target.read_text()
        if existing == content:
            click.echo("SKILL.md is up-to-date.")
        else:
            click.echo("SKILL.md is STALE — run `cortex docs generate` to update.")
            raise SystemExit(1)
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    click.echo(f"Generated: {target}")
