
import pytest
from unittest.mock import patch, MagicMock
import os
import time
from pathlib import Path
from gemini_manager.prune_backups import _calculate_prune_list_generic, perform_prune_backups
from gemini_manager.config import DEFAULT_BACKUP_DIR, OLD_CONFIGS_DIR

def test_calculate_prune_list_generic_per_account():
    entries = [
        {"name": "u1_new", "email": "u1", "time": 300},
        {"name": "u1_old", "email": "u1", "time": 200},
        {"name": "u2_new", "email": "u2", "time": 100},
        {"name": "u2_old", "email": "u2", "time": 50},
    ]
    # --keep 1 should keep 1 per account (u1_new, u2_new)
    # and delete (u1_old, u2_old)
    to_delete = _calculate_prune_list_generic(entries, keep=1)
    assert len(to_delete) == 2
    names = [e["name"] for e in to_delete]
    assert "u1_old" in names
    assert "u2_old" in names
    assert "u1_new" not in names
    assert "u2_new" not in names

@patch("gemini_manager.prune_backups.console")
def test_perform_prune_backups_local_sorting_backup_time(mock_console, fs):
    backup_dir = "/tmp/backups"
    os.makedirs(backup_dir, exist_ok=True)
    
    # f1 has newer filename timestamp (Reset Time) but older mtime (Backup Time)
    f1 = "2025-01-01_120000-u1.gemini-manager.tar.gz"
    f2 = "2024-01-01_120000-u1.gemini-manager.tar.gz"
    
    fs.create_file(os.path.join(backup_dir, f1))
    os.utime(os.path.join(backup_dir, f1), (1000, 1000)) # Older backup time
    
    fs.create_file(os.path.join(backup_dir, f2))
    os.utime(os.path.join(backup_dir, f2), (2000, 2000)) # Newer backup time
    
    # If it sorts by Backup Time, f2 is "newest" and f1 is pruned.
    args = MagicMock(keep=1, keep_latest_per_email=False, dry_run=False, cloud=False, backup_dir=backup_dir)
    
    perform_prune_backups(args)
    
    assert os.path.exists(os.path.join(backup_dir, f2))
    assert not os.path.exists(os.path.join(backup_dir, f1))

@patch("gemini_manager.prune_backups.console")
def test_perform_prune_backups_local_directories(mock_console, fs):
    dir_backup_path = OLD_CONFIGS_DIR
    os.makedirs(dir_backup_path, exist_ok=True)
    
    d1 = "2023-01-01_100000-u1.gemini-manager"
    d2 = "2023-01-02_100000-u1.gemini-manager"
    
    os.makedirs(os.path.join(dir_backup_path, d1), exist_ok=True)
    os.makedirs(os.path.join(dir_backup_path, d2), exist_ok=True)
    
    args = MagicMock(keep=1, keep_latest_per_email=False, dry_run=False, cloud=False, backup_dir="/tmp/none")
    
    perform_prune_backups(args)
    
    assert os.path.exists(os.path.join(dir_backup_path, d2))
    assert not os.path.exists(os.path.join(dir_backup_path, d1))

@patch("gemini_manager.prune_backups.resolve_credentials")
@patch("gemini_manager.prune_backups.B2Manager")
@patch("gemini_manager.prune_backups.console")
def test_perform_prune_backups_cloud_only_prunes_cloud(mock_console, mock_b2_cls, mock_creds, fs):
    mock_creds.return_value = ("id", "key", "bucket")
    mock_b2 = mock_b2_cls.return_value
    
    # Cloud entries
    fv1 = MagicMock()
    fv1.file_name = "f1-u1.gemini-manager.tar.gz"
    fv1.upload_timestamp = 100000
    fv1.id_ = "id1"
    
    fv2 = MagicMock()
    fv2.file_name = "f2-u1.gemini-manager.tar.gz"
    fv2.upload_timestamp = 200000
    fv2.id_ = "id2"
    
    mock_b2.list_backups.return_value = [(fv1, None), (fv2, None)]
    
    # Local entries
    backup_dir = "/tmp/backups"
    os.makedirs(backup_dir, exist_ok=True)
    local_f = os.path.join(backup_dir, "local-u1.gemini-manager.tar.gz")
    fs.create_file(local_f)
    
    # Run with --cloud
    args = MagicMock(keep=1, keep_latest_per_email=False, dry_run=False, cloud=True, backup_dir=backup_dir)
    perform_prune_backups(args)
    
    # Should delete cloud fv1 (older)
    mock_b2.bucket.delete_file_version.assert_called_with("id1", "f1-u1.gemini-manager.tar.gz")
    
    # Should NOT delete local archive
    assert os.path.exists(local_f)
