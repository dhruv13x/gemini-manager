# tests/test_restore.py

import pytest
from unittest.mock import patch, MagicMock, ANY
import os
import argparse
import tempfile
from gemini_manager import restore
from gemini_manager.restore import perform_restore
from gemini_manager.recommend import Recommendation, AccountStatus


# Fixture to mock the filesystem for all tests in this file
@pytest.fixture(autouse=True)
def fs_setup(fs):
    """Ensure basic directories exist."""
    pass


@patch("gemini_manager.restore.fcntl")
def test_acquire_lock_success(mock_fcntl):
    with patch("gemini_manager.restore.LOCKFILE", "/tmp/restore.lock"):
        fd = restore.acquire_lock()
        assert fd is not None
        mock_fcntl.flock.assert_called()


@patch("gemini_manager.restore.fcntl")
def test_acquire_lock_fail(mock_fcntl):
    with patch("gemini_manager.restore.LOCKFILE", "/tmp/restore.lock"):
        mock_fcntl.flock.side_effect = BlockingIOError
        with pytest.raises(SystemExit) as e:
            restore.acquire_lock()
        assert e.value.code == 2


def test_run():
    with patch("subprocess.run") as mock_run:
        restore.run("ls")
        mock_run.assert_called_with("ls", shell=True, check=True)


def test_parse_timestamp_from_name():
    ts = restore.parse_timestamp_from_name("2025-10-22_042211-test@test.gemini-manager")
    assert ts is not None
    assert ts.tm_year == 2025

    assert restore.parse_timestamp_from_name("invalid") is None


def test_find_oldest_archive_backup(fs):
    backup_dir = "/tmp/backups"
    fs.create_dir(backup_dir)
    fs.create_file(
        os.path.join(backup_dir, "2025-10-23_042211-test.gemini-manager.tar.gz")
    )
    fs.create_file(
        os.path.join(backup_dir, "2025-10-22_042211-test.gemini-manager.tar.gz")
    )

    oldest = restore.find_oldest_archive_backup(backup_dir)
    assert "2025-10-22" in oldest


def test_find_oldest_archive_backup_none(fs):
    backup_dir = "/tmp/backups"
    fs.create_dir(backup_dir)
    assert restore.find_oldest_archive_backup(backup_dir) is None


@patch("gemini_manager.restore.run")
def test_extract_archive(mock_run, fs):
    fs.create_dir("/dest")
    fs.create_file("/archive.tar.gz")
    restore.extract_archive("/archive.tar.gz", "/dest")
    mock_run.assert_called()


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.run")
@patch("os.replace")
def test_main_from_dir(mock_replace, mock_run, mock_lock, fs):
    src_dir = "/tmp/backup_source"
    dest_dir = os.path.expanduser("~/.gemini-manager")
    fs.create_dir(src_dir)
    fs.create_dir(dest_dir)

    mock_run.return_value.returncode = 0

    with patch("shutil.move"):
        with patch("sys.argv", ["restore.py", "--from-dir", src_dir]):
            restore.main()

    assert mock_run.call_count >= 1


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.run")
@patch("os.replace")
def test_main_from_archive(mock_replace, mock_run, mock_lock, fs):
    archive = "/tmp/backup.tar.gz"
    fs.create_file(archive)
    dest_dir = os.path.expanduser("~/.gemini-manager")
    fs.create_dir(dest_dir)

    mock_run.return_value.returncode = 0

    with patch("sys.argv", ["restore.py", "--from-archive", archive]):
        restore.main()


