import os
import json
import datetime
import pytest
import shutil
from unittest.mock import MagicMock, patch
from gemini_manager import restore, cooldown
from gemini_manager.cooldown import record_switch, merge_cooldowns, do_remove_account
from gemini_manager.restore import _backup_current_auth_files, extract_archive

def test_backup_current_auth_files_dry_run(fs):
    dest = "/mock/dest"
    fs.create_file(os.path.join(dest, "credentials.json"))
    with patch("gemini_manager.restore.AUTH_ONLY_INCLUDES", ["credentials.json"]):
        res = _backup_current_auth_files(dest, "2026", dry_run=True)
        assert ".gemini-auth.bak-2026" in res

def test_extract_archive_encrypted_no_passphrase(fs):
    archive = "/tmp/test.tar.gz.gpg"
    fs.create_file(archive, contents="encrypted")
    # Mock getpass to return empty (which triggers SystemExit in code if no passphrase)
    with patch("getpass.getpass", return_value=""):
        with patch.dict(os.environ, {}, clear=True):
            if "GEMINI_BACKUP_PASSWORD" in os.environ:
                 del os.environ["GEMINI_BACKUP_PASSWORD"]
            with pytest.raises(SystemExit):
                extract_archive(archive, "/tmp/out")

def test_record_switch_migration_from_string(fs, mocker):
    email = "old@test.com"
    old_ts = "2020-01-01T00:00:00+00:00"
    path = cooldown.COOLDOWN_FILE
    fs.create_file(path, contents=json.dumps({email: old_ts}))
    
    mock_datetime = mocker.patch("gemini_manager.cooldown.datetime")
    mock_now = mock_datetime.datetime.now.return_value
    mock_astimezone = mock_now.astimezone.return_value
    new_ts = "2026-05-16T10:00:00+00:00"
    mock_astimezone.isoformat.return_value = new_ts
    
    record_switch(email)
    
    with open(path, "r") as f:
        data = json.load(f)
    assert data[email]["first_used"] == old_ts
    assert data[email]["last_used"] == new_ts

def test_record_switch_24h_reset(fs, mocker):
    email = "active@test.com"
    # Over 24h ago
    first_used = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)).isoformat()
    last_used = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).isoformat()
    
    path = cooldown.COOLDOWN_FILE
    fs.create_file(path, contents=json.dumps({email: {"first_used": first_used, "last_used": last_used}}))
    
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_datetime = mocker.patch("gemini_manager.cooldown.datetime")
    mock_datetime.datetime.now.return_value.astimezone.return_value = now
    mock_datetime.datetime.fromisoformat = datetime.datetime.fromisoformat
    
    record_switch(email)
    
    with open(path, "r") as f:
        data = json.load(f)
    # first_used should be updated to 'now' because it's been > 24h
    assert data[email]["first_used"] == now.isoformat()

def test_merge_cooldowns_legacy(fs):
    local = {"a@b.com": "2020-01-01T00:00:00+00:00"}
    remote = {"a@b.com": "2021-01-01T00:00:00+00:00"}
    merged = merge_cooldowns(local, remote)
    assert merged["a@b.com"] == remote["a@b.com"]

def test_do_remove_account_not_found(fs, mocker):
    mock_cp = mocker.patch("gemini_manager.cooldown.cprint")
    # Mock resolve_credentials to avoid SystemExit(1)
    mocker.patch("gemini_manager.cooldown.resolve_credentials", return_value=(None, None, None))
    
    fs.create_file(cooldown.COOLDOWN_FILE, contents="{}")
    with patch("gemini_manager.cooldown.remove_entry_by_id", return_value=False):
        do_remove_account("missing@test.com")
        
    mock_cp.assert_any_call(cooldown.NEON_YELLOW, "[INFO] No reset history found for missing@test.com")
    mock_cp.assert_any_call(cooldown.NEON_YELLOW, "[INFO] No active cooldown state found for missing@test.com")

def test_find_latest_archive_backup_invalid_names(fs):
    backup_dir = "/tmp/backups"
    fs.create_dir(backup_dir)
    # Too short
    fs.create_file(os.path.join(backup_dir, "short.tar.gz"))
    # Wrong suffix
    fs.create_file(os.path.join(backup_dir, "2023-01-01_120000-user@test.com.wrong"))
    
    res = restore.find_latest_archive_backup_for_email("user@test.com", backup_dir)
    assert res is None
