#!/usr/bin/env python3
# src/gemini_manager/prune.py

import os
import time
from .ui import cprint, NEON_GREEN, NEON_RED, NEON_YELLOW, NEON_CYAN
from .b2 import B2Manager
import shutil
from .credentials import resolve_credentials
from .config import TIMESTAMPED_DIR_REGEX, OLD_CONFIGS_DIR

def parse_ts(name):
    m = TIMESTAMPED_DIR_REGEX.match(name)
    if m:
        return time.strptime(m.group(1), "%Y-%m-%d_%H%M%S")
    return None

def get_backup_list(files):
    """
    Filter and sort backups.
    files: list of filenames
    Returns list of (timestamp_struct, filename) sorted NEWEST first.
    """
    valid = []
    for f in files:
        if f.endswith(".gemini-manager.tar.gz"):
            ts = parse_ts(f)
            if ts:
                valid.append((ts, f))
    # Sort: Newest first (descending timestamp)
    valid.sort(key=lambda x: x[0], reverse=True)
    return valid

def get_backup_list_dirs(files):
    """
    Filter and sort directory backups.
    files: list of filenames/dirnames
    Returns list of (timestamp_struct, dirname) sorted NEWEST first.
    """
    valid = []
    for f in files:
        # Check if it's a directory and matches the pattern
        # The pattern does not need to check for .tar.gz
        m = TIMESTAMPED_DIR_REGEX.match(f)
        if m:
            # Check if the matched part is the whole string, but without .tar.gz
            # This avoids matching archive files if they are passed in
            if not f.endswith(".tar.gz"):
                ts = parse_ts(f)
                if ts:
                    valid.append((ts, f))
    # Sort: Newest first (descending timestamp)
    valid.sort(key=lambda x: x[0], reverse=True)
    return valid

def prune_list(backups, keep_count, dry_run, delete_callback):
    """
    backups: list of (ts, filename) sorted newest first.
    keep_count: int
    delete_callback: func(filename)
    """
    if len(backups) <= keep_count:
        cprint(NEON_GREEN, f"Total backups ({len(backups)}) <= keep count ({keep_count}). No pruning needed.")
        return

    to_keep = backups[:keep_count]
    to_delete = backups[keep_count:]

    cprint(NEON_CYAN, f"Keeping {len(to_keep)} latest backups.")
    cprint(NEON_YELLOW, f"Pruning {len(to_delete)} old backups...")

    for ts, fname in to_delete:
        if dry_run:
            print(f"[DRY-RUN] Would delete: {fname}")
        else:
            delete_callback(fname)
            print(f"[DELETED] {fname}")

def do_prune(args):
    # backup_dir from args is for archives. Directory backups are in OLD_CONFIGS_DIR
    archive_dir = os.path.abspath(os.path.expanduser(args.backup_dir))
    dir_backup_path = os.path.abspath(os.path.expanduser(OLD_CONFIGS_DIR))
    keep = int(args.keep)
    dry_run = args.dry_run
    
    cprint(NEON_CYAN, "✂️  Gemini Backup Pruning Tool")
    
    # 1. Local Prune
    if not args.cloud_only:
        # Prune Archives
        cprint(NEON_CYAN, f"\n[LOCAL ARCHIVES] Scanning {archive_dir}...")
        if os.path.exists(archive_dir):
            files = os.listdir(archive_dir)
            backups = get_backup_list(files)
            
            def local_delete_file(fname):
                path = os.path.join(archive_dir, fname)
                try:
                    os.remove(path)
                except Exception as e:
                    cprint(NEON_RED, f"Failed to remove {path}: {e}")

            prune_list(backups, keep, dry_run, local_delete_file)
        else:
             cprint(NEON_YELLOW, f"Archive backup directory not found: {archive_dir}")

        # Prune Directories
        cprint(NEON_CYAN, f"\n[LOCAL DIRECTORIES] Scanning {dir_backup_path}...")
        if os.path.exists(dir_backup_path):
            dirs = os.listdir(dir_backup_path)
            dir_backups = get_backup_list_dirs(dirs)

            def local_delete_dir(dirname):
                path = os.path.join(dir_backup_path, dirname)
                try:
                    shutil.rmtree(path)
                except Exception as e:
                    cprint(NEON_RED, f"Failed to remove directory {path}: {e}")

            prune_list(dir_backups, keep, dry_run, local_delete_dir)
        else:
            cprint(NEON_YELLOW, f"Directory backup path not found: {dir_backup_path}")

    # 2. Cloud Prune (Only for archives, which is correct)
    if args.cloud or args.cloud_only:
        key_id, app_key, bucket_name = resolve_credentials(args)

        if key_id and app_key and bucket_name:
            cprint(NEON_CYAN, f"\n[CLOUD] Scanning B2 Bucket: {bucket_name}...")
            try:
                b2 = B2Manager(key_id, app_key, bucket_name)
                files = []
                cloud_files_map = {} # fname -> file_id (for deletion)
                
                for fv, _ in b2.list_backups():
                    files.append(fv.file_name)
                    cloud_files_map[fv.file_name] = fv.id_
                
                backups = get_backup_list(files)
                
                def cloud_delete(fname):
                    try:
                        b2.bucket.delete_file_version(cloud_files_map[fname], fname)
                    except Exception as e:
                         cprint(NEON_RED, f"Failed to delete cloud file {fname}: {e}")

                prune_list(backups, keep, dry_run, cloud_delete)

            except Exception as e:
                cprint(NEON_RED, f"[ERROR] Cloud prune failed: {e}")
        else:
             if args.cloud_only:
                 cprint(NEON_RED, "[ERROR] Cloud credentials missing.")
             else:
                 cprint(NEON_YELLOW, "\n[CLOUD] Skipping (credentials not set).")
