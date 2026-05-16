# tests/test_sync.py

import pytest
from unittest.mock import patch, MagicMock
import os
from gemini_manager.sync import perform_sync, get_local_backups, get_cloud_backups
from gemini_manager.config import ACCOUNTS_DIR

# NOTE: Since conftest.py uses pyfakefs (autouse=True), standard os functions are already patched.
# We should NOT patch os.path.isdir, os.listdir, etc. manually.
# Instead, we create files in the fake filesystem.

def mock_args(backup_dir="/tmp/backups", b2_id=None, b2_key=None, bucket=None):
    return MagicMock(backup_dir=backup_dir, b2_id=b2_id, b2_key=b2_key, bucket=bucket)

def test_get_local_backups(fs):
    # Setup fake filesystem
    backup_dir = "/path/backups"
    accounts_dir = ACCOUNTS_DIR
    fs.create_dir(backup_dir)
    fs.create_dir(accounts_dir)
    fs.create_file(os.path.join(backup_dir, "file1.gemini-manager.tar.gz"))
    fs.create_file(os.path.join(backup_dir, "file1.gemini-manager.snapshot.json"))
    fs.create_file(os.path.join(accounts_dir, "user@example.com.state.json"))
    fs.create_file(os.path.join(backup_dir, "file2.txt"))

    files = get_local_backups(backup_dir)
    assert "file1.gemini-manager.tar.gz" in files
    assert "file1.gemini-manager.snapshot.json" in files
    assert "accounts/user@example.com.state.json" in files
    assert "file2.txt" not in files

def test_get_local_backups_no_dir(fs):
    # Setup accounts dir even if backup dir is missing
    fs.create_dir(ACCOUNTS_DIR)
    # Directory does not exist in fake fs
    files = get_local_backups("/nonexistent")
    assert isinstance(files, set)

def test_get_cloud_backups():
    mock_b2 = MagicMock()

    file1 = MagicMock()
    file1.name = "cloud.gemini-manager.tar.gz"

    file2 = MagicMock()
    file2.name = "accounts/user.state.json"

    file3 = MagicMock()
    file3.name = "cloud.txt"

    mock_b2.list_files.return_value = [file1, file2, file3]

    files = get_cloud_backups(mock_b2)
    assert "cloud.gemini-manager.tar.gz" in files
    assert "accounts/user.state.json" in files
    assert "cloud.txt" not in files

def test_get_cloud_backups_fail():
    mock_b2 = MagicMock()
    mock_b2.list_files.side_effect = Exception("Fail")
    with pytest.raises(SystemExit):
        get_cloud_backups(mock_b2)

@patch("gemini_manager.sync.get_cloud_provider")
@patch("gemini_manager.sync.get_cloud_backups")
@patch("gemini_manager.sync.cprint")
def test_perform_sync_push_upload(mock_cprint, mock_get_cloud, mock_get_provider, fs):
    mock_get_cloud.return_value = set() # Empty cloud

    mock_b2 = MagicMock()
    mock_b2.bucket_name = "test-bucket"
    mock_get_provider.return_value = mock_b2

    # Create local file in fake fs
    backup_dir = "/tmp/backups"
    fs.create_dir(backup_dir)
    fs.create_dir(ACCOUNTS_DIR)
    fs.create_file(os.path.join(backup_dir, "local.gemini-manager.tar.gz"))

    args = mock_args(backup_dir=backup_dir)
    perform_sync("push", args)

    mock_b2.upload_file.assert_called()

@patch("gemini_manager.sync.get_cloud_provider")
@patch("gemini_manager.sync.get_cloud_backups")
@patch("gemini_manager.sync.cprint")
def test_perform_sync_push_no_upload(mock_cprint, mock_get_cloud, mock_get_provider, fs):
    mock_get_cloud.return_value = {"file.gemini-manager.tar.gz"} # Already exists

    mock_b2 = MagicMock()
    mock_b2.bucket_name = "test-bucket"
    mock_get_provider.return_value = mock_b2

    # Create local file in fake fs
    backup_dir = "/tmp/backups"
    fs.create_dir(backup_dir)
    fs.create_dir(ACCOUNTS_DIR)
    fs.create_file(os.path.join(backup_dir, "file.gemini-manager.tar.gz"))

    args = mock_args(backup_dir=backup_dir)
    perform_sync("push", args)

    mock_b2.upload_file.assert_not_called()

@patch("gemini_manager.sync.get_cloud_provider")
@patch("gemini_manager.sync.get_cloud_backups")
@patch("gemini_manager.sync.cprint")
def test_perform_sync_pull_download(mock_cprint, mock_get_cloud, mock_get_provider, fs):
    mock_get_cloud.return_value = {"cloud.gemini-manager.tar.gz"}

    mock_b2 = MagicMock()
    mock_b2.bucket_name = "test-bucket"
    mock_get_provider.return_value = mock_b2

    # Local dir exists but is empty
    backup_dir = "/tmp/backups"
    fs.create_dir(backup_dir)
    fs.create_dir(ACCOUNTS_DIR)

    args = mock_args(backup_dir=backup_dir)
    perform_sync("pull", args)

    mock_b2.download_file.assert_called()

@patch("gemini_manager.sync.get_cloud_provider")
@patch("gemini_manager.sync.get_cloud_backups")
@patch("gemini_manager.sync.cprint")
def test_perform_sync_pull_no_download(mock_cprint, mock_get_cloud, mock_get_provider, fs):
    mock_get_cloud.return_value = {"file.gemini-manager.tar.gz"}

    mock_b2 = MagicMock()
    mock_b2.bucket_name = "test-bucket"
    mock_get_provider.return_value = mock_b2

    # Local file exists
    backup_dir = "/tmp/backups"
    fs.create_dir(backup_dir)
    fs.create_file(os.path.join(backup_dir, "file.gemini-manager.tar.gz"))

    args = mock_args(backup_dir=backup_dir)
    perform_sync("pull", args)

    mock_b2.download_file.assert_not_called()

@patch("gemini_manager.sync.get_cloud_provider")
@patch("gemini_manager.sync.cprint")
def test_perform_sync_push_missing_dir(mock_cprint, mock_get_provider, fs):
    mock_b2 = MagicMock()
    mock_b2.bucket_name = "test-bucket"
    mock_get_provider.return_value = mock_b2

    fs.create_dir(ACCOUNTS_DIR)
    # Directory does not exist
    args = mock_args(backup_dir="/nonexistent")

    with pytest.raises(SystemExit):
        perform_sync("push", args)
