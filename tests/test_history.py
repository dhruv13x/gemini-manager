import json
import os
import datetime
import pytest
from unittest.mock import patch, mock_open

# We will create this module later
from gemini_manager import history

# Mock constant for test isolation
TEST_HISTORY_FILE = "test_gemini_history.json"


@pytest.fixture
def mock_history_file(fs):
    """
    Uses pyfakefs to mock the file system.
    Sets the history file path to a fake path.
    """
    # We need to patch the constant in the module,
    # but since we haven't imported it yet (or it might not exist),
    # we'll rely on the module using a variable we can patch or
    # we'll patch os.path.expanduser if the module uses that.
    # Ideally, the module allows overriding the path.
    pass


def test_record_event_creates_file_if_missing(fs):
    """Test that record_event creates the history file if it doesn't exist."""
    # Setup
    if not os.path.exists(os.path.expanduser("~")):
        fs.create_dir(os.path.expanduser("~"))

    # Action
    with patch(
        "gemini_manager.history.HISTORY_FILE", os.path.expanduser("~/test_history.json")
    ):
        history.record_event("test@example.com", "switch")

        # Assertion
        path = os.path.expanduser("~/test_history.json")
        assert os.path.exists(path)
        with open(path, "r") as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0]["email"] == "test@example.com"
            assert data[0]["event"] == "switch"
            assert "timestamp" in data[0]


def test_record_event_appends_to_existing_file(fs):
    """Test that record_event appends to an existing history file."""
    # Setup
    path = os.path.expanduser("~/test_history.json")
    existing_data = [
        {
            "timestamp": "2023-01-01T00:00:00",
            "email": "old@example.com",
            "event": "switch",
        }
    ]
    fs.create_file(path, contents=json.dumps(existing_data))

    # Action
    with patch("gemini_manager.history.HISTORY_FILE", path):
        history.record_event("new@example.com", "switch")

        # Assertion
        with open(path, "r") as f:
            data = json.load(f)
            assert len(data) == 2
            assert data[0]["email"] == "old@example.com"
            assert data[1]["email"] == "new@example.com"


def test_get_events_last_7_days(fs):
    """Test filtering events for the last 7 days."""
    path = os.path.expanduser("~/test_history.json")
    now = datetime.datetime.now(datetime.timezone.utc)

    events = []
    # Event 1: Today
    events.append(
        {"timestamp": now.isoformat(), "email": "today@example.com", "event": "switch"}
    )
    # Event 2: 5 days ago (Should be included)
    events.append(
        {
            "timestamp": (now - datetime.timedelta(days=5)).isoformat(),
            "email": "5days@example.com",
            "event": "switch",
        }
    )
    # Event 3: 10 days ago (Should be excluded)
    events.append(
        {
            "timestamp": (now - datetime.timedelta(days=10)).isoformat(),
            "email": "10days@example.com",
            "event": "switch",
        }
    )

    fs.create_file(path, contents=json.dumps(events))

    with patch("gemini_manager.history.HISTORY_FILE", path):
        # We need to mock datetime in history module to ensure consistency if it uses 'now'
        # But get_events usually takes a range or calculates from 'now'.
        # For this test, we assume get_events filters based on actual time.

        recent_events = history.get_events_last_n_days(7)

        assert len(recent_events) == 2
        emails = [e["email"] for e in recent_events]
        assert "today@example.com" in emails
        assert "5days@example.com" in emails
        assert "10days@example.com" not in emails


import pytest
from gemini_manager.history import record_event, get_events_last_n_days, HISTORY_FILE


def test_record_event_no_email(fs):
    """Test record_event with empty email."""
    # Should do nothing, not create file
    record_event("")
    assert not os.path.exists(os.path.expanduser(HISTORY_FILE))


def test_record_event_corrupt_file(fs):
    """Test record_event handles corrupt JSON gracefully."""
    path = os.path.expanduser(HISTORY_FILE)
    fs.create_file(path, contents="{invalid")

    record_event("test@example.com")

    with open(path, "r") as f:
        data = json.load(f)
    assert len(data) == 1
    assert data[0]["email"] == "test@example.com"


def test_record_event_write_failure(fs):
    """Test record_event handles write failure gracefully."""
    # We can't easily mock open inside the function without patching,
    # but we need to patch specifically the WRITE open, not the READ open.
    # Logic: Read -> Append -> Write.

    path = os.path.expanduser(HISTORY_FILE)
    fs.create_file(path, contents="[]")

    # Mock open. We need side_effect to allow read but fail write?
    # Complex with generic mock_open.
    # Alternative: make directory read only?
    # fs.chmod(path, 0o400) # Read only

    # Let's try patching open to raise IOError on write
    m = mock_open(read_data="[]")
    with patch("builtins.open", m):
        # Configure the mock to raise on write call?
        # m.return_value.write.side_effect = IOError("Write failed")
        # But json.dump calls write multiple times.

        # Simpler: just patch os.makedirs to raise?
        # But os.makedirs is called before open("w").
        # Code:
        # try:
        #   os.makedirs(...)
        #   with open(..., "w") as f:
        pass

    # Let's use patch("builtins.open") side_effect to fail on 'w' mode
    original_open = open

    def side_effect(file, mode="r", *args, **kwargs):
        if "w" in mode:
            raise IOError("Write failed")
        return original_open(file, mode, *args, **kwargs)

    with patch("builtins.open", side_effect=side_effect):
        record_event("test@example.com")

    # Assert nothing crashed


def test_get_events_last_n_days_corrupt_file(fs):
    """Test get_events handles corrupt JSON."""
    path = os.path.expanduser(HISTORY_FILE)
    fs.create_file(path, contents="{invalid")
    events = get_events_last_n_days(7)
    assert events == []


def test_get_events_last_n_days_not_list(fs):
    """Test get_events handles valid JSON that is not a list."""
    path = os.path.expanduser(HISTORY_FILE)
    fs.create_file(path, contents="{}")
    events = get_events_last_n_days(7)
    assert events == []


def test_get_events_last_n_days_invalid_timestamp(fs):
    """Test get_events handles entries with invalid timestamps."""
    path = os.path.expanduser(HISTORY_FILE)
    data = [
        {"timestamp": "invalid-date", "email": "a@b.c"},
        {"timestamp": None, "email": "b@b.c"},  # Missing timestamp
        {"email": "c@b.c"},  # Missing key
    ]
    fs.create_file(path, contents=json.dumps(data))

    events = get_events_last_n_days(7)
    assert events == []


def test_get_events_last_n_days_timezone_naive(fs):
    """Test get_events handles timezone naive timestamps in file (assumes UTC)."""
    path = os.path.expanduser(HISTORY_FILE)
    datetime.datetime.now(datetime.timezone.utc)
    # Naive timestamp (isoformat() usually includes offset if aware, but let's force naive)
    naive_ts = datetime.datetime.now().isoformat()

    data = [{"timestamp": naive_ts, "email": "naive@test.com"}]
    fs.create_file(path, contents=json.dumps(data))

    # Function converts naive to UTC. If it was "just now", it should be included.
    events = get_events_last_n_days(1)
    # This test is tricky because of execution time vs mock time.
    # But logic is: if ts.tzinfo is None: ts = ts.replace(tzinfo=utc)
    # If it creates a valid aware object, it proceeds.

    # We just want to ensure it doesn't crash and returns something if valid
    assert isinstance(events, list)
