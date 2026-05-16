import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from gemini_manager import metadata
from gemini_manager.cooldown import do_cooldown_list
from rich.console import Console


def test_metadata_path_for_archive_handles_gpg():
    path = "/tmp/2026-01-01_120000-user@example.com.gemini-manager.tar.gz.gpg"
    assert metadata.snapshot_path_for_archive(path).endswith(
        "2026-01-01_120000-user@example.com.gemini-manager.snapshot.json"
    )


def test_patch_status_metadata_creates_metadata_only(fs):
    backup_dir = "/tmp/backups"
    accounts_dir = "/root/.gemini-manager/accounts"
    fs.create_dir(backup_dir)
    fs.create_dir(accounts_dir)
    status = {
        "email": "user@example.com",
        "models": {
            "Flash": {"percent": 12, "extra": "Resets", "reset_h": 1, "reset_m": 2}
        },
    }

    path = metadata.patch_status_metadata(status, SimpleNamespace(backup_dir=backup_dir, accounts_dir=accounts_dir, cloud=False))

    assert path is not None
    assert path.endswith("user_at_example.com.state.json")
    data = json.loads(open(path).read())
    assert data["email"] == "user@example.com"
    assert data["metadata_only"] is True
    assert data["models"]["Flash"]["percent"] == 12
    assert data["models"]["Flash"]["reset_at"]


def test_patch_status_metadata_updates_unique_account_file(fs):
    backup_dir = "/tmp/backups"
    accounts_dir = "/root/.gemini-manager/accounts"
    fs.create_dir(backup_dir)
    fs.create_dir(accounts_dir)
    # Existing account file
    account_file = os.path.join(accounts_dir, "user_at_example.com.state.json")
    fs.create_file(
        account_file,
        contents=json.dumps({"email": "user@example.com", "created_at": "old-timestamp"}),
    )

    status = {
        "email": "user@example.com",
        "models": {
            "Pro": {"percent": 80, "extra": "", "reset_h": None, "reset_m": None}
        },
    }

    path = metadata.patch_status_metadata(status, SimpleNamespace(backup_dir=backup_dir, accounts_dir=accounts_dir, cloud=False))

    assert path == account_file
    data = json.loads(open(path).read())
    assert data["email"] == "user@example.com"
    assert data["created_at"] == "old-timestamp"
    assert data["models"]["Pro"]["percent"] == 80


def test_patch_status_metadata_uploads_cloud(fs):
    backup_dir = "/tmp/backups"
    accounts_dir = "/root/.gemini-manager/accounts"
    fs.create_dir(backup_dir)
    fs.create_dir(accounts_dir)
    provider = MagicMock()
    args = SimpleNamespace(backup_dir=backup_dir, accounts_dir=accounts_dir, cloud=True)
    status = {"email": "user@example.com", "models": {}}

    with patch("gemini_manager.cloud_factory.get_cloud_provider", return_value=provider):
        # We need to mock sync_registry_with_cloud to avoid it calling real B2
        with patch("gemini_manager.registry.sync_registry_with_cloud"):
            path = metadata.patch_status_metadata(status, args)

    # In Layered Authority, we upload the state file AND sync the registry
    # Here we verify the state file upload. Registry sync is mocked above.
    provider.upload_file.assert_any_call(path, f"accounts/{os.path.basename(path)}")


def test_load_local_snapshots_and_states(fs):
    backup_dir = "/tmp/backups"
    accounts_dir = "/root/.gemini-manager/accounts"
    fs.create_dir(backup_dir)
    fs.create_dir(accounts_dir)
    
    # 1. Create a legacy snapshot
    fs.create_file(os.path.join(backup_dir, "old.metadata.json"), contents=json.dumps({"email": "old@example.com"}))
    # 2. Create a new snapshot
    fs.create_file(os.path.join(backup_dir, "new.snapshot.json"), contents=json.dumps({"email": "new@example.com"}))
    # 3. Create a state
    fs.create_file(os.path.join(accounts_dir, "user_at_example.com.state.json"), contents=json.dumps({"email": "user@example.com"}))
    
    snapshots = metadata.load_local_snapshots(backup_dir)
    states = metadata.load_local_states(accounts_dir)
    
    assert len(snapshots) == 2
    assert any(s["email"] == "old@example.com" for s in snapshots)
    assert any(s["email"] == "new@example.com" for s in snapshots)
    assert all(s["_entity_type"] == "snapshot" for s in snapshots)
    
    assert len(states) == 1
    assert states[0]["email"] == "user@example.com"
    assert states[0]["_entity_type"] == "state"


