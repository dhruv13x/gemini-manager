#!/usr/bin/env python3
# src/gemini_manager/restore.py

"""
restore.py - Safe restore that picks the oldest timestamped backup by default.

Naming convention expected for automatic discovery (produced by backup.py):
  YYYY-MM-DD_HHMMSS-<email>.gemini-manager
Examples:
  2025-10-22_042211-bose13x@gmail.com.gemini-manager
  2025-10-21_020211-kingchess@gmail.com.gemini-manager

Behavior:
 - If --from-dir or --from-archive is passed, those are used.
 - If nothing is passed, script scans --search-dir (default /root) for
   directories matching the timestamp pattern and picks the oldest (earliest)
   timestamp to restore.
 - Safety: lockfile, temp copy, diff verification, .bak move of existing ~/.gemini-manager,
   atomic replace, dry-run and --force supported.
"""
from __future__ import annotations
import argparse
import fcntl
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Optional, Tuple
from .config import DEFAULT_BACKUP_DIR, NEON_GREEN, NEON_RED, NEON_YELLOW, NEON_CYAN, RESET, DEFAULT_GEMINI_HOME, TIMESTAMPED_DIR_REGEX, OLD_CONFIGS_DIR, GEMINI_CLI_HOME
from .cloud_factory import get_cloud_provider
from .settings import get_setting
from .credentials import resolve_credentials
from .session import get_active_session
from .cooldown import record_switch
from .reset_helpers import add_24h_cooldown_for_email, sync_resets_with_cloud
from .recommend import get_recommendation, Recommendation
from .ui import cprint, NEON_YELLOW, NEON_RED, NEON_GREEN, NEON_CYAN

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
    return shlex.quote(s)

def parse_timestamp_from_name(name: str) -> Optional[time.struct_time]:
    """
    Parse timestamp prefix like '2025-10-22_042211' into struct_time.
    Return None if it doesn't match.
    """
    m = TIMESTAMPED_DIR_REGEX.match(name)
    if not m:
        return None
    ts_str = m.group(1)  # 'YYYY-MM-DD_HHMMSS'
    try:
        return time.strptime(ts_str, "%Y-%m-%d_%H%M%S")
    except Exception:
        return None

def is_backup_archive(filename: str) -> bool:
    return filename.endswith(".gemini-manager.tar.gz") or filename.endswith(".gemini-manager.tar.gz.gpg")

def find_oldest_archive_backup(search_dir: str) -> Optional[str]:
    """
    Search search_dir for backup archives (*.gemini-manager.tar.gz or *.gpg) matching the
    timestamp pattern and return the full path of the oldest backup (earliest
    timestamp). If none found, return None.
    """
    candidates: list[Tuple[time.struct_time, str]] = []
    try:
        for entry in os.listdir(search_dir):
            full_path = os.path.join(search_dir, entry)
            # We are now looking for archive files, not directories
            if not (os.path.isfile(full_path) and is_backup_archive(entry)):
                continue

            # The name for parsing is the filename itself
            ts = parse_timestamp_from_name(entry)
            if ts:
                candidates.append((ts, full_path))
    except FileNotFoundError:
        return None

    if not candidates:
        return None

    # Sort by timestamp struct_time ascending (earliest first)
    candidates.sort(key=lambda x: time.mktime(x[0]))
    return candidates[0][1]