@patch("gemini_manager.restore.acquire_lock")
@patch(
    "gemini_manager.restore.find_oldest_archive_backup",
    return_value="/tmp/oldest.tar.gz",
)
@patch("gemini_manager.restore.run")
@patch("os.replace")
def test_main_auto_oldest(mock_replace, mock_run, mock_find_oldest, mock_lock, fs):
    fs.create_file("/tmp/oldest.tar.gz")
    dest_dir = os.path.expanduser("~/.gemini-manager")
    fs.create_dir(dest_dir)

    mock_run.return_value.returncode = 0

    with patch("sys.argv", ["restore.py"]):
        restore.main()
        mock_find_oldest.assert_called()


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.get_cloud_provider")
@patch("gemini_manager.restore.run")
@patch("gemini_manager.cooldown._sync_cooldown_file")
@patch("os.replace")
def test_main_cloud(
    mock_replace, mock_sync, mock_run, mock_get_provider, mock_lock, fs
):
    dest_dir = os.path.expanduser("~/.gemini-manager")
    fs.create_dir(dest_dir)

    with patch(
        "sys.argv",
        ["restore.py", "--cloud", "--bucket", "b", "--b2-id", "i", "--b2-key", "k"],
    ):
        mock_file = MagicMock()
        mock_file.name = "2025-10-22_042211-test.gemini-manager.tar.gz"
        mock_get_provider.return_value.list_files.return_value = [mock_file]

        mock_run.return_value.returncode = 0

        # Create temp file so os.remove doesn't fail if called, though we patch it usually
        # But here we want normal execution flow
        temp_path = os.path.join(tempfile.gettempdir(), mock_file.name)
        fs.create_file(temp_path)

        restore.main()
        mock_get_provider.return_value.download_file.assert_called()


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.run")
def test_main_verification_fail(mock_run, mock_lock, fs):
    archive = "/tmp/archive.tar.gz"
    fs.create_file(archive)
    dest_dir = os.path.expanduser("~/.gemini-manager")
    fs.create_dir(dest_dir)

    with patch("sys.argv", ["restore.py", "--from-archive", archive]):
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=1, stdout="diff"),
        ]
        with pytest.raises(SystemExit) as e:
            restore.main()
        assert e.value.code == 3


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.run")
@patch("os.replace")
def test_main_post_verification_fail(mock_replace, mock_run, mock_lock, fs):
    archive = "/tmp/archive.tar.gz"
    fs.create_file(archive)
    dest_dir = os.path.expanduser("~/.gemini-manager")
    fs.create_dir(dest_dir)

    with patch("sys.argv", ["restore.py", "--from-archive", archive]):
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=1, stdout="diff"),
        ]
        with pytest.raises(SystemExit) as e:
            restore.main()
        assert e.value.code == 4


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.run")
def test_main_dry_run(mock_run, mock_lock, fs):
    fs.create_file("/tmp/archive.tar.gz")
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))

    with patch(
        "sys.argv", ["restore.py", "--from-archive", "/tmp/archive.tar.gz", "--dry-run"]
    ):
        restore.main()
        mock_run.assert_not_called()


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.get_cloud_provider")
def test_main_cloud_missing_creds(mock_get_provider, mock_lock, fs):
    with patch("sys.argv", ["restore.py", "--cloud"]):
        mock_get_provider.return_value = None
        with pytest.raises(SystemExit):
            restore.main()


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.get_cloud_provider")
def test_main_cloud_no_backups(mock_get_provider, mock_lock, fs):
    with patch(
        "sys.argv",
        ["restore.py", "--cloud", "--bucket", "b", "--b2-id", "i", "--b2-key", "k"],
    ):
        mock_get_provider.return_value.list_files.return_value = []
        with pytest.raises(SystemExit):
            restore.main()


@patch("gemini_manager.restore.acquire_lock")
def test_main_from_dir_not_found(mock_lock, fs):
    with patch("sys.argv", ["restore.py", "--from-dir", "/tmp/notfound"]):
        with pytest.raises(SystemExit):
            restore.main()


@patch("gemini_manager.restore.acquire_lock")
@patch("os.replace")
def test_main_from_archive_search_dir(mock_replace, mock_lock, fs):
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))
    search_dir = os.path.expanduser("~/.gemini-manager/backups")
    fs.create_dir(search_dir)
    fs.create_file(os.path.join(search_dir, "archive.tar.gz"))

    with patch("gemini_manager.restore.run") as mock_run:
        mock_run.return_value.returncode = 0

        with patch("sys.argv", ["restore.py", "--from-archive", "archive.tar.gz"]):
            restore.main()


