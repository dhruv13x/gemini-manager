import os
import json
import datetime
import pytest
from unittest.mock import MagicMock, patch

from gemini_manager import cooldown
from gemini_manager.cooldown import (
    get_cooldown_data,
    record_switch,
    do_cooldown_list,
    do_remove_account,
    do_reset_all,
    _sync_cooldown_file,
    sync_cooldown_with_cloud
)

# Constants for testing
TEST_EMAIL = "test@example.com"
TEST_TIMESTAMP = "2023-10-27T10:00:00+00:00"
MOCK_HOME = "/mock/home"
MOCK_COOLDOWN_PATH = os.path.join(MOCK_HOME, ".gemini-manager", "cooldown.json")

@pytest.fixture
def mock_args():
    args = MagicMock()
    args.profile = None
    args.cloud = False
    return args

@pytest.fixture
def mock_cprint(mocker):
    return mocker.patch("gemini_manager.cooldown.cprint")

@pytest.fixture
def mock_resolve_credentials(mocker):
    return mocker.patch("gemini_manager.cooldown.resolve_credentials")

@pytest.fixture
def mock_b2_manager(mocker):
    return mocker.patch("gemini_manager.cooldown.B2Manager")

@pytest.fixture
def mock_datetime(mocker):
    return mocker.patch("gemini_manager.cooldown.datetime")

@pytest.fixture
def mock_fs(fs):
    if not os.path.exists(os.path.dirname(MOCK_COOLDOWN_PATH)):
        fs.create_dir(os.path.dirname(MOCK_COOLDOWN_PATH))
    return fs


@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    # Patch the COOLDOWN_FILE in the module to point to our mock path
    monkeypatch.setattr("gemini_manager.cooldown.COOLDOWN_FILE", MOCK_COOLDOWN_PATH)


def test_sync_cooldown_file_no_creds(mock_resolve_credentials, mock_cprint, mock_args):
    mock_resolve_credentials.return_value = (None, None, None)
    _sync_cooldown_file("download", mock_args)
    # No credentials simply returns silently
    assert mock_cprint.call_count == 0


def test_sync_cooldown_file_download_success(mock_resolve_credentials, mock_b2_manager, mock_cprint, mock_args, fs):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    b2_instance = mock_b2_manager.return_value
    b2_instance.download_to_string.return_value = "{}"

    sync_cooldown_with_cloud(mock_args)

    b2_instance.download_to_string.assert_called_once()
    mock_cprint.assert_any_call(cooldown.NEON_GREEN, "[OK] Cooldowns synced successfully!")


def test_sync_cooldown_file_download_fail_not_found(mock_resolve_credentials, mock_b2_manager, mock_cprint, mock_args):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    b2_instance = mock_b2_manager.return_value
    b2_instance.download_to_string.return_value = None

    sync_cooldown_with_cloud(mock_args)
    # With bi-directional sync, even if cloud is empty, it succeeds (by uploading local if exists)
    mock_cprint.assert_any_call(cooldown.NEON_GREEN, "[OK] Cooldowns synced successfully!")


def test_sync_cooldown_file_download_fail_other(mock_resolve_credentials, mock_b2_manager, mock_cprint, mock_args):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    b2_instance = mock_b2_manager.return_value
    b2_instance.download_to_string.side_effect = Exception("Network error")

    sync_cooldown_with_cloud(mock_args)

    args, _ = mock_cprint.call_args_list[-1]
    assert args[0] == cooldown.NEON_RED
    assert "Unexpected error during cooldown sync" in args[1]


def test_sync_cooldown_file_upload_no_local_file(mock_resolve_credentials, mock_b2_manager, mock_cprint, mock_args, fs):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    # Ensure file does not exist
    if os.path.exists(MOCK_COOLDOWN_PATH):
        os.remove(MOCK_COOLDOWN_PATH)

    _sync_cooldown_file("upload", mock_args)
    # upload direction via _sync_cooldown_file doesn't print if file missing now
    mock_b2_manager.return_value.upload.assert_not_called()


def test_sync_cooldown_file_upload_success(mock_resolve_credentials, mock_b2_manager, mock_cprint, mock_args, fs):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    fs.create_file(MOCK_COOLDOWN_PATH, contents="{}")

    _sync_cooldown_file("upload", mock_args)

    mock_b2_manager.return_value.upload.assert_called_once()


def test_sync_cooldown_file_upload_fail(mock_resolve_credentials, mock_b2_manager, mock_cprint, mock_args, fs):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    fs.create_file(MOCK_COOLDOWN_PATH, contents="{}")
    mock_b2_manager.return_value.upload.side_effect = Exception("Upload fail")

    # In deprecated upload mode, it swallows exceptions silently
    _sync_cooldown_file("upload", mock_args)


def test_sync_cooldown_file_unexpected_exception(mock_resolve_credentials, mock_cprint, mock_args):
    mock_resolve_credentials.side_effect = Exception("Unexpected")

    sync_cooldown_with_cloud(mock_args)

    args, _ = mock_cprint.call_args_list[-1]
    assert args[0] == cooldown.NEON_RED
    assert "Unexpected error during cooldown sync" in args[1]


def test_get_cooldown_data_no_file(fs):
    if os.path.exists(MOCK_COOLDOWN_PATH):
        os.remove(MOCK_COOLDOWN_PATH)
    assert get_cooldown_data() == {}


def test_get_cooldown_data_valid_file(fs):
    data = {TEST_EMAIL: {"first_used": TEST_TIMESTAMP, "last_used": TEST_TIMESTAMP}}
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


