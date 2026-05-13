#!/usr/bin/env python3
# src/gemini_manager/list_backups.py

"""
list_backups.py

Lists all available backups from the backup directory.
"""

import os
import sys
import argparse
from .ui import cprint, NEON_CYAN, NEON_YELLOW, NEON_RED
from .b2 import B2Manager
from .config import DEFAULT_BACKUP_DIR, OLD_CONFIGS_DIR
from .credentials import resolve_credentials


def perform_list_backups(args: argparse.Namespace):
    if hasattr(args, "cloud") and args.cloud:
        key_id, app_key, bucket_name = resolve_credentials(args)

        b2 = B2Manager(key_id, app_key, bucket_name)
        cprint(NEON_CYAN, f"Available backups in B2 bucket: {bucket_name}:")
        try:
            found_backups = False
            for file_version, _ in b2.list_backups():
                if file_version.file_name.endswith(".gemini-manager.tar.gz"):
                    cprint(NEON_CYAN, f"  {file_version.file_name}")
                    found_backups = True
            if not found_backups:
                cprint(NEON_YELLOW, "No backups found in B2 bucket.")
        except Exception as e:
            cprint(NEON_RED, f"[CLOUD] Failed to list backups from B2: {e}")
            sys.exit(1)

    else:  # List local backups
        # --- List Archive Backups ---
        archive_dir = os.path.expanduser(args.search_dir or DEFAULT_BACKUP_DIR)
        if not os.path.isdir(archive_dir):
            cprint(NEON_YELLOW, f"Archive backup directory not found: {archive_dir}")
        else:
            try:
                archives = [
                    f
                    for f in os.listdir(archive_dir)
                    if os.path.isfile(os.path.join(archive_dir, f))
                    and f.endswith(".gemini-manager.tar.gz")
                ]
                if not archives:
                    cprint(
                        NEON_YELLOW,
                        f"No archive backups (*.tar.gz) found in {archive_dir}",
                    )
                else:
                    cprint(NEON_CYAN, f"Available archive backups in {archive_dir}:")
                    for backup in sorted(archives):
                        print(f"  {backup}")
            except OSError as e:
                cprint(NEON_RED, f"Error reading archive backup directory: {e}")

        print()  # Add a space between sections

        # --- List Directory Backups ---
        dir_backup_path = os.path.expanduser(OLD_CONFIGS_DIR)
        if not os.path.isdir(dir_backup_path):
            cprint(NEON_YELLOW, f"Directory backup path not found: {dir_backup_path}")
        else:
            try:
                dir_backups = [
                    d
                    for d in os.listdir(dir_backup_path)
                    if os.path.isdir(os.path.join(dir_backup_path, d)) and ".gm" in d
                ]
                if not dir_backups:
                    cprint(
                        NEON_YELLOW, f"No directory backups found in {dir_backup_path}"
                    )
                else:
                    cprint(
                        NEON_CYAN, f"Available directory backups in {dir_backup_path}:"
                    )
                    for backup in sorted(dir_backups):
                        print(f"  {backup}")
            except OSError as e:
                cprint(NEON_RED, f"Error reading directory backup path: {e}")


def main():
    parser = argparse.ArgumentParser(description="List available Gemini backups.")
    parser.add_argument(
        "--search-dir",
        default=DEFAULT_BACKUP_DIR,
        help=f"Directory to search for archive backups (default {DEFAULT_BACKUP_DIR})",
    )
    parser.add_argument(
        "--cloud", action="store_true", help="List backups from Cloud (B2)"
    )
    parser.add_argument("--bucket", help="B2 Bucket Name")
    parser.add_argument("--b2-id", help="B2 Key ID (or set env GEMINI_B2_KEY_ID)")
    parser.add_argument("--b2-key", help="B2 App Key (or set env GEMINI_B2_APP_KEY)")
    args = parser.parse_args()

    perform_list_backups(args)


if __name__ == "__main__":
    main()
