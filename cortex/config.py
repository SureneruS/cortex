from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CORTEX_DIR = Path.home() / ".cortex"
CONFIG_PATH = CORTEX_DIR / "config.json"

DEFAULT_REPOS = {
    "recruitment-backend": "~/workspace/cercli/recruitment-backend",
    "frontend": "~/workspace/cercli/frontend",
    "cercli-backend": "~/workspace/cercli/cercli-backend",
    "infrastructure": "~/workspace/cercli/infrastructure",
    "storage-service": "~/workspace/cercli/storage-service",
    "orbit": "~/workspace/cercli/orbit",
    "suren-toolbox": "~/workspace/cercli/suren-toolbox",
}

DEFAULT_DB_PATH = "~/.cortex/state.db"


@dataclass(frozen=True)
class Config:
    repos: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_REPOS))
    db_path: str = DEFAULT_DB_PATH

    @property
    def resolved_db_path(self) -> Path:
        return Path(self.db_path).expanduser()

    def resolved_repo_path(self, name: str) -> Path:
        return Path(self.repos[name]).expanduser()


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        return Config()
    raw = json.loads(CONFIG_PATH.read_text())
    return Config(
        repos=raw.get("repos", dict(DEFAULT_REPOS)),
        db_path=raw.get("db_path", DEFAULT_DB_PATH),
    )


def save_config(config: Config) -> None:
    CORTEX_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(
            {
                "repos": config.repos,
                "db_path": config.db_path,
            },
            indent=2,
        )
        + "\n"
    )
