#!/usr/bin/env python3
# src/gemini_manager/config.py


import os
import re

# 🔥 NEON COLOR THEME (Bright & Glowing)
NEON_GREEN   = "\033[92;1m"
NEON_CYAN    = "\033[96;1m"
NEON_YELLOW  = "\033[93;1m"
NEON_MAGENTA = "\033[95;1m"
NEON_RED     = "\033[91;1m"
RESET        = "\033[0m"

# Dynamic Paths
GEMINI_CLI_HOME = os.path.join(os.path.expanduser("~"), ".gemini-manager")

# Sub-directories and Files
DEFAULT_BACKUP_DIR = os.path.join(GEMINI_CLI_HOME, "backups")
ACCOUNTS_DIR = os.path.join(GEMINI_CLI_HOME, "accounts")
CHAT_HISTORY_BACKUP_PATH = os.path.join(GEMINI_CLI_HOME, "chat_backups")
# Move old_configs INSIDE to keep home directory clean, but separate from active data
OLD_CONFIGS_DIR = os.path.join(GEMINI_CLI_HOME, "old_configs")

# Data files
REGISTRY_FILE = os.path.join(GEMINI_CLI_HOME, "registry.json")
COOLDOWN_FILE = os.path.join(GEMINI_CLI_HOME, "cooldown.json")
RESETS_FILE = os.path.join(GEMINI_CLI_HOME, "resets.json")
HISTORY_FILE = os.path.join(GEMINI_CLI_HOME, "history.json")


# Original Gemini directory, for backup/restore source. 
# This should remain ~/.gemini as that is where the target application stores its data.
DEFAULT_GEMINI_HOME = os.path.join(os.path.expanduser("~"), ".gemini")

# Ensure base directories exist
for _dir in [GEMINI_CLI_HOME, DEFAULT_BACKUP_DIR, ACCOUNTS_DIR, CHAT_HISTORY_BACKUP_PATH, OLD_CONFIGS_DIR]:
    os.makedirs(_dir, exist_ok=True)

LOGIN_URL_PATH = "/sdcard/tools/login_url.txt"
# Backup naming and matching patterns
# Archives: YYYY-MM-DD_HHMMSS-<email>.gemini-manager.tar.gz[.gpg]
ARCHIVE_REGEX = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{6})-.+\.gemini-manager\.tar\.gz(\.gpg)?$")
# Snapshots: YYYY-MM-DD_HHMMSS-<email>.gemini-manager.snapshot.json
SNAPSHOT_REGEX = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{6})-.+\.gemini-manager\.snapshot\.json$")

# Legacy/Directory match (for pruning old formats)
TIMESTAMPED_DIR_REGEX = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{6})-.+\.gemini-manager$")