@patch("gemini_manager.restore.acquire_lock")
def test_main_from_archive_not_found(mock_lock, fs):
    with patch("sys.argv", ["restore.py", "--from-archive", "archive.tar.gz"]):
        with pytest.raises(SystemExit):
            restore.main()


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.find_oldest_archive_backup", return_value=None)
def test_main_auto_no_backups(mock_find, mock_lock, fs):
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))
    with patch("sys.argv", ["restore.py"]):
        with pytest.raises(SystemExit):
            restore.main()


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.run")
@patch("os.replace")
def test_main_rollback_success(mock_replace, mock_run, mock_lock, fs):
    archive = "/tmp/archive.tar.gz"
    fs.create_file(archive)
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))

    with patch("sys.argv", ["restore.py", "--from-archive", archive]):
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=1, stdout="diff"),
        ]
        with pytest.raises(SystemExit) as e:
            restore.main()
        assert e.value.code == 4


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.run")
def test_main_rollback_fail(mock_run, mock_lock, fs):
    archive = "/tmp/archive.tar.gz"
    fs.create_file(archive)
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))

    with patch("sys.argv", ["restore.py", "--from-archive", archive]):
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=1),
        ]

        with patch(
            "os.replace", side_effect=[None, None, OSError("Rollback Error")]
        ):
            with pytest.raises(SystemExit) as e:
                restore.main()
            assert e.value.code == 4


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.get_cloud_provider")
@patch("gemini_manager.restore.run")
@patch("gemini_manager.cooldown._sync_cooldown_file")
@patch("os.replace")
def test_main_cloud_specific_archive(
    mock_replace, mock_sync, mock_run, mock_get_provider, mock_lock, fs
):
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))
    specific_archive = "2025-11-21_231311-specific@test.gemini-manager.tar.gz"

    with patch(
        "sys.argv",
        [
            "restore.py",
            "--cloud",
            "--bucket",
            "b",
            "--b2-id",
            "i",
            "--b2-key",
            "k",
            "--from-archive",
            specific_archive,
        ],
    ):
        mock_file_specific = MagicMock()
        mock_file_specific.name = specific_archive

        mock_file_old = MagicMock()
        mock_file_old.name = "2025-10-22_042211-old@test.gemini-manager.tar.gz"

        mock_get_provider.return_value.list_files.return_value = [
            mock_file_old,
            mock_file_specific,
        ]

        mock_run.return_value.returncode = 0

        # Create temp file
        temp_path = os.path.join(tempfile.gettempdir(), specific_archive)
        fs.create_file(temp_path)

        restore.main()

        mock_get_provider.return_value.download_file.assert_called_with(
            specific_archive, ANY
        )


