from unittest.mock import patch, MagicMock
from gemini_manager.status import (
    capture_live_status_and_update,
    extract_email,
    _parse_reset_time_from_model_string,
    handle_status,
    capture_live_status,
)
import datetime
import json


def test_extract_email():
    assert extract_email("Account: test@example.com") == "test@example.com"
    assert extract_email("No email here") is None


def test_parse_reset_time_from_model_string():
    with patch("gemini_manager.status._now_local") as mock_now:
        mock_now.return_value = datetime.datetime(2025, 1, 1, 12, 0, 0)
        dt = _parse_reset_time_from_model_string("0% Resets: 1:15 PM (24h)")
        assert dt is not None
        assert dt.hour == 13
        assert dt.minute == 15

        dt2 = _parse_reset_time_from_model_string("No resets here")
        assert dt2 is None


@patch("gemini_manager.status.capture_live_status")
@patch("gemini_manager.status._save_store")
@patch("gemini_manager.status._load_store", return_value=[])
def test_capture_live_status_and_update_success(mock_load, mock_save, mock_capture, fs):
    mock_capture.return_value = (
        "test@example.com",
        "0% Resets: 1:15 PM (24h)",
        "0%",
        "0%",
    )
    cooldown_path = "/home/runner/gm-cooldown.json"
    with patch("gemini_manager.status.COOLDOWN_FILE", cooldown_path):
        capture_live_status_and_update()
        assert fs.exists(cooldown_path)
        with open(cooldown_path, "r") as f:
            data = json.load(f)
            assert "test@example.com" in data
            assert (
                data["test@example.com"]["models"]["flash"]
                == "0% Resets: 1:15 PM (24h)"
            )


@patch("gemini_manager.status.capture_live_status")
@patch("gemini_manager.status.add_24h_cooldown_for_email")
def test_capture_live_status_and_update_fallback(mock_add_24h, mock_capture):
    mock_capture.return_value = ("N/A", "N/A", "N/A", "N/A")
    capture_live_status_and_update(expected_email="test@example.com", fallback_24h=True)
    mock_add_24h.assert_called_with("test@example.com")


@patch("gemini_manager.status.capture_live_status_and_update")
@patch("gemini_manager.cooldown.do_cooldown_list")
def test_handle_status(mock_list, mock_capture):
    args = MagicMock()
    handle_status(args)
    mock_capture.assert_called_once_with(args=args)
    mock_list.assert_called_once_with(args)


@patch("gemini_manager.status.subprocess.run")
@patch("gemini_manager.status.sh")
def test_capture_live_status_no_tmux(mock_sh, mock_run):
    mock_run.side_effect = FileNotFoundError()
    email, f, fl, p = capture_live_status()
    assert email == "N/A"
    assert f == "N/A"


@patch("gemini_manager.status.subprocess.run")
@patch("gemini_manager.status.sh")
def test_capture_live_status_tmux_error(mock_sh, mock_run):
    mock_run.return_value = MagicMock()
    mock_sh.side_effect = [None, RuntimeError("error")]
    email, f, fl, p = capture_live_status()
    assert email == "N/A"


@patch("gemini_manager.status.subprocess.run")
@patch("gemini_manager.status.sh")
@patch("gemini_manager.status.sh_out")
def test_capture_live_status_no_session(mock_sh_out, mock_sh, mock_run):
    mock_run.return_value = MagicMock()
    mock_sh_out.return_value = "other_session"
    email, f, fl, p = capture_live_status()
    assert email == "N/A"


@patch("gemini_manager.status.subprocess.run")
@patch("gemini_manager.status.sh")
@patch("gemini_manager.status.sh_out")
@patch("gemini_manager.status.wait_ready")
@patch("gemini_manager.status.run_and_wait")
@patch("gemini_manager.status.extract_email")
@patch("gemini_manager.status.capture")
def test_capture_live_status_success(
    mock_capture,
    mock_extract,
    mock_run_and_wait,
    mock_wait_ready,
    mock_sh_out,
    mock_sh,
    mock_run,
):
    mock_run.return_value = MagicMock()
    mock_sh_out.return_value = "gemini_capture"
    mock_run_and_wait.side_effect = [
        "Session Stats",
        "0% Resets: 1:12 PM",
    ]
    mock_extract.side_effect = ["test@example.com", None]
    email, f, fl, p = capture_live_status()
    assert email == "test@example.com"
