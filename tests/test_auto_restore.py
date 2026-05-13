
import pytest
from unittest.mock import patch, MagicMock
import sys
import os
from gemini_manager import restore

# Now that restore.py imports get_recommendation, we can patch it directly in restore module
@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.get_recommendation")
@patch("gemini_manager.restore.run")
@patch("os.path.exists", return_value=True)
@patch("os.makedirs")
@patch("os.replace")
@patch("gemini_manager.restore.shutil.move")
@patch("shutil.rmtree")
@patch("tempfile.mkdtemp", return_value="/tmp/restore_tmp")
def test_restore_auto_success(mock_mkdtemp, mock_rmtree, mock_move, mock_replace, mock_makedirs, mock_exists, mock_run, mock_rec, mock_lock, fs):
    # Setup mock recommendation
    mock_rec_obj = MagicMock()
    mock_rec_obj.email = "auto@example.com"
    mock_rec.return_value = mock_rec_obj

    # Setup mock backups in search_dir
    # restore.py uses DEFAULT_BACKUP_DIR by default which is ~/.gemini-manager/backups
    # But wait, we need to make sure we put files where restore.py looks.
    # restore.py:
    # args.search_dir = DEFAULT_BACKUP_DIR
    # sd = os.path.abspath(os.path.expanduser(args.search_dir))

    search_dir = os.path.expanduser("~/.gemini-manager/backups")
    fs.create_dir(search_dir)
    fs.create_file(os.path.join(search_dir, "2025-10-20_000000-other@example.com.gemini-manager.tar.gz"))
    fs.create_file(os.path.join(search_dir, "2025-10-21_100000-auto@example.com.gemini-manager.tar.gz")) # Old
    fs.create_file(os.path.join(search_dir, "2025-10-22_100000-auto@example.com.gemini-manager.tar.gz")) # Latest

    mock_run.return_value.returncode = 0

    with patch("sys.argv", ["restore.py", "--full", "--auto"]):
        restore.main()

    # Verify that get_recommendation was called
    mock_rec.assert_called_once()

    # Verify extraction of correct file
    found = False
    expected_file = "2025-10-22_100000-auto@example.com.gemini-manager.tar.gz"
    for call in mock_run.call_args_list:
        args, _ = call
        if args and isinstance(args[0], str):
            cmd = args[0]
            if "tar -C" in cmd and expected_file in cmd:
                found = True
                break

    assert found, f"Did not find extraction command for {expected_file}"

@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.get_recommendation")
def test_restore_auto_no_recommendation(mock_rec, mock_lock, fs):
    mock_rec.return_value = None
    with patch("sys.argv", ["restore.py", "--auto"]):
        with pytest.raises(SystemExit) as e:
            restore.main()
        # Should exit with error if no recommendation
        assert e.value.code != 0

@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.get_recommendation")
def test_restore_auto_no_backups_for_email(mock_rec, mock_lock, fs):
    mock_rec_obj = MagicMock()
    mock_rec_obj.email = "auto@example.com"
    mock_rec.return_value = mock_rec_obj

    search_dir = os.path.expanduser("~/.gemini-manager/backups")
    fs.create_dir(search_dir)
    fs.create_file(os.path.join(search_dir, "2025-10-20_000000-other@example.com.gemini-manager.tar.gz"))

    with patch("sys.argv", ["restore.py", "--auto"]):
        with pytest.raises(SystemExit) as e:
            restore.main()
        assert e.value.code != 0

@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.get_recommendation")
def test_find_latest_archive_backup_for_email_robustness(mock_rec, mock_lock, fs):
    # Test strict email matching
    search_dir = os.path.expanduser("~/.gemini-manager/backups")
    fs.create_dir(search_dir)
    fs.create_file(os.path.join(search_dir, "2025-10-20_000000-sue@example.com.gemini-manager.tar.gz"))
    fs.create_file(os.path.join(search_dir, "2025-10-20_000000-josue@example.com.gemini-manager.tar.gz"))

    # We test function directly
    latest = restore.find_latest_archive_backup_for_email(search_dir, "sue@example.com")
    assert latest is not None
    assert "josue" not in latest
    assert "sue@example.com" in latest
