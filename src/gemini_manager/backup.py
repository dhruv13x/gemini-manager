#!/usr/bin/env python3
# src/gemini_manager/backup.py

"""
backup.py - automatic Gemini CLI backup that names backups with timestamp + email

Example result:
  /root/2025-10-22_042211-bose13x@gmail.com.gm
Archive:
  /root/backups/2025-10-22_042211-bose13x@gmail.com.gemini-manager.tar.gz
Stable "latest" symlink:
  /root/bose13x@gmail.com.gm -> /root/2025-10-22_042211-bose13x@gmail.com.gm

Usage:
  ./backup.py
  ./backup.py --dry-run
  ./backup.py --src ~/.gemini-manager --archive-dir /root/backups --dest-dir-parent /root
"""

from __future__ import annotations
import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Optional
from .config import TIMESTAMPED_DIR_REGEX, DEFAULT_BACKUP_DIR, OLD_CONFIGS_DIR, GEMINI_CLI_HOME, NEON_RED, NEON_YELLOW, NEON_CYAN
from .ui import cprint
from .cloud_factory import get_cloud_provider
from .metadata import create_backup_snapshot, load_latest_status_for_email

LOCKFILE = os.path.join(GEMINI_CLI_HOME, ".backup.lock")

def acquire_lock(path: str = LOCKFILE):
    # Ensure the directory for the lockfile exists
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = open(path, "w+")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Another backup/restore is running. Exiting.")
        sys.exit(2)
    return fd

def run(cmd: str, check: bool = True, capture: bool = False):
    if capture:
        return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return subprocess.run(cmd, shell=True, check=check)

def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)

