#!/usr/bin/env python3
# src/gemini_manager/settings.py


import json
import os
from typing import Dict, Any, Optional

CONFIG_FILE = os.path.expanduser("~/.gemini-manager/config.json")

def load_settings() -> Dict[str, Any]:
    """Load settings from the JSON config file."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_settings(settings: Dict[str, Any]):
    """Save settings to the JSON config file."""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(settings, f, indent=2)

def set_setting(key: str, value: Any):
    """Set a specific setting key."""
    s = load_settings()
    s[key] = value
    save_settings(s)

def get_setting(key: str, default: Any = None) -> Any:
    """Get a specific setting key."""
    s = load_settings()
    return s.get(key, default)

def remove_setting(key: str) -> bool:
    """Remove a setting key. Returns True if removed."""
    s = load_settings()
    if key in s:
        del s[key]
        save_settings(s)
        return True
    return False

def list_settings() -> Dict[str, Any]:
    """Return all settings."""
    return load_settings()
