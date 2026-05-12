# tests/test_reset_helpers.py

import pytest
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime, timedelta, timezone
import json
import os
import subprocess
from gemini_manager import reset_helpers
from gemini_manager.reset_helpers import (
    run_cmd_safe, _parse_time_from_text, _parse_email_from_text,
    add_reset_entry, save_reset_time_from_output, _compute_next_local_for_time,
    cleanup_expired, do_list_resets, do_next_reset, do_capture_reset,
    remove_entry_by_id, _load_store, _save_store, RESETS_FILE, _normalize_minutes
)

# Using pyfakefs via conftest.py

def test_run_cmd_safe():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "output"
        mock_run.return_value.stderr = ""

        rc, out, err = run_cmd_safe("ls", detect_reset_time=False)
        assert rc == 0
        assert out == "output"

def test_run_cmd_safe_timeout():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 1)):
        rc, out, err = run_cmd_safe("sleep 2", detect_reset_time=False)
        assert rc == 124
        assert "Timeout" in err

def test_run_cmd_safe_exception():
    with patch("subprocess.run", side_effect=Exception("Error")):
        rc, out, err = run_cmd_safe("bad", detect_reset_time=False)
        assert rc == 1
        assert "Error" in err

def test_run_cmd_safe_capture_reset(mocker):
    # Mock save_reset_time_from_output to verify it's called
    mock_save = mocker.patch("gemini_manager.reset_helpers.save_reset_time_from_output")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Access resets at 10:00 AM UTC"
        mock_run.return_value.stderr = ""

        run_cmd_safe("cmd")
        mock_save.assert_called()

def test_run_cmd_safe_timeout_capture(mocker):
    mock_save = mocker.patch("gemini_manager.reset_helpers.save_reset_time_from_output")
    exc = subprocess.TimeoutExpired("cmd", 1)
    exc.output = "Access resets at 10:00 AM UTC"
    with patch("subprocess.run", side_effect=exc):
        run_cmd_safe("cmd")
        mock_save.assert_called()

def test_run_cmd_safe_exception_capture(mocker):
    # Exception string is passed to save_reset
    mock_save = mocker.patch("gemini_manager.reset_helpers.save_reset_time_from_output")
    with patch("subprocess.run", side_effect=Exception("Access resets at 10:00 AM UTC")):
        run_cmd_safe("cmd")
        mock_save.assert_called()

def test_parse_time_from_text():
    assert _parse_time_from_text("at 10:05 AM") == (10, 5, "AM")
    assert _parse_time_from_text("at 10:05 PM") == (10, 5, "PM")
    assert _parse_time_from_text("at 14:30") == (14, 30, None)
    assert _parse_time_from_text("invalid") is None

def test_normalize_minutes():
    assert _normalize_minutes(5) == 5
    assert _normalize_minutes(-1) == 0
    assert _normalize_minutes(60) == 59

def test_parse_email_from_text():
    assert _parse_email_from_text("user@example.com") == "user@example.com"
    assert _parse_email_from_text("no email") is None

def test_compute_next_ist_for_time_am():
    # Mock _now_local
    now = datetime(2023, 1, 1, 9, 0, 0).astimezone()
    with patch("gemini_manager.reset_helpers._now_local", return_value=now):
        # 10 AM same day
        dt = _compute_next_local_for_time(10, 0, "AM")
        assert dt.day == 1
        assert dt.hour == 10

def test_compute_next_ist_for_time_pm():
    now = datetime(2023, 1, 1, 9, 0, 0).astimezone()
    with patch("gemini_manager.reset_helpers._now_local", return_value=now):
        # 1 PM same day (13:00)
        dt = _compute_next_local_for_time(1, 0, "PM")
        assert dt.day == 1
        assert dt.hour == 13

def test_compute_next_ist_for_time_next_day():
    now = datetime(2023, 1, 1, 15, 0, 0).astimezone()
    with patch("gemini_manager.reset_helpers._now_local", return_value=now):
        # 10 AM next day
        dt = _compute_next_local_for_time(10, 0, "AM")
        assert dt.day == 2
        assert dt.hour == 10

def test_load_store_no_file(fs):
    assert _load_store() == []

