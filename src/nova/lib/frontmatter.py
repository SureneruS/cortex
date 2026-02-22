import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DELIMITER = "---"
_DELIMITER_LEN = len(_DELIMITER)


def read_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text()
    if not text.startswith(_DELIMITER):
        raise ValueError(f"File does not start with frontmatter delimiter: {path}")

    try:
        end = text.index(_DELIMITER, _DELIMITER_LEN)
    except ValueError:
        raise ValueError(f"No closing frontmatter delimiter found in: {path}")

    yaml_block = text[_DELIMITER_LEN:end]
    body = text[end + _DELIMITER_LEN :]

    # The format is "---\nyaml\n---\nbody" — after splitting on the closing
    # delimiter we get "\nbody", so strip exactly one leading newline.
    if body.startswith("\n"):
        body = body[1:]

    metadata = yaml.safe_load(yaml_block) or {}
    return metadata, body


def write_frontmatter(path: Path, metadata: dict[str, Any], content: str) -> None:
    yaml_str = yaml.safe_dump(metadata, default_flow_style=False, sort_keys=False)
    path.write_text(f"{_DELIMITER}\n{yaml_str}{_DELIMITER}\n{content}\n")
