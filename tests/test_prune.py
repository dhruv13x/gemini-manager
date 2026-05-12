# tests/test_prune.py

import pytest
from unittest.mock import patch, MagicMock, call
import os
import time
from gemini_manager.prune import do_prune, get_backup_list, get_backup_list_dirs, prune_list, parse_ts
from gemini_manager.config import OLD_CONFIGS_DIR

# Using pyfakefs via conftest.py

def mock_args(backup_dir="/tmp/backups", keep=2, cloud=False, cloud_only=False, dry_run=False, b2_id=None, b2_key=None, bucket=None):
    return MagicMock(backup_dir=backup_dir, keep=keep, cloud=cloud, cloud_only=cloud_only, dry_run=dry_run, b2_id=b2_id, b2_key=b2_key, bucket=bucket)

def test_parse_ts():
    ts = parse_ts("2023-01-01_120000-backup.gemini-manager.tar.gz")
    assert ts is not None
    assert ts.tm_year == 2023

    assert parse_ts("invalid") is None
    assert parse_ts("2023-01-01_120000-backup.gemini-manager") is not None # Directory format

def test_get_backup_list():
    files = [
        "2023-01-01_100000-user@example.com.gemini-manager.tar.gz",
        "2023-01-02_100000-user@example.com.gemini-manager.tar.gz",
        "invalid.txt",
        "2023-01-03_100000-user@example.com.gemini-manager" # Should be ignored by get_backup_list
    ]
    backups = get_backup_list(files)
    assert len(backups) == 2
    # Should be sorted newest first
    assert backups[0][1] == "2023-01-02_100000-user@example.com.gemini-manager.tar.gz"
    assert backups[1][1] == "2023-01-01_100000-user@example.com.gemini-manager.tar.gz"

def test_get_backup_list_dirs():
    files = [
        "2023-01-01_100000-user@example.com.gemini-manager",
        "2023-01-02_100000-user@example.com.gemini-manager",
        "invalid.txt",
        "2023-01-03_100000-user@example.com.gemini-manager.tar.gz" # Should be ignored by get_backup_list_dirs
    ]
    dirs = get_backup_list_dirs(files)
    assert len(dirs) == 2
    # Should be sorted newest first
    assert dirs[0][1] == "2023-01-02_100000-user@example.com.gemini-manager"
    assert dirs[1][1] == "2023-01-01_100000-user@example.com.gemini-manager"

def test_prune_list_no_action():
    backups = [("ts1", "file1"), ("ts2", "file2")]
    callback = MagicMock()
    # Keep 5, have 2. No prune.
    prune_list(backups, 5, False, callback)
    callback.assert_not_called()

def test_prune_list_action():
    backups = [("ts3", "file3"), ("ts2", "file2"), ("ts1", "file1")]
    callback = MagicMock()
    # Keep 1, have 3. Delete 2 oldest (file2, file1).
    prune_list(backups, 1, False, callback)
    assert callback.call_count == 2
    callback.assert_has_calls([call("file2"), call("file1")])

def test_prune_list_dry_run():
    backups = [("ts3", "file3"), ("ts2", "file2"), ("ts1", "file1")]
    callback = MagicMock()
    prune_list(backups, 1, True, callback)
    callback.assert_not_called()

@patch("gemini_manager.prune.cprint")
def test_do_prune_local(mock_cprint, fs):
    archive_dir = "/tmp/backups"
    dir_backup_path = OLD_CONFIGS_DIR

    fs.create_dir(archive_dir)
    fs.create_dir(dir_backup_path)

    # Create archive files
    fs.create_file(os.path.join(archive_dir, "2023-01-01_100000-u.gemini-manager.tar.gz"))
    fs.create_file(os.path.join(archive_dir, "2023-01-02_100000-u.gemini-manager.tar.gz"))
    fs.create_file(os.path.join(archive_dir, "2023-01-03_100000-u.gemini-manager.tar.gz"))

    # Create directory backups
    fs.create_dir(os.path.join(dir_backup_path, "2023-01-01_110000-u.gemini-manager"))
    fs.create_dir(os.path.join(dir_backup_path, "2023-01-02_110000-u.gemini-manager"))
    fs.create_dir(os.path.join(dir_backup_path, "2023-01-03_110000-u.gemini-manager"))

    args = mock_args(keep=1) # Keep only the newest for both archives and directories

    do_prune(args)

    # Verify archives deleted
    assert not os.path.exists(os.path.join(archive_dir, "2023-01-01_100000-u.gemini-manager.tar.gz"))
    assert not os.path.exists(os.path.join(archive_dir, "2023-01-02_100000-u.gemini-manager.tar.gz"))
    assert os.path.exists(os.path.join(archive_dir, "2023-01-03_100000-u.gemini-manager.tar.gz")) # Kept

    # Verify directories deleted
    assert not os.path.exists(os.path.join(dir_backup_path, "2023-01-01_110000-u.gemini-manager"))
    assert not os.path.exists(os.path.join(dir_backup_path, "2023-01-02_110000-u.gemini-manager"))
    assert os.path.exists(os.path.join(dir_backup_path, "2023-01-03_110000-u.gemini-manager")) # Kept


@patch("gemini_manager.prune.cprint")
def test_do_prune_local_no_dir(mock_cprint, fs):
    # Dirs don't exist
    args = mock_args(keep=1) # default local
    do_prune(args)
    # Just prints warning for both archive and directory paths not found
    # Checking console output is tricky with cprint mock unless we inspect calls

    # Since we use cprint from .ui, and we mocked it
    # We can check call args

    found_archive_warn = False
    found_dir_warn = False
    for call_args in mock_cprint.call_args_list:
        if "Archive backup directory not found" in str(call_args):
            found_archive_warn = True
        if "Directory backup path not found" in str(call_args):
            found_dir_warn = True

    assert found_archive_warn
    assert found_dir_warn


