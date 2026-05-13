# tests/test_cleanup.py

import pytest
import os
from unittest.mock import MagicMock, patch
from pathlib import Path
from gemini_manager.chat import cleanup_chat_history

# Note: We use pyfakefs via conftest.py, so file operations are already on fake fs.
# We should NOT mock os.path.exists, os.listdir etc manually.


@pytest.fixture
def mock_args():
    args = MagicMock()
    args.force = False
    args.dry_run = False
    return args


def test_do_cleanup_dir_not_exists(mock_args, capsys, fs):
    # Directory /mock/home does not exist in fake fs
    cleanup_chat_history(mock_args.dry_run, mock_args.force, Path("/mock/home"))

    captured = capsys.readouterr()
    assert "Nothing to clean. Directory not found" in captured.out


def test_do_cleanup_list_error(mock_args, capsys, fs):
    # Simulate listdir error by making it unreadable?
    # Or patch os.listdir since pyfakefs behavior for permissions is specific.
    # To test exception handling specifically, patching is okay but we must be careful.

    # Create the directory first
    fs.create_dir("/mock/home/tmp")

    with patch("os.listdir", side_effect=Exception("Permission denied")):
        cleanup_chat_history(mock_args.dry_run, mock_args.force, Path("/mock/home"))

    captured = capsys.readouterr()
    assert "Could not list directory" in captured.out


def test_do_cleanup_nothing_to_remove(mock_args, capsys, fs):
    # Create dir with only 'bin'
    fs.create_dir("/mock/home/tmp")
    fs.create_file("/mock/home/tmp/bin")  # bin is skipped

    cleanup_chat_history(mock_args.dry_run, mock_args.force, Path("/mock/home"))

    captured = capsys.readouterr()
    assert "Directory is already clean" in captured.out


def test_do_cleanup_cancelled(mock_args, capsys, fs):
    fs.create_dir("/mock/home/tmp")
    fs.create_file("/mock/home/tmp/file1")
    fs.create_file("/mock/home/tmp/bin")

    with patch("builtins.input", return_value="n"):
        cleanup_chat_history(mock_args.dry_run, mock_args.force, Path("/mock/home"))

    captured = capsys.readouterr()
    assert "Cleanup cancelled" in captured.out


def test_do_cleanup_force_success(mock_args, capsys, fs):
    mock_args.force = True
    fs.create_dir("/mock/home/tmp")
    fs.create_file("/mock/home/tmp/file1")
    fs.create_dir("/mock/home/tmp/dir1")
    fs.create_file("/mock/home/tmp/bin")

    cleanup_chat_history(mock_args.dry_run, mock_args.force, Path("/mock/home"))

    assert not os.path.exists("/mock/home/tmp/file1")
    assert not os.path.exists("/mock/home/tmp/dir1")
    assert os.path.exists("/mock/home/tmp/bin")

    captured = capsys.readouterr()
    assert "Cleanup finished. Removed 2 items" in captured.out


def test_do_cleanup_dry_run(mock_args, capsys, fs):
    mock_args.dry_run = True
    fs.create_dir("/mock/home/tmp")
    fs.create_file("/mock/home/tmp/file1")
    fs.create_dir("/mock/home/tmp/dir1")
    fs.create_file("/mock/home/tmp/bin")

    cleanup_chat_history(mock_args.dry_run, mock_args.force, Path("/mock/home"))

    assert os.path.exists("/mock/home/tmp/file1")
    assert os.path.exists("/mock/home/tmp/dir1")

    captured = capsys.readouterr()
    assert "Would delete: file1" in captured.out
    assert "Would delete: dir1" in captured.out
    assert "Cleanup dry run finished. Would remove 2 items" in captured.out


def test_do_cleanup_interactive_yes(mock_args, capsys, fs):
    fs.create_dir("/mock/home/tmp")
    fs.create_file("/mock/home/tmp/file1")

    with patch("builtins.input", return_value="y"):
        cleanup_chat_history(mock_args.dry_run, mock_args.force, Path("/mock/home"))

    assert not os.path.exists("/mock/home/tmp/file1")
    captured = capsys.readouterr()
    assert "Cleaning up..." in captured.out


def test_do_cleanup_delete_error(mock_args, capsys, fs):
    mock_args.force = True
    fs.create_dir("/mock/home/tmp")
    fs.create_file("/mock/home/tmp/file1")

    with patch("os.unlink", side_effect=Exception("Disk error")):
        cleanup_chat_history(mock_args.dry_run, mock_args.force, Path("/mock/home"))

    captured = capsys.readouterr()
    assert "Failed to delete file1" in captured.out