@patch("gemini_manager.restore.acquire_lock")
@patch("os.replace")
def test_main_lock_exception(mock_replace, mock_lock, fs):
    fs.create_file("/tmp/backup.tar.gz")
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))

    mock_fd = MagicMock()
    mock_lock.return_value = mock_fd

    with patch(
        "gemini_manager.restore.find_oldest_archive_backup",
        return_value="/tmp/backup.tar.gz",
    ):
        with patch("gemini_manager.restore.run", return_value=MagicMock(returncode=0)):
            with patch("sys.argv", ["restore.py"]):
                with patch("gemini_manager.restore.fcntl.flock") as mock_flock:
                    mock_flock.side_effect = [None, Exception("Unlock fail")]
                    restore.main()


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.run")
def test_main_os_replace_fail_fallback(mock_run, mock_lock, fs):
    archive = "/tmp/archive.tar.gz"
    fs.create_file(archive)
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))

    mock_run.return_value.returncode = 0

    with patch("os.replace", side_effect=OSError(18, "Cross-device link")):
        with patch("shutil.move") as mock_move:
            with patch("sys.argv", ["restore.py", "--from-archive", archive]):
                restore.main()
                mock_move.assert_called()


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.run")
@patch("os.replace")
def test_main_temp_extraction_rmtree_fail(mock_replace, mock_run, mock_lock, fs):
    archive = "/tmp/archive.tar.gz"
    fs.create_file(archive)
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))
    mock_run.return_value.returncode = 0

    # Mock shutil.rmtree to fail
    with patch("shutil.rmtree", side_effect=Exception("Perm error")):
        with patch("sys.argv", ["restore.py", "--from-archive", archive]):
            restore.main()


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.run")
@patch("os.replace")
def test_main_dest_not_exists(mock_replace, mock_run, mock_lock, fs):
    # dest dir does not exist (we don't create it in fs)
    archive = "/tmp/archive.tar.gz"
    fs.create_file(archive)

    mock_run.return_value.returncode = 0

    with patch("sys.argv", ["restore.py", "--from-archive", archive]):
        restore.main()
        # Verify it created dest
        # Since we mocked os.replace, the actual move didn't happen, so dest isn't created by replace.
        # But `main` does verify verification success.
        # We can assert that `mock_replace` was called.
        mock_replace.assert_called()


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.run")
@patch("os.replace")
def test_main_tmp_dest_not_exists(mock_replace, mock_run, mock_lock, fs):
    archive = "/tmp/archive.tar.gz"
    fs.create_file(archive)
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))
    mock_run.return_value.returncode = 0

    with patch("sys.argv", ["restore.py", "--from-archive", archive]):
        restore.main()


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.run")
def test_main_force_replace(mock_run, mock_lock, fs):
    archive = "/tmp/archive.tar.gz"
    fs.create_file(archive)
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))
    mock_run.return_value.returncode = 0

    with patch("shutil.rmtree") as mock_rmtree:
        with patch("os.replace"):
            with patch(
                "sys.argv", ["restore.py", "--from-archive", archive, "--force"]
            ):
                restore.main()
                assert mock_rmtree.call_count >= 1


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.get_cloud_provider")
def test_main_cloud_specific_archive_not_found(mock_get_provider, mock_lock, fs):
    with patch(
        "sys.argv",
        [
            "restore.py",
            "--cloud",
            "--bucket",
            "b",
            "--b2-id",
            "i",
            "--b2-key",
            "k",
            "--from-archive",
            "missing.tar.gz",
        ],
    ):
        mock_file = MagicMock()
        mock_file.name = "other.tar.gz"
        mock_get_provider.return_value.list_files.return_value = [mock_file]
        with pytest.raises(SystemExit) as e:
            restore.main()
        assert e.value.code == 1


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.run")
@patch("gemini_manager.cooldown._sync_cooldown_file")
@patch("os.replace")
def test_main_cleanup_temp_download(mock_replace, mock_sync, mock_run, mock_lock, fs):
    dest_dir = os.path.expanduser("~/.gemini-manager")
    fs.create_dir(dest_dir)

    with patch(
        "sys.argv",
        ["restore.py", "--cloud", "--bucket", "b", "--b2-id", "i", "--b2-key", "k"],
    ):
        with patch("gemini_manager.restore.get_cloud_provider") as mock_get_provider:
            mock_file = MagicMock()
            mock_file.name = "2025-10-22_042211-test.gemini-manager.tar.gz"
            mock_get_provider.return_value.list_files.return_value = [mock_file]
            mock_run.return_value.returncode = 0

            # Create the temp file so it exists to be cleaned up
            temp_path = os.path.join(tempfile.gettempdir(), mock_file.name)
            fs.create_file(temp_path)

            with patch("os.remove") as mock_remove:
                # We need to manually simulate os.exists returning true for this path if fs doesn't handle it well
                # but fs SHOULD handle it.
                restore.main()
                mock_remove.assert_called()


@patch("gemini_manager.restore.acquire_lock")
@patch("gemini_manager.restore.run")
def test_main_verification_fail_with_stdout(mock_run, mock_lock, fs):
    archive = "/tmp/archive.tar.gz"
    fs.create_file(archive)
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))

    mock_run.side_effect = [
        MagicMock(returncode=0),
        MagicMock(returncode=0),
        MagicMock(returncode=1, stdout="diff output"),
    ]
    with patch("sys.argv", ["restore.py", "--from-archive", archive]):
        with pytest.raises(SystemExit) as e:
            restore.main()
        assert e.value.code == 3


# For perform_restore tests that use argparse.Namespace directly, we rely on fs setup too


def test_restore_auto_local_no_rec(fs, capsys):
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))

    args = argparse.Namespace(
        auto=True,
        cloud=False,
        dest="~/.gemini-manager",
        search_dir="~/gm/backups",
        from_dir=None,
        from_archive=None,
        dry_run=False,
        force=False,
    )

    with patch("gemini_manager.restore.get_recommendation", return_value=None):
        with pytest.raises(SystemExit):
            perform_restore(args)


