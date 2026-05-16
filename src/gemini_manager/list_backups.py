#!/usr/bin/env python3
# src/gemini_manager/list_backups.py

"""
List Gemini Manager backups in a metadata-backed table.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any

from .b2 import B2Manager
from .config import DEFAULT_BACKUP_DIR, OLD_CONFIGS_DIR
from .credentials import resolve_credentials
from .metadata import (
    latest_entity_by_email,
    load_local_snapshots,
    load_local_states,
    load_cloud_snapshots,
    load_cloud_states,
)
from .restore import is_backup_archive, parse_timestamp_from_name
from .ui import NEON_RED, NEON_YELLOW, Panel, Table, console, cprint, style_quota_percent


@dataclass(frozen=True)
class BackupRow:
    archive_name: str
    email: str
    captured_at: str
    reset_at: str
    flash: int | None
    lite: int | None
    pro: int | None
    penalty: str
    sort_key: float
    source: str = "local"


def _email_from_archive_name(filename: str) -> str | None:
    """
    Extract the email address from a backup archive filename.
    Expected formats:
      YYYY-MM-DD_HHMMSS-email@example.com.gemini-manager.tar.gz
      YYYY-MM-DD_HHMMSS-email@example.com.gemini-manager.tar.gz.gpg
    Returns the email string if found, else None.
    """
    if len(filename) <= 18:
        return None

    suffix = filename[18:]
    if suffix.endswith(".gemini-manager.tar.gz"):
        return suffix[:-22]
    if suffix.endswith(".gemini-manager.tar.gz.gpg"):
        return suffix[:-26]
    return None


def _timestamp_key(name: str) -> float:
    """
    Generate a numeric sort key from a filename's timestamp prefix.
    Expects prefix: YYYY-MM-DD_HHMMSS
    """
    parsed = parse_timestamp_from_name(name)
    if not parsed:
        return 0
    return time.mktime(parsed)


def _display_archive(name: str) -> str:
    """
    Format the archive filename for display in the table.
    Shortens '2026-05-13_120000' to '05-13_120000' for better fit in narrow terminals.
    """
    parsed = parse_timestamp_from_name(name)
    if parsed:
        return time.strftime("%m-%d_%H%M%S", parsed)
    return name


def _metadata_time_key(record: dict[str, Any], archive_name: str = "") -> float:
    """
    Extract a timestamp from a metadata record for sorting or comparison.
    Priority: updated_at > captured_at > saved_at > created_at > reset_at > reset_ist
    """
    for field in ("updated_at", "captured_at", "saved_at", "created_at", "reset_at", "reset_ist"):
        value = record.get(field)
        if not value:
            continue
        try:
            from datetime import datetime

            return datetime.fromisoformat(str(value)).timestamp()
        except Exception:
            pass
    return _timestamp_key(archive_name)


def _model_percent(models: dict[str, Any], wanted: str) -> int | None:
    wanted_key = wanted.lower().replace(" ", "")
    for name, info in (models or {}).items():
        normalized = str(name).lower().replace(" ", "")
        if wanted_key not in normalized:
            continue
        
        info = info or {}
        # Standardize to USAGE percentage
        if "percent_used" in info:
            try:
                return int(info["percent_used"])
            except (TypeError, ValueError):
                pass
        if "percent_left" in info:
            try:
                return 100 - int(info["percent_left"])
            except (TypeError, ValueError):
                pass
        if "remaining_percent" in info:
            try:
                return 100 - int(info["remaining_percent"])
            except (TypeError, ValueError):
                pass

        # Default to 'percent', treating it as Usage (matches Gemini CLI behavior)
        percent = info.get("percent")
        
        try:
            return int(percent)
        except (TypeError, ValueError):
            return None
    return None


def _quota_text(row: BackupRow) -> str:
    return f"F:{style_quota_percent(row.flash, is_usage=True)} L:{style_quota_percent(row.lite, is_usage=True)} P:{style_quota_percent(row.pro, is_usage=True)}"


def _penalty_for_flash(usage: int | None) -> str:
    """
    Calculate penalty based on Flash usage.
    """
    if usage is None:
        return "[dim]UNKNOWN[/]"
    
    if usage >= 100:
        return "[red]HIGH[/]"
    if usage >= 90:
        return "[bright_red]HEAVY[/]"
    if usage >= 65:
        return "[yellow]MEDIUM[/]"
    return "[green]LOW[/]"


def _row_from_metadata(record: dict[str, Any], archive_name: str, source: str) -> BackupRow:
    models = record.get("models") or {}
    flash = _model_percent(models, "flash")
    lite = _model_percent(models, "lite")
    pro = _model_percent(models, "pro")
    email = str(record.get("email") or _email_from_archive_name(archive_name) or "unknown")
    captured_at = str(record.get("captured_at") or record.get("created_at") or record.get("saved_at") or "unknown")
    reset_at = str(record.get("next_available_at") or record.get("reset_at") or record.get("reset_ist") or "unknown")
    return BackupRow(
        archive_name=archive_name,
        email=email,
        captured_at=captured_at,
        reset_at=reset_at,
        flash=flash,
        lite=lite,
        pro=pro,
        penalty=_penalty_for_flash(flash),
        sort_key=_timestamp_key(archive_name) or _metadata_time_key(record, archive_name),
        source=source,
    )


def _row_from_archive_name(archive_name: str, source: str) -> BackupRow:
    email = _email_from_archive_name(archive_name) or "unknown"
    return BackupRow(
        archive_name=archive_name,
        email=email,
        captured_at="unknown",
        reset_at="unknown",
        flash=None,
        lite=None,
        pro=None,
        penalty=_penalty_for_flash(None),
        sort_key=_timestamp_key(archive_name),
        source=source,
    )


def _latest_per_email(rows: list[BackupRow]) -> list[BackupRow]:
    latest: dict[str, BackupRow] = {}
    for row in sorted(rows, key=lambda item: item.sort_key, reverse=True):
        key = row.email.lower()
        if key not in latest:
            latest[key] = row
    return list(latest.values())


def _sort_rows(rows: list[BackupRow], latest_only: bool) -> list[BackupRow]:
    if latest_only:
        rows = _latest_per_email(rows)
    return sorted(rows, key=lambda item: item.sort_key, reverse=True)


def _local_rows(search_dir: str) -> list[BackupRow]:
    archive_dir = os.path.abspath(os.path.expanduser(search_dir or DEFAULT_BACKUP_DIR))
    if not os.path.isdir(archive_dir):
        cprint(NEON_YELLOW, f"Archive backup directory not found: {archive_dir}")
        return []

    try:
        names = sorted(os.listdir(archive_dir))
    except OSError as exc:
        cprint(NEON_RED, f"Error reading archive backup directory: {exc}")
        return []

    archives = [
        name
        for name in names
        if os.path.isfile(os.path.join(archive_dir, name)) and is_backup_archive(name)
    ]
    
    # Pre-calculate latest archive per email
    latest_archives = {}
    for name in archives:
        email = _email_from_archive_name(name)
        if not email: continue
        key = email.lower()
        ts = _timestamp_key(name)
        if key not in latest_archives or ts > _timestamp_key(latest_archives[key]):
            latest_archives[key] = name

    # 1. Load authoritative snapshots
    snapshots = load_local_snapshots(archive_dir)
    
    # 2. Load Registry (The high-performance index)
    from .registry import get_registry
    registry_records = get_registry().get_all()
    
    # 3. Load decentralized states
    states = load_local_states()
    
    # Merge entries from the global resets store (used by gm cooldown)
    # as a fallback when specific archival information is missing.
    from .reset_helpers import get_all_resets
    all_records = list(snapshots)
    all_records.extend(registry_records) # Prioritize registry for composition
    all_records.extend(states)
    all_records.extend(get_all_resets())

    metadata_by_archive = {
        record.get("archive_name"): record
        for record in snapshots
        if record.get("archive_name")
    }
    
    # Index by email for fallbacks
    metadata_by_account: dict[str, dict[str, Any]] = {
        record["email"].lower(): record
        for record in (registry_records + states) # Use Registry or State
        if record.get("email")
    }

    from .metadata import ENTITY_PRIORITY
    metadata_by_email = latest_entity_by_email(all_records)

    rows = []
    for archive_name in archives:
        email = _email_from_archive_name(archive_name)
        
        # Default to archive-specific record
        record = metadata_by_archive.get(archive_name)
        
        # If this is the LATEST archive for this email, 
        # attempt to use the most authoritative account health (Registry/State/Reset)
        if email and archive_name == latest_archives.get(email.lower()):
            latest_rec = metadata_by_email.get(email.lower())
            if latest_rec:
                # Only upgrade to latest_rec if it's more authoritative or newer than the archive snapshot
                rec_type = latest_rec.get("_entity_type", "reset")
                rec_prio = ENTITY_PRIORITY.get(rec_type, 0)
                
                # archive snapshot prio is effectively 200 (SnapshotRecord)
                if rec_prio > 200 or _metadata_time_key(latest_rec) > _timestamp_key(archive_name):
                    record = latest_rec
        
        if not record and email:
            # Fallback 1: Registry or Mutable Account State
            record = metadata_by_account.get(email.lower())
        
        if not record and email:
            # Fallback 2: Latest general record (snapshot or reset)
            record = metadata_by_email.get(email.lower())
            
        if record:
            rows.append(_row_from_metadata(record, archive_name, "local"))
        else:
            rows.append(_row_from_archive_name(archive_name, "local"))
    return rows


def _cloud_rows(args: argparse.Namespace) -> list[BackupRow]:
    key_id, app_key, bucket_name = resolve_credentials(args)
    b2 = B2Manager(key_id, app_key, bucket_name)

    try:
        listed = list(b2.list_files()) # Returns List[CloudFile]
    except Exception as exc:
        cprint(NEON_RED, f"[CLOUD] Failed to list backups from B2: {exc}")
        sys.exit(1)

    names = [f.name for f in listed]
    archives = [name for name in names if is_backup_archive(name)]
    
    # Pre-calculate latest archive per email
    latest_archives = {}
    for name in archives:
        email = _email_from_archive_name(name)
        if not email: continue
        key = email.lower()
        ts = _timestamp_key(name)
        if key not in latest_archives or ts > _timestamp_key(latest_archives[key]):
            latest_archives[key] = name

    # 1. Sync Registry from cloud (The primary health source)
    from .registry import sync_registry_with_cloud, get_registry
    try:
        sync_registry_with_cloud(b2, direction="pull")
    except Exception:
        pass
    
    registry_records = get_registry().get_all()
    
    # 2. Namespace Peeking: Extract identity and reset time from filenames
    # This provides a near-zero cost initial view.
    peeking_records = []
    for archive_name in archives:
        email = _email_from_archive_name(archive_name)
        # We use parse_timestamp_from_name to get the 'reset_at' encoded in filename
        reset_ts = parse_timestamp_from_name(archive_name)
        if email and reset_ts:
            peeking_records.append({
                "email": email,
                "reset_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", reset_ts),
                "next_available_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", reset_ts),
                "archive_name": archive_name,
                "_entity_type": "snapshot",
                "status_source": "namespace_peeking"
            })

    metadata_by_archive: dict[str, dict[str, Any]] = {
        record.get("archive_name"): record
        for record in peeking_records
    }
    
    metadata_by_account: dict[str, dict[str, Any]] = {
        record["email"].lower(): record
        for record in registry_records
        if record.get("email")
    }

    # Compose all cloud-sourced records
    all_cloud_records = list(peeking_records)
    all_cloud_records.extend(registry_records)

    # Pull in the remote resets store if available
    try:
        remote_resets = b2.download_to_string("gm-resets.json")
        if remote_resets:
            resets_data = json.loads(remote_resets)
            if isinstance(resets_data, list):
                all_cloud_records.extend(resets_data)
    except Exception:
        pass

    from .metadata import ENTITY_PRIORITY
    metadata_by_email = latest_entity_by_email(all_cloud_records)

    rows = []
    for archive_name in archives:
        email = _email_from_archive_name(archive_name)
        
        # Start with archive-specific peeking
        record = metadata_by_archive.get(archive_name)
        
        # If this is the LATEST archive for this email, prefer the most authoritative cloud record
        if email and archive_name == latest_archives.get(email.lower()):
            latest_rec = metadata_by_email.get(email.lower())
            if latest_rec:
                # Use latest_rec if it's more authoritative or newer than filename peeking
                rec_type = latest_rec.get("_entity_type", "reset")
                rec_prio = ENTITY_PRIORITY.get(rec_type, 0)
                
                # peeking is priority 200 (snapshot) but lacks model info
                if rec_prio > 200 or latest_rec.get("models") or _metadata_time_key(latest_rec) > _timestamp_key(archive_name):
                    record = latest_rec

        if not record and email:
            # Fallback 1: Registry
            record = metadata_by_account.get(email.lower())

        if not record and email:
            # Fallback 2: Latest general record (Cloud)
            record = metadata_by_email.get(email.lower())

        if record:
            rows.append(_row_from_metadata(record, archive_name, "cloud"))
        else:
            rows.append(_row_from_archive_name(archive_name, "cloud"))
    return rows


def _print_rows(rows: list[BackupRow], *, latest_only: bool, source: str) -> None:
    if not rows:
        console.print(f"[yellow]No backup archives found ({source}).[/]")
        return

    rows = _sort_rows(rows, latest_only=latest_only)

    table = Table(show_header=True, header_style="bold bright_magenta")
    table.add_column("Backup", style="bright_cyan", no_wrap=True)
    table.add_column("Email", style="bright_green", no_wrap=True)
    table.add_column("Quota", no_wrap=True)
    table.add_column("Penalty", justify="center")

    for row in rows:
        table.add_row(
            _display_archive(row.archive_name),
            row.email,
            _quota_text(row),
            row.penalty,
        )

    mode = "latest per email" if latest_only else "all archives"
    console.print(
        Panel(
            table,
            title=f"[bold bright_cyan]Available Backups ({source}, {mode})[/]",
            border_style="bright_cyan",
            expand=False,
        )
    )


def _print_directory_backups() -> None:
    dir_backup_path = os.path.expanduser(OLD_CONFIGS_DIR)
    if not os.path.isdir(dir_backup_path):
        cprint(NEON_YELLOW, f"Directory backup path not found: {dir_backup_path}")
        return

    try:
        dir_backups = [
            name
            for name in os.listdir(dir_backup_path)
            if os.path.isdir(os.path.join(dir_backup_path, name)) and ".gm" in name
        ]
    except OSError as exc:
        cprint(NEON_RED, f"Error reading directory backup path: {exc}")
        return

    if not dir_backups:
        cprint(NEON_YELLOW, f"No directory backups found in {dir_backup_path}")
        return

    table = Table(show_header=True, header_style="bold bright_magenta")
    table.add_column("Directory Backup", style="bright_cyan")
    for backup in sorted(dir_backups):
        table.add_row(backup)
    console.print(Panel(table, title="[bold yellow]Old Directory Backups[/]", border_style="yellow", expand=False))


def perform_list_backups(args: argparse.Namespace):
    latest_only = not bool(getattr(args, "all", False))
    if getattr(args, "cloud", False):
        _print_rows(_cloud_rows(args), latest_only=latest_only, source="cloud")
    else:
        _print_rows(_local_rows(getattr(args, "search_dir", DEFAULT_BACKUP_DIR)), latest_only=latest_only, source="local")
        if getattr(args, "show_dirs", False):
            _print_directory_backups()


def main():
    parser = argparse.ArgumentParser(description="List available Gemini backups.")
    parser.add_argument("--search-dir", default=DEFAULT_BACKUP_DIR, help=f"Directory to search for archive backups (default {DEFAULT_BACKUP_DIR})")
    parser.add_argument("--all", action="store_true", help="Show every archive instead of only the latest backup per email")
    parser.add_argument("--show-dirs", action="store_true", help="Also show legacy directory backups from ~/.gemini-manager-old")
    parser.add_argument("--cloud", action="store_true", help="List backups from Cloud (B2)")
    parser.add_argument("--bucket", help="B2 Bucket Name")
    parser.add_argument("--b2-id", help="B2 Key ID (or set env GEMINI_B2_KEY_ID)")
    parser.add_argument("--b2-key", help="B2 App Key (or set env GEMINI_B2_APP_KEY)")
    args = parser.parse_args()

    perform_list_backups(args)


if __name__ == "__main__":
    main()
