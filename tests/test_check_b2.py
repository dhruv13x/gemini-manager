# tests/test_check_b2.py

import pytest
from unittest.mock import patch, MagicMock
import sys
import os
from gemini_manager import check_b2

@patch("gemini_manager.check_b2.B2Manager")
def test_main_success(mock_b2):
    with patch("sys.argv", ["check_b2.py", "--b2-id", "i", "--b2-key", "k", "--bucket", "b"]):
        check_b2.main()
        mock_b2.assert_called_with("i", "k", "b")

@patch.dict(os.environ, {}, clear=True)
@patch("gemini_manager.check_b2.get_setting", return_value=None)
def test_main_missing_creds(mock_get_setting):
    with patch("sys.argv", ["check_b2.py"]):
        with pytest.raises(SystemExit):
            check_b2.main()

@patch("gemini_manager.check_b2.B2Manager")
def test_main_b2_fail(mock_b2):
    with patch("sys.argv", ["check_b2.py", "--b2-id", "i", "--b2-key", "k", "--bucket", "b"]):
        mock_b2.side_effect = SystemExit(1)
        with pytest.raises(SystemExit):
            check_b2.main()

@patch("gemini_manager.check_b2.B2Manager")
def test_main_b2_exception(mock_b2):
    with patch("sys.argv", ["check_b2.py", "--b2-id", "i", "--b2-key", "k", "--bucket", "b"]):
        mock_b2.side_effect = Exception("Unexpected")
        with pytest.raises(SystemExit):
            check_b2.main()

import runpy

@patch.dict(os.environ, {}, clear=True)
@patch("gemini_manager.check_b2.get_setting", return_value=None)
def test_main_entrypoint_no_creds(mock_get_setting):
    with patch("sys.argv", ["check_b2.py"]):
        with pytest.raises(SystemExit) as e:
            runpy.run_module("gemini_manager.check_b2", run_name="__main__")
    assert e.value.code == 1
