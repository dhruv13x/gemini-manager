# tests/test_session.py

import pytest
from unittest.mock import patch
import os
import json
from gemini_manager import session
# Note: session.py hardcodes "~/.gemini-manager/google_accounts.json" inside get_active_session
# So we must create that specific file in the fake fs

def test_get_active_session_exists(fs):
    # The code expands "~", so we need to match that.
    # pyfakefs mocks os.path.expanduser to work with the fake /home/user (usually)
    # let's assume standard behavior of expanduser with pyfakefs

    home = os.path.expanduser("~")
    gemini_home = os.path.join(home, ".gemini")
    account_file = os.path.join(gemini_home, "google_accounts.json")

    fs.create_file(account_file, contents='{"active": "test@example.com"}')

    assert session.get_active_session() == "test@example.com"

def test_get_active_session_not_exists(fs):
    # File not created
    assert session.get_active_session() is None

def test_get_active_session_malformed(fs):
    home = os.path.expanduser("~")
    gemini_home = os.path.join(home, ".gemini")
    account_file = os.path.join(gemini_home, "google_accounts.json")

    fs.create_file(account_file, contents='{invalid_json}')
    assert session.get_active_session() is None

@patch("gemini_manager.session.get_active_session")
@patch("gemini_manager.session.cprint")
def test_do_session_active(mock_cprint, mock_get_session):
    mock_get_session.return_value = "user@example.com"
    session.do_session()
    # Check that success message was printed
    # cprint arguments: color, text
    # call_args_list[1] should be the success message
    assert mock_cprint.call_count == 2
    assert "Active Session" in mock_cprint.call_args_list[1][0][1]

@patch("gemini_manager.session.get_active_session")
@patch("gemini_manager.session.cprint")
def test_do_session_inactive(mock_cprint, mock_get_session):
    mock_get_session.return_value = None
    session.do_session()
    assert mock_cprint.call_count == 3 # Heading, Error, Hint
    assert "No active session" in mock_cprint.call_args_list[1][0][1]

# Patch the symbol in CLI module where it is imported!
@patch("gemini_manager.cli.do_session")
def test_main_session_arg(mock_do_session, fs):
    from gemini_manager.cli import main
    # main() might parse args which triggers file checks or config loading
    with patch("sys.argv", ["gm", "--session"]):
        main()
        mock_do_session.assert_called_once()
