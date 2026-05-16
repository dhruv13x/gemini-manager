import json
import pytest
from unittest.mock import MagicMock, patch
from gemini_manager.registry import RegistryManager, sync_registry_with_cloud
from gemini_manager.cloud_storage import CloudFile

def test_registry_invalid_json(fs):
    path = "/tmp/registry.json"
    fs.create_file(path, contents="invalid")
    reg = RegistryManager(path)
    assert reg.get_all() == []

def test_registry_not_dict(fs):
    path = "/tmp/registry.json"
    fs.create_file(path, contents='"a list"')
    reg = RegistryManager(path)
    assert reg.get_all() == []

def test_sync_registry_push(fs):
    provider = MagicMock()
    path = "/tmp/registry.json"
    fs.create_file(path, contents='{"test@test.com": {"email": "test@test.com", "_entity_type": "state"}}')
    
    reg = RegistryManager(path)
    with patch("gemini_manager.registry.get_registry", return_value=reg):
        sync_registry_with_cloud(provider, direction="push")
        
    provider.upload_file.assert_called()

def test_sync_registry_pull_merge(fs):
    provider = MagicMock()
    path = "/tmp/registry.json"
    local_data = {"local@test.com": {"email": "local@test.com", "captured_at": "2026-01-01T10:00:00", "_entity_type": "state"}}
    fs.create_file(path, contents=json.dumps(local_data))
    
    remote_record = {"email": "remote@test.com", "captured_at": "2026-01-01T11:00:00", "_entity_type": "state"}
    remote_data = json.dumps({"remote@test.com": remote_record})
    provider.download_to_string.return_value = remote_data
    
    reg = RegistryManager(path)
    with patch("gemini_manager.registry.get_registry", return_value=reg):
        sync_registry_with_cloud(provider, direction="pull")
        
    with open(path, "r") as f:
        data = json.load(f)
    
    assert "local@test.com" in data
    assert "remote@test.com" in data
    assert len(data) == 2

def test_sync_registry_pull_corrupt_remote(fs):
    provider = MagicMock()
    path = "/tmp/registry.json"
    fs.create_file(path, contents="{}")
    provider.download_to_string.return_value = "corrupt"
    
    reg = RegistryManager(path)
    with patch("gemini_manager.registry.get_registry", return_value=reg):
        sync_registry_with_cloud(provider, direction="pull")

def test_registry_reconstruct(fs):
    path = "/tmp/registry.json"
    reg = RegistryManager(path)
    
    with patch("gemini_manager.registry.load_local_states", return_value=[{"email": "s@t.com", "_entity_type": "state"}]):
        with patch("gemini_manager.registry.load_local_snapshots", return_value=[]):
            reg.reconstruct()
            
    assert len(reg.get_all()) == 1
    assert reg.get_all()[0]["email"] == "s@t.com"
