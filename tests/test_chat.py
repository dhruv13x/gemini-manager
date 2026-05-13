import os
import shutil
from pathlib import Path
from unittest.mock import patch
from gemini_manager.chat import (
    backup_chat_history,
    restore_chat_history,
    cleanup_chat_history,
    resume_chat,
)

# Note: Using pyfakefs via conftest.py (fs fixture), so file operations are already on fake fs.


def test_backup_and_restore_chat_history(fs):
    home_dir = Path("/home/user")
    gemini_home_dir = home_dir / ".gm"
    gemini_tmp_dir = gemini_home_dir / "tmp"
    backup_path = home_dir / "chat_backups"

    fs.create_dir(gemini_tmp_dir)
    fs.create_file(gemini_tmp_dir / "chat1.txt", contents="This is a chat history.")

    # 1. Backup the chat history
    backup_chat_history(str(backup_path), str(gemini_home_dir))

    # Verify the backup
    backup_dir = backup_path / "tmp"
    assert (backup_dir / "chat1.txt").exists()

    with open(backup_dir / "chat1.txt", "r") as f:
        assert f.read() == "This is a chat history."

    # 2. Clear the original chat history
    shutil.rmtree(gemini_tmp_dir)
    os.makedirs(gemini_tmp_dir)
    assert not (gemini_tmp_dir / "chat1.txt").exists()

    # 3. Restore the chat history
    restore_chat_history(str(backup_path), str(gemini_home_dir))

    # Verify the restore
    assert (gemini_tmp_dir / "chat1.txt").exists()
    with open(gemini_tmp_dir / "chat1.txt", "r") as f:
        assert f.read() == "This is a chat history."


def test_cleanup_chat_history(fs):
    home_dir = Path("/home/user")
    gemini_home_dir = home_dir / ".gm"
    gemini_tmp_dir = gemini_home_dir / "tmp"

    fs.create_dir(gemini_tmp_dir)
    fs.create_file(gemini_tmp_dir / "chat1.txt", contents="This is a chat history.")
    fs.create_dir(gemini_tmp_dir / "bin")
    fs.create_file(gemini_tmp_dir / "bin" / "some_executable", contents="...")

    # Cleanup without force (interactive yes)
    with patch("builtins.input", return_value="y"):
        cleanup_chat_history(
            dry_run=False, force=False, gemini_home_dir=str(gemini_home_dir)
        )

    # Verify that chat1.txt is deleted and bin is preserved
    assert not (gemini_tmp_dir / "chat1.txt").exists()
    assert (gemini_tmp_dir / "bin").exists()


@patch("subprocess.run")
def test_resume_chat(mock_run):
    resume_chat()
    mock_run.assert_called_once_with(["gm", "--model", "pro", "--resume"])


def test_backup_chat_history_exception(fs, capsys):
    fs.create_dir("/home/user/.gm/tmp")
    fs.create_file("/home/user/.gm/tmp/chat.log")
    fs.create_dir("/backup")

    gemini_home_dir = "/home/user/.gm"
    backup_path = "/backup"

    # Patch shutil.copy to raise exception
    with patch("shutil.copy", side_effect=Exception("Copy failed")):
        backup_chat_history(backup_path, gemini_home_dir)

    captured = capsys.readouterr()
    assert "Failed to backup chat history: Copy failed" in captured.out


def test_restore_chat_history_exception(fs, capsys):
    fs.create_dir("/backup/tmp")
    fs.create_file("/backup/tmp/chat.log")

    gemini_home_dir = "/home/user/.gm"
    # Ensure home dir exists without error
    if not os.path.exists(gemini_home_dir):
        fs.create_dir(gemini_home_dir)

    backup_path = "/backup"

    # Patch shutil.copy to raise exception
    with patch("shutil.copy", side_effect=Exception("Restore failed")):
        restore_chat_history(backup_path, gemini_home_dir)

    captured = capsys.readouterr()
    assert "Failed to restore chat history: Restore failed" in captured.out


def test_cleanup_chat_history_listdir_exception(fs, capsys):
    fs.create_dir("/home/user/.gm/tmp")
    gemini_home_dir = "/home/user/.gm"

    # Patch os.listdir to raise
    with patch("os.listdir", side_effect=Exception("Access denied")):
        cleanup_chat_history(
            dry_run=False, force=False, gemini_home_dir=gemini_home_dir
        )

    captured = capsys.readouterr()
    assert "[ERROR] Could not list directory" in captured.out
    assert "Access denied" in captured.out


def test_cleanup_chat_history_interactive_cancel(fs, capsys):
    fs.create_dir("/home/user/.gm/tmp")
    fs.create_file("/home/user/.gm/tmp/chat.log")
    gemini_home_dir = "/home/user/.gm"

    with patch("builtins.input", return_value="n"):
        cleanup_chat_history(
            dry_run=False, force=False, gemini_home_dir=gemini_home_dir
        )

    captured = capsys.readouterr()
    assert "Cleanup cancelled." in captured.out


def test_cleanup_chat_history_delete_exception(fs, capsys):
    fs.create_dir("/home/user/.gm/tmp")
    fs.create_file("/home/user/.gm/tmp/chat.log")
    gemini_home_dir = "/home/user/.gm"

    # Patch os.unlink to raise
    with patch("os.unlink", side_effect=Exception("Delete failed")):
        cleanup_chat_history(dry_run=False, force=True, gemini_home_dir=gemini_home_dir)

    captured = capsys.readouterr()
    assert "[ERROR] Failed to delete chat.log: Delete failed" in captured.out


def test_resume_chat_file_not_found(capsys):
    with patch("subprocess.run", side_effect=FileNotFoundError):
        resume_chat()

    captured = capsys.readouterr()
    assert "The 'gm' command was not found" in captured.out


def test_resume_chat_exception(capsys):
    with patch("subprocess.run", side_effect=Exception("Unexpected error")):
        resume_chat()

    captured = capsys.readouterr()
    assert "Failed to resume chat: Unexpected error" in captured.out
