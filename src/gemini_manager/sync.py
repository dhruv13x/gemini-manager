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
from .config import ACCOUNTS_DIR

def get_local_backups(backup_dir):
    """Returns a set of local backup filenames (archives, snapshots, and account states)."""
    backup_dir = os.path.abspath(os.path.expanduser(backup_dir))
    accounts_dir = os.path.abspath(os.path.expanduser(ACCOUNTS_DIR))

    all_files = set()

    # 1. Archives and Snapshots (Backup Dir)
    if os.path.isdir(backup_dir):
        for f in os.listdir(backup_dir):
            if os.path.isfile(os.path.join(backup_dir, f)) and (
                f.endswith(".gemini-manager.tar.gz") or 
                f.endswith(".gemini-manager.tar.gz.gpg") or
                f.endswith(".snapshot.json") or
                f.endswith(".metadata.json") # Legacy support
            ):
                all_files.add(f)

    # 2. Account States (Accounts Dir)
    if os.path.isdir(accounts_dir):
        for f in os.listdir(accounts_dir):
            if os.path.isfile(os.path.join(accounts_dir, f)) and f.endswith(".state.json"):
                # We prefix with 'accounts/' for cloud mapping
                all_files.add(f"accounts/{f}")

    return all_files

def get_cloud_backups(provider):
    """Returns a set of cloud backup filenames (archives, snapshots, and account states)."""
    cloud_files = set()
    try:
        files = provider.list_files()
        for f in files:
            name = getattr(f, "name", "")
            if (name.endswith(".gemini-manager.tar.gz") or 
                name.endswith(".gemini-manager.tar.gz.gpg") or
                name.endswith(".snapshot.json") or
                name.endswith(".state.json") or
                name.endswith(".metadata.json")):
                cloud_files.add(name)
    except Exception as e:
        cprint(NEON_RED, f"[ERROR] Failed to list cloud backups: {e}")
        sys.exit(1)
    return cloud_files

def perform_sync(direction: str, args):
    """
    Unified sync logic.
    direction: "push" (Local -> Cloud) or "pull" (Cloud -> Local)
    """
    provider = get_cloud_provider(args)
    if not provider:
        sys.exit(1)

    bucket_name = getattr(provider, "bucket_name", "Cloud")

    backup_dir = os.path.abspath(os.path.expanduser(args.backup_dir))
    accounts_dir = os.path.abspath(os.path.expanduser(ACCOUNTS_DIR))

    # Ensure dirs exist if pulling
    if direction == "pull":
        os.makedirs(backup_dir, exist_ok=True)
        os.makedirs(accounts_dir, exist_ok=True)

    # For push, ensure backup dir exists (accounts dir is optional but likely exists)
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

        cprint(NEON_YELLOW, f"Found {len(missing)} files missing in cloud. Uploading...")

        for filename in sorted(missing):
            if filename.startswith("accounts/"):
                local_path = os.path.join(accounts_dir, os.path.basename(filename))
            else:
                local_path = os.path.join(backup_dir, filename)
            
            # Simple standard upload (No custom headers needed anymore)
            provider.upload_file(local_path, filename)

        # After pushing authoritative files, sync the Registry
        try:
            from .registry import sync_registry_with_cloud
            sync_registry_with_cloud(provider, direction="push")
        except Exception:
            pass

    elif direction == "pull":
        missing = cloud_files - local_files
        if not missing:
            cprint(NEON_GREEN, "Local storage is already up-to-date with cloud backups.")
            return

        cprint(NEON_YELLOW, f"Found {len(missing)} files missing locally. Downloading...")
        for filename in sorted(missing):
            if filename.startswith("accounts/"):
                local_path = os.path.join(accounts_dir, os.path.basename(filename))
            else:
                local_path = os.path.join(backup_dir, filename)

            # Ensure parent dir exists for pulling
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            provider.download_file(filename, local_path)

    cprint(NEON_GREEN, "Sync Completed Successfully!")