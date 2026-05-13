# tests/test_backup.py

import pytest
from unittest.mock import patch, MagicMock
import os
import json
from gemini_manager import backup
from gemini_manager.config import DEFAULT_GEMINI_HOME, GEMINI_CLI_HOME

# In tests, os.path.expanduser('~') resolves to actual user home
SRC_DIR = os.path.expanduser("~/.gemini-manager")

# Note: We rely on pyfakefs (fs fixture) which is autouse in conftest.py
# So standard os operations work on the fake filesystem.

@patch("gemini_manager.backup.fcntl")
def test_acquire_lock_success(mock_fcntl, fs):
    fs.create_file('/tmp/gm.lock')
    # Patch backup.LOCKFILE to point to our fake file
    with patch("gemini_manager.backup.LOCKFILE", "/tmp/gm.lock"):
        fd = backup.acquire_lock("/tmp/gm.lock")
        assert fd is not None
        mock_fcntl.flock.assert_called()

@patch("gemini_manager.backup.fcntl")
def test_acquire_lock_fail(mock_fcntl, fs):
    fs.create_file('/tmp/gm.lock')
    mock_fcntl.flock.side_effect = BlockingIOError
    with pytest.raises(SystemExit) as e:
        backup.acquire_lock("/tmp/gm.lock")
    assert e.value.code == 2

def test_run():
    with patch("subprocess.run") as mock_run:
        backup.run("ls")
        mock_run.assert_called_with("ls", shell=True, check=True)

def test_run_capture():
    with patch("subprocess.run") as mock_run:
        backup.run("ls", capture=True)
        # subprocess.run(..., stdout=PIPE, stderr=PIPE)
        # Check call args more loosely or strictly
        kwargs = mock_run.call_args[1]
        assert kwargs.get("stdout") is not None
        assert kwargs.get("stderr") is not None

def test_read_active_email_no_file(fs):
    assert backup.read_active_email("/tmp") is None

def test_read_active_email_valid(fs):
    data = json.dumps({"active": "user@example.com"})
    fs.create_file("/tmp/google_accounts.json", contents=data)
    assert backup.read_active_email("/tmp") == "user@example.com"

def test_read_active_email_invalid_json(fs):
    fs.create_file("/tmp/google_accounts.json", contents="{invalid")
    assert backup.read_active_email("/tmp") is None

def test_read_active_email_no_active_field(fs):
    fs.create_file("/tmp/google_accounts.json", contents="{}")
    assert backup.read_active_email("/tmp") is None

def test_ensure_dir(fs):
    backup.ensure_dir("/tmp/dir")
    assert os.path.exists("/tmp/dir")

def test_make_timestamp():
    assert len(backup.make_timestamp()) > 0

def test_atomic_symlink(fs):
    fs.create_file("target")
    backup.atomic_symlink("target", "link")
    assert os.path.islink("link")
    assert os.readlink("link") == "target"

def test_atomic_symlink_exceptions(fs):
    fs.create_file("target")
    with patch("os.symlink", side_effect=OSError("Symlink fail")):
        with pytest.raises(OSError):
            backup.atomic_symlink("target", "link")