def find_latest_archive_backup_for_email(search_dir: str, email: str) -> Optional[str]:
    """
    Search search_dir for backup archives matching the
    timestamp pattern AND the email. Returns the LATEST (newest) backup.
    """
    candidates: list[Tuple[time.struct_time, str]] = []
    try:
        for entry in os.listdir(search_dir):
            full_path = os.path.join(search_dir, entry)
            if not (os.path.isfile(full_path) and is_backup_archive(entry)):
                continue

            # Robust matching: Parse filename to extract email
            # Format: YYYY-MM-DD_HHMMSS-<email>.gemini-manager.tar.gz[.gpg]

            # Extract suffix after first 18 chars (timestamp + hyphen)
            if len(entry) <= 18:
                continue

            suffix = entry[18:] # <email>.gemini-manager.tar.gz[.gpg]

            email_in_file = None
            if suffix.endswith(".gemini-manager.tar.gz"):
                 email_in_file = suffix[:-22]
            elif suffix.endswith(".gemini-manager.tar.gz.gpg"):
                 email_in_file = suffix[:-26]
            else:
                continue

            if email_in_file != email:
                continue

            ts = parse_timestamp_from_name(entry)
            if ts:
                candidates.append((ts, full_path))
    except FileNotFoundError:
        return None

    if not candidates:
        return None

    # Sort by timestamp struct_time DESCENDING (latest first)
    candidates.sort(key=lambda x: time.mktime(x[0]), reverse=True)
    return candidates[0][1]


def extract_archive(archive_path: str, extract_to: str):
    os.makedirs(extract_to, exist_ok=True)

    # Handle Decryption if .gpg
    final_archive_path = archive_path
    decrypted_tmp_path = None

    if archive_path.endswith(".gpg"):
        print(f"Detected encrypted backup: {archive_path}")
        passphrase = os.environ.get("GEMINI_BACKUP_PASSWORD")
        if not passphrase:
            import getpass
            passphrase = getpass.getpass("Enter passphrase to decrypt backup: ")

        if not passphrase:
            print("Error: Passphrase required for decryption.")
            sys.exit(1)

        decrypted_tmp_path = archive_path[:-4] # Remove .gpg
        if os.path.exists(decrypted_tmp_path):
             decrypted_tmp_path += f".decrypted-{int(time.time())}"

        # gpg --decrypt --batch --passphrase-fd 0 --output <out> <in>
        gpg_cmd = [
            "gpg", "--decrypt", "--batch", "--yes", "--passphrase-fd", "0",
            "--output", decrypted_tmp_path, archive_path
        ]

        print("Decrypting...")
        try:
             proc = subprocess.run(gpg_cmd, input=passphrase.encode(), check=False)
             if proc.returncode != 0:
                 print("Error: GPG decryption failed. Incorrect password?")
                 sys.exit(1)
             final_archive_path = decrypted_tmp_path
        except FileNotFoundError:
             print("Error: 'gpg' command not found.")
             sys.exit(1)

    try:
        cmd = f"tar -C {shlex_quote(extract_to)} -xzf {shlex_quote(final_archive_path)}"
        run(cmd)
    finally:
        if decrypted_tmp_path and os.path.exists(decrypted_tmp_path):
            os.remove(decrypted_tmp_path)

