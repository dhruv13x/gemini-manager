import json
import os
import datetime
import pytest
from unittest.mock import MagicMock, patch
from gemini_manager import cooldown
from gemini_manager.cooldown import (
    _sync_cooldown_file,
    get_cooldown_data,
    record_switch,
    do_cooldown_list,
    do_remove_account,
    do_reset_all,
)
from rich.console import Console

# Constants for testing
TEST_EMAIL = "test@example.com"
TEST_TIMESTAMP = "2023-10-27T10:00:00+00:00"
MOCK_HOME = "/home/testuser"
MOCK_COOLDOWN_PATH = os.path.join(MOCK_HOME, "gm", "data", "cooldown.json")


@pytest.fixture
def mock_args():
    args = MagicMock()
    args.cloud = True
    return args


@pytest.fixture
def mock_b2_manager(mocker):
    return mocker.patch("gemini_manager.cooldown.B2Manager")


@pytest.fixture
def mock_resolve_credentials(mocker):
    return mocker.patch("gemini_manager.cooldown.resolve_credentials")


@pytest.fixture
def mock_cprint(mocker):
    return mocker.patch("gemini_manager.cooldown.cprint")


@pytest.fixture
def mock_console(mocker):
    return mocker.patch("gemini_manager.cooldown.console")


@pytest.fixture
def mock_fs(fs):
    """
    Using pyfakefs to mock the file system.
    """
    fs.create_dir(MOCK_HOME)
    # Ensure directory structure exists for MOCK_COOLDOWN_PATH
    if not os.path.exists(os.path.dirname(MOCK_COOLDOWN_PATH)):
        fs.create_dir(os.path.dirname(MOCK_COOLDOWN_PATH))
    return fs


@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    # Patch the COOLDOWN_FILE in the module to point to our mock path
    monkeypatch.setattr("gemini_manager.cooldown.COOLDOWN_FILE", MOCK_COOLDOWN_PATH)


def test_sync_cooldown_file_no_creds(mock_resolve_credentials, mock_cprint, mock_args):
    mock_resolve_credentials.return_value = (None, None, None)
    _sync_cooldown_file("upload", mock_args)
    mock_cprint.assert_any_call(
        cooldown.NEON_YELLOW,
        "Warning: Cloud credentials not fully configured. Skipping cloud sync.",
    )


def test_sync_cooldown_file_download_success(
    mock_resolve_credentials, mock_b2_manager, mock_cprint, mock_args, fs
):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    b2_instance = mock_b2_manager.return_value
    b2_instance.download_to_string.return_value = "{}"

    _sync_cooldown_file("download", mock_args)

    b2_instance.download_to_string.assert_called_once()
    mock_cprint.assert_any_call(cooldown.NEON_GREEN, "Cooldown file synced from cloud.")


def test_sync_cooldown_file_download_fail_not_found(
    mock_resolve_credentials, mock_b2_manager, mock_cprint, mock_args
):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    b2_instance = mock_b2_manager.return_value
    b2_instance.download_to_string.return_value = None

    _sync_cooldown_file("download", mock_args)

    mock_cprint.assert_any_call(
        cooldown.NEON_YELLOW,
        "No cooldown file found in the cloud. Using local version.",
    )


def test_sync_cooldown_file_download_fail_other(
    mock_resolve_credentials, mock_b2_manager, mock_cprint, mock_args
):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    b2_instance = mock_b2_manager.return_value
    b2_instance.download_to_string.side_effect = Exception("Network error")

    _sync_cooldown_file("download", mock_args)

    args, _ = mock_cprint.call_args_list[-1]
    assert args[0] == cooldown.NEON_RED
    assert "An unexpected error occurred" in args[1]


def test_sync_cooldown_file_upload_no_local_file(
    mock_resolve_credentials, mock_b2_manager, mock_cprint, mock_args, fs
):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    # Ensure file does not exist
    if os.path.exists(MOCK_COOLDOWN_PATH):
        os.remove(MOCK_COOLDOWN_PATH)

    _sync_cooldown_file("upload", mock_args)

    mock_cprint.assert_any_call(
        cooldown.NEON_YELLOW, "Local cooldown file not found. Skipping upload."
    )
    mock_b2_manager.return_value.upload.assert_not_called()


def test_sync_cooldown_file_upload_success(
    mock_resolve_credentials, mock_b2_manager, mock_cprint, mock_args, fs
):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    fs.create_file(MOCK_COOLDOWN_PATH, contents="{}")

    _sync_cooldown_file("upload", mock_args)

    mock_b2_manager.return_value.upload.assert_called_once()
    mock_cprint.assert_any_call(cooldown.NEON_GREEN, "Cooldown file synced to cloud.")


def test_sync_cooldown_file_upload_fail(
    mock_resolve_credentials, mock_b2_manager, mock_cprint, mock_args, fs
):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    fs.create_file(MOCK_COOLDOWN_PATH, contents="{}")
    mock_b2_manager.return_value.upload.side_effect = Exception("Upload fail")

    _sync_cooldown_file("upload", mock_args)

    args, _ = mock_cprint.call_args_list[-1]
    assert args[0] == cooldown.NEON_RED
    assert "Error uploading cooldown file" in args[1]