def test_load_store_invalid_json(fs):
    fs.create_file(RESETS_FILE, contents="{invalid")
    assert _load_store() == []

def test_load_store_valid(fs):
    data = [{"reset_ist": "2023-01-01T10:00:00+00:00", "id": "1", "email": "test"}]
    fs.create_file(RESETS_FILE, contents=json.dumps(data))
    store = _load_store()
    assert len(store) == 1
    assert store[0]["id"] == "1"

def test_save_store_fail(fs):
    # fs is active, but we can patch open to fail
    with patch("builtins.open", side_effect=OSError("Write fail")):
        # Should not crash
        _save_store([{"a":1}])

def test_add_reset_entry_valid(fs):
    with patch("gemini_manager.reset_helpers._now_local", return_value=datetime(2023, 1, 1, 9, 0, 0).astimezone()):
        entry = add_reset_entry("10:00 AM", "test@example.com")
        assert entry["email"] == "test@example.com"
        assert "2023-01-01" in entry["reset_ist"] # Should be today

def test_add_reset_entry_invalid(fs):
    with pytest.raises(ValueError):
        add_reset_entry("invalid")

def test_cleanup_expired(fs):
    now = datetime(2023, 1, 2, 10, 0, 0).astimezone()
    old = (now - timedelta(days=1)).isoformat()
    future = (now + timedelta(days=1)).isoformat()

    data = [
        {"reset_ist": old, "id": "1"},
        {"reset_ist": future, "id": "2"}
    ]
    fs.create_file(RESETS_FILE, contents=json.dumps(data))

    with patch("gemini_manager.reset_helpers._now_local", return_value=now):
        removed = cleanup_expired()
        assert len(removed) == 1
        assert removed[0]["id"] == "1"

    # Check store
    store = _load_store()
    assert len(store) == 1
    assert store[0]["id"] == "2"

def test_save_reset_time_from_output(fs, capsys):
    with patch("gemini_manager.reset_helpers._now_local", return_value=datetime(2023, 1, 1, 9, 0, 0).astimezone()):
        res = save_reset_time_from_output("Access resets at 10:00 AM UTC test@example.com")
        assert res is True

    captured = capsys.readouterr()
    assert "Saved reset for test@example.com" in captured.out

def test_save_reset_time_from_output_fail(fs, capsys):
    res = save_reset_time_from_output("No time here")
    assert res is False
    captured = capsys.readouterr()
    assert "Could not find a valid time" in captured.out

def test_save_reset_time_from_output_ambiguous(fs, capsys):
    # 10:00 without AM/PM is ambiguous if we enforce prompt.
    # Logic: if 1 <= hour <= 12 and no AM/PM, prompt.
    with patch("builtins.input", return_value="AM"):
        with patch("gemini_manager.reset_helpers._now_local", return_value=datetime(2023, 1, 1, 9, 0, 0).astimezone()):
            res = save_reset_time_from_output("Access resets at 10:00 UTC")
            assert res is True

    captured = capsys.readouterr()
    assert "Ambiguous time" in captured.out

def test_do_list_resets_empty(fs, capsys):
    do_list_resets()
    captured = capsys.readouterr()
    assert "No reset schedules saved" in captured.out

def test_do_list_resets(fs, capsys):
    future = (datetime.now().astimezone() + timedelta(hours=1)).isoformat()
    data = [{"reset_ist": future, "id": "1", "email": "test"}]
    fs.create_file(RESETS_FILE, contents=json.dumps(data))

    do_list_resets()
    captured = capsys.readouterr()
    assert "Saved reset entries" in captured.out
    assert "test" in captured.out

def test_do_next_reset_empty(fs, capsys):
    do_next_reset()
    captured = capsys.readouterr()
    assert "No reset schedules saved" in captured.out

def test_do_next_reset(fs, capsys):
    future = (datetime.now().astimezone() + timedelta(minutes=10)).isoformat()
    data = [{"reset_ist": future, "id": "1", "email": "test"}]
    fs.create_file(RESETS_FILE, contents=json.dumps(data))

    do_next_reset()
    captured = capsys.readouterr()
    assert "Next reset for test" in captured.out