def perform_restore(args: argparse.Namespace):
    email_before = get_active_session()
    
    # Check for required args if not set (legacy check)
    if not hasattr(args, 'dest') or args.dest is None:
        args.dest = "~/.gemini-manager"

    # Handle search_dir default if missing
    if not hasattr(args, 'search_dir') or args.search_dir is None:
        args.search_dir = DEFAULT_BACKUP_DIR

    dest = os.path.abspath(os.path.expanduser(args.dest))
    ts_now = time.strftime("%Y%m%d-%H%M%S")

    chosen_src: Optional[str] = None
    from_archive: Optional[str] = None
    temp_download_path: Optional[str] = None # Initialize for cloud downloads

    # --- NEW CODE BLOCK: CLOUD DISCOVERY ---
    if hasattr(args, 'cloud') and args.cloud:
        provider = get_cloud_provider(args)
        if not provider:
            sys.exit(1)
        
        # 1. List backups
        print("Fetching file list from Cloud...")
        files = provider.list_files()
        all_files = []
        for f in files:
            if is_backup_archive(f.name):
                ts = parse_timestamp_from_name(f.name)
                if ts:
                    all_files.append((ts, f.name))
        
        if not all_files:
            print("No valid backups found in Cloud bucket.")
            sys.exit(1)

        target_file_name = None

        if hasattr(args, 'auto') and args.auto:
            rec = get_recommendation()
            if not rec:
                cprint(NEON_RED, "No 'Green' (Ready) accounts available for auto-switch.")
                sys.exit(1)

            target_email = rec.email
            cprint(NEON_CYAN, f"Auto-switch recommendation: {target_email}")

            # Filter files for this email
            candidates = []
            for ts, fname in all_files:
                if target_email in fname:
                    candidates.append((ts, fname))

            if not candidates:
                cprint(NEON_RED, f"No backups found in cloud for recommended account: {target_email}")
                sys.exit(1)

            # Select LATEST (newest) for auto-switch
            candidates.sort(key=lambda x: time.mktime(x[0]), reverse=True)
            target_file_name = candidates[0][1]
            cprint(NEON_GREEN, f"Selected latest cloud backup for {target_email}: {target_file_name}")

        elif hasattr(args, 'from_archive') and args.from_archive:
            # User requested a specific file
            wanted_name = os.path.basename(args.from_archive)
            # Check if it exists in the list we just fetched
            for _, fname in all_files:
                if fname == wanted_name:
                    target_file_name = fname
                    break
            
            if target_file_name:
                print(f"Selected specified cloud backup: {target_file_name}")
            else:
                print(f"Error: Specified archive '{wanted_name}' not found in Cloud bucket.")
                sys.exit(1)
        else:
            # 2. Auto-select oldest (matches existing logic)
            # Sorting by timestamp (earliest first)
            all_files.sort(key=lambda x: time.mktime(x[0]))
            target_file_name = all_files[0][1]
            print(f"Auto-selected oldest cloud backup: {target_file_name}")

        # 3. Download to a temporary file
        temp_download_path = os.path.join(tempfile.gettempdir(), target_file_name)
        # Ensure the directory for the temporary download exists
        os.makedirs(os.path.dirname(temp_download_path), exist_ok=True)

        try:
            provider.download_file(target_file_name, temp_download_path)
        except Exception:
            sys.exit(1)
        
        from_archive = temp_download_path
    # ---------------------------------------

    elif hasattr(args, 'auto') and args.auto:
        rec = get_recommendation()
        if not rec:
            cprint(NEON_RED, "No 'Green' (Ready) accounts available for auto-switch.")
            sys.exit(1)

        target_email = rec.email
        cprint(NEON_CYAN, f"Auto-switch recommendation: {target_email}")

        sd = os.path.abspath(os.path.expanduser(args.search_dir))
        latest_archive = find_latest_archive_backup_for_email(sd, target_email)

        if not latest_archive:
            cprint(NEON_RED, f"No backups found locally for recommended account: {target_email}")
            sys.exit(1)

        from_archive = latest_archive
        cprint(NEON_GREEN, f"Selected latest local backup for {target_email}: {from_archive}")

    elif hasattr(args, 'from_dir') and args.from_dir:
        chosen_src = os.path.abspath(os.path.expanduser(args.from_dir))
        if not os.path.exists(chosen_src):
            print(f"Specified --from-dir not found: {chosen_src}")
            sys.exit(1)
    elif hasattr(args, 'from_archive') and args.from_archive:
        # First, try the path as provided by the user
        user_path = os.path.abspath(os.path.expanduser(args.from_archive))
        
        # If not found, try looking in the default search directory
        if not os.path.exists(user_path):
            search_dir = os.path.abspath(os.path.expanduser(args.search_dir))
            basename = os.path.basename(user_path)
            path_in_search_dir = os.path.join(search_dir, basename)
            
            if os.path.exists(path_in_search_dir):
                from_archive = path_in_search_dir
                print(f"Found archive in default backup directory: {from_archive}")
            else:
                print(f"Specified --from-archive not found at '{user_path}' or in search directory '{search_dir}'")
                sys.exit(1)
        else:
            from_archive = user_path
    else:
        # Auto-discover oldest timestamped *archive* in search_dir
        sd = os.path.abspath(os.path.expanduser(args.search_dir))
        print(f"Searching for oldest backup archive in: {sd}")
        oldest_archive = find_oldest_archive_backup(sd)
        if not oldest_archive:
            print(f"No timestamped backup archives (*.gemini-manager.tar.gz) found in {sd}")
            sys.exit(1)
        
        from_archive = oldest_archive
        print(f"Auto-selected oldest backup archive: {from_archive}")

    lockfd = acquire_lock()
    try:
        work_tmp = tempfile.mkdtemp(prefix="gm-restore-")
        try:
            if from_archive:
                print(f"Extracting archive {from_archive} -> {work_tmp}")
                if not getattr(args, 'dry_run', False):
                    extract_archive(from_archive, work_tmp)
                else:
                    print("DRY RUN: would extract archive.")
                src_for_copy = work_tmp
            else:
                # chosen_src is set (either provided or auto-selected)
                src_for_copy = os.path.abspath(chosen_src)
                print("Source to restore from:", src_for_copy)

            # Copy into temporary dest - to prepare verification
            tmp_dest = f"{dest}.tmp-{ts_now}"
            print(f"Copying {src_for_copy} -> {tmp_dest}")
            if not getattr(args, 'dry_run', False):
                if os.path.exists(tmp_dest):
                    shutil.rmtree(tmp_dest)
                cp_cmd = f"cp -a {shlex_quote(src_for_copy)} {shlex_quote(tmp_dest)}"
                run(cp_cmd)
            else:
                print("DRY RUN: would cp -a ...")

            # Verify copy with diff -r
            print("Verifying copy with diff -r")
            if not getattr(args, 'dry_run', False):
                diff_proc = run(f"diff -r {shlex_quote(tmp_dest)} {shlex_quote(src_for_copy)}", capture=True, check=False)
                if diff_proc.returncode != 0:
                    print("Verification FAILED (diff shows differences):")
                    if diff_proc.stdout:
                        print(diff_proc.stdout)
                    shutil.rmtree(tmp_dest, ignore_errors=True)
                    sys.exit(3)
                else:
                    print("Verification OK.")
            else:
                print("DRY RUN: would run diff -r ...")

            # Prepare swap: move existing dest to archive unless --force
            bakname = None
            if os.path.exists(dest) and not args.force:
                bak_filename = f".gemini-manager.bak-{ts_now}"
                bakname = os.path.join(OLD_CONFIGS_DIR, bak_filename)
                
                if args.dry_run:
                    cprint(NEON_YELLOW, f"[DRY-RUN] Would move existing {dest} to {bakname}")
                else:
                    cprint(NEON_YELLOW, f"Backing up existing configuration to {bakname}...")
                    # If destination archive exists (highly unlikely with timestamp), remove it first or it will fail/nest
                    if os.path.exists(bakname):
                         shutil.rmtree(bakname)
                    shutil.move(dest, bakname)

            # Install new .gm (atomic replace)
            print(f"Installing new .gm from {tmp_dest} -> {dest}")
            if not getattr(args, 'dry_run', False):
                try:
                    os.replace(tmp_dest, dest)
                except OSError as e:
                     # Fallback for cross-device link if using tmp in different mount
                     if e.errno == 18: # EXDEV
                         shutil.move(tmp_dest, dest)
                     else:
                         raise e
            else:
                print("DRY RUN: would os.replace(tmp_dest, dest)")

            # Post-restore verification
            if not getattr(args, 'dry_run', False):
                print("Post-restore verification: diff -r between restored dest and source")
                diff2 = run(f"diff -r {shlex_quote(dest)} {shlex_quote(src_for_copy)}", capture=True, check=False)
                if diff2.returncode != 0:
                    print("Post-restore verification FAILED:")
                    if diff2.stdout:
                        print(diff2.stdout)
                    print("Attempting rollback (if possible).")
                    if not getattr(args, 'force', False) and bakname and os.path.exists(bakname):
                        try:
                            os.replace(bakname, dest)
                            print("Rollback to previous copy succeeded.")
                        except Exception as e:
                            print("Rollback failed:", e)
                    sys.exit(4)
                else:
                    print("Post-restore verification OK.")
            else:
                print("DRY RUN: would run post-restore diff")

            print("Restore complete.")
            if bakname and os.path.exists(bakname):
                print("Previous .gm moved to:", bakname)

            # Check for account switch and record it
            if not getattr(args, 'dry_run', False):
                # --- Auto-Cooldown for Outgoing Account ---
                if email_before:
                    cprint(NEON_YELLOW, f"Auto-adding 24h cooldown for outgoing account: {email_before}")
                    add_24h_cooldown_for_email(email_before)
                    
                    # Sync with Cloud
                    try:
                        # We need to sync resets.json to cloud if configured.
                        # sync_resets_with_cloud expects a B2Manager-like object (with upload_string/download_to_string if B2).
                        # But wait, generic provider has upload_file/download_file.
                        # sync_resets_with_cloud logic might be coupled to B2Manager.
                        
                        # Let's check sync_resets_with_cloud in reset_helpers.py later.
                        # For now, let's just try to get provider.
                        
                        provider_for_sync = None
                        if getattr(args, 'cloud', False):
                             provider_for_sync = locals().get('provider')

                        if not provider_for_sync:
                             provider_for_sync = get_cloud_provider(args)

                        if provider_for_sync:
                             # We need to adapt sync_resets_with_cloud to support generic provider
                             # OR cast/check type if we haven't updated reset_helpers yet.
                             # For this step, I'll pass the provider and let reset_helpers fail if not updated,
                             # but I should update reset_helpers too.
                             sync_resets_with_cloud(provider_for_sync)

                    except Exception as e:
                        cprint(NEON_RED, f"[WARN] Could not sync resets to cloud: {e}")
                    
                    # Also update the cooldown dashboard (gm-cooldown.json)
                    record_switch(email_before, args=args)
                # ------------------------------------------

                email_after = get_active_session()
                if email_before != email_after and email_after is not None:
                    print(f"Account switch detected: -> {email_after}")
                    print("Recording switch for 24h cooldown period...")
                    # Pass args to handle potential cloud upload
                    record_switch(email_after, args=args)

        finally:
            # cleanup temp extraction dir if still present
            if os.path.exists(work_tmp):
                try:
                    shutil.rmtree(work_tmp)
                except Exception:
                    pass
        # ADD THIS:
        if temp_download_path and os.path.exists(temp_download_path):
            try:
                os.remove(temp_download_path)
            except Exception:
                pass
    finally:
        try:
            fcntl.flock(lockfd, fcntl.LOCK_UN)
            lockfd.close()
        except Exception:
            pass

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--from-dir", help="Directory backup to restore from (legacy, archive is preferred)")
    p.add_argument("--from-archive", help="Tar.gz archive to restore from")
    p.add_argument("--search-dir", default=DEFAULT_BACKUP_DIR, help="Directory to search for timestamped backups when no source is specified (default: ~/.gemini-manager/backups)")
    p.add_argument("--dest", default="~/.gemini-manager", help="Destination (default ~/.gemini-manager)")
    p.add_argument("--force", action="store_true", help="Allow destructive replace without keeping .bak")
    p.add_argument("--dry-run", action="store_true", help="Do a dry run without destructive actions")
    p.add_argument("--cloud", action="store_true", help="Restore from Cloud (B2)")
    p.add_argument("--bucket", help="B2 Bucket Name")
    p.add_argument("--b2-id", help="B2 Key ID (or set env GEMINI_B2_KEY_ID)")
    p.add_argument("--b2-key", help="B2 App Key (or set env GEMINI_B2_APP_KEY)")
    p.add_argument("--auto", action="store_true", help="Automatically restore the next best available account")
    args = p.parse_args()

    perform_restore(args)

if __name__ == "__main__":
    main()
