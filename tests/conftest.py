import pytest
import os
from unittest.mock import patch, MagicMock

@pytest.fixture(autouse=True)
def mock_gemini_home(fs):
    """
    Automatically mock the file system and essential paths for all tests.
    Using pyfakefs `fs` fixture.
    """
    # Create the fake home directory
    fake_home = "/home/runner"
    os.makedirs(fake_home, exist_ok=True)

    # Define paths
    gemini_cli_home = os.path.join(fake_home, ".gemini-manager")
    default_backup_dir = os.path.join(gemini_cli_home, "backups")
    chat_history_backup_path = os.path.join(gemini_cli_home, "chat_backups")
    old_configs_dir = os.path.join(fake_home, ".gemini-manager-old")
    default_gemini_home = os.path.join(fake_home, ".gemini")

    # Create directories in fake fs
    for d in [gemini_cli_home, default_backup_dir, chat_history_backup_path, old_configs_dir, default_gemini_home]:
        if not os.path.exists(d):
            fs.create_dir(d)

    # Patch the constants in config.py
    with patch("gemini_manager.config.GEMINI_CLI_HOME", gemini_cli_home), \
         patch("gemini_manager.config.DEFAULT_BACKUP_DIR", default_backup_dir), \
         patch("gemini_manager.config.CHAT_HISTORY_BACKUP_PATH", chat_history_backup_path), \
         patch("gemini_manager.config.OLD_CONFIGS_DIR", old_configs_dir), \
         patch("gemini_manager.config.DEFAULT_GEMINI_HOME", default_gemini_home):
        yield

@pytest.fixture
def mock_console(mocker):
    """Mocks the rich console to prevent actual output during tests."""
    mock = mocker.patch("rich.console.Console")
    return mock.return_value