def test_do_capture_reset_arg(fs, capsys):
    # Using argument
    with patch("gemini_manager.reset_helpers.save_reset_time_from_output", return_value=True):
        do_capture_reset("Access resets at 10:00 AM")
    captured = capsys.readouterr()
    assert "Reset time saved" in captured.out

def test_do_capture_reset_stdin(fs, capsys):
    # Mock sys.stdin directly on the module where it is used
    with patch("gemini_manager.reset_helpers.sys.stdin") as mock_stdin:
        mock_stdin.isatty.return_value = False
        mock_stdin.read.return_value = "Access resets at 10:00 AM"

        with patch("gemini_manager.reset_helpers.save_reset_time_from_output", return_value=True):
            do_capture_reset()

    captured = capsys.readouterr()
    assert "Reset time saved" in captured.out

def test_do_capture_reset_interactive(fs, capsys):
    # Mock sys.stdin.isatty = True
    with patch("gemini_manager.reset_helpers.sys.stdin") as mock_stdin:
        mock_stdin.isatty.return_value = True

        with patch("builtins.input", return_value="Access resets at 10:00 AM"):
            with patch("gemini_manager.reset_helpers.save_reset_time_from_output", return_value=True):
                do_capture_reset()

    captured = capsys.readouterr()
    assert "Paste the 'Access resets at ... UTC' line" in captured.out

def test_remove_entry_by_id(fs):
    data = [{"reset_ist": "2023-01-01", "id": "123", "email": "test"}]
    fs.create_file(RESETS_FILE, contents=json.dumps(data))

    assert remove_entry_by_id("123") is True
    assert _load_store() == []

def test_remove_entry_by_email(fs):
    data = [{"reset_ist": "2023-01-01", "id": "123", "email": "test@example.com"}]
    fs.create_file(RESETS_FILE, contents=json.dumps(data))

    assert remove_entry_by_id("test@example.com") is True
    assert _load_store() == []

def test_remove_entry_not_found(fs):
    assert remove_entry_by_id("missing") is False

# Added tests for coverage

def test_save_reset_time_from_output_ambiguous_invalid(fs, capsys):
    with patch("builtins.input", return_value="INVALID"):
        res = save_reset_time_from_output("Access resets at 10:00 UTC")
        assert res is False
    captured = capsys.readouterr()
    assert "Invalid AM/PM specified" in captured.out

def test_save_reset_time_from_output_exception(fs, capsys):
    with patch("gemini_manager.reset_helpers.add_reset_entry", side_effect=Exception("Storage error")):
        res = save_reset_time_from_output("Access resets at 10:00 AM UTC")
        assert res is False
    captured = capsys.readouterr()
    assert "Failed to save reset: Storage error" in captured.out

def test_do_capture_reset_success(fs, capsys):
    # Test valid capture with output
    with patch("gemini_manager.reset_helpers.save_reset_time_from_output", return_value=True):
        do_capture_reset("some text")
    captured = capsys.readouterr()
    assert "[OK] Reset time saved" in captured.out

def test_do_next_reset_no_entries(fs, capsys):
    # _load_and_cleanup_store returns []
    with patch("gemini_manager.reset_helpers._load_and_cleanup_store", return_value=[]):
        do_next_reset()
    captured = capsys.readouterr()
    assert "No reset schedules saved" in captured.out

def test_do_next_reset_found(fs, capsys):
    future = (datetime.now().astimezone() + timedelta(hours=1)).isoformat()
    data = [{"reset_ist": future, "id": "1", "email": "test"}]
    with patch("gemini_manager.reset_helpers._load_and_cleanup_store", return_value=data):
        do_next_reset()
    captured = capsys.readouterr()
    assert "Next reset for test" in captured.out

def test_do_next_reset_not_found(fs, capsys):
    future = (datetime.now().astimezone() + timedelta(hours=1)).isoformat()
    data = [{"reset_ist": future, "id": "1", "email": "test"}]
    with patch("gemini_manager.reset_helpers._load_and_cleanup_store", return_value=data):
        do_next_reset("other")
    captured = capsys.readouterr()
    assert "No entries matching 'other'" in captured.out

