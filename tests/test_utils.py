# tests/test_utils.py

from unittest.mock import patch
import subprocess
import os
from gemini_manager.utils import run, read_file, run_capture
from gemini_manager.reset_helpers import run_cmd_safe


@patch("subprocess.check_output")
def test_run_capture(mock_check_output):
    mock_check_output.return_value = b"hello"
    assert run_capture("echo hello") == "hello"


@patch("subprocess.check_output")
def test_run_capture_exception(mock_check_output):
    mock_check_output.side_effect = subprocess.CalledProcessError(1, "cmd")
    assert run_capture("echo hello") is None


@patch("subprocess.run")
def test_run_cmd_safe(mock_subprocess_run):
    mock_subprocess_run.return_value.returncode = 0
    mock_subprocess_run.return_value.stdout = "hello"
    mock_subprocess_run.return_value.stderr = ""
    rc, stdout, stderr = run_cmd_safe("echo hello", capture=True)
    assert rc == 0
    assert stdout == "hello"
    assert stderr == ""


@patch("subprocess.run")
def test_run_cmd_safe_exception(mock_subprocess_run):
    # Test CalledProcessError
    called_process_error = subprocess.CalledProcessError(1, "cmd")
    called_process_error.stdout = b"error_out"
    called_process_error.stderr = b"error_err"

    # Test TimeoutExpired
    timeout_expired = subprocess.TimeoutExpired("cmd", 10)
    timeout_expired.stdout = b"timeout_out"
    timeout_expired.stderr = b"timeout_err"

    mock_subprocess_run.side_effect = [called_process_error, timeout_expired]

    rc, stdout, stderr = run_cmd_safe("echo hello", capture=True)
    assert rc == 1
    assert str(called_process_error) in stderr

    rc, stdout, stderr = run_cmd_safe("echo hello", capture=True, timeout=1)
    assert rc == 124
    assert "timeout_out" in stdout or "timeout_err" in stderr


@patch("subprocess.run")
def test_run(mock_run):
    run("echo hello")
    mock_run.assert_called_with("echo hello", shell=True, check=True)


@patch("subprocess.run")
@patch("gemini_manager.utils.sys.exit")
@patch("gemini_manager.utils.cprint")
def test_run_exception(mock_cprint, mock_exit, mock_run):
    mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
    run("echo hello")
    mock_exit.assert_called_with(1)
    mock_cprint.assert_called()


def test_read_file_not_exists(fs):
    # fs is empty, file doesn't exist
    assert read_file("test.txt") == ""


def test_read_file_exists(fs):
    fs.create_file("test.txt", contents="hello")
    assert read_file("test.txt") == "hello"


def test_read_file_exception(fs):
    # Simulate an exception (e.g., permission denied)
    fs.create_file("test.txt", contents="hello")
    os.chmod("test.txt", 0o000)  # Make unreadable

    # pyfakefs handles permission errors mostly correctly, but read_file swallows exceptions
    # Let's see if read_file handles PermissionError
    # If not, we might need to patch open to raise exception if we want to test that specific branch

    with patch("builtins.open", side_effect=Exception("Read error")):
        assert read_file("test.txt") == ""