def test_sync_cooldown_file_unexpected_exception(
    mock_resolve_credentials, mock_cprint, mock_args
):
    mock_resolve_credentials.side_effect = Exception("Unexpected")

    _sync_cooldown_file("upload", mock_args)

    args, _ = mock_cprint.call_args_list[-1]
    assert args[0] == cooldown.NEON_RED
    assert "An unexpected error occurred" in args[1]


def test_get_cooldown_data_no_file(fs):
    if os.path.exists(MOCK_COOLDOWN_PATH):
        os.remove(MOCK_COOLDOWN_PATH)
    assert get_cooldown_data() == {}


def test_get_cooldown_data_valid_file(fs):
    data = {TEST_EMAIL: TEST_TIMESTAMP}
    fs.create_file(MOCK_COOLDOWN_PATH, contents=json.dumps(data))
    assert get_cooldown_data() == data


def test_get_cooldown_data_invalid_json(fs):
    fs.create_file(MOCK_COOLDOWN_PATH, contents="invalid json")
    assert get_cooldown_data() == {}


def test_record_switch_local_only(fs, mocker):
    mock_datetime = mocker.patch("gemini_manager.cooldown.datetime")
    mock_now = mock_datetime.datetime.now.return_value
    mock_astimezone = mock_now.astimezone.return_value
    mock_astimezone.isoformat.return_value = TEST_TIMESTAMP

    mock_datetime.timezone.utc = datetime.timezone.utc

    record_switch(TEST_EMAIL)

    with open(MOCK_COOLDOWN_PATH, "r") as f:
        data = json.load(f)
    assert data[TEST_EMAIL]["last_used"] == TEST_TIMESTAMP
    assert data[TEST_EMAIL]["first_used"] == TEST_TIMESTAMP


def test_record_switch_with_cloud(
    mock_fs, fs, mocker, mock_args, mock_resolve_credentials, mock_b2_manager
):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    mock_datetime = mocker.patch("gemini_manager.cooldown.datetime")
    mock_now = mock_datetime.datetime.now.return_value
    mock_astimezone = mock_now.astimezone.return_value
    mock_astimezone.isoformat.return_value = TEST_TIMESTAMP

    mock_datetime.timezone.utc = datetime.timezone.utc

    mock_b2_manager.return_value.download_to_string.return_value = json.dumps(
        {"other@example.com": "2020-01-01T00:00:00+00:00"}
    )

    record_switch(TEST_EMAIL, args=mock_args)

    mock_b2_manager.return_value.download_to_string.assert_called_once()

    with open(MOCK_COOLDOWN_PATH, "r") as f:
        data = json.load(f)
    assert data[TEST_EMAIL]["last_used"] == TEST_TIMESTAMP
    assert "other@example.com" in data

    mock_b2_manager.return_value.upload.assert_called_once()


def test_record_switch_write_fail(fs, mocker, mock_cprint):
    mock_datetime = mocker.patch("gemini_manager.cooldown.datetime")
    mock_now = mock_datetime.datetime.now.return_value
    mock_astimezone = mock_now.astimezone.return_value
    mock_astimezone.isoformat.return_value = TEST_TIMESTAMP

    mock_datetime.timezone.utc = datetime.timezone.utc

    if os.path.exists(MOCK_COOLDOWN_PATH):
        os.remove(MOCK_COOLDOWN_PATH)

    fs.create_dir(MOCK_COOLDOWN_PATH)

    record_switch(TEST_EMAIL)

    args, _ = mock_cprint.call_args_list[-1]
    assert args[0] == cooldown.NEON_RED
    assert "Error: Could not write" in args[1]


def test_do_cooldown_list_no_data(fs, mock_cprint):
    if os.path.exists(MOCK_COOLDOWN_PATH):
        os.remove(MOCK_COOLDOWN_PATH)

    with patch("gemini_manager.cooldown.get_all_resets", return_value=[]):
        do_cooldown_list()

    mock_cprint.assert_any_call(
        cooldown.NEON_YELLOW, "No account data found (switches or resets)."
    )


def test_do_cooldown_list_with_cloud(
    fs, mock_args, mock_resolve_credentials, mock_b2_manager
):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")

    do_cooldown_list(args=mock_args)

    assert mock_b2_manager.return_value.download_to_string.called


def test_do_remove_account_no_credentials(fs, capsys):
    """Test removing an account when no credentials are provided."""
    cooldown_path = os.path.expanduser(MOCK_COOLDOWN_PATH)

    fs.create_file(
        cooldown_path,
        contents=json.dumps({"test@example.com": "2023-10-27T10:00:00+00:00"}),
    )

    with patch("gemini_manager.cooldown.remove_entry_by_id", return_value=True):
        with patch(
            "gemini_manager.cooldown.resolve_credentials",
            return_value=(None, None, None),
        ):
            do_remove_account("test@example.com", args=None)

    captured = capsys.readouterr()
    assert "Removed reset history" in captured.out
    assert "Removed cooldown state" in captured.out
    assert "Cloud sync complete" not in captured.out


