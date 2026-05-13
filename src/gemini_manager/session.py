#!/usr/bin/env python3
# src/gemini_manager/session.py


import os
import json
from typing import Optional, Dict
from .ui import cprint
from .config import (
    NEON_CYAN,
    NEON_GREEN,
    NEON_YELLOW,
    NEON_RED,
    RESET,
    DEFAULT_GEMINI_HOME,
)

GOOGLE_ACCOUNTS_PATH = os.path.join(DEFAULT_GEMINI_HOME, "google_accounts.json")


def get_active_session() -> Optional[str]:
    """
    Reads the google_accounts.json file and returns the active email.
    Returns None if file doesn't exist or no active session found.
    """
    # Use the constant defined above which points to ~/.gemini/google_accounts.json
    path = GOOGLE_ACCOUNTS_PATH

    if not os.path.exists(path):
        return None

    try:
        with open(path, "r") as f:
            data: Dict = json.load(f)
            return data.get("active")
    except (json.JSONDecodeError, IOError):
        return None


def do_session():
    """
    Command to show current active session.
    """
    active = get_active_session()

    cprint(NEON_CYAN, "🔍 Checking current Gemini session...")

    if active:
        cprint(NEON_GREEN, f"✅ Active Session: {NEON_YELLOW}{active}{RESET}")
    else:
        cprint(NEON_RED, "❌ No active session found.")
        cprint(
            NEON_YELLOW,
            "   (Try running 'gm --login' or check ~/.gemini/google_accounts.json)",
        )
