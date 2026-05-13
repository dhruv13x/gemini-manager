#!/usr/bin/env python3
# src/gemini_manager/integrity.py

"""
integrity.py - Check integrity of current configuration against the latest backup.
"""
from __future__ import annotations
import argparse
import os
import sys
import time
from typing import Optional, Tuple

from .config import TIMESTAMPED_DIR_REGEX, OLD_CONFIGS_DIR
import subprocess


def run(cmd: str, check: bool = True, capture: bool = False):
    if capture:
        return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return subprocess.run(cmd, shell=True, check=check)

def parse_timestamp_from_name(name: str) -> Optional[time.struct_time]:
    match = TIMESTAMPED_DIR_REGEX.match(name)
    if not match:
        return None
    ts_str = match.group(1)
    try:
        return time.strptime(ts_str, "%Y-%m-%d_%H%M%S")
    except ValueError:
        return None
    
def find_latest_backup(search_dir: str) -> Optional[str]:
    """
    Search search_dir for directories matching timestamp pattern and return
    full path of the latest backup (newest timestamp). If none found, return None.
    """
    candidates: list[Tuple[time.struct_time, str]] = []
    try:
        for entry in os.listdir(search_dir):
            full = os.path.join(search_dir, entry)
            if not os.path.isdir(full):
                continue
            ts = parse_timestamp_from_name(entry)
            if ts:
                candidates.append((ts, full))
    except FileNotFoundError:
        return None

    if not candidates:
        return None

    # sort by timestamp struct_time descending (newest first)
    candidates.sort(key=lambda x: time.mktime(x[0]), reverse=True)
    return candidates[0][1]

def perform_integrity_check(args: argparse.Namespace):
    # Fallback if args missing or None
    if not hasattr(args, 'src') or args.src is None:
        args.src = "~/.gemini-manager"
    
    src = os.path.abspath(os.path.expanduser(args.src))
    
    # This command specifically checks against directory backups, so we hardcode the search path
    search_dir = os.path.abspath(os.path.expanduser(OLD_CONFIGS_DIR))

    if not os.path.exists(src):
        print(f"Source directory does not exist: {src}")
        sys.exit(1)

    latest_backup = find_latest_backup(search_dir)

    if not latest_backup:
        print(f"No directory backups found in {search_dir}")
        sys.exit(1)

    print(f"Found latest backup: {latest_backup}")
    print(f"Comparing {src} with {latest_backup}")

    diff_proc = run(f"diff -r {src} {latest_backup}", check=False, capture=True)

    if diff_proc.returncode == 0:
        print("Integrity check passed: No differences found.")
    else:
        print("Integrity check failed: Differences found.")
        if diff_proc.stdout:
            print(diff_proc.stdout)
        if diff_proc.stderr:
            print(diff_proc.stderr)

def main():
    p = argparse.ArgumentParser(description="Check integrity of current configuration against the latest backup.")
    p.add_argument("--src", default="~/.gemini-manager", help="Source gm dir (default ~/.gemini-manager)")
    # The search directory is now fixed, so we can remove this argument from the standalone runner
    # p.add_argument("--search-dir", default=OLD_CONFIGS_DIR, help="Directory to search for timestamped backups")
    args = p.parse_args()
    perform_integrity_check(args)

if __name__ == "__main__":
    main()