@patch("gemini_manager.prune.resolve_credentials")
@patch("gemini_manager.prune.B2Manager")
@patch("gemini_manager.prune.cprint")
def test_do_prune_cloud(mock_cprint, mock_b2_cls, mock_creds, fs):
    mock_creds.return_value = ("id", "key", "bucket")

    mock_b2 = mock_b2_cls.return_value

    fv1 = MagicMock()
    fv1.file_name = "2023-01-01_100000-u.gemini-manager.tar.gz"
    fv1.id_ = "id1"

    fv2 = MagicMock()
    fv2.file_name = "2023-01-02_100000-u.gemini-manager.tar.gz"
    fv2.id_ = "id2"

    mock_b2.list_backups.return_value = [(fv1, None), (fv2, None)]

    args = mock_args(keep=1, cloud=True, backup_dir="/tmp/nonexistent") # Local part will be skipped
    
    # Don't mock os.path.exists if we want fs to work normally,
    # but here we want to ensure local logic is skipped or handles missing dir
    # backup_dir points to non-existent so local logic prints warnings which is fine.

    do_prune(args)

    mock_b2.bucket.delete_file_version.assert_called_once_with("id1", "2023-01-01_100000-u.gemini-manager.tar.gz")

@patch("gemini_manager.prune.resolve_credentials")
@patch("gemini_manager.prune.cprint")
def test_do_prune_cloud_no_creds(mock_cprint, mock_creds, fs):
    mock_creds.return_value = (None, None, None)
    args = mock_args(cloud=True, cloud_only=False, backup_dir="/tmp/nonexistent")
    
    do_prune(args)
    assert any("Skipping (credentials not set)." in str(args) for args in mock_cprint.call_args_list)

@patch("gemini_manager.prune.resolve_credentials")
@patch("gemini_manager.prune.cprint")
def test_do_prune_cloud_only_no_creds_error(mock_cprint, mock_creds, fs):
    mock_creds.return_value = (None, None, None)
    args = mock_args(cloud_only=True)
    do_prune(args)
    # Error printed
    assert any("Cloud credentials missing." in str(args) for args in mock_cprint.call_args_list)


@patch("gemini_manager.prune.resolve_credentials")
@patch("gemini_manager.prune.B2Manager")
@patch("gemini_manager.prune.cprint")
def test_do_prune_cloud_exception(mock_cprint, mock_b2_cls, mock_creds, fs):
    mock_creds.return_value = ("id", "key", "bucket")
    mock_b2_cls.side_effect = Exception("B2 Fail")

    args = mock_args(cloud=True, backup_dir="/tmp/nonexistent")

    do_prune(args)

    assert any("Cloud prune failed" in str(args) for args in mock_cprint.call_args_list)

@patch("gemini_manager.prune.cprint")
def test_do_prune_local_remove_fail(mock_cprint, fs):
    archive_dir = "/tmp/backups"
    dir_backup_path = OLD_CONFIGS_DIR

    fs.create_dir(archive_dir)
    fs.create_dir(dir_backup_path)

    # Create files
    file_path = os.path.join(archive_dir, "2023-01-01_100000-u.gemini-manager.tar.gz")
    fs.create_file(file_path)
    dir_path = os.path.join(dir_backup_path, "2023-01-01_110000-u.gemini-manager")
    fs.create_dir(dir_path)

    # Patch os.remove and shutil.rmtree to fail
    with patch("os.remove", side_effect=Exception("Permission denied for file")):
        with patch("shutil.rmtree", side_effect=Exception("Permission denied for dir")):
            args = mock_args(keep=0) # delete all
            do_prune(args)

    # Assert error logged
    file_err_found = False
    dir_err_found = False
    for call_args in mock_cprint.call_args_list:
        arg_str = str(call_args)
        if "Failed to remove" in arg_str and "2023-01-01_100000-u.gemini-manager.tar.gz" in arg_str:
            file_err_found = True
        if "Failed to remove directory" in arg_str and "2023-01-01_110000-u.gemini-manager" in arg_str:
            dir_err_found = True
    
    assert file_err_found, f"File removal error not found in cprint calls: {mock_cprint.call_args_list}"
    assert dir_err_found, f"Directory removal error not found in cprint calls: {mock_cprint.call_args_list}"


@patch("gemini_manager.prune.resolve_credentials")
@patch("gemini_manager.prune.B2Manager")
@patch("gemini_manager.prune.cprint")
def test_do_prune_cloud_delete_fail(mock_cprint, mock_b2_cls, mock_creds, fs):
    mock_creds.return_value = ("id", "key", "bucket")
    mock_b2 = mock_b2_cls.return_value

    fv1 = MagicMock()
    fv1.file_name = "2023-01-01_100000-u.gemini-manager.tar.gz"
    fv1.id_ = "id1"
    fv2 = MagicMock()
    fv2.file_name = "2023-01-02_100000-u.gemini-manager.tar.gz"
    fv2.id_ = "id2"

    mock_b2.list_backups.return_value = [(fv1, None), (fv2, None)]
    mock_b2.bucket.delete_file_version.side_effect = Exception("API Fail")

    args = mock_args(keep=1, cloud=True, backup_dir="/tmp/nonexistent")

    do_prune(args)

    mock_b2.bucket.delete_file_version.assert_called()
    assert any("Failed to delete cloud file 2023-01-01_100000-u.gemini-manager.tar.gz" in str(args) for args in mock_cprint.call_args_list)