def test_do_remove_account_with_credentials_sync_fail(fs, capsys):
    """Test removing an account with credentials but sync failing."""
    cooldown_path = os.path.expanduser(MOCK_COOLDOWN_PATH)
    fs.create_file(
        cooldown_path,
        contents=json.dumps({"test@example.com": "2023-10-27T10:00:00+00:00"}),
    )

    args = MagicMock()
    args.b2_key_id = "key"
    args.b2_app_key = "app_key"
    args.b2_bucket = "bucket"

    with patch(
        "gemini_manager.cooldown.resolve_credentials",
        return_value=("key", "app_key", "bucket"),
    ):
        with patch(
            "gemini_manager.cooldown._sync_cooldown_file",
            side_effect=Exception("Sync failed"),
        ):
            do_remove_account("test@example.com", args=args)

    captured = capsys.readouterr()
    assert "Syncing removal to cloud..." in captured.out


def test_do_cooldown_list_with_data(fs, capsys):
    """Test do_cooldown_list with various account states."""
    cooldown_path = MOCK_COOLDOWN_PATH

    now = datetime.datetime.now().astimezone()
    recent = (now - datetime.timedelta(hours=1)).isoformat()
    old = (now - datetime.timedelta(hours=25)).isoformat()

    fs.create_file(
        cooldown_path,
        contents=json.dumps(
            {
                "locked@example.com": recent,
                "ready@example.com": old,
                "scheduled@example.com": old,
            }
        ),
    )

    resets = [
        {
            "email": "scheduled@example.com",
            "reset_ist": (now + datetime.timedelta(hours=2)).isoformat(),
            "saved_string": "Access resets at...",
        },
        {
            "email": "ready@example.com",
            "reset_ist": (now - datetime.timedelta(hours=2)).isoformat(),
        },
    ]

    with patch(
        "gemini_manager.cooldown.console", new=Console(width=200, force_terminal=True)
    ):
        with patch("gemini_manager.cooldown.get_all_resets", return_value=resets):
            do_cooldown_list(args=None)

    captured = capsys.readouterr()
    assert "locked@example.com" in captured.out
    assert "COOLDOWN" in captured.out
    assert "scheduled@example.com" in captured.out
    assert "SCHEDULED" in captured.out
    assert "ready@example.com" in captured.out
    assert "READY" in captured.out


def test_do_reset_all_aborted(fs, capsys):
    """Test reset all when user aborts."""
    with patch("rich.prompt.Confirm.ask", return_value=False):
        do_reset_all(args=None)

    captured = capsys.readouterr()
    assert "Aborted" in captured.out


def test_do_reset_all_success_local(fs, capsys):
    """Test successful reset all locally."""
    # Ensure directory exists for file creation - ensure we can create file there
    fs.create_file(MOCK_COOLDOWN_PATH, contents="{}")

    with patch("rich.prompt.Confirm.ask", return_value=True):
        with patch(
            "gemini_manager.cooldown.resolve_credentials",
            return_value=(None, None, None),
        ):
            # Mock reset_helpers
            with patch("gemini_manager.reset_helpers._save_store") as mock_save:
                do_reset_all(args=None)
                mock_save.assert_called_with([])

    captured = capsys.readouterr()
    assert "Local cooldown state wiped" in captured.out
    assert "Local reset history wiped" in captured.out
    assert "System clean" in captured.out


def test_do_reset_all_success_cloud(fs, capsys):
    """Test successful reset all with cloud."""
    args = MagicMock()
    # Create file to avoid local wipe failure noise, though not strictly needed if we don't assert it
    fs.create_file(MOCK_COOLDOWN_PATH, contents="{}")

    with patch("rich.prompt.Confirm.ask", return_value=True):
        with patch(
            "gemini_manager.cooldown.resolve_credentials",
            return_value=("key", "app", "bucket"),
        ):
            with patch("gemini_manager.cooldown.B2Manager") as MockB2:
                with patch("gemini_manager.reset_helpers._save_store"):
                    do_reset_all(args=args)

                MockB2.return_value.upload_string.assert_any_call(
                    "{}", "gm-cooldown.json"
                )
                MockB2.return_value.upload_string.assert_any_call(
                    "[]", "gm-resets.json"
                )

    captured = capsys.readouterr()
    assert "Cloud data wiped successfully" in captured.out


def test_do_reset_all_exceptions(fs, capsys):
    """Test reset all with exceptions during wipe."""
    fs.create_dir(os.path.dirname(MOCK_COOLDOWN_PATH))

    with patch("rich.prompt.Confirm.ask", return_value=True):
        with patch(
            "gemini_manager.cooldown.resolve_credentials",
            return_value=(None, None, None),
        ):
            with patch("builtins.open", side_effect=Exception("Wipe fail")):
                # Mock reset_helpers
                with patch(
                    "gemini_manager.reset_helpers._save_store",
                    side_effect=Exception("Store fail"),
                ):
                    do_reset_all(args=None)

    captured = capsys.readouterr()
    assert "Failed to wipe local cooldowns: Wipe fail" in captured.out
    assert "Failed to wipe local resets: Store fail" in captured.out
