
import pytest
from unittest.mock import MagicMock, patch
from rich.prompt import Prompt
from gemini_manager.wizard import run_wizard
from gemini_manager.config import NEON_CYAN, NEON_GREEN, NEON_YELLOW, DEFAULT_BACKUP_DIR

@pytest.fixture
def mock_set_setting(mocker):
    """Mocks the set_setting function used by the wizard."""
    return mocker.patch("gemini_manager.wizard.set_setting")

@pytest.fixture
def mock_prompt_ask(mocker):
    """Mocks rich.prompt.Prompt.ask to control user input."""
    return mocker.patch("rich.prompt.Prompt.ask")

@pytest.fixture
def mock_cprint(mocker):
    """Mocks the cprint function used by the wizard."""
    return mocker.patch("gemini_manager.wizard.cprint")

def test_run_wizard_success(mock_prompt_ask, mock_set_setting, mock_cprint):
    """
    Test a successful run of the wizard with all inputs provided.
    """
    mock_prompt_ask.side_effect = [
        "mock_b2_id",
        "mock_b2_key",
        "mock_b2_bucket",
        "/custom/backup/dir"
    ]

    run_wizard()

    # Verify calls to Prompt.ask
    assert mock_prompt_ask.call_count == 4
    mock_prompt_ask.assert_any_call(f"[{NEON_YELLOW}]Enter B2 Key ID[/{NEON_YELLOW}]")
    mock_prompt_ask.assert_any_call(f"[{NEON_YELLOW}]Enter B2 App Key[/{NEON_YELLOW}]")
    mock_prompt_ask.assert_any_call(f"[{NEON_YELLOW}]Enter B2 Bucket Name[/{NEON_YELLOW}]")
    mock_prompt_ask.assert_any_call(f"[{NEON_YELLOW}]Enter Local Backup Directory (default: {DEFAULT_BACKUP_DIR})[/{NEON_YELLOW}]", default=DEFAULT_BACKUP_DIR)

    # Verify calls to set_setting
    assert mock_set_setting.call_count == 4 # Now 4 calls expected
    mock_set_setting.assert_any_call("GEMINI_B2_KEY_ID", "mock_b2_id")
    mock_set_setting.assert_any_call("GEMINI_B2_APP_KEY", "mock_b2_key")
    mock_set_setting.assert_any_call("GEMINI_B2_BUCKET", "mock_b2_bucket")
    mock_set_setting.assert_any_call("GEMINI_BACKUP_DIR", "/custom/backup/dir") # Added assertion

    # Verify console output
    mock_cprint.assert_any_call(NEON_CYAN, "Welcome to the Gemini CLI Configuration Wizard!")
    mock_cprint.assert_any_call(NEON_GREEN, "We will set up your Cloud Backups (B2).")
    mock_cprint.assert_any_call(NEON_GREEN, "Configuration saved successfully!")

def test_run_wizard_with_default_backup_dir(mock_prompt_ask, mock_set_setting, mock_cprint):
    """
    Test wizard run where user accepts default backup directory.
    """
    mock_prompt_ask.side_effect = [
        "mock_b2_id_2",
        "mock_b2_key_2",
        "mock_b2_bucket_2",
        DEFAULT_BACKUP_DIR # User accepts default
    ]

    run_wizard()

    # Verify calls to Prompt.ask (check for default value)
    mock_prompt_ask.assert_any_call(f"[{NEON_YELLOW}]Enter Local Backup Directory (default: {DEFAULT_BACKUP_DIR})[/{NEON_YELLOW}]", default=DEFAULT_BACKUP_DIR)

    # Verify calls to set_setting for B2 credentials AND backup_dir
    assert mock_set_setting.call_count == 4 # Now 4 calls expected
    mock_set_setting.assert_any_call("GEMINI_B2_KEY_ID", "mock_b2_id_2")
    mock_set_setting.assert_any_call("GEMINI_B2_APP_KEY", "mock_b2_key_2")
    mock_set_setting.assert_any_call("GEMINI_B2_BUCKET", "mock_b2_bucket_2")
    mock_set_setting.assert_any_call("GEMINI_BACKUP_DIR", DEFAULT_BACKUP_DIR) # Added assertion

def test_run_wizard_no_b2_credentials(mock_prompt_ask, mock_set_setting, mock_cprint):
    """
    Test wizard run where user provides empty B2 credentials.
    set_setting should not be called for empty B2 values, but should be called for backup_dir.
    """
    mock_prompt_ask.side_effect = [
        "",  # Empty B2 Key ID
        "",  # Empty B2 App Key
        "",  # Empty B2 Bucket
        "/custom/backup/dir_empty"
    ]

    run_wizard()

    # Verify calls to Prompt.ask (check for default value for backup dir)
    mock_prompt_ask.assert_any_call(f"[{NEON_YELLOW}]Enter B2 Key ID[/{NEON_YELLOW}]")
    mock_prompt_ask.assert_any_call(f"[{NEON_YELLOW}]Enter B2 App Key[/{NEON_YELLOW}]")
    mock_prompt_ask.assert_any_call(f"[{NEON_YELLOW}]Enter B2 Bucket Name[/{NEON_YELLOW}]")
    mock_prompt_ask.assert_any_call(f"[{NEON_YELLOW}]Enter Local Backup Directory (default: {DEFAULT_BACKUP_DIR})[/{NEON_YELLOW}]", default=DEFAULT_BACKUP_DIR)

    # Verify that set_setting was NOT called for B2 credentials since they were empty
    mock_set_setting.assert_any_call("GEMINI_BACKUP_DIR", "/custom/backup/dir_empty") # Assert only this call
    mock_set_setting.assert_called_once() # Ensure only one call was made
