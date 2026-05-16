import os
import json
import pytest
from gemini_manager.reset_helpers import _save_store, _load_store, RESETS_FILE
from gemini_manager.history import record_event, HISTORY_FILE

def test_reset_pruning(fs):
    """
    Verify that _save_store keeps only 2 entries per email.
    """
    email = "test@example.com"
    entries = [
        {"id": "1", "email": email, "saved_at": "2026-05-16T10:00:00", "reset_ist": "2026-05-16T10:00:00"},
        {"id": "2", "email": email, "saved_at": "2026-05-16T11:00:00", "reset_ist": "2026-05-16T11:00:00"},
        {"id": "3", "email": email, "saved_at": "2026-05-16T12:00:00", "reset_ist": "2026-05-16T12:00:00"},
    ]
    
    _save_store(entries)
    
    saved = _load_store()
    # Should only have the 2 latest: "3" and "2"
    assert len(saved) == 2
    ids = [e["id"] for e in saved]
    assert "3" in ids
    assert "2" in ids
    assert "1" not in ids

def test_history_capping(fs):
    """
    Verify that record_event caps history at 50 events.
    """
    email = "test@example.com"
    for i in range(60):
        record_event(email, f"event_{i}")
        
    with open(HISTORY_FILE, "r") as f:
        events = json.load(f)
        
    assert len(events) == 50
    # Latest should be event_59
    assert events[-1]["event"] == "event_59"
    # Oldest should be event_10 (because we added 60 events, so we keep 10-59)
    assert events[0]["event"] == "event_10"
