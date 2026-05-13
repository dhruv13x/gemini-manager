# tests/test_list_backups.py

import pytest
from unittest.mock import patch, MagicMock
import os
from gemini_manager import list_backups


@patch("gemini_manager.list_backups.B2Manager")
def test_main_cloud(mock_b2):
    with patch(
        "sys.argv",
        [
            "list_backups.py",
            "--cloud",
            "--bucket",
            "b",
            "--b2-id",
            "i",
            "--b2-key",
            "k",
        ],
    ):
        mock_file = MagicMock()
        mock_file.file_name = "backup.gemini-manager.tar.gz"
        mock_b2.return_value.list_backups.return_value = [(mock_file, None)]
        list_backups.main()
        mock_b2.return_value.list_backups.assert_called()


@patch("gemini_manager.list_backups.B2Manager")
def test_main_cloud_empty(mock_b2):
    with patch(
        "sys.argv",
        [
            "list_backups.py",
            "--cloud",
            "--bucket",
            "b",
            "--b2-id",
            "i",
            "--b2-key",
            "k",
        ],
    ):
        mock_b2.return_value.list_backups.return_value = []
        list_backups.main()


@patch("gemini_manager.list_backups.B2Manager")
def test_main_cloud_error(mock_b2):
    with patch(
        "sys.argv",
        [
            "list_backups.py",
            "--cloud",
            "--bucket",
            "b",
            "--b2-id",
            "i",
            "--b2-key",
            "k",
        ],
    ):
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
    with patch(
        "sys.argv",
        [
            "list_backups.py",
            "--cloud",
            "--bucket",
            "b",
            "--b2-id",
            "i",
            "--b2-key",
            "k",
        ],
    ):
        mock_file = MagicMock()
        mock_file.file_name = "other.txt"  # Not ending in .gemini-manager.tar.gz
        mock_b2.return_value.list_backups.return_value = [(mock_file, None)]
        list_backups.main()
        # Should print "No backups found" because only non-matching file
