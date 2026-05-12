import os
import json
import datetime
from typing import List, Dict, Any

from .config import HISTORY_FILE

def record_event(email: str, event_type: str = "switch"):
    """
    Appends an event to the history log.
    """
    if not email:
        return

    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "email": email,
        "event": event_type
    }

    events = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                events = json.load(f)
                if not isinstance(events, list):
                    events = []
        except (json.JSONDecodeError, IOError):
            events = []

    events.append(entry)

    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w") as f:
            json.dump(events, f, indent=2)
    except IOError:
        pass

def get_events_last_n_days(n: int) -> List[Dict[str, Any]]:
    """
    Returns events from the last N days.
    """
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, "r") as f:
            events = json.load(f)
            if not isinstance(events, list):
                return []
    except (json.JSONDecodeError, IOError):
        return []

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=n)

    recent = []
    for e in events:
        try:
            ts_str = e.get("timestamp")
            if not ts_str:
                continue
            ts = datetime.datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=datetime.timezone.utc)

            if ts >= cutoff:
                recent.append(e)
        except ValueError:
            continue

    return recent