def test_record_switch_with_cloud(mock_fs, fs, mocker, mock_args, mock_resolve_credentials, mock_b2_manager):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    mock_datetime = mocker.patch("gemini_manager.cooldown.datetime")
    mock_now = mock_datetime.datetime.now.return_value
    mock_astimezone = mock_now.astimezone.return_value
    mock_astimezone.isoformat.return_value = TEST_TIMESTAMP

    mock_datetime.timezone.utc = datetime.timezone.utc

    mock_b2_manager.return_value.download_to_string.return_value = json.dumps({
        "other@example.com": {"first_used": "2020-01-01T00:00:00+00:00", "last_used": "2020-01-01T00:00:00+00:00"}
    })

    record_switch(TEST_EMAIL, args=mock_args)

    mock_b2_manager.return_value.download_to_string.assert_called()

    with open(MOCK_COOLDOWN_PATH, "r") as f:
        data = json.load(f)
    assert data[TEST_EMAIL]["last_used"] == TEST_TIMESTAMP
    assert "other@example.com" in data

    mock_b2_manager.return_value.upload_string.assert_called()


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


def test_do_cooldown_list_with_cloud(mock_resolve_credentials, mock_b2_manager, mock_cprint, mock_args, fs):
    mock_args.cloud = True
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    mock_b2_manager.return_value.download_to_string.return_value = "{}"

    with patch("gemini_manager.cooldown.get_all_resets", return_value=[]):
        with patch("gemini_manager.cooldown.sync_resets_with_cloud"):
            with patch("gemini_manager.registry.sync_registry_with_cloud"):
                do_cooldown_list(args=mock_args)

    mock_b2_manager.return_value.download_to_string.assert_called()


def test_do_remove_account_no_credentials(mock_resolve_credentials, mock_cprint):
    mock_resolve_credentials.return_value = (None, None, None)
    with patch("gemini_manager.cooldown.remove_entry_by_id", return_value=True):
        do_remove_account(TEST_EMAIL)
    mock_cprint.assert_any_call(cooldown.NEON_GREEN, f"[OK] Removed reset history for {TEST_EMAIL}")


def test_do_remove_account_with_credentials_sync_fail(mock_resolve_credentials, mock_b2_manager, mock_cprint, mock_args):
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    mock_b2_manager.return_value.upload.side_effect = Exception("Cloud sync fail")
    
    with patch("gemini_manager.cooldown.remove_entry_by_id", return_value=True):
        with patch("gemini_manager.cooldown.get_cooldown_data", return_value={TEST_EMAIL: TEST_TIMESTAMP}):
            do_remove_account(TEST_EMAIL, args=mock_args)
    
    # It should still proceed even if cloud sync fails (it just warns/skips silently in some paths)
    mock_cprint.assert_any_call(cooldown.NEON_GREEN, f"[OK] Removed reset history for {TEST_EMAIL}")


def test_do_cooldown_list_with_data(fs, mock_cprint):
    data = {TEST_EMAIL: {"first_used": TEST_TIMESTAMP, "last_used": TEST_TIMESTAMP}}
    fs.create_file(MOCK_COOLDOWN_PATH, contents=json.dumps(data))

    with patch("gemini_manager.cooldown.get_all_resets", return_value=[]):
        do_cooldown_list()


def test_do_reset_all_aborted(mock_cprint):
    with patch("rich.prompt.Confirm.ask", return_value=False):
        do_reset_all(args=None)
    mock_cprint.assert_any_call(cooldown.NEON_YELLOW, "Aborted.")


def test_do_reset_all_success_local(fs, mock_cprint):
    fs.create_dir(os.path.dirname(MOCK_COOLDOWN_PATH))
    fs.create_file(MOCK_COOLDOWN_PATH, contents="{}")

    with patch("rich.prompt.Confirm.ask", return_value=True):
        with patch("gemini_manager.cooldown.resolve_credentials", return_value=(None, None, None)):
            with patch("gemini_manager.reset_helpers._save_store") as mock_save:
                do_reset_all(args=None)
                mock_save.assert_called_once_with([])

    assert get_cooldown_data() == {}


def test_do_reset_all_success_cloud(fs, mock_resolve_credentials, mock_b2_manager, mock_cprint, capsys):
    args = MagicMock()
    mock_resolve_credentials.return_value = ("key", "app", "bucket")
    MockB2 = mock_b2_manager
    fs.create_dir(os.path.dirname(MOCK_COOLDOWN_PATH))

    with patch("rich.prompt.Confirm.ask", return_value=True):
        with patch("gemini_manager.cooldown.resolve_credentials", return_value=("key", "app", "bucket")):
             # Mock reset_helpers
                with patch("gemini_manager.reset_helpers._save_store"):
                    do_reset_all(args=args)

                MockB2.return_value.upload_string.assert_any_call("{}", "gm-cooldown.json")
                MockB2.return_value.upload_string.assert_any_call("[]", "gm-resets.json")

    mock_cprint.assert_any_call(cooldown.NEON_GREEN, "[OK] Cloud data wiped successfully.")


def test_do_reset_all_exceptions(fs, capsys):
    """Test reset all with exceptions during wipe."""
    fs.create_dir(os.path.dirname(MOCK_COOLDOWN_PATH))

    with patch("rich.prompt.Confirm.ask", return_value=True):
        with patch("gemini_manager.cooldown.resolve_credentials", return_value=(None, None, None)):
            with patch("builtins.open", side_effect=Exception("Wipe fail")):
                 # Mock reset_helpers
                with patch("gemini_manager.reset_helpers._save_store", side_effect=Exception("Store fail")):
                    do_reset_all(args=None)

    captured = capsys.readouterr()
    assert "Failed to wipe local cooldowns: Wipe fail" in captured.out
    assert "Failed to wipe local resets: Store fail" in captured.out
