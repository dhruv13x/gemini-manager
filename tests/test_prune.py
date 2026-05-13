
import pytest
from unittest.mock import patch, MagicMock, call
import os
import json
from gemini_manager.prune import prune_list, do_prune
from gemini_manager.config import DEFAULT_BACKUP_DIR, OLD_CONFIGS_DIR

def mock_args(keep=5, cloud=False, cloud_only=False, backup_dir=DEFAULT_BACKUP_DIR, dry_run=False):
    return MagicMock(keep=keep, cloud=cloud, cloud_only=cloud_only, backup_dir=backup_dir, dry_run=dry_run)

def test_prune_list_no_prune():
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

    os.makedirs(archive_dir, exist_ok=True)
    # dir_backup_path (OLD_CONFIGS_DIR) is already created by fixture
    
    # Create archive files
    fs.create_file(os.path.join(archive_dir, "2023-01-01_100000-u.gemini-manager.tar.gz"))
    fs.create_file(os.path.join(archive_dir, "2023-01-02_100000-u.gemini-manager.tar.gz"))
    fs.create_file(os.path.join(archive_dir, "2023-01-03_100000-u.gemini-manager.tar.gz"))

    # Create directory backups
    fs.create_dir(os.path.join(dir_backup_path, "2023-01-01_110000-u.gemini-manager"))
    fs.create_dir(os.path.join(dir_backup_path, "2023-01-02_110000-u.gemini-manager"))
    fs.create_dir(os.path.join(dir_backup_path, "2023-01-03_110000-u.gemini-manager"))

    args = mock_args(keep=1, backup_dir=archive_dir) # Keep only the newest for both archives and directories

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
    # Dirs don't exist - We must ensure they are GONE if conftest created them
    from gemini_manager.config import DEFAULT_BACKUP_DIR, OLD_CONFIGS_DIR
    if os.path.exists(DEFAULT_BACKUP_DIR):
        fs.remove_object(DEFAULT_BACKUP_DIR)
    if os.path.exists(OLD_CONFIGS_DIR):
        fs.remove_object(OLD_CONFIGS_DIR)

    args = mock_args(keep=1) # default local
    do_prune(args)
    
    found_archive_warn = False
    found_dir_warn = False
    for call_args in mock_cprint.call_args_list:
        arg_str = str(call_args)
        if "Archive backup directory not found" in arg_str:
            found_archive_warn = True
        if "Directory backup path not found" in arg_str:
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

    os.makedirs(archive_dir, exist_ok=True)
    os.makedirs(dir_backup_path, exist_ok=True)

    # Create files
    file_path = os.path.join(archive_dir, "2023-01-01_100000-u.gemini-manager.tar.gz")
    fs.create_file(file_path)
    dir_path = os.path.join(dir_backup_path, "2023-01-01_110000-u.gemini-manager")
    fs.create_dir(dir_path)

    # Patch os.remove and shutil.rmtree to fail
    with patch("os.remove", side_effect=Exception("Permission denied for file")):
        with patch("shutil.rmtree", side_effect=Exception("Permission denied for dir")):
            args = mock_args(keep=0, backup_dir=archive_dir) # delete all
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
