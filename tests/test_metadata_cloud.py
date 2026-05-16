import os
import json
import pytest
from unittest.mock import MagicMock, patch
from gemini_manager import metadata
from gemini_manager.cloud_storage import CloudFile

def test_parse_cloud_summary():
    # 1. Missing email
    cf = CloudFile("test.json", 100, 1.0)
    cf.metadata = {}
    assert metadata.parse_cloud_summary(cf) is None
    
    # 2. Full metadata
    cf.metadata = {
        "gm-email": "user@example.com",
        "gm-entity-type": "state",
        "gm-captured-at": "2026-01-01T12:00:00",
        "gm-reset-at": "2026-01-01T13:00:00",
        "gm-q-flash": "50",
        "gm-q-pro": "100"
    }
    summary = metadata.parse_cloud_summary(cf)
    assert summary["email"] == "user@example.com"
    assert summary["models"]["Flash"]["percent"] == 50
    assert summary["models"]["Pro"]["percent"] == 100
    assert summary["_is_cloud_summary"] is True

def test_load_cloud_snapshots(fs):
    provider = MagicMock()
    # Mock list_files returning one with shadow metadata and one without
    f1 = CloudFile("backup.snapshot.json", 100, 1.0)
    f1.metadata = {"gm-email": "shadow@example.com"}
    
    f2 = CloudFile("backup2.snapshot.json", 100, 1.0)
    f2.metadata = {} # No shadow metadata, will trigger download
    
    provider.list_files.return_value = [f1, f2]
    provider.download_file.side_effect = lambda name, local: fs.create_file(local, contents=json.dumps({"email": "downloaded@example.com"}))
    
    results = metadata.load_cloud_snapshots(provider)
    assert len(results) == 2
    emails = [r["email"] for r in results]
    assert "shadow@example.com" in emails
    assert "downloaded@example.com" in emails

def test_load_cloud_states(fs):
    provider = MagicMock()
    f1 = CloudFile("accounts/user.state.json", 100, 1.0)
    f1.metadata = {"gm-email": "state@example.com"}
    
    provider.list_files.return_value = [f1]
    
    results = metadata.load_cloud_states(provider)
    assert len(results) == 1
    assert results[0]["email"] == "state@example.com"

def test_model_reset_at():
    now = metadata._now()
    # 1. Valid
    res = metadata._model_reset_at(now, {"reset_h": 1, "reset_m": 30})
    assert res is not None
    
    # 2. Missing
    assert metadata._model_reset_at(now, {}) is None
    
    # 3. Invalid
    assert metadata._model_reset_at(now, {"reset_h": "bad"}) is None

def test_load_latest_status_for_email():
    resets = [
        {"email": "test@test.com", "models": {"m1": {}}, "saved_at": "2026-01-01T10:00:00"},
        {"email": "test@test.com", "models": {"m2": {}}, "saved_at": "2026-01-01T11:00:00"},
        {"email": "other@test.com", "models": {"m3": {}}, "saved_at": "2026-01-01T12:00:00"},
    ]
    latest = metadata.load_latest_status_for_email("test@test.com", resets)
    assert latest["models"] == {"m2": {}}
    
    assert metadata.load_latest_status_for_email("none@test.com", resets) is None

def test_create_backup_snapshot(fs):
    archive_path = "/tmp/backup.tar.gz"
    fs.create_file(archive_path, contents="data")
    
    # 1. No email
    assert metadata.create_backup_snapshot(archive_path=archive_path, active_email=None) is None
    
    # 2. Success
    res = metadata.create_backup_snapshot(archive_path=archive_path, active_email="test@test.com")
    assert res.endswith(".snapshot.json")
    assert os.path.exists(res)

def test_historical_snapshot_paths(fs):
    backup_dir = "/tmp/backups"
    fs.create_dir(backup_dir)
    fs.create_file(os.path.join(backup_dir, "2026-01-01-user_at_test.com.snapshot.json"))
    fs.create_file(os.path.join(backup_dir, "2026-01-02-user_at_test.com.metadata.json"))
    fs.create_file(os.path.join(backup_dir, "other.snapshot.json"))
    
    paths = metadata._historical_snapshot_paths(backup_dir, "user@test.com")
    assert len(paths) == 2

def test_patch_status_metadata_no_email():
    status = {"email": None, "models": {}}
    assert metadata.patch_status_metadata(status, MagicMock()) is None

def test_load_cloud_snapshots_error(fs):
    provider = MagicMock()
    cf = CloudFile("err.snapshot.json", 10, 1.0)
    cf.metadata = {}
    provider.list_files.return_value = [cf]
    provider.download_file.side_effect = Exception("Fail")
    
    # Should not crash
    assert metadata.load_cloud_snapshots(provider) == []

def test_get_cloud_summary():
    entity = {
        "email": "user@example.com",
        "_entity_type": "state",
        "captured_at": "2026-01-01T12:00:00",
        "next_available_at": "2026-01-01T13:00:00",
        "models": {
            "Flash": {"percent": 10},
            "Pro": {"percent": 90}
        }
    }
    summary = metadata.get_cloud_summary(entity)
    assert summary["gm-email"] == "user@example.com"
    assert summary["gm-q-flash"] == "10"
    assert summary["gm-q-pro"] == "90"

def test_write_state_change_detection(fs):
    path = "/tmp/test.state.json"
    meta = {"email": "test@test.com", "val": 1, "updated_at": "now"}
    
    # 1. First write
    assert metadata.write_state(path, meta) is True
    
    # 2. Write same data (ignoring updated_at)
    meta2 = {"email": "test@test.com", "val": 1, "updated_at": "later"}
    assert metadata.write_state(path, meta2) is False
    
    # 3. Write different data
    meta3 = {"email": "test@test.com", "val": 2, "updated_at": "now"}
    assert metadata.write_state(path, meta3) is True