@patch("gemini_manager.backup.acquire_lock")
@patch("gemini_manager.backup.read_active_email", return_value="user@example.com")
@patch("gemini_manager.backup.run")
@patch("os.replace") # Mock os.replace to bypass pyfakefs limitation for symlink rename
def test_main_success(mock_replace, mock_run, mock_email, mock_lock, fs):
    # Setup source directory
    os.makedirs(SRC_DIR, exist_ok=True)
    fs.create_file(os.path.join(SRC_DIR, "file"))

    mock_run.return_value.returncode = 0

    # We also need to patch os.path.lexists because atomic_symlink uses it and mocking os.replace might interfere
    # But wait, the failure was os.replace(tmp_dest, dest).
    # This is backup step 4 (directory backup).
    # tmp_dest is copied via cp -a. We mocked run('cp -a ...').
    # But run is mocked, so the CP command never ran!
    # So tmp_dest DOES NOT EXIST in the fake fs.

    # SOLUTION: We must manually create tmp_dest in the test since we mocked cp.
    # OR unmock 'run' but 'run' calls subprocess which we shouldn't use.
    # So we simulate the effect of 'cp -a' by creating the directory.

    # We need to know the timestamp to predict the tmp name.
    with patch("gemini_manager.backup.make_timestamp", return_value="2025-01-01_120000"):
        # tmp_dest = ... + ".tmp-..."
        # logic: tmp_dest = os.path.join(tmp_parent, f".{os.path.basename(dest)}.tmp-{ts}")
        # We need to create this directory in fs before main calls os.replace.

        # But we don't know the exact paths main will derive easily without duplicating logic.
        # But we can patch shutil.rmtree and os.replace to do nothing, or verify calls.

        # If we patch os.replace, the FileNotFoundError won't happen.
        # And we can verify os.replace was called.

        with patch("sys.argv", ["backup.py"]):
            backup.main()

    assert mock_replace.call_count >= 1 # One for directory move, maybe one for symlink

@patch("gemini_manager.backup.acquire_lock")
@patch("gemini_manager.backup.read_active_email", return_value="user@example.com")
@patch("gemini_manager.backup.run")
def test_main_diff_fail(mock_run, mock_email, mock_lock, fs):
    os.makedirs(SRC_DIR, exist_ok=True)

    with patch("sys.argv", ["backup.py"]):
        mock_run.return_value.returncode = 1
        with pytest.raises(SystemExit) as e:
            backup.main()
        assert e.value.code == 3

@patch("gemini_manager.backup.acquire_lock")
@patch("gemini_manager.backup.read_active_email", return_value="user@example.com")
def test_main_src_not_exist(mock_email, mock_lock, fs):
    # Ensure source does NOT exist by removing it if it was created by fixture
    from gemini_manager.config import DEFAULT_GEMINI_HOME
    if os.path.exists(DEFAULT_GEMINI_HOME):
        fs.remove_object(DEFAULT_GEMINI_HOME)

    with patch("sys.argv", ["backup.py"]):
        with pytest.raises(SystemExit) as e:
            backup.main()
        assert e.value.code == 1

@patch("gemini_manager.backup.acquire_lock")
@patch("gemini_manager.backup.read_active_email", return_value="user@example.com")
@patch("gemini_manager.backup.run")
def test_main_dry_run(mock_run, mock_email, mock_lock, fs):
    os.makedirs(SRC_DIR, exist_ok=True)
    with patch("sys.argv", ["backup.py", "--dry-run"]):
        backup.main()
        mock_run.assert_not_called()

@patch("gemini_manager.backup.acquire_lock")
@patch("gemini_manager.backup.read_active_email", return_value="user@example.com")
@patch("gemini_manager.backup.run")
@patch("gemini_manager.backup.get_cloud_provider")
@patch("os.replace")
def test_main_cloud(mock_replace, mock_get_provider, mock_run, mock_email, mock_lock, fs):
    os.makedirs(SRC_DIR, exist_ok=True)

    with patch("sys.argv", ["backup.py", "--cloud", "--bucket", "b", "--b2-id", "i", "--b2-key", "k"]):
        mock_run.return_value.returncode = 0
        mock_b2 = MagicMock()
        mock_get_provider.return_value = mock_b2

        backup.main()

        mock_get_provider.assert_called()
        mock_b2.upload_file.assert_called()


@patch("gemini_manager.backup.acquire_lock")
@patch("gemini_manager.backup.read_active_email", return_value="user@example.com")
@patch("gemini_manager.backup.run")
@patch("os.replace")
def test_main_creates_metadata_sidecar(mock_replace, mock_run, mock_email, mock_lock, fs):
    source_dir = "/tmp/gemini-src"
    fs.create_dir(source_dir)
    mock_run.return_value.returncode = 0

    with patch("gemini_manager.backup.make_timestamp", return_value="2025-01-01_120000"):
        with patch("sys.argv", ["backup.py", "--src", source_dir]):
            backup.main()

    metadata_path = os.path.expanduser(
        "~/.gemini-manager/backups/2025-01-01_120000-user@example.com.gemini-manager.metadata.json"
    )
    assert os.path.exists(metadata_path)
    data = json.loads(open(metadata_path).read())
    assert data["email"] == "user@example.com"
    assert data["product"] == "gemini"

