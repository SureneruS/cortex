import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from nova.cli.main import cmd_start, cmd_list, cmd_exchange_install, cmd_rotate, main


@patch("nova.cli.main.create_window")
@patch("nova.cli.main.ensure_session")
def test_cmd_start_basic(mock_ensure, mock_create):
    cmd_start(repo="/path/to/recruitment-backend")

    mock_ensure.assert_called_once_with("sessions")
    mock_create.assert_called_once()
    create_args = mock_create.call_args
    assert create_args[1]["window_name"] == "recruitment-backend"
    assert "acceptEdits" in create_args[1]["command"]


@patch("nova.cli.main.create_window")
@patch("nova.cli.main.ensure_session")
def test_cmd_start_with_agent_and_prompt(mock_ensure, mock_create):
    cmd_start(
        repo="/path/to/recruitment-backend",
        name="custom-name",
        agent="dev",
        prompt="fix OAuth",
    )

    create_args = mock_create.call_args
    assert create_args[1]["window_name"] == "custom-name"
    assert "--agent dev" in create_args[1]["command"]
    assert "fix OAuth" in create_args[1]["command"]


@patch("nova.cli.main.list_windows", return_value=["recruitment-backend", "frontend"])
def test_cmd_list(mock_list, capsys, tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}, "slack": {}}')

    cmd_list(state_file=state_file)

    output = capsys.readouterr().out
    assert "recruitment-backend" in output
    assert "frontend" in output


@patch("nova.cli.main.list_windows", return_value=[])
def test_cmd_list_empty(mock_list, capsys, tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}, "slack": {}}')

    cmd_list(state_file=state_file)

    output = capsys.readouterr().out
    assert "No active sessions" in output


@patch("nova.cli.main.list_windows", return_value=["recruitment-backend"])
def test_cmd_list_with_session_data(mock_list, capsys, tmp_path):
    import json

    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "last_dream_run": None,
                "sessions": {
                    "abc123": {
                        "repos": ["recruitment-backend"],
                        "tmux_window": "recruitment-backend",
                        "slack_thread_ts": "1234567890.123",
                        "slack_channel": "C123",
                        "transcript_path": "/tmp/t",
                        "memory_injected": False,
                        "goal": None,
                        "started_at": "2026-01-01T00:00:00",
                        "last_active_at": "2026-01-01T00:00:00",
                        "tmux_target": None,
                    }
                },
                "slack": {},
            }
        )
    )

    cmd_list(state_file=state_file)

    output = capsys.readouterr().out
    assert "recruitment-backend" in output
    assert "threaded" in output


@patch("nova.cli.main.list_windows", return_value=["frontend"])
def test_cmd_list_no_state_file(mock_list, capsys, tmp_path):
    state_file = tmp_path / "nonexistent" / "state.json"

    cmd_list(state_file=state_file)

    output = capsys.readouterr().out
    assert "frontend" in output


def test_main_exchange_start():
    with (
        patch("sys.argv", ["nova", "exchange", "start"]),
        patch("nova.exchange.run_exchange") as mock_run,
    ):
        main()
    mock_run.assert_called_once()


def test_cmd_exchange_install(capsys, tmp_path):
    # Set up fake project root at tmp_path (mimics src/nova/cli/main.py -> root)
    fake_main = tmp_path / "src" / "nova" / "cli" / "main.py"
    fake_main.parent.mkdir(parents=True)
    fake_main.touch()

    plist_src = tmp_path / "resources" / "com.nova.exchange.plist"
    plist_src.parent.mkdir()
    plist_src.write_text("<plist>test</plist>")

    plist_dst = tmp_path / "Library" / "LaunchAgents" / "com.nova.exchange.plist"
    plist_dst.parent.mkdir(parents=True)

    logs_dir = tmp_path / ".nova" / "logs"

    with (
        patch.object(Path, "home", return_value=tmp_path),
        patch("nova.cli.main.__file__", str(fake_main)),
    ):
        cmd_exchange_install()

    output = capsys.readouterr().out
    assert "Installed plist to" in output
    assert "launchctl load" in output
    assert plist_dst.exists()
    assert plist_dst.read_text() == "<plist>test</plist>"
    assert logs_dir.is_dir()


def test_cmd_exchange_install_missing_plist(tmp_path):
    fake_main = tmp_path / "src" / "nova" / "cli" / "main.py"
    fake_main.parent.mkdir(parents=True)
    fake_main.touch()

    with (
        patch.object(Path, "home", return_value=tmp_path),
        patch("nova.cli.main.__file__", str(fake_main)),
    ):
        import pytest
        with pytest.raises(SystemExit):
            cmd_exchange_install()


def test_main_exchange_no_subcommand(capsys):
    with patch("sys.argv", ["nova", "exchange"]):
        main()
    output = capsys.readouterr().out
    assert "nova exchange" in output.lower()


@patch("nova.rotation.RotationManager")
def test_cmd_rotate(mock_rm_class, tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({
        "sessions": {
            "s1": {
                "repos": ["r"], "transcript_path": "/t.jsonl",
                "memory_injected": True, "goal": "test",
                "started_at": "2026-01-01T00:00:00Z", "last_active_at": "2026-01-01T00:00:00Z",
                "tmux_target": "sessions:mywin", "tmux_window": "mywin",
                "slack_thread_ts": "1.2", "slack_channel": "C1",
                "chain_id": None, "chain_sequence": 1, "parent_session_id": None,
                "compaction_count": 0, "status": "active",
            }
        }
    }))

    mock_mgr = MagicMock()
    mock_rm_class.return_value = mock_mgr

    cmd_rotate("mywin", state_file=state_file)
    mock_mgr.rotate_now.assert_called_once_with("s1")


@patch("nova.rotation.RotationManager")
def test_cmd_rotate_not_found(mock_rm_class, tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('{"sessions": {}}')

    import pytest
    with pytest.raises(SystemExit):
        cmd_rotate("nonexistent", state_file=state_file)