def test_restore_auto_local_success(fs, capsys):
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))
    search_dir = os.path.expanduser("~/gm/backups")
    fs.create_dir(search_dir)
    fs.create_file(
        os.path.join(
            search_dir, "2025-01-01_120000-test@example.com.gemini-manager.tar.gz"
        )
    )

    args = argparse.Namespace(
        auto=True,
        cloud=False,
        dest="~/.gemini-manager",
        search_dir="~/gm/backups",
        from_dir=None,
        from_archive=None,
        dry_run=False,
        force=False,
    )

    rec = Recommendation(
        email="test@example.com",
        status=AccountStatus.READY,
        last_used=None,
        next_reset=None,
    )

    with patch("gemini_manager.restore.get_recommendation", return_value=rec):
        with patch("gemini_manager.restore.acquire_lock"), patch(
            "gemini_manager.restore.extract_archive"
        ), patch("gemini_manager.restore.run") as mock_run, patch("os.replace"), patch(
            "gemini_manager.restore.get_active_session", return_value=None
        ):
            mock_run.return_value.returncode = 0
            perform_restore(args)

    capsys.readouterr()
    # assert "Auto-switch recommendation: test@example.com" in captured.out


def test_restore_auto_local_not_found(fs, capsys):
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))
    search_dir = os.path.expanduser("~/gm/backups")
    fs.create_dir(search_dir)

    args = argparse.Namespace(
        auto=True,
        cloud=False,
        dest="~/.gemini-manager",
        search_dir="~/gm/backups",
        from_dir=None,
        from_archive=None,
        dry_run=False,
        force=False,
    )

    rec = Recommendation(
        email="test@example.com",
        status=AccountStatus.READY,
        last_used=None,
        next_reset=None,
    )

    with patch("gemini_manager.restore.get_recommendation", return_value=rec):
        with pytest.raises(SystemExit):
            perform_restore(args)


def test_restore_cloud_auto_success(fs, capsys):
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))

    args = argparse.Namespace(
        auto=True,
        cloud=True,
        dest="~/.gemini-manager",
        search_dir="~/gm/backups",
        from_dir=None,
        from_archive=None,
        dry_run=False,
        force=False,
        b2_id="id",
        b2_key="key",
        bucket="bucket",
    )

    rec = Recommendation(
        email="test@example.com",
        status=AccountStatus.READY,
        last_used=None,
        next_reset=None,
    )

    with patch(
        "gemini_manager.restore.resolve_credentials",
        return_value=("id", "key", "bucket"),
    ):
        with patch("gemini_manager.restore.get_cloud_provider") as MockProvider:
            provider = MockProvider.return_value
            file_version = MagicMock()
            file_version.name = (
                "2025-01-01_120000-test@example.com.gemini-manager.tar.gz"
            )
            provider.list_files.return_value = [file_version]

            with patch("gemini_manager.restore.get_recommendation", return_value=rec):
                with patch("gemini_manager.restore.acquire_lock"), patch(
                    "gemini_manager.restore.extract_archive"
                ), patch("gemini_manager.restore.run") as mock_run, patch(
                    "os.replace"
                ), patch(
                    "gemini_manager.restore.get_active_session", return_value=None
                ), patch("os.remove"):  # Prevent temp file cleanup error
                    mock_run.return_value.returncode = 0
                    perform_restore(args)


def test_restore_cloud_auto_not_found(fs, capsys):
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))

    args = argparse.Namespace(
        auto=True,
        cloud=True,
        dest="~/.gemini-manager",
        search_dir="~/gm/backups",
        from_dir=None,
        from_archive=None,
        dry_run=False,
        force=False,
    )

    rec = Recommendation(
        email="test@example.com",
        status=AccountStatus.READY,
        last_used=None,
        next_reset=None,
    )

    with patch(
        "gemini_manager.restore.resolve_credentials",
        return_value=("id", "key", "bucket"),
    ):
        with patch("gemini_manager.restore.get_cloud_provider") as MockProvider:
            provider = MockProvider.return_value
            file_version = MagicMock()
            file_version.name = (
                "2025-01-01_120000-other@example.com.gemini-manager.tar.gz"
            )
            provider.list_files.return_value = [file_version]

            with patch("gemini_manager.restore.get_recommendation", return_value=rec):
                with pytest.raises(SystemExit):
                    perform_restore(args)


def test_restore_from_archive_search_fallback(fs, capsys):
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))
    search_dir = os.path.expanduser("~/gm/backups")
    fs.create_dir(search_dir)
    fs.create_file(os.path.join(search_dir, "mybackup.tar.gz"))

    args = argparse.Namespace(
        from_archive="mybackup.tar.gz",
        search_dir="~/gm/backups",
        dest="~/.gemini-manager",
        cloud=False,
        auto=False,
        from_dir=None,
        dry_run=False,
        force=False,
    )

    with patch("gemini_manager.restore.acquire_lock"), patch(
        "gemini_manager.restore.extract_archive"
    ), patch("gemini_manager.restore.run") as mock_run, patch("os.replace"), patch(
        "gemini_manager.restore.get_active_session", return_value=None
    ):
        mock_run.return_value.returncode = 0
        perform_restore(args)