@patch("gemini_manager.backup.acquire_lock")
@patch("gemini_manager.backup.read_active_email", return_value="user@example.com")
@patch("gemini_manager.backup.run")
@patch("gemini_manager.backup.get_cloud_provider", return_value=None)
@patch("gemini_manager.credentials.get_setting", return_value=None)
@patch("os.replace")
@patch.dict(os.environ, {}, clear=True)
def test_main_cloud_missing_creds(mock_replace, mock_get_setting, mock_get_provider, mock_run, mock_email, mock_lock, fs):
    os.makedirs(SRC_DIR, exist_ok=True)

    with patch("sys.argv", ["backup.py", "--cloud"]):
        mock_run.return_value.returncode = 0
        with pytest.raises(SystemExit) as e:
            backup.main()
        assert e.value.code == 1

@patch("gemini_manager.backup.acquire_lock")
@patch("gemini_manager.backup.read_active_email", return_value=None)
@patch("gemini_manager.backup.run")
@patch("os.replace")
def test_main_no_active_email(mock_replace, mock_run, mock_email, mock_lock, fs):
    os.makedirs(SRC_DIR, exist_ok=True)
    with patch("sys.argv", ["backup.py"]):
        mock_run.return_value.returncode = 0
        backup.main()
        assert mock_run.call_count >= 2

@patch("gemini_manager.backup.acquire_lock")
@patch("gemini_manager.backup.read_active_email", return_value="user@example.com")
@patch("gemini_manager.backup.run")
@patch("gemini_manager.backup.atomic_symlink", side_effect=Exception("Symlink error"))
@patch("os.replace")
def test_main_symlink_fail(mock_replace, mock_symlink, mock_run, mock_email, mock_lock, fs):
    os.makedirs(SRC_DIR, exist_ok=True)
    with patch("sys.argv", ["backup.py"]):
        mock_run.return_value.returncode = 0
        backup.main()
        mock_symlink.assert_called()

@patch("gemini_manager.backup.acquire_lock")
@patch("gemini_manager.backup.read_active_email", return_value="user@example.com")
@patch("gemini_manager.backup.run")
@patch("os.replace")
def test_main_tmp_exists(mock_replace, mock_run, mock_email, mock_lock, fs):
    os.makedirs(SRC_DIR, exist_ok=True)
    mock_run.return_value.returncode = 0
    with patch("sys.argv", ["backup.py"]):
        backup.main()

@patch("gemini_manager.backup.acquire_lock")
@patch("os.replace")
def test_main_lock_exception(mock_replace, mock_lock, fs):
    os.makedirs(SRC_DIR, exist_ok=True)
    mock_fd = MagicMock()
    mock_lock.return_value = mock_fd

    with patch("gemini_manager.backup.read_active_email", return_value="user@example.com"):
        with patch("gemini_manager.backup.run") as mock_run:
             mock_run.return_value.returncode = 0
             with patch("sys.argv", ["backup.py"]):
                 with patch("gemini_manager.backup.fcntl.flock") as mock_flock:
                     mock_flock.side_effect = [None, Exception("Unlock fail")]
                     # Should not crash
                     backup.main()

@patch("gemini_manager.backup.acquire_lock")
@patch("gemini_manager.backup.read_active_email", return_value="user@example.com")
@patch("gemini_manager.backup.run")
def test_main_diff_fail_no_stdout(mock_run, mock_email, mock_lock, fs):
    os.makedirs(SRC_DIR, exist_ok=True)
    with patch("sys.argv", ["backup.py"]):
        mock_run.return_value.returncode = 2
        mock_run.return_value.stdout = ""
        with pytest.raises(SystemExit) as e:
            backup.main()
        assert e.value.code == 3
