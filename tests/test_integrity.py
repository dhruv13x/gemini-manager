# tests/test_integrity.py

import pytest
from unittest.mock import patch, MagicMock
import os
import time
import sys
import subprocess
from gemini_manager import integrity
from gemini_manager.config import OLD_CONFIGS_DIR, DEFAULT_GEMINI_HOME

# Note: We rely on pyfakefs (fs fixture) which is autouse in conftest.py
# So standard os operations work on the fake filesystem.

def test_run():
    with patch("subprocess.run") as mock_run:
        integrity.run("ls")
        mock_run.assert_called_with("ls", shell=True, check=True)

def test_run_capture():
    with patch("subprocess.run") as mock_run:
        integrity.run("ls", capture=True)
        # subprocess.run(..., stdout=PIPE, stderr=PIPE)
        kwargs = mock_run.call_args[1]
        assert kwargs.get("stdout") is not None
        assert kwargs.get("stderr") is not None

def test_parse_timestamp_from_name():
    ts = integrity.parse_timestamp_from_name("2025-10-22_042211-test@test.gemini-manager")
    assert ts is not None
    assert ts.tm_year == 2025

    assert integrity.parse_timestamp_from_name("invalid") is None

def test_find_latest_backup(fs):
    backup_dir = "/tmp/backups"
    fs.create_dir(backup_dir)
    fs.create_dir(os.path.join(backup_dir, "2025-10-23_042211-test.gemini-manager"))
    fs.create_dir(os.path.join(backup_dir, "2025-10-22_042211-test.gemini-manager"))

    latest = integrity.find_latest_backup(backup_dir)
    assert "2025-10-23" in latest

def test_find_latest_backup_none(fs):
    backup_dir = "/tmp/backups"
    fs.create_dir(backup_dir)
    assert integrity.find_latest_backup(backup_dir) is None

def test_main_src_not_exists(fs):
    # DEFAULT_GEMINI_HOME not created
    with patch("sys.argv", ["integrity.py"]):
        with pytest.raises(SystemExit) as e:
            integrity.main()
        assert e.value.code == 1

def test_main_no_backup(fs):
    fs.create_dir(DEFAULT_GEMINI_HOME)
    # OLD_CONFIGS_DIR is created by conftest usually, but it might be empty
    # integrity uses OLD_CONFIGS_DIR as search_dir
    # Ensure it's empty
    # fs.create_dir(OLD_CONFIGS_DIR) # conftest already does

    with patch("sys.argv", ["integrity.py"]):
        with pytest.raises(SystemExit) as e:
            integrity.main()
        assert e.value.code == 1

@patch("gemini_manager.integrity.run")
def test_main_diff_ok(mock_run, fs):
    fs.create_dir("/root/.gemini-manager")
    fs.create_dir(OLD_CONFIGS_DIR)
    fs.create_dir(os.path.join(OLD_CONFIGS_DIR, "2025-10-23_042211-test.gemini-manager"))

    with patch("sys.argv", ["integrity.py", "--src", "/root/.gemini-manager"]):
        mock_run.return_value.returncode = 0
        integrity.main()

@patch("gemini_manager.integrity.run")
def test_main_diff_fail(mock_run, fs):
    src_path = "/root/.gemini-manager"
    fs.create_dir(src_path)
    fs.create_dir(OLD_CONFIGS_DIR)
    fs.create_dir(os.path.join(OLD_CONFIGS_DIR, "2025-10-23_042211-test.gemini-manager"))
    
    print(f"Path exists check: {os.path.exists(src_path)}")

    with patch("sys.argv", ["integrity.py", "--src", src_path]):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = "diff"
        mock_run.return_value.stderr = "err"
        integrity.main()

@patch("gemini_manager.integrity.run")
@patch("builtins.print")
def test_main_diff_fail_stderr(mock_print, mock_run, fs):
    src_path = "/root/.gemini-manager"
    fs.create_dir(src_path)
    fs.create_dir(OLD_CONFIGS_DIR)
    fs.create_dir(os.path.join(OLD_CONFIGS_DIR, "2025-10-23_042211-test.gemini-manager"))

    with patch("sys.argv", ["integrity.py", "--src", src_path]):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = "error"
        integrity.main()
        
        all_args = []
        for call in mock_print.call_args_list:
            all_args.extend([str(a) for a in call[0]])

        assert "error" in all_args

@patch("gemini_manager.integrity.run")
@patch("builtins.print")
def test_main_diff_fail_no_stderr(mock_print, mock_run, fs):
    src_path = "/root/.gemini-manager"
    os.makedirs(src_path, exist_ok=True)
    # OLD_CONFIGS_DIR is already created by fixture
    fs.create_dir(os.path.join(OLD_CONFIGS_DIR, "2025-10-23_042211-test.gemini-manager"))

    with patch("sys.argv", ["integrity.py", "--src", src_path]):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = "out"
        mock_run.return_value.stderr = ""
        integrity.main()

        all_args = []
        for call in mock_print.call_args_list:
            all_args.extend([str(a) for a in call[0]])

        assert "out" in all_args
