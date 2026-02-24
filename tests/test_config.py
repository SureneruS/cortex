import pytest

from nova.config import load_config


def test_load_config_from_file(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "slack:\n  bot_token: xoxb-test\n  app_token: xapp-test\n"
    )
    config = load_config(config_file)
    assert config["slack"]["bot_token"] == "xoxb-test"
    assert config["slack"]["app_token"] == "xapp-test"


def test_load_config_from_env(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    monkeypatch.setenv("NOVA_SLACK_BOT_TOKEN", "xoxb-env")
    monkeypatch.setenv("NOVA_SLACK_APP_TOKEN", "xapp-env")
    config = load_config(config_file)
    assert config["slack"]["bot_token"] == "xoxb-env"
    assert config["slack"]["app_token"] == "xapp-env"


def test_load_config_env_overrides_file(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "slack:\n  bot_token: xoxb-file\n  app_token: xapp-file\n"
    )
    monkeypatch.setenv("NOVA_SLACK_BOT_TOKEN", "xoxb-env")
    config = load_config(config_file)
    assert config["slack"]["bot_token"] == "xoxb-env"
    assert config["slack"]["app_token"] == "xapp-file"


def test_load_config_missing_token_raises(tmp_path):
    config_file = tmp_path / "config.yaml"
    with pytest.raises(ValueError, match="bot_token"):
        load_config(config_file)
