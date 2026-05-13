#!/usr/bin/env python3
# src/gemini_manager/sync.py

"""
sync.py - Synchronize backups between local storage and Cloud (B2).

Features:
- sync push: Upload local backups that are missing in the cloud.
- sync pull: Download cloud backups that are missing locally.
"""

import os
import sys
from .ui import cprint, NEON_GREEN, NEON_CYAN, NEON_YELLOW, NEON_RED, NEON_MAGENTA
from .cloud_factory import get_cloud_provider


def get_local_backups(backup_dir):
    """Returns a set of local backup filenames (only .tar.gz)."""
    if not os.path.isdir(backup_dir):
        # If directory doesn't exist, return empty set or exit?
        # If we are pushing, it's an error. If pulling, we might create it.
        # Let's return empty set and let logic handle it, but warn.
        return set()

    files = {
        f
        for f in os.listdir(backup_dir)
        if os.path.isfile(os.path.join(backup_dir, f))
        and f.endswith(".gemini-manager.tar.gz")
    }
    return files


def get_cloud_backups(provider):
    """Returns a set of cloud backup filenames."""
    cloud_files = set()
    try:
        files = provider.list_files()
        for f in files:
            if f.name.endswith(".gemini-manager.tar.gz"):
                cloud_files.add(f.name)
    except Exception as e:
        cprint(NEON_RED, f"[ERROR] Failed to list cloud backups: {e}")
        sys.exit(1)
    return cloud_files


def perform_sync(direction: str, args):
    """
    Unified sync logic.
    direction: "push" (Local -> Cloud) or "pull" (Cloud -> Local)
    """
    # Attempt to resolve generic cloud provider first
    # But wait, resolve_credentials was B2 specific. We need to adapt it or handle inside get_cloud_provider.
    # Actually, get_cloud_provider handles finding keys.

    provider = get_cloud_provider(args)
    if not provider:
        sys.exit(1)

    # We should know the bucket name for display?
    # provider doesn't expose bucket name in interface, let's just say "Cloud".
    # Or cast and check.
    bucket_name = getattr(provider, "bucket_name", "Cloud")

    backup_dir = os.path.abspath(os.path.expanduser(args.backup_dir))

    # Ensure backup dir exists if pulling
    if direction == "pull" and not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    # For push, if it doesn't exist, it's an error
    if direction == "push" and not os.path.isdir(backup_dir):
        cprint(NEON_RED, f"[ERROR] Local backup directory not found: {backup_dir}")
        sys.exit(1)

    arrow_str = "Local -> Cloud" if direction == "push" else "Cloud -> Local"
    cprint(NEON_MAGENTA, f"Starting Sync ({arrow_str}: {bucket_name})...")

    cprint(NEON_CYAN, "Analyzing differences...")
    local_files = get_local_backups(backup_dir)
    cloud_files = get_cloud_backups(provider)

    if direction == "push":
        missing = local_files - cloud_files
        if not missing:
            cprint(NEON_GREEN, "Cloud is already up-to-date with local backups.")
            return

        cprint(
            NEON_YELLOW, f"Found {len(missing)} files missing in cloud. Uploading..."
        )
        for filename in sorted(missing):
            local_path = os.path.join(backup_dir, filename)
            provider.upload_file(local_path, filename)

    elif direction == "pull":
        missing = cloud_files - local_files
        if not missing:
            cprint(
                NEON_GREEN, "Local storage is already up-to-date with cloud backups."
            )
            return

        cprint(
            NEON_YELLOW, f"Found {len(missing)} files missing locally. Downloading..."
        )
        for filename in sorted(missing):
            local_path = os.path.join(backup_dir, filename)
            provider.download_file(filename, local_path)

    cprint(NEON_GREEN, "Sync Completed Successfully!")
