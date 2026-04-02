#!/usr/bin/env python3
"""Auto-increment the patch version in cortex/_version.py based on git commit count."""

import subprocess
from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parent.parent / "cortex" / "_version.py"
MAJOR_MINOR = "0.3"


def get_commit_count() -> int:
    result = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        capture_output=True,
        text=True,
        cwd=VERSION_FILE.parent.parent,
    )
    if result.returncode != 0:
        return 0
    return int(result.stdout.strip()) + 1  # +1 for the upcoming commit


def main():
    patch = get_commit_count()
    version = f"{MAJOR_MINOR}.{patch}"
    VERSION_FILE.write_text(f'__version__ = "{version}"\n')
    # Stage the updated file
    subprocess.run(["git", "add", str(VERSION_FILE)], cwd=VERSION_FILE.parent.parent)
    print(f"Version bumped to {version}")


if __name__ == "__main__":
    main()
