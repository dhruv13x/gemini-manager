
import pytest
from unittest.mock import patch, MagicMock
import os
from gemini_manager import integrity
from gemini_manager.config import DEFAULT_GEMINI_HOME, OLD_CONFIGS_DIR

def test_parse_timestamp_from_name():
    ts = integrity.parse_timestamp_from_name("2025-10-22_042211-test@test.gemini-manager")
    assert ts is not None
    assert ts.tm_year == 2025

    assert integrity.parse_timestamp_from_name("invalid") is None

def test_find_latest_backup(fs):
    backup_dir = "/tmp/backups"
    os.makedirs(backup_dir, exist_ok=True)
    fs.create_dir(os.path.join(backup_dir, "2025-10-23_042211-test.gemini-manager"))
    fs.create_dir(os.path.join(backup_dir, "2025-10-22_042211-test.gemini-manager"))

    latest = integrity.find_latest_backup(backup_dir)
    assert "2025-10-23" in latest

def test_find_latest_backup_none(fs):
    backup_dir = "/tmp/backups"
    os.makedirs(backup_dir, exist_ok=True)
    assert integrity.find_latest_backup(backup_dir) is None

def test_main_src_not_exists(fs):
    # DEFAULT_GEMINI_HOME not created
    # Ensure it's gone
    if os.path.exists(DEFAULT_GEMINI_HOME):
        fs.remove_object(DEFAULT_GEMINI_HOME)

    with patch("sys.argv", ["integrity.py"]):
        with pytest.raises(SystemExit) as e:
            integrity.main()
        assert e.value.code == 1

def test_main_no_backup(fs):
    os.makedirs(DEFAULT_GEMINI_HOME, exist_ok=True)
    # OLD_CONFIGS_DIR is created by conftest usually, but it might be empty
    # Ensure it's empty
    if os.path.exists(OLD_CONFIGS_DIR):
        for item in os.listdir(OLD_CONFIGS_DIR):
            fs.remove_object(os.path.join(OLD_CONFIGS_DIR, item))

    with patch("sys.argv", ["integrity.py"]):
        with pytest.raises(SystemExit) as e:
            integrity.main()
        assert e.value.code == 1

@patch("gemini_manager.integrity.run")
def test_main_diff_ok(mock_run, fs):
    os.makedirs("/root/.gemini-manager", exist_ok=True)
    os.makedirs(OLD_CONFIGS_DIR, exist_ok=True)
    fs.create_dir(os.path.join(OLD_CONFIGS_DIR, "2025-10-23_042211-test.gemini-manager"))

    with patch("sys.argv", ["integrity.py", "--src", "/root/.gemini-manager"]):
        mock_run.return_value.returncode = 0
        integrity.main()

@patch("gemini_manager.integrity.run")
def test_main_diff_fail(mock_run, fs):
    src_path = "/root/.gemini-manager"
    os.makedirs(src_path, exist_ok=True)
    os.makedirs(OLD_CONFIGS_DIR, exist_ok=True)
    fs.create_dir(os.path.join(OLD_CONFIGS_DIR, "2025-10-23_042211-test.gemini-manager"))
    
    with patch("sys.argv", ["integrity.py", "--src", src_path]):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = "diff"
        mock_run.return_value.stderr = "err"
        integrity.main()

@patch("gemini_manager.integrity.run")
@patch("builtins.print")
def test_main_diff_fail_stderr(mock_print, mock_run, fs):
    src_path = "/root/.gemini-manager"
    os.makedirs(src_path, exist_ok=True)
    os.makedirs(OLD_CONFIGS_DIR, exist_ok=True)
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
    os.makedirs(OLD_CONFIGS_DIR, exist_ok=True)
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
