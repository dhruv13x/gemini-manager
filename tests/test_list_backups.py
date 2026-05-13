# tests/test_list_backups.py

import pytest
from unittest.mock import patch, MagicMock
import json
import os
import sys
import tempfile
from gemini_manager import list_backups

@patch("gemini_manager.list_backups.B2Manager")
def test_main_cloud(mock_b2):
    with patch("sys.argv", ["list_backups.py", "--cloud", "--bucket", "b", "--b2-id", "i", "--b2-key", "k"]):
        mock_file = MagicMock()
        mock_file.file_name = "backup.gemini-manager.tar.gz"
        mock_b2.return_value.list_backups.return_value = [(mock_file, None)]
        list_backups.main()
        mock_b2.return_value.list_backups.assert_called()

@patch("gemini_manager.list_backups.B2Manager")
def test_main_cloud_empty(mock_b2):
    with patch("sys.argv", ["list_backups.py", "--cloud", "--bucket", "b", "--b2-id", "i", "--b2-key", "k"]):
        mock_b2.return_value.list_backups.return_value = []
        list_backups.main()

@patch("gemini_manager.list_backups.B2Manager")
def test_main_cloud_error(mock_b2):
    with patch("sys.argv", ["list_backups.py", "--cloud", "--bucket", "b", "--b2-id", "i", "--b2-key", "k"]):
        mock_b2.return_value.list_backups.side_effect = Exception("Error")
        with pytest.raises(SystemExit):
            list_backups.main()

@patch("gemini_manager.credentials.get_setting", return_value=None)
@patch.dict(os.environ, {}, clear=True)
def test_main_cloud_no_creds(mock_get_setting):
    with patch("sys.argv", ["list_backups.py", "--cloud"]):
        with pytest.raises(SystemExit):
            list_backups.main()

@patch("os.path.isdir", return_value=True)
@patch("os.listdir")
@patch("os.path.isfile", return_value=True)
def test_main_local(mock_isfile, mock_listdir, mock_isdir):
    mock_listdir.return_value = ["backup.gemini-manager.tar.gz", "other.txt"]
    with patch("sys.argv", ["list_backups.py", "--search-dir", "/tmp"]):
        list_backups.main()

@patch("os.path.isdir", return_value=True)
@patch("os.listdir")
def test_main_local_empty(mock_listdir, mock_isdir):
    mock_listdir.return_value = []
    with patch("sys.argv", ["list_backups.py", "--search-dir", "/tmp"]):
        list_backups.main()

@patch("os.path.isdir", return_value=False)
def test_main_local_no_dir(mock_isdir):
    with patch("sys.argv", ["list_backups.py", "--search-dir", "/tmp"]):
        list_backups.main()

@patch("os.path.isdir", return_value=True)
@patch("os.listdir", side_effect=OSError)
def test_main_local_error(mock_listdir, mock_isdir):
    with patch("sys.argv", ["list_backups.py", "--search-dir", "/tmp"]):
        list_backups.main()

@patch("gemini_manager.list_backups.B2Manager")
def test_main_cloud_loop_continue(mock_b2):
    # Test line 38: if file_version.file_name.endswith...
    with patch("sys.argv", ["list_backups.py", "--cloud", "--bucket", "b", "--b2-id", "i", "--b2-key", "k"]):
        mock_file = MagicMock()
        mock_file.file_name = "other.txt" # Not ending in .gemini-manager.tar.gz
        mock_b2.return_value.list_backups.return_value = [(mock_file, None)]
        list_backups.main()
        # Should print "No backups found" because only non-matching file


def test_local_rows_latest_per_email_uses_metadata():
    with tempfile.TemporaryDirectory(prefix="gm-test-list-") as tmpdir:
        old_archive_name = "2026-05-13_110000-user@example.com.gemini-manager.tar.gz"
        new_archive_name = "2026-05-13_120000-user@example.com.gemini-manager.tar.gz"
        open(os.path.join(tmpdir, old_archive_name), "w").close()
        open(os.path.join(tmpdir, new_archive_name), "w").close()
        metadata = {
            "email": "user@example.com",
            "archive_name": new_archive_name,
            "captured_at": "2026-05-13T12:01:00+05:30",
            "next_available_at": "2026-05-14T12:01:00+05:30",
            "models": {
                "Flash": {"percent_left": 12},
                "Flash Lite": {"percent_left": 0},
                "Pro": {"percent_left": 100},
            },
        }
        metadata_path = os.path.join(tmpdir, "2026-05-13_120000-user@example.com.gemini-manager.metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as fh:
            json.dump(metadata, fh)

        rows = list_backups._sort_rows(list_backups._local_rows(tmpdir), latest_only=True)

    assert len(rows) == 1
    assert rows[0].archive_name == new_archive_name
    assert rows[0].email == "user@example.com"
    assert rows[0].flash == 88
    assert rows[0].lite == 100
    assert rows[0].pro == 0


def test_directory_backups_hidden_unless_requested():
    with tempfile.TemporaryDirectory(prefix="gm-test-list-") as tmpdir:
        args = MagicMock(cloud=False, search_dir=tmpdir, all=False, show_dirs=False)
        with patch("gemini_manager.list_backups._print_directory_backups") as mock_dirs:
            list_backups.perform_list_backups(args)
        mock_dirs.assert_not_called()

        args.show_dirs = True
        with patch("gemini_manager.list_backups._print_directory_backups") as mock_dirs:
            list_backups.perform_list_backups(args)
        mock_dirs.assert_called_once()
