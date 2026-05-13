import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from gemini_manager import metadata
from gemini_manager.cooldown import do_cooldown_list
from rich.console import Console


def test_metadata_path_for_archive_handles_gpg():
    path = "/tmp/2026-01-01_120000-user@example.com.gemini-manager.tar.gz.gpg"
    assert metadata.metadata_path_for_archive(path).endswith(
        "2026-01-01_120000-user@example.com.gemini-manager.metadata.json"
    )


def test_patch_status_metadata_creates_metadata_only(fs):
    backup_dir = "/tmp/backups"
    fs.create_dir(backup_dir)
    status = {
        "email": "user@example.com",
        "models": {
            "Flash": {"percent": 12, "extra": "Resets", "reset_h": 1, "reset_m": 2}
        },
    }

    path = metadata.patch_status_metadata(status, SimpleNamespace(backup_dir=backup_dir, cloud=False))

    assert path is not None
    data = json.loads(open(path).read())
    assert data["email"] == "user@example.com"
    assert data["metadata_only"] is True
    assert data["models"]["Flash"]["percent"] == 12
    assert data["models"]["Flash"]["reset_at"]


def test_patch_status_metadata_updates_existing_backup_metadata(fs):
    backup_dir = "/tmp/backups"
    fs.create_dir(backup_dir)
    existing = os.path.join(backup_dir, "2026-01-01_120000-user@example.com.gemini-manager.metadata.json")
    fs.create_file(
        existing,
        contents=json.dumps({"email": "user@example.com", "archive_name": "backup.tar.gz", "created_at": "old"}),
    )

    status = {
        "email": "user@example.com",
        "models": {
            "Pro": {"percent": 80, "extra": "", "reset_h": None, "reset_m": None}
        },
    }

    path = metadata.patch_status_metadata(status, SimpleNamespace(backup_dir=backup_dir, cloud=False))

    assert path == existing
    data = json.loads(open(path).read())
    assert data["archive_name"] == "backup.tar.gz"
    assert data["created_at"] == "old"
    assert data["metadata_only"] is False
    assert data["models"]["Pro"]["percent"] == 80


def test_patch_status_metadata_uploads_cloud(fs):
    backup_dir = "/tmp/backups"
    fs.create_dir(backup_dir)
    provider = MagicMock()
    args = SimpleNamespace(backup_dir=backup_dir, cloud=True)
    status = {"email": "user@example.com", "models": {}}

    with patch("gemini_manager.cloud_factory.get_cloud_provider", return_value=provider):
        path = metadata.patch_status_metadata(status, args)

    provider.upload_file.assert_called_once_with(path, os.path.basename(path))


def test_cooldown_reads_metadata_only_accounts(fs, capsys):
    backup_dir = os.path.expanduser("~/.gemini-manager/backups")
    fs.create_dir(backup_dir)
    path = os.path.join(backup_dir, "2026-01-01_120000-user@example.com.gemini-manager.metadata.json")
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
