import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path.home() / ".nova" / "config.yaml"

ROTATION_DEFAULTS = {
    "enabled": False,
    "idle_threshold_minutes": 2880,
    "warning_delay_seconds": 120,
    "memorize_timeout_seconds": 180,
    "handoff_timeout_seconds": 180,
    "min_activity_bytes": 10000,
    "dream_capture_threshold": 3,
    "dream_check_interval_hours": 24,
}


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    config_path = config_path or DEFAULT_CONFIG_PATH

    data: dict[str, Any] = {}
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text()) or {}

    slack = data.setdefault("slack", {})

    env_bot = os.environ.get("NOVA_SLACK_BOT_TOKEN")
    env_app = os.environ.get("NOVA_SLACK_APP_TOKEN")
    if env_bot:
        slack["bot_token"] = env_bot
    if env_app:
        slack["app_token"] = env_app

    if not slack.get("bot_token"):
        raise ValueError(
            "Slack bot_token not configured. Set NOVA_SLACK_BOT_TOKEN env var "
            "or add slack.bot_token to ~/.nova/config.yaml"
        )

    rotation = data.setdefault("rotation", {})
    for key, default in ROTATION_DEFAULTS.items():
        rotation.setdefault(key, default)

    return data