def read_active_email(gemini_dir: str = None) -> Optional[str]:
    from .config import DEFAULT_GEMINI_HOME
    path = os.path.join(gemini_dir or DEFAULT_GEMINI_HOME, "google_accounts.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        active = data.get("active")
        if not active:
            return None
        active = str(active).strip()
        # Basic sanitization: remove path separators and spaces
        active = active.replace(os.path.sep, "_").replace(" ", "_")
        return active
    except Exception:
        return None

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def make_timestamp() -> str:
    # Format: YYYY-MM-DD_HHMMSS  -> example: 2025-10-22_042211
    return time.strftime("%Y-%m-%d_%H%M%S")

def atomic_symlink(target: str, link_name: str):
    """
    Create an atomic symlink: create tmp symlink and replace existing link atomically.
    """
    tmp = f"{link_name}.tmp-{int(time.time() * 1000)}"
    try:
        if os.path.lexists(tmp):
            try:
                os.unlink(tmp)
            except Exception:
                pass
        os.symlink(target, tmp)
        # os.replace will atomically rename the tmp symlink over the old link_name
        os.replace(tmp, link_name)
    finally:
        if os.path.lexists(tmp):
            try:
                os.unlink(tmp)
            except Exception:
                pass

def perform_backup(args: argparse.Namespace):
    """
    Main backup logic separated from argument parsing.
    Accepts an argparse.Namespace or any object with the required attributes.
    """
    from .config import DEFAULT_GEMINI_HOME
    from .reset_helpers import get_all_resets

    src = os.path.abspath(os.path.expanduser(args.src))
    # If src is the default GEMINI_CLI_HOME (~/.gemini-manager), 
    # we should actually be backing up ~/.gemini (the application data)
    # unless the user explicitly changed --src.
    actual_src = src
    if src == os.path.abspath(os.path.expanduser(GEMINI_CLI_HOME)):
        actual_src = os.path.abspath(os.path.expanduser(DEFAULT_GEMINI_HOME))

    archive_dir = os.path.abspath(os.path.expanduser(args.archive_dir))
    dest_parent = os.path.abspath(os.path.expanduser(args.dest_dir_parent))
    
    active_email = read_active_email(actual_src)
    
    # Try to find a reset time for this email to use as the timestamp
    ts = None
    if active_email:
        resets = get_all_resets()
        my_resets = [r for r in resets if r.get("email") == active_email]
        if my_resets:
            # Sort by reset_ist descending to get the latest captured reset
            my_resets.sort(key=lambda x: x.get("reset_ist"), reverse=True)
            latest_reset = my_resets[0].get("reset_ist")
            if latest_reset:
                from datetime import datetime
                dt = datetime.fromisoformat(latest_reset)
                ts = dt.strftime("%Y-%m-%d_%H%M%S")
                print(f"Using captured reset time for backup naming: {ts}")

    if not ts:
        ts = make_timestamp()

    if not os.path.exists(actual_src):
        print(f"Source does not exist: {actual_src}")
        sys.exit(1)

    if not active_email:
        cprint(NEON_YELLOW, "Warning: Could not read active email from source.")
        cprint(NEON_YELLOW, "Proceeding with 'unknown-session' as the identity.")
        active_email = "unknown-session"

    # Example: 2025-10-22_042211-bose13x@gmail.com.gemini-manager
    dest_basename = f"{ts}-{active_email}.gemini-manager"

    if not TIMESTAMPED_DIR_REGEX.match(dest_basename):
        print(f"Error: Generated backup name '{dest_basename}' does not match the required pattern.")
        sys.exit(1)

    dest = os.path.join(dest_parent, dest_basename)
    archive_path = os.path.join(archive_dir, f"{dest_basename}.tar.gz")
    metadata_path = None
    latest_symlink = os.path.join(dest_parent, f"{active_email}.gm") if active_email else None

    lockfd = acquire_lock()
    try:
        # 1) Create archive (tar gz) of the source
        print(f"[1/4] Creating archive: {archive_path}")
        if not args.dry_run:
            ensure_dir(archive_dir)
            tar_cmd = f"tar -C {shlex_quote(actual_src)} -czf {shlex_quote(archive_path)} ."
            run(tar_cmd)

            # --- ENCRYPTION LOGIC ---
            if hasattr(args, 'encrypt') and args.encrypt:
                print(f"Encrypting archive: {archive_path} -> .gpg")
                passphrase = os.environ.get("GEMINI_BACKUP_PASSWORD")
                if not passphrase:
                    import getpass
                    passphrase = getpass.getpass("Enter passphrase for backup encryption: ")

                if not passphrase:
                    print("Error: Encryption requested but no passphrase provided.")
                    sys.exit(1)

                encrypted_path = f"{archive_path}.gpg"
                # gpg --symmetric --cipher-algo AES256 --passphrase-fd 0 --batch --yes --output <out> <in>
                gpg_cmd = [
                    "gpg", "--symmetric", "--cipher-algo", "AES256",
                    "--passphrase-fd", "0", "--batch", "--yes",
                    "--output", encrypted_path, archive_path
                ]

                try:
                    proc = subprocess.run(gpg_cmd, input=passphrase.encode(), check=False)
                    if proc.returncode != 0:
                        print("Error: GPG encryption failed.")
                        sys.exit(1)

                    # Remove original unencrypted archive and update path
                    os.remove(archive_path)
                    archive_path = encrypted_path
                    print(f"Encrypted archive created at: {archive_path}")

                except FileNotFoundError:
                     print("Error: 'gpg' command not found. Please install GPG or disable encryption.")
                     sys.exit(1)
            # -------------------------

        else:
            print("DRY RUN: would run tar -C ...")
            if hasattr(args, 'encrypt') and args.encrypt:
                print("DRY RUN: would run gpg --symmetric ...")

        # 2) Copy to temporary location (sibling of dest)
        tmp_parent = os.path.dirname(dest) or "/tmp"
        tmp_dest = os.path.join(tmp_parent, f".{os.path.basename(dest)}.tmp-{ts}")
        print(f"[2/4] Copying to temporary location: {tmp_dest}")
        if not args.dry_run:
            if os.path.exists(tmp_dest):
                shutil.rmtree(tmp_dest)
            cp_cmd = f"cp -a {shlex_quote(actual_src)} {shlex_quote(tmp_dest)}"
            run(cp_cmd)
        else:
            print("DRY RUN: would cp -a ...")

        # 3) Verify copy with diff -r
        print("[3/4] Verifying copy with diff -r")
        if not args.dry_run:
            diff_proc = run(f"diff -r {shlex_quote(actual_src)} {shlex_quote(tmp_dest)}", check=False, capture=True)
            if diff_proc.returncode != 0:
                print("Verification FAILED: diff reported differences.")
                if diff_proc.stdout:
                    print(diff_proc.stdout)
                shutil.rmtree(tmp_dest, ignore_errors=True)
                print("Temporary copy removed. Aborting.")
                sys.exit(3)
            else:
                print("Verification OK (no differences).")
        else:
            print("DRY RUN: would run diff -r ...")

        # 4) Move temporary backup into final timestamped destination
        print(f"[4/4] Installing directory backup: {dest}")
        if not args.dry_run:
            ensure_dir(os.path.dirname(dest))
            # tmp_dest is full copy of src; move it to dest (atomic rename)
            try:
                os.replace(tmp_dest, dest)
            except OSError as e:
                # Fallback for cross-device link OR non-empty directory conflict
                # ENOTEMPTY (39) or EEXIST (17) or EBUSY (16)
                if e.errno in [16, 17, 18, 39]:
                    if os.path.exists(dest):
                        if os.path.isdir(dest) and not os.path.islink(dest):
                            shutil.rmtree(dest)
                        else:
                            os.remove(dest)
                    shutil.move(tmp_dest, dest)
                else:
                    raise e
            print("Directory backup created at:", dest)
            print("Archive saved at:", archive_path)
            try:
                latest_status = load_latest_status_for_email(active_email, get_all_resets()) if active_email else None
                metadata_path = create_backup_snapshot(
                    archive_path=archive_path,
                    active_email=active_email,
                    status=latest_status,
                )
                if metadata_path:
                    print("Metadata saved at:", metadata_path)
            except Exception as e:
                print("Warning: failed to create backup metadata:", e)

            # Update stable symlink /root/<email>.gm -> timestamped dir
            if latest_symlink:
                try:
                    print(f"Updating latest symlink: {latest_symlink} -> {dest}")
                    atomic_symlink(dest, latest_symlink)
                except Exception as e:
                    print("Failed to update latest symlink:", e)
            else:
                print("No active email available; skipping latest symlink.")
        else:
            print("DRY RUN: would os.replace(tmp_dest, dest) and update symlink if available")
        
        # --- NEW CODE BLOCK: CLOUD UPLOAD ---
        if args.cloud:
            provider = get_cloud_provider(args)
            if provider:
                # Upload the tar.gz we just created
                provider.upload_file(archive_path, os.path.basename(archive_path))
                if metadata_path and os.path.exists(metadata_path):
                    provider.upload_file(metadata_path, os.path.basename(metadata_path))
            else:
                print("Error: Cloud backup requested but no valid credentials found.")
                sys.exit(1)
        # ------------------------------------

        print("Backup complete.")
    finally:
        try:
            fcntl.flock(lockfd, fcntl.LOCK_UN)
            lockfd.close()
        except Exception:
            pass

# For backwards compatibility with CLI call via sys.modules or direct import
def main():
    p = argparse.ArgumentParser(description="Safe timestamped backup for ~/.gemini-manager (name: YYYY-MM-DD_HHMMSS-email.gm)")
    p.add_argument("--src", default="~/.gemini-manager", help="Source gm dir (default ~/.gemini-manager)")
    p.add_argument("--archive-dir", default=DEFAULT_BACKUP_DIR, help="Directory to store tar.gz archives")
    p.add_argument("--dest-dir-parent", default=OLD_CONFIGS_DIR, help="Parent directory where timestamped backups are stored")
    p.add_argument("--dry-run", action="store_true", help="Do not perform destructive actions")
    p.add_argument("--encrypt", action="store_true", help="Encrypt the backup archive using GPG")
    p.add_argument("--cloud", action="store_true", help="Upload backup to Cloud (B2)")
    p.add_argument("--bucket", help="B2 Bucket Name")
    p.add_argument("--b2-id", help="B2 Key ID (or set env GEMINI_B2_KEY_ID)")
    p.add_argument("--b2-key", help="B2 App Key (or set env GEMINI_B2_APP_KEY)")
    args = p.parse_args()
    perform_backup(args)

if __name__ == "__main__":
    main()
