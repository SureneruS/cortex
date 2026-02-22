from pathlib import Path
from typing import Any

import yaml


def read_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text()
    if not text.startswith("---"):
        return {}, text

    # Find the closing --- (first occurrence after the opening ---)
    end = text.index("---", 3)
    yaml_block = text[3:end]
    body = text[end + 3 :]

    # Strip exactly one leading newline from body if present
    if body.startswith("\n"):
        body = body[1:]

    metadata = yaml.safe_load(yaml_block) or {}
    return metadata, body


def write_frontmatter(path: Path, metadata: dict[str, Any], content: str) -> None:
    yaml_str = yaml.safe_dump(metadata, default_flow_style=False, sort_keys=False)
    path.write_text(f"---\n{yaml_str}---\n{content}\n")
