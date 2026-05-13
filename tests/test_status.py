import pytest
from unittest.mock import patch, MagicMock
from gemini_manager import status

def test_extract_email():
    assert status.extract_email("some text with a@b.com here") == "a@b.com"
    assert status.extract_email("no email here") is None

@patch("gemini_manager.status.sh")
def test_sh_out(mock_sh):
    mock_run = MagicMock()
    mock_run.stdout = "output"
    mock_sh.return_value = mock_run
    assert status.sh_out("cmd") == "output"

@patch("gemini_manager.status.sh_out", side_effect=Exception)
def test_capture_exception(mock_sh_out):
    assert status.capture() == ""

@patch("gemini_manager.status.sh_out", return_value="some output")
def test_capture(mock_sh_out):
    assert status.capture() == "some output"

@patch("gemini_manager.status.sh")
def test_send_cmd(mock_sh):
    with patch("time.sleep"):
        status.send_cmd("cmd")
        assert mock_sh.call_count == 4

@patch("gemini_manager.status.capture", side_effect=["not ready", "› Waiting for authentication", "› Ready", "› Ready", "› Ready"])
def test_wait_ready(mock_capture):
    with patch("time.sleep"):
        out = status.wait_ready(timeout=1)
        assert out == "› Ready"

@patch("gemini_manager.status.capture", side_effect=["not ready", "not ready", "not ready"])
def test_wait_ready_timeout(mock_capture):
    with patch("time.sleep"):
        with patch("time.time", side_effect=[0, 0, 0, 2]):
            out = status.wait_ready(timeout=1)
            assert out == "not ready"

@patch("gemini_manager.status.capture", side_effect=["not match", "match"])
def test_wait_for(mock_capture):
    with patch("time.sleep"):
        out = status.wait_for(lambda o: o == "match", timeout=1)
        assert out == "match"

@patch("gemini_manager.status.capture", side_effect=["not match", "not match"])
def test_wait_for_timeout(mock_capture):
    with patch("time.sleep"):
        with patch("time.time", side_effect=[0, 0, 2]):
            out = status.wait_for(lambda o: o == "match", timeout=1)
            assert out == "not match"

@patch("gemini_manager.status.send_cmd")
@patch("gemini_manager.status.capture", side_effect=["Usage: /stats", "match"])
@patch("gemini_manager.status.wait_for", return_value="match")
def test_run_and_wait(mock_wait_for, mock_capture, mock_send):
    with patch("time.sleep"):
        out = status.run_and_wait("cmd", lambda o: o == "match")
        assert out == "match"

@patch("gemini_manager.status.sh")
@patch("gemini_manager.status.sh_out", return_value="")
def test_get_live_status_no_session(mock_sh_out, mock_sh):
    assert status.get_live_status() is None

@patch("gemini_manager.status.sh")
@patch("gemini_manager.status.sh_out", return_value="gemini_capture_status")
@patch("gemini_manager.status.wait_ready")
@patch("gemini_manager.status.run_and_wait", side_effect=[
    "Session Stats a@b.com",
    "Model usage Flash 100% (21h 3m)\nFlash Lite 15% (22h 23m)\nPro 50% │"
])
@patch("gemini_manager.status.extract_email", return_value="a@b.com")
def test_get_live_status(mock_email, mock_run, mock_wait, mock_sh_out, mock_sh):
    res = status.get_live_status()
    assert res is not None
    assert res["email"] == "a@b.com"
    assert res["models"]["Flash"]["percent"] == 100
    assert res["models"]["Flash"]["reset_h"] == 21
    assert res["models"]["Flash"]["reset_m"] == 3
    assert res["models"]["Flash Lite"]["percent"] == 15
    assert res["models"]["Flash Lite"]["reset_h"] == 22
    assert res["models"]["Flash Lite"]["reset_m"] == 23
    assert res["models"]["Pro"]["percent"] == 50
    assert res["models"]["Pro"]["reset_h"] == None

@patch("gemini_manager.status.sh")
@patch("gemini_manager.status.sh_out", return_value="gemini_capture_status")
@patch("gemini_manager.status.wait_ready")
@patch("gemini_manager.status.run_and_wait", side_effect=[
    "Session Stats",
    "Auth Method",
    "No email"
])
@patch("gemini_manager.status.extract_email", side_effect=[None, None, None])
@patch("gemini_manager.status.capture", return_value="none")
def test_get_live_status_no_email(mock_capture, mock_email, mock_run, mock_wait, mock_sh_out, mock_sh):
    assert status.get_live_status() is None

@patch("gemini_manager.status.get_live_status", return_value=None)
def test_do_status_no_status(mock_get, capsys):
    status.do_status()
    captured = capsys.readouterr()
    assert "Could not retrieve status" in captured.out

@patch("gemini_manager.status.get_live_status", side_effect=Exception("API error"))
def test_do_status_exception(mock_get, capsys):
    status.do_status()
    captured = capsys.readouterr()
    assert "Failed to get live status: API error" in captured.out

@patch("gemini_manager.status.get_live_status", return_value={"email": "a@b.com", "models": {"Flash": {"percent": 100, "extra": "extra", "reset_h": 1, "reset_m": 2}}})
def test_do_status(mock_get, capsys):
    status.do_status()
    captured = capsys.readouterr()
    assert "Email : a@b.com" in captured.out

@patch("gemini_manager.status.get_live_status", return_value={"email": "a@b.com", "models": {}})
@patch("gemini_manager.cloud_factory.get_cloud_provider")
@patch("gemini_manager.reset_helpers.sync_resets_with_cloud")
def test_do_status_cloud(mock_sync, mock_get_cloud, mock_get, capsys):
    class Args:
        cloud = True
    args = Args()
    mock_get_cloud.return_value = MagicMock()
    status.do_status(args)
    assert mock_sync.call_count == 2
    captured = capsys.readouterr()
    assert "Cloud sync (post-fetch) complete." in captured.out
