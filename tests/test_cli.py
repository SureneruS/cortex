from unittest.mock import patch, MagicMock

from nova.cli.main import cmd_start, cmd_list, main


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


def test_main_exchange_start(capsys):
    with patch("sys.argv", ["nova", "exchange", "start"]):
        main()
    output = capsys.readouterr().out
    assert "not yet implemented" in output.lower()


def test_main_exchange_install(capsys):
    with patch("sys.argv", ["nova", "exchange", "install"]):
        main()
    output = capsys.readouterr().out
    assert "not yet implemented" in output.lower()


def test_main_exchange_no_subcommand(capsys):
    with patch("sys.argv", ["nova", "exchange"]):
        main()
    output = capsys.readouterr().out
    assert "nova exchange" in output.lower()
