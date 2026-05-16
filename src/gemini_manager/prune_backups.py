#!/usr/bin/env python3
# src/gemini_manager/prune_backups.py

import os
import time
from pathlib import Path
from typing import Any, List, Dict

from .ui import console, cprint, NEON_CYAN, NEON_RED, NEON_YELLOW, NEON_GREEN
from .b2 import B2Manager
from .credentials import resolve_credentials
from .list_backups import _email_from_archive_name
from .restore import is_backup_archive
from .metadata import snapshot_path_for_archive, load_local_snapshots
from .config import TIMESTAMPED_DIR_REGEX, DEFAULT_BACKUP_DIR, OLD_CONFIGS_DIR, GEMINI_CLI_HOME

def _parse_reset_ts(name: str) -> float:
    import re
    m = re.match(r"^(\d{4}-\d{2}-\d{2}_\d{6})", name)
    if m:
        try:
            return time.mktime(time.strptime(m.group(1), "%Y-%m-%d_%H%M%S"))
        except Exception:
            pass
    return 0.0

def perform_prune_backups(args: Any) -> None:
    """
    Enhanced pruning logic for Gemini Manager backups, matching Codex Manager.
    """
    keep = args.keep
    dry_run = args.dry_run
    cloud = getattr(args, "cloud", False)
    backup_dir = os.path.abspath(os.path.expanduser(args.backup_dir))
    dir_backup_path = os.path.abspath(os.path.expanduser(OLD_CONFIGS_DIR))

    if keep is None:
        console.print("[yellow]Nothing to do: must specify --keep (e.g., --keep 1 to keep latest per account)[/]")
        return

    cprint(NEON_CYAN, "✂️  Gemini Backup Pruning Tool")

    if cloud:
        # --- CLOUD PRUNING ONLY ---
        # ... (rest of cloud logic unchanged)
        key_id, app_key, bucket_name = resolve_credentials(args)
        if key_id and app_key and bucket_name:
            cprint(NEON_CYAN, f"\n[CLOUD ARCHIVES] Scanning B2 Bucket: {bucket_name}...")
            try:
                b2 = B2Manager(key_id, app_key, bucket_name)
                listed = list(b2.list_backups())
                
                entries = []
                for fv, _ in listed:
                    if is_backup_archive(fv.file_name):
                        entries.append({
                            "name": fv.file_name,
                            "email": _email_from_archive_name(fv.file_name) or "unknown",
                            "time": fv.upload_timestamp / 1000.0,
                            "id": fv.id_
                        })
                
                entries.sort(key=lambda x: x["time"], reverse=True)
                to_delete_entries = _calculate_prune_list_generic(entries, keep)
                
                if not to_delete_entries:
                    cprint(NEON_GREEN, "No cloud backups matched pruning criteria.")
                else:
                    all_cloud_files = {fv.file_name: [] for fv, _ in listed}
                    for fv, _ in listed:
                        all_cloud_files[fv.file_name].append(fv.id_)

                    for entry in to_delete_entries:
                        fname = entry["name"]
                        metadata_name = os.path.basename(snapshot_path_for_archive(fname))
                        if dry_run:
                            console.print(f"[DRY-RUN] Would delete cloud: {fname}")
                        else:
                            try:
                                for vid in all_cloud_files.get(fname, []):
                                    b2.bucket.delete_file_version(vid, fname)
                                console.print(f"[DELETED CLOUD] {fname}")
                                for vid in all_cloud_files.get(metadata_name, []):
                                    b2.bucket.delete_file_version(vid, metadata_name)
                            except Exception as e:
                                cprint(NEON_RED, f"Failed to delete cloud file {fname}: {e}")
            except Exception as e:
                cprint(NEON_RED, f"[ERROR] Cloud prune failed: {e}")
        else:
            cprint(NEON_RED, "[ERROR] Cloud credentials missing.")
    else:
        # --- LOCAL PRUNING ---
        # 1. Archives
        cprint(NEON_CYAN, f"\n[LOCAL ARCHIVES] Scanning {backup_dir}...")
        if os.path.exists(backup_dir):
            metadata_records = load_local_snapshots(backup_dir)
            metadata_by_archive = {r.get("archive_name"): r for r in metadata_records if r.get("archive_name")}
            files = [f for f in os.listdir(backup_dir) if is_backup_archive(f)]
            
            entries = []
            for f in files:
                m = metadata_by_archive.get(f)
                email = _email_from_archive_name(f) or "unknown"
                ctime = 0.0
                if m and m.get("created_at"):
                    try:
                        from datetime import datetime
                        ctime = datetime.fromisoformat(m["created_at"]).timestamp()
                    except Exception:
                        ctime = os.path.getmtime(os.path.join(backup_dir, f))
                else:
                    ctime = os.path.getmtime(os.path.join(backup_dir, f))
                
                entries.append({"name": f, "email": email, "time": ctime})

            entries.sort(key=lambda x: x["time"], reverse=True)
            to_delete_entries = _calculate_prune_list_generic(entries, keep)
            
            if not to_delete_entries:
                cprint(NEON_GREEN, "No local archives matched pruning criteria.")
            else:
                for entry in to_delete_entries:
                    fname = entry["name"]
                    archive_path = Path(backup_dir) / fname
                    metadata_path = Path(snapshot_path_for_archive(str(archive_path)))
                    if dry_run:
                        console.print(f"[DRY-RUN] Would delete local archive: {fname}")
                    else:
                        try:
                            archive_path.unlink()
                            console.print(f"[DELETED] {fname}")
                            if metadata_path.exists():
                                metadata_path.unlink()
                        except Exception as e:
                            cprint(NEON_RED, f"Failed to delete {fname}: {e}")
        else:
            cprint(NEON_YELLOW, f"Archive directory not found: {backup_dir}")

        # 2. Directories (Legacy)
        cprint(NEON_CYAN, f"\n[LOCAL DIRECTORIES] Scanning {dir_backup_path}...")
        if os.path.exists(dir_backup_path):
            # Directories use the same email-in-name pattern
            dirs = [d for d in os.listdir(dir_backup_path) if os.path.isdir(os.path.join(dir_backup_path, d)) and ".gemini-manager" in d]
            
            dir_entries = []
            for d in dirs:
                # Email extraction for dirs: YYYY-MM-DD_HHMMSS-<email>.gemini-manager
                email = "unknown"
                if len(d) > 18:
                    suffix = d[18:]
                    if suffix.endswith(".gemini-manager"):
                        email = suffix[:-15]
                
                # For directories, we mostly rely on reset timestamp in name or mtime
                # Since we don't have metadata for legacy dirs, use mtime or parse name
                ctime = os.path.getmtime(os.path.join(dir_backup_path, d))
                # Prefer reset time from name for directory sorting if mtime is unreliable
                name_ts = _parse_reset_ts(d)
                if name_ts > 0:
                    ctime = name_ts

                dir_entries.append({"name": d, "email": email, "time": ctime})

            dir_entries.sort(key=lambda x: x["time"], reverse=True)
            to_delete_dirs = _calculate_prune_list_generic(dir_entries, keep)

            if not to_delete_dirs:
                cprint(NEON_GREEN, "No legacy directories matched pruning criteria.")
            else:
                import shutil
                for entry in to_delete_dirs:
                    dname = entry["name"]
                    dpath = os.path.join(dir_backup_path, dname)
                    if dry_run:
                        console.print(f"[DRY-RUN] Would delete directory: {dname}")
                    else:
                        try:
                            shutil.rmtree(dpath)
                            console.print(f"[DELETED] {dname}")
                        except Exception as e:
                            cprint(NEON_RED, f"Failed to delete directory {dname}: {e}")
        else:
            cprint(NEON_YELLOW, f"Directory backup path not found: {dir_backup_path}")

def _calculate_prune_list_generic(entries: List[Dict[str, Any]], keep: int | None) -> List[Dict[str, Any]]:
    """
    Identity-First retention logic:
    1. Group entries by email.
    2. Within each email group, sort by time (newest first).
    3. Keep N newest entries per email.
    """
    if keep is None:
        return []

    # Grouping
    by_email: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        email = e.get("email") or "unknown"
        if email not in by_email:
            by_email[email] = []
        by_email[email].append(e)

    to_delete = []
    
    for email, group in by_email.items():
        # Sort newest first
        group.sort(key=lambda x: x["time"], reverse=True)
        
        # Identify backups to delete for THIS account
        if len(group) > keep:
            to_delete.extend(group[keep:])

    return to_delete