def test_restore_from_archive_not_found_cli(fs, capsys):
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))

    args = argparse.Namespace(
        from_archive="nonexistent.tar.gz",
        search_dir="~/gm/backups",
        dest="~/.gemini-manager",
        cloud=False,
        auto=False,
        from_dir=None,
        dry_run=False,
        force=False,
    )

    with pytest.raises(SystemExit):
        perform_restore(args)


def test_restore_cloud_specific_success_cli(fs, capsys):
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))
    valid_name = "2025-01-01_120000-specific.gemini-manager.tar.gz"
    args = argparse.Namespace(
        cloud=True,
        from_archive=valid_name,
        auto=False,
        dest="~/.gemini-manager",
        search_dir="~/gm/backups",
        from_dir=None,
        dry_run=False,
        force=False,
        b2_id="id",
        b2_key="key",
        bucket="bucket",
    )

    with patch(
        "gemini_manager.restore.resolve_credentials",
        return_value=("id", "key", "bucket"),
    ):
        with patch("gemini_manager.restore.get_cloud_provider") as MockProvider:
            provider = MockProvider.return_value
            fv = MagicMock()
            fv.name = valid_name
            provider.list_files.return_value = [fv]

            with patch("gemini_manager.restore.acquire_lock"), patch(
                "gemini_manager.restore.extract_archive"
            ), patch("gemini_manager.restore.run") as mock_run, patch(
                "os.replace"
            ), patch(
                "gemini_manager.restore.get_active_session", return_value=None
            ), patch("os.remove"):
                mock_run.return_value.returncode = 0
                perform_restore(args)


def test_restore_cloud_specific_fail_cli(fs, capsys):
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))
    args = argparse.Namespace(
        cloud=True,
        from_archive="missing.gemini-manager.tar.gz",
        auto=False,
        dest="~/.gemini-manager",
        search_dir="~/gm/backups",
        from_dir=None,
        dry_run=False,
        force=False,
        b2_id="id",
        b2_key="key",
        bucket="bucket",
    )

    with patch(
        "gemini_manager.restore.resolve_credentials",
        return_value=("id", "key", "bucket"),
    ):
        with patch("gemini_manager.restore.get_cloud_provider") as MockProvider:
            provider = MockProvider.return_value
            fv = MagicMock()
            fv.name = "2025-01-01_120000-existing.gemini-manager.tar.gz"
            provider.list_files.return_value = [fv]

            with pytest.raises(SystemExit):
                perform_restore(args)


def test_restore_auto_cooldown_outgoing(fs, capsys):
    fs.create_dir(os.path.expanduser("~/.gemini-manager"))
    search_dir = os.path.expanduser("~/gm/backups")
    fs.create_dir(search_dir)
    fs.create_file(
        os.path.join(
            search_dir, "2025-01-01_120000-test@example.com.gemini-manager.tar.gz"
        )
    )

    args = argparse.Namespace(
        cloud=False,
        auto=False,
        dest="~/.gemini-manager",
        search_dir="~/gm/backups",
        from_dir=None,
        from_archive="2025-01-01_120000-test@example.com.gemini-manager.tar.gz",
        dry_run=False,
        force=False,
    )

    with patch(
        "gemini_manager.restore.get_active_session",
        side_effect=["old@test.com", "new@test.com"],
    ):
        # Patch resolve_credentials to prevent exit if called (it shouldn't be for local)
        with patch("gemini_manager.restore.acquire_lock"), patch(
            "gemini_manager.restore.extract_archive"
        ), patch("gemini_manager.restore.run") as mock_run, patch(
            "gemini_manager.restore.add_24h_cooldown_for_email"
        ) as mock_cooldown, patch(
            "gemini_manager.restore.record_switch"
        ) as mock_switch, patch("os.replace"):
            mock_run.return_value.returncode = 0
            perform_restore(args)

            mock_cooldown.assert_called_once()
            mock_switch.assert_any_call("old@test.com", args=args)
            mock_switch.assert_any_call("new@test.com", args=args)
