#!/usr/bin/env python3
# src/gemini_manager/prune.py

import os
import shutil
from .ui import cprint, NEON_GREEN, NEON_RED, NEON_YELLOW, NEON_CYAN
from .config import DEFAULT_GEMINI_HOME

# Workspace items to prune (Matching Codex Manager philosophy)
FILE_GLOBS = [
    "logs.json",
    "history.jsonl",
    "models_cache.json",
]

DIRECTORY_NAMES = [
    "tmp",
    ".tmp",
    "history",
    "cache",
    "log",
    "sessions",
]

def do_prune(args):
    """
    Workspace Pruning: Remove temporary runtime state while preserving identity and configuration.
    This matches the 'cm prune' behavior.
    """
    gemini_home = os.path.abspath(os.path.expanduser(getattr(args, "src", DEFAULT_GEMINI_HOME)))
    dry_run = getattr(args, "dry_run", False)
    
    cprint(NEON_CYAN, f"✂️  Gemini Workspace Pruning Tool")
    cprint(NEON_CYAN, f"Target: {gemini_home}\n")

    if not os.path.exists(gemini_home):
        cprint(NEON_RED, f"Error: Gemini home directory not found: {gemini_home}")
        return

    to_remove_files = []
    to_remove_dirs = []

    # Identify files
    for entry in os.listdir(gemini_home):
        path = os.path.join(gemini_home, entry)
        if os.path.isfile(path):
            for pattern in FILE_GLOBS:
                if entry.startswith(pattern.replace("*", "")):
                    to_remove_files.append(entry)
                    break
        elif os.path.isdir(path):
            if entry in DIRECTORY_NAMES:
                to_remove_dirs.append(entry)

    if not to_remove_files and not to_remove_dirs:
        cprint(NEON_GREEN, "Workspace is already clean.")
        return

    # Files
    for fname in to_remove_files:
        path = os.path.join(gemini_home, fname)
        if dry_run:
            console_print(f"[DRY-RUN] Would delete file: {fname}")
        else:
            try:
                os.remove(path)
                print(f"[DELETED FILE] {fname}")
            except Exception as e:
                cprint(NEON_RED, f"Failed to delete {fname}: {e}")

    # Directories
    for dname in to_remove_dirs:
        path = os.path.join(gemini_home, dname)
        if dry_run:
            print(f"[DRY-RUN] Would delete directory: {dname}")
        else:
            try:
                # Special case: preserve 'bin' inside 'tmp' if needed? 
                # chat.py's cleanup_chat_history preserves 'bin'.
                if dname == "tmp":
                    bin_path = os.path.join(path, "bin")
                    if os.path.exists(bin_path):
                        if dry_run:
                            print(f"[DRY-RUN] Would prune directory: {dname} (preserving bin/)")
                            continue
                        
                        # Use chat.py's logic or similar
                        for item in os.listdir(path):
                            if item == "bin": continue
                            item_path = os.path.join(path, item)
                            if os.path.isdir(item_path): shutil.rmtree(item_path)
                            else: os.remove(item_path)
                        print(f"[PRUNED DIR] {dname} (preserved bin/)")
                        continue
                
                shutil.rmtree(path)
                print(f"[DELETED DIR] {dname}")
            except Exception as e:
                cprint(NEON_RED, f"Failed to delete {dname}: {e}")

    cprint(NEON_GREEN, "\nWorkspace pruning complete.")
    cprint(NEON_YELLOW, "Preserved: google_accounts.json, settings.json, installation_id, oauth_creds.json")

def console_print(msg):
    # Helper to avoid circular import if needed, but ui is usually safe
    from .ui import console
    console.print(msg)