def test_latest_entity_by_email_ranking():
    # 1. State vs Snapshot (State wins even if Snapshot is newer, assuming both have models)
    records = [
        {"email": "a@b.com", "_entity_type": "state", "captured_at": "2026-01-01T00:00:00", "models": {"m": {}}},
        {"email": "a@b.com", "_entity_type": "snapshot", "captured_at": "2026-01-02T00:00:00", "models": {"m": {}}},
    ]
    latest = metadata.latest_entity_by_email(records)
    assert latest["a@b.com"]["_entity_type"] == "state"

    # 2. Model richness (Snapshot with models wins over newer State without models)
    records = [
        {"email": "b@b.com", "_entity_type": "state", "captured_at": "2026-01-02T00:00:00"},
        {"email": "b@b.com", "_entity_type": "snapshot", "captured_at": "2026-01-01T00:00:00", "models": {"m": {}}},
    ]
    latest = metadata.latest_entity_by_email(records)
    assert latest["b@b.com"]["_entity_type"] == "snapshot"

    # 3. Same priority, richness wins
    records = [
        {"email": "c@b.com", "_entity_type": "state", "captured_at": "2026-01-01T00:00:00"},
        {"email": "c@b.com", "_entity_type": "state", "captured_at": "2026-01-02T00:00:00", "models": {"m": {}}},
    ]
    latest = metadata.latest_entity_by_email(records)
    assert latest["c@b.com"]["captured_at"] == "2026-01-02T00:00:00"

    # 4. Same priority and richness, timestamp wins
    records = [
        {"email": "d@b.com", "_entity_type": "snapshot", "captured_at": "2026-01-01T00:00:00", "models": {"m": {}}},
        {"email": "d@b.com", "_entity_type": "snapshot", "captured_at": "2026-01-02T00:00:00", "models": {"m": {}}},
    ]
    latest = metadata.latest_entity_by_email(records)
    assert latest["d@b.com"]["captured_at"] == "2026-01-02T00:00:00"

    # 6. High Prio (No models) vs Low Prio (Has models) -> Low Prio wins richness
    records = [
        {"email": "f@b.com", "_entity_type": "snapshot", "captured_at": "2026-01-02T00:00:00"},
        {"email": "f@b.com", "_entity_type": "reset", "reset_ist": "2026-01-01T00:00:00", "models": {"m": {}}},
    ]
    latest = metadata.latest_entity_by_email(records)
    assert latest["f@b.com"]["_entity_type"] == "reset"

    # 7. Low Prio (No models) vs High Prio (Has models) -> High Prio wins both
    records = [
        {"email": "g@b.com", "_entity_type": "reset", "reset_ist": "2026-01-02T00:00:00"},
        {"email": "g@b.com", "_entity_type": "snapshot", "captured_at": "2026-01-01T00:00:00", "models": {"m": {}}},
    ]
    latest = metadata.latest_entity_by_email(records)
    assert latest["g@b.com"]["_entity_type"] == "snapshot"

    # 8. Reset with models richness
    records = [
        {"email": "h@b.com", "_entity_type": "reset", "reset_ist": "2026-01-01T00:00:00"},
        {"email": "h@b.com", "_entity_type": "reset", "reset_ist": "2026-01-02T00:00:00", "models": {"m": {}}},
    ]
    latest = metadata.latest_entity_by_email(records)
    assert latest["h@b.com"]["reset_ist"] == "2026-01-02T00:00:00"
def test_cooldown_reads_metadata_only_accounts(fs, capsys):
    backup_dir = os.path.expanduser("~/.gemini-manager/backups")
    accounts_dir = os.path.expanduser("~/.gemini-manager/accounts")
    # Redundant fs.create_dir removed
    path = os.path.join(accounts_dir, "user_at_example.com.state.json")
    fs.create_file(
        path,
        contents=json.dumps(
            {
                "product": "gemini",
                "email": "user@example.com",
                "captured_at": "2099-01-01T00:00:00+00:00",
                "updated_at": "2099-01-01T00:00:00+00:00",
                "next_available_at": "2099-01-01T01:00:00+00:00",
                "models": {
                    "Flash": {
                        "percent": 7,
                        "reset_at": "2099-01-01T01:00:00+00:00",
                    },
                    "Pro": {
                        "percent": 100,
                    },
                },
            }
        ),
    )

    with patch("gemini_manager.cooldown.console", new=Console(width=200, force_terminal=False)):
        do_cooldown_list()

    out = capsys.readouterr().out
    assert "user@example.com" in out
    assert "Flsh:" in out
    assert "Pro:" in out
