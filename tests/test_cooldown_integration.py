
import pytest
from unittest.mock import patch, MagicMock
from gemini_manager import cooldown

def test_record_switch_records_history(fs):
    """Verify that record_switch calls history.record_event"""

    # We need to mock os.makedirs and open because record_switch tries to write to disk
    # But since we use pyfakefs (fs fixture), file operations are fine.

    # We mock _sync_cooldown_file to avoid network calls or complex logic
    with patch("gemini_manager.cooldown._sync_cooldown_file"), \
         patch("gemini_manager.history.record_event") as mock_record:

        # We need to ensure COOLDOWN_FILE_PATH is writable in fs
        fs.create_dir("/home/jules") # adjust if needed, or rely on expanduser

        cooldown.record_switch("test@example.com")

        mock_record.assert_called_once_with("test@example.com", "switch")