def test_do_next_reset_expired_now(fs, capsys):
    # Case where reset is <= now but cleanup hasn't happened yet (race condition or just timing)
    # Actually do_next_reset logic handles this: if delta <= 0, expire and return
    past = (datetime.now().astimezone() - timedelta(minutes=1)).isoformat()
    data = [{"reset_ist": past, "id": "1", "email": "test"}]
    with patch("gemini_manager.reset_helpers._load_and_cleanup_store", return_value=data):
        with patch("gemini_manager.reset_helpers.cleanup_expired") as mock_clean:
            do_next_reset()
            mock_clean.assert_called()
    captured = capsys.readouterr()
    assert "Next reset already passed" in captured.out

def test_do_capture_reset_invalid(fs, capsys):
    with patch("gemini_manager.reset_helpers.save_reset_time_from_output", return_value=False):
        do_capture_reset("invalid text")
    captured = capsys.readouterr()
    assert "Could not parse reset time" in captured.out

def test_do_capture_reset_no_input(fs, capsys):
    # Patch sys.stdin.isatty on module
    with patch("gemini_manager.reset_helpers.sys.stdin") as mock_stdin:
        mock_stdin.isatty.return_value = True
        with patch("builtins.input", side_effect=EOFError):
            do_capture_reset()

    captured = capsys.readouterr()
    assert "No input provided" in captured.out

def test_load_and_cleanup_store(fs):
    # Test wrapper
    with patch("gemini_manager.reset_helpers.cleanup_expired", return_value=[]) as mock_clean:
        with patch("gemini_manager.reset_helpers._load_store", return_value=[]) as mock_load:
            reset_helpers._load_and_cleanup_store()
            mock_clean.assert_called()
            mock_load.assert_called()

def test_cleanup_expired_malformed(fs):
    # Test entry with bad date
    data = [{"reset_ist": "invalid-date", "id": "1"}]
    fs.create_file(RESETS_FILE, contents=json.dumps(data))

    # Because _load_store implicitly filters out invalid dates, 'entries' will be empty
    # So cleanup_expired will loop over nothing and return [].
    # But we want to ensure it doesn't crash.

    with patch("gemini_manager.reset_helpers._now_local", return_value=datetime.now().astimezone()):
        removed = cleanup_expired()
        # _load_store filters invalid entries, so removed is empty
        assert len(removed) == 0

    # Check store, it should be empty now if _save_store called with []
    # _load_store -> []
    # loop -> keep=[]
    # _save_store([])
    # So file is effectively cleared of the bad entry (by _save_store).
    store = _load_store()
    assert len(store) == 0

def test_run_cmd_safe_capture_reset_exception(mocker):
    # Exception during save_reset_time_from_output should be swallowed
    mock_save = mocker.patch("gemini_manager.reset_helpers.save_reset_time_from_output", side_effect=Exception("Save fail"))
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        run_cmd_safe("cmd")
        # Should NOT raise
        mock_save.assert_called()

def test_run_cmd_safe_timeout_bytes(mocker):
    # TimeoutExpired with bytes output
    exc = subprocess.TimeoutExpired("cmd", 1)
    exc.output = b"bytes out"
    exc.stderr = b"bytes err"

    with patch("subprocess.run", side_effect=exc):
        rc, out, err = run_cmd_safe("cmd", detect_reset_time=False)
        assert rc == 124
        assert out == "bytes out"
        assert err == "bytes err"

def test_run_cmd_safe_exception_no_detect(mocker):
    with patch("subprocess.run", side_effect=Exception("Err")):
        rc, out, err = run_cmd_safe("cmd", detect_reset_time=False)
        assert rc == 1
        assert err == "Err"

def test_load_and_cleanup_store_removed(fs, capsys):
    with patch("gemini_manager.reset_helpers.cleanup_expired", return_value=["one"]):
        reset_helpers._load_and_cleanup_store()
    captured = capsys.readouterr()
    assert "Removed 1 expired" in captured.out

