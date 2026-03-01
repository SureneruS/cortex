from unittest.mock import patch, MagicMock

from nova.tmux import (
    ensure_session,
    send_keys,
    is_client_attached,
    has_window,
)

TMUX_SESSION = "sessions"


@patch("nova.tmux.subprocess.run")
def test_ensure_session_creates_if_missing(mock_run):
    mock_run.side_effect = [
        MagicMock(returncode=1),  # has-session fails
        MagicMock(returncode=0),  # new-session succeeds
    ]
    ensure_session(TMUX_SESSION)
    assert mock_run.call_count == 2


@patch("nova.tmux.subprocess.run")
def test_ensure_session_noop_if_exists(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    ensure_session(TMUX_SESSION)
    assert mock_run.call_count == 1


@patch("nova.tmux.subprocess.run")
def test_send_keys(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    send_keys("sessions:my-window", "hello world")
    cmd = mock_run.call_args[0][0]
    assert "send-keys" in cmd
    assert "sessions:my-window" in cmd


@patch("nova.tmux.subprocess.run")
def test_is_client_attached_true(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="/dev/ttys001\n")
    assert is_client_attached("sessions:my-window") is True


@patch("nova.tmux.subprocess.run")
def test_is_client_attached_false(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="")
    assert is_client_attached("sessions:my-window") is False


@patch("nova.tmux.subprocess.run")
def test_has_window_true(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    assert has_window("sessions", "my-window") is True


@patch("nova.tmux.subprocess.run")
def test_has_window_false(mock_run):
    mock_run.return_value = MagicMock(returncode=1)
    assert has_window("sessions", "my-window") is False
