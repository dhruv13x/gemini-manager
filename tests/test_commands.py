# tests/test_commands.py

import pytest
from unittest.mock import patch, mock_open, MagicMock
import subprocess
import os
import sys

# Import commands individually
from gemini_manager.login import do_login
from gemini_manager.utils import run, read_file
from gemini_manager.reset_helpers import run_cmd_safe, save_reset_time_from_output
from gemini_manager.config import LOGIN_URL_PATH

# --- Tests for do_login ---

@patch("gemini_manager.login.run_cmd_safe")
@patch("gemini_manager.login.read_file")
def test_do_login_second_run(mock_read_file, mock_run_cmd_safe):
    # Mock run_cmd_safe to return success with a URL
    mock_run_cmd_safe.return_value = (0, "https://example.com/auth", "")
    mock_read_file.return_value = "https://example.com/auth" # Simulate file content
    
    do_login()
    # login.py calls run_cmd_safe with "gm 2> {LOGIN_URL_PATH}"
    mock_run_cmd_safe.assert_called_with(f"gm 2> {LOGIN_URL_PATH}", timeout=30, capture=True)
    assert mock_run_cmd_safe.call_count == 1
    # Check that read_file was called
    mock_read_file.assert_called_with(LOGIN_URL_PATH)


@patch("gemini_manager.login.run_cmd_safe")
@patch("gemini_manager.login.read_file")
def test_do_login_first_run(mock_read_file, mock_run_cmd_safe):
    # Simulates first run where "choose a login method" is found in output
    mock_run_cmd_safe.side_effect = [
        # First attempt: output indicates interactive menu
        (0, "Choose a login method", ""), 
        # Second attempt: after sending ENTER, returns URL
        (0, "https://example.com/auth-interactive", ""),
        # Third attempt (from login.py) after sleep to capture URL
        (0, "https://example.com/auth-interactive-final", ""), 
    ]
    mock_read_file.side_effect = ["Choose a login method", "https://example.com/auth-interactive-final"] # Simulate file content changing
    
    do_login(retries=1)
    # Expect at least 3 calls for the interactive flow: initial, enter, final capture
    assert mock_run_cmd_safe.call_count >= 3
    # Check that it tried to send ENTER
    assert any("printf \"\\n\" | gm" in call[0][0] for call in mock_run_cmd_safe.call_args_list)
    mock_read_file.assert_called_with(LOGIN_URL_PATH)


@patch("gemini_manager.login.run_cmd_safe")
@patch("gemini_manager.login.read_file", return_value="")
def test_do_login_fail(mock_read_file, mock_run_cmd_safe):
    # Fail all attempts - return no URL/code in output
    mock_run_cmd_safe.return_value = (1, "error", "error")
    # Redirect stderr to suppress output during test
    with patch('sys.stderr', new_callable=MagicMock):
        do_login(retries=1) # Reduced retries to speed up test if it actually loops
    assert mock_run_cmd_safe.called
    # Assert that read_file was called even in failure to get preview
    mock_read_file.assert_called_with(LOGIN_URL_PATH)


@patch("gemini_manager.login.run_cmd_safe")
@patch("gemini_manager.login.read_file", side_effect=Exception("File read error"))
def test_do_login_file_read_error(mock_read_file, mock_run_cmd_safe):
    mock_run_cmd_safe.return_value = (0, "output", "error") # Should return something to exit loop
    with patch('sys.stderr', new_callable=MagicMock):
        do_login(retries=1)
    assert mock_run_cmd_safe.called
    mock_read_file.assert_called_with(LOGIN_URL_PATH)


@patch("gemini_manager.login.run_cmd_safe")
@patch("gemini_manager.login.read_file")
def test_do_login_success_with_code(mock_read_file, mock_run_cmd_safe):
    mock_run_cmd_safe.return_value = (0, "Verification code: ABC-123", "")
    mock_read_file.return_value = "Verification code: ABC-123" # Simulate file content
    do_login(retries=1)
    assert mock_run_cmd_safe.called
    mock_read_file.assert_called_with(LOGIN_URL_PATH)

@patch("gemini_manager.login.run_cmd_safe")
@patch("gemini_manager.login.read_file")
def test_do_login_interactive_exception(mock_read_file, mock_run_cmd_safe):
    # Test exception during interactive URL capture (lines 61-62)
    # Also test run_cmd_safe returning empty output (lines 62->66)
    mock_run_cmd_safe.side_effect = [
        (0, "Choose a login method", ""), # First attempt: interactive
        (0, "", ""), # Enter attempt
        (0, "output3", "err3") # Third attempt
    ]
    # read_file side_effect:
    # 1. First attempt -> "Choose a login method"
    # 2. Interactive capture -> Exception!
    mock_read_file.side_effect = ["Choose a login method", Exception("Read fail")]

    do_login(retries=1)

    # Should hit lines 61-62: except Exception: text = err3 + out3
    # And then check regex on "err3output3" -> fails -> loop continues -> max retries -> exit
    assert mock_run_cmd_safe.call_count >= 3

@patch("gemini_manager.login.run_cmd_safe")
@patch("gemini_manager.login.read_file")
def test_do_login_fail_preview_exception(mock_read_file, mock_run_cmd_safe):
    # Test lines 76->77: Exception during final preview read
    mock_run_cmd_safe.return_value = (1, "", "")
    mock_read_file.side_effect = Exception("Read fail")

    do_login(retries=1)
    # Should catch exception and set raw=None, then print "(no file)"