def test_do_list_resets_future(fs, capsys):
    # Test date parsing/display logic
    future_dt = datetime.now().astimezone() + timedelta(hours=2)
    future = future_dt.isoformat()
    data = [{"reset_ist": future, "id": "1", "email": "test"}]

    # Mock _now_local to fixed time to ensure deterministic diff
    now = datetime(2023, 1, 1, 10, 0, 0).astimezone()
    future_fixed = (now + timedelta(hours=2)).isoformat()
    data = [{"reset_ist": future_fixed, "id": "1", "email": "test"}]

    with patch("gemini_manager.reset_helpers._now_local", return_value=now):
        with patch("gemini_manager.reset_helpers._load_and_cleanup_store", return_value=data):
            do_list_resets()

    captured = capsys.readouterr()
    assert "In 2h 0m" in captured.out

def test_do_next_reset_malformed_entries(fs, capsys):
    data = [{"reset_ist": "bad", "id": "1"}]
    with patch("gemini_manager.reset_helpers._load_and_cleanup_store", return_value=data):
        do_next_reset()
    captured = capsys.readouterr()
    assert "No valid upcoming resets" in captured.out

def test_load_store_skip_invalid_entries(fs):
    # JSON list containing invalid entries
    data = [{"reset_ist": "invalid"}, {"reset_ist": "2023-01-01T10:00:00+00:00"}]
    fs.create_file(RESETS_FILE, contents=json.dumps(data))

    store = _load_store()
    # Should only return the valid one
    assert len(store) == 1
    assert store[0]["reset_ist"] == "2023-01-01T10:00:00+00:00"

def test_load_store_not_list(fs):
    fs.create_file(RESETS_FILE, contents='{"key": "value"}')
    assert _load_store() == []

def test_compute_next_ist_for_time_12_am():
    now = datetime(2023, 1, 1, 10, 0, 0).astimezone() # 10 AM
    with patch("gemini_manager.reset_helpers._now_local", return_value=now):
        # 12 AM same day (midnight at start of day) -> 00:00
        # Since it's < now, should be tomorrow 00:00
        dt = _compute_next_local_for_time(12, 0, "AM")
        assert dt.day == 2
        assert dt.hour == 0

def test_compute_next_ist_for_time_12_pm():
    now = datetime(2023, 1, 1, 10, 0, 0).astimezone()
    with patch("gemini_manager.reset_helpers._now_local", return_value=now):
        # 12 PM same day (noon) -> 12:00
        # > now (10 AM)
        dt = _compute_next_local_for_time(12, 0, "PM")
        assert dt.day == 1
        assert dt.hour == 12

def test_compute_next_ist_for_time_24h():
    now = datetime(2023, 1, 1, 10, 0, 0).astimezone()
    with patch("gemini_manager.reset_helpers._now_local", return_value=now):
        dt = _compute_next_local_for_time(13, 0, None)
        assert dt.day == 1
        assert dt.hour == 13

def test_do_capture_reset_empty_input(fs, capsys):
    # Patch sys.stdin on module
    with patch("gemini_manager.reset_helpers.sys.stdin") as mock_stdin:
        mock_stdin.isatty.return_value = True
        with patch("builtins.input", side_effect=EOFError):
            do_capture_reset()
    captured = capsys.readouterr()
    assert "No input provided" in captured.out

def test_do_list_resets_exception(fs, capsys):
    # Malformed date string in list resets loop
    data = [{"reset_ist": "bad-date", "id": "1", "email": "test"}]
    with patch("gemini_manager.reset_helpers._load_and_cleanup_store", return_value=data):
        do_list_resets()
    captured = capsys.readouterr()
    # It prints raw string if parse fails
    assert "bad-date" in captured.out

def test_add_24h_cooldown_for_email_default(fs, capsys):
    # Tests default behavior when no cooldown data exists (now + 24h)
    with patch("gemini_manager.reset_helpers._save_store") as mock_save:
        reset_helpers.add_24h_cooldown_for_email("test@example.com")
        mock_save.assert_called()
    captured = capsys.readouterr()
    assert "Started 24h cooldown for test@example.com" in captured.out

