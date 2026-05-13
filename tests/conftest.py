import pytest
import os
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_gemini_home(fs):
    fake_home = "/home/runner"
    os.makedirs(fake_home, exist_ok=True)

    gemini_cli_home = os.path.join(fake_home, ".gemini-manager")
    default_backup_dir = os.path.join(gemini_cli_home, "backups")
    chat_history_backup_path = os.path.join(gemini_cli_home, "chat_backups")
    old_configs_dir = os.path.join(fake_home, ".gemini-manager-old")
    default_gemini_home = os.path.join(fake_home, ".gemini")

    # DON'T create the directories automatically, let the tests do it if needed!
    # Wait, the failure in backup is because they ARE created but the test creates them again.
    # It's better to let them be created here and tests DONT create them.
    # But tests create SRC_DIR themselves.
    # We will let pyfakefs throw if it exists OR we can just ignore FileExistsError

    for d in [
        gemini_cli_home,
        default_backup_dir,
        chat_history_backup_path,
        old_configs_dir,
        default_gemini_home,
    ]:
        try:
            if not os.path.exists(d):
                fs.create_dir(d)
        except Exception:
            pass

    with patch("gemini_manager.config.GEMINI_CLI_HOME", gemini_cli_home), patch(
        "gemini_manager.config.DEFAULT_BACKUP_DIR", default_backup_dir
    ), patch(
        "gemini_manager.config.CHAT_HISTORY_BACKUP_PATH", chat_history_backup_path
    ), patch("gemini_manager.config.OLD_CONFIGS_DIR", old_configs_dir), patch(
        "gemini_manager.config.DEFAULT_GEMINI_HOME", default_gemini_home
    ):
        yield


@pytest.fixture
def mock_console(mocker):
    mock = mocker.patch("rich.console.Console")
    return mock.return_value