def test_add_24h_cooldown_for_email_with_first_used(fs, capsys):
    # Tests that reset_dt = first_used + 24h if in future
    from gemini_manager.config import COOLDOWN_FILE
    now = datetime.now().astimezone()
    # first_used 5h ago -> reset should be in 19h
    first_used = now - timedelta(hours=5)
    
    cd_data = {
        "test@example.com": {
            "first_used": first_used.isoformat(),
            "last_used": now.isoformat()
        }
    }
    fs.create_dir(os.path.dirname(COOLDOWN_FILE))
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(cd_data, f)
        
    with patch("gemini_manager.reset_helpers._save_store") as mock_save:
        reset_helpers.add_24h_cooldown_for_email("test@example.com")
        
        args, _ = mock_save.call_args
        saved_entries = args[0]
        entry = next(e for e in saved_entries if e["email"] == "test@example.com")
        
        expected_reset = first_used + timedelta(hours=24)
        actual_reset = datetime.fromisoformat(entry["reset_ist"])
        
        assert abs((actual_reset - expected_reset).total_seconds()) < 2

def test_add_24h_cooldown_for_email_with_stale_first_used(fs, capsys):
    # Tests that reset_dt = now + 24h if first_used + 24h is in past
    from gemini_manager.config import COOLDOWN_FILE
    now = datetime.now().astimezone()
    # first_used 25h ago -> reset was 1h ago (stale)
    first_used = now - timedelta(hours=25)
    
    cd_data = {
        "test@example.com": {
            "first_used": first_used.isoformat(),
            "last_used": now.isoformat()
        }
    }
    fs.create_dir(os.path.dirname(COOLDOWN_FILE))
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(cd_data, f)
        
    with patch("gemini_manager.reset_helpers._save_store") as mock_save:
        reset_helpers.add_24h_cooldown_for_email("test@example.com")
        
        args, _ = mock_save.call_args
        saved_entries = args[0]
        entry = next(e for e in saved_entries if e["email"] == "test@example.com")
        
        # Should fallback to now + 24h
        expected_reset = now + timedelta(hours=24)
        actual_reset = datetime.fromisoformat(entry["reset_ist"])
        
        assert abs((actual_reset - expected_reset).total_seconds()) < 2

def test_merge_resets(fs):
    local = [
        {"email": "a@a.com", "reset_ist": "2023-01-01T10:00:00", "id": "1"},
        {"email": "b@b.com", "reset_ist": "2023-01-01T10:00:00", "id": "2"}
    ]
    remote = [
        {"email": "a@a.com", "reset_ist": "2023-01-02T10:00:00", "id": "3"},
        {"email": "c@c.com", "reset_ist": "2023-01-01T10:00:00", "id": "4"}
    ]

    merged = reset_helpers.merge_resets(local, remote)
    # Now preserves all 4 because IDs are unique
    assert len(merged) == 4

def test_merge_resets_invalid_ts(fs):
    local = [{"email": "a@a.com", "reset_ist": "2023-01-01T10:00:00", "id": "1"}]
    remote = [{"email": "a@a.com", "reset_ist": "invalid", "id": "2"}]

    # Now preserves both because IDs are unique
    merged = reset_helpers.merge_resets(local, remote)
    assert len(merged) == 2

def test_sync_resets_with_cloud(fs, capsys):
    mock_provider = MagicMock()
    mock_provider.download_to_string.return_value = '[]'

    with patch("gemini_manager.reset_helpers._load_store", return_value=[]):
        with patch("gemini_manager.reset_helpers._save_store") as mock_save:
            reset_helpers.sync_resets_with_cloud(mock_provider)
            mock_provider.upload_string.assert_called()

def test_sync_resets_with_cloud_download_corrupt(fs, capsys):
    mock_provider = MagicMock()
    mock_provider.download_to_string.return_value = '{invalid'

    with patch("gemini_manager.reset_helpers._load_store", return_value=[]):
        reset_helpers.sync_resets_with_cloud(mock_provider)

    captured = capsys.readouterr()
    assert "Cloud cooldown file was corrupt" in captured.out

def test_sync_resets_with_cloud_upload_fail(fs, capsys):
    mock_provider = MagicMock()
    mock_provider.download_to_string.return_value = '[]'
    mock_provider.upload_string.side_effect = Exception("Upload fail")

    with patch("gemini_manager.reset_helpers._load_store", return_value=[]):
        reset_helpers.sync_resets_with_cloud(mock_provider)

    captured = capsys.readouterr()
    assert "Failed to upload cooldowns" in captured.out
