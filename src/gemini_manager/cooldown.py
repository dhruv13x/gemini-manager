#!/usr/bin/env python3
# src/gemini_manager/cooldown.py

import os
import json
import datetime
from typing import Dict, Optional

from .ui import cprint, console, NEON_CYAN, NEON_GREEN, NEON_YELLOW, NEON_RED, RESET
from .b2 import B2Manager
from .credentials import resolve_credentials
from .reset_helpers import get_all_resets, remove_entry_by_id, sync_resets_with_cloud
from . import history

# ... existing code ...

from rich.prompt import Confirm

def do_reset_all(args):
    """
    Nuclear reset: Wipes all cooldown and reset data from local and cloud.
    """
    banner_text = "[bold red]⚠️  WARNING: This will wipe ALL account activity and reset data. ⚠️[/]"
    console.print(Panel(Align.center(banner_text), border_style="red"))
    
    if not Confirm.ask("[bold yellow]Are you absolutely sure you want to proceed?[/]"):
        cprint(NEON_YELLOW, "Aborted.")
        return

    cprint(NEON_CYAN, "Performing nuclear reset...")

    # 1. Wipe Local Cooldowns
    path = os.path.expanduser(COOLDOWN_FILE)
    try:
        with open(path, "w") as f:
            json.dump({}, f)
        cprint(NEON_GREEN, "[OK] Local cooldown state wiped.")
    except Exception as e:
        cprint(NEON_RED, f"[ERROR] Failed to wipe local cooldowns: {e}")

    # 2. Wipe Local Resets
    # Import here to avoid circular imports if any
    from .reset_helpers import _save_store
    try:
        _save_store([])
        cprint(NEON_GREEN, "[OK] Local reset history wiped.")
    except Exception as e:
        cprint(NEON_RED, f"[ERROR] Failed to wipe local resets: {e}")

    # 3. Wipe Cloud (if credentials available)
    try:
        key_id, app_key, bucket_name = resolve_credentials(args)
        if key_id and app_key and bucket_name:
            cprint(NEON_CYAN, "Wiping cloud data...")
            b2 = B2Manager(key_id, app_key, bucket_name)
            
            # Overwrite both cloud files with empty state
            b2.upload_string("{}", "gm-cooldown.json")
            b2.upload_string("[]", "gm-resets.json")
            
            cprint(NEON_GREEN, "[OK] Cloud data wiped successfully.")
    except Exception as e:
        # Creds might not be set, usually fine to skip silent unless explicitly requested
        pass

    cprint(NEON_GREEN, "\n✨ System clean. All account timers have been reset.")

def do_remove_account(email: str, args=None):
    """
    Removes an account from the dashboard.
    1. Removes from 'gm-resets.json' (Log)
    2. Removes from 'gm-cooldown.json' (State)
    3. Syncs both changes to cloud (if credentials available)
    """
    cprint(NEON_CYAN, f"Removing account '{email}' from dashboard...")
    
    # 1. Remove from Resets (Logbook)
    removed_resets = remove_entry_by_id(email)
    if removed_resets:
        cprint(NEON_GREEN, f"[OK] Removed reset history for {email}")
    else:
        cprint(NEON_YELLOW, f"[INFO] No reset history found for {email}")

    # 2. Remove from Cooldowns (State)
    path = os.path.expanduser(COOLDOWN_FILE)
    data = get_cooldown_data()
    
    if email in data:
        del data[email]
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(data, f, indent=4)
            cprint(NEON_GREEN, f"[OK] Removed cooldown state for {email}")
        except IOError as e:
            cprint(NEON_RED, f"[ERROR] Failed to update local file: {e}")
    else:
        cprint(NEON_YELLOW, f"[INFO] No active cooldown state found for {email}")

    # 3. Cloud Sync (Both files)
    # Only attempt if we have credentials in args (or environment)
    try:
        key_id, app_key, bucket_name = resolve_credentials(args)
        if key_id and app_key and bucket_name:
            cprint(NEON_CYAN, "Syncing removal to cloud...")
            
            # 3a. Sync Cooldowns (Direct Upload to ensure removal sticks)
            _sync_cooldown_file(direction='upload', args=args)
            
            # 3b. Sync Resets (Direct Upload to ensure removal sticks)
            try:
                b2 = B2Manager(key_id, app_key, bucket_name)
                # Overwrite cloud file with clean local state
                local_resets = get_all_resets()
                resets_json_str = json.dumps(local_resets, ensure_ascii=False, indent=2)
                b2.upload_string(resets_json_str, "gm-resets.json")
            except Exception as e:
                 cprint(NEON_RED, f"[WARN] Failed to sync resets removal: {e}")
                 
            cprint(NEON_GREEN, "Cloud sync complete.")
    except Exception:
        # Creds not available, skip silent
        pass
from rich.table import Table
from rich.panel import Panel
from rich.align import Align


from .config import NEON_CYAN, NEON_YELLOW, NEON_GREEN, NEON_RED, RESET, COOLDOWN_FILE

# File to store cooldown data
CLOUD_COOLDOWN_FILENAME = "gm-cooldown.json"
COOLDOWN_HOURS = 24


def _sync_cooldown_file(direction: str, args):
    """
    Private helper to sync the cooldown file with B2 cloud storage.

    Args:
        direction: 'upload' or 'download'.
        args: Command-line arguments containing B2 credentials.
    """
    try:
        key_id, app_key, bucket_name = resolve_credentials(args)
        if not all([key_id, app_key, bucket_name]):
            cprint(NEON_YELLOW, "Warning: Cloud credentials not fully configured. Skipping cloud sync.")
            return

        b2 = B2Manager(key_id, app_key, bucket_name)
        local_path = os.path.expanduser(COOLDOWN_FILE)

        if direction == "download":
            cprint(NEON_CYAN, f"Downloading latest cooldown file from B2 bucket '{bucket_name}'...")
            content = b2.download_to_string(CLOUD_COOLDOWN_FILENAME)
            
            if content is None:
                cprint(NEON_YELLOW, "No cooldown file found in the cloud. Using local version.")
            else:
                try:
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    with open(local_path, "w") as f:
                        f.write(content)
                    cprint(NEON_GREEN, "Cooldown file synced from cloud.")
                except IOError as e:
                    cprint(NEON_RED, f"Error writing local cooldown file: {e}")

        elif direction == "upload":
            if not os.path.exists(local_path):
                cprint(NEON_YELLOW, "Local cooldown file not found. Skipping upload.")
                return
            cprint(NEON_CYAN, f"Uploading cooldown file to B2 bucket '{bucket_name}'...")
            try:
                b2.upload(local_path, CLOUD_COOLDOWN_FILENAME)
                cprint(NEON_GREEN, "Cooldown file synced to cloud.")
            except Exception as e:
                cprint(NEON_RED, f"Error uploading cooldown file: {e}")

    except Exception as e:
        cprint(NEON_RED, f"An unexpected error occurred during cloud sync: {e}")


def get_cooldown_data() -> Dict[str, str]:
    """
    Reads the cooldown data from the JSON file.

    Returns:
        A dictionary mapping email addresses to their last switch timestamp (ISO 8601).
        Returns an empty dictionary if the file doesn't exist or is invalid.
    """
    path = os.path.expanduser(COOLDOWN_FILE)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except (json.JSONDecodeError, IOError):
        return {}

def record_switch(email: str, args=None):
    """
    Records an account switch using a "merge-before-write" strategy for cloud sync.
    It downloads the latest state from the cloud, adds the new entry, and uploads.

    Args:
        email: The email address of the account that has become active.
        args: Optional command-line arguments for cloud credentials.
    """
    if not email:
        return
        
    # Record to history log
    history.record_event(email, "switch")

    # If cloud is configured, sync down the master file first to merge with it.
    if args:
        _sync_cooldown_file(direction='download', args=args)
        
    path = os.path.expanduser(COOLDOWN_FILE)
    # Now, get the most up-to-date data (either from cloud or local).
    data = get_cooldown_data()
    
    now = datetime.datetime.now().astimezone()
    now_iso = now.isoformat()

    # Get existing record or handle migration from old string-only format
    existing = data.get(email)
    if isinstance(existing, str):
        # Migrate old format to new dict format
        data[email] = {
            "first_used": existing,
            "last_used": now_iso
        }
    elif isinstance(existing, dict):
        # Already in new format, update last_used
        data[email]["last_used"] = now_iso
        
        # Reset first_used if it's been more than 24 hours since the last session start
        try:
            first_ts = datetime.datetime.fromisoformat(existing.get("first_used", now_iso))
            if (now - first_ts).total_seconds() > 86400: # 24 hours
                data[email]["first_used"] = now_iso
        except Exception:
            data[email]["first_used"] = now_iso
    else:
        # New account
        data[email] = {
            "first_used": now_iso,
            "last_used": now_iso
        }
    
    try:
        # Write the newly merged data back to the local file.
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except IOError as e:
        cprint(NEON_RED, f"Error: Could not write to local cooldown file at {path}: {e}")
        return # Don't proceed to upload if local write failed

    # If cloud is configured, sync the merged file back up.
    if args:
        _sync_cooldown_file(direction='upload', args=args)

def do_cooldown_list(args=None):
    """
    Displays the Master Dashboard: merged view of Cooldowns (Switch events) and Scheduled Resets.
    """
    # 1. Sync if requested
    if args and getattr(args, 'cloud', False):
        _sync_cooldown_file(direction='download', args=args)
        # Also sync resets
        try:
            key_id, app_key, bucket_name = resolve_credentials(args)
            if key_id and app_key and bucket_name:
                b2 = B2Manager(key_id, app_key, bucket_name)
                sync_resets_with_cloud(b2)
        except Exception as e:
             cprint(NEON_RED, f"[WARN] Failed to sync resets: {e}")

    # 2. Load Data
    cooldown_map = get_cooldown_data() # {email: last_switch_iso}
    resets_list = get_all_resets()     # [{email:..., reset_ist:...}, ...]

    all_emails = set(cooldown_map.keys())
    for entry in resets_list:
        if entry.get("email"):
            all_emails.add(entry["email"].lower())

    if not all_emails:
        cprint(NEON_YELLOW, "No account data found (switches or resets).")
        return

    # 3. Build Table
    table = Table(show_header=True, header_style="bold white", border_style="blue", padding=(0, 1))
    table.add_column("Account", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Availability", style="white")
    table.add_column("First Used", style="dim")
    table.add_column("Last Used", style="dim")
    table.add_column("Next Scheduled Reset", style="magenta")

    now = datetime.datetime.now().astimezone()
    
    # Helper for relative time
    def format_delta(delta):
        s = int(delta.total_seconds())
        if s < 0: return "passed"
        h, r = divmod(s, 3600)
        m, _ = divmod(r, 60)
        return f"In {h}h {m}m"

    def format_ago(delta):
        s = int(delta.total_seconds())
        if s < 60: return "Just now"
        if s < 3600: return f"{s//60}m ago"
        if s < 86400: return f"{s//3600}h ago"
        return f"{s//86400}d ago"

    sorted_emails = sorted(list(all_emails))

    for email in sorted_emails:
        # --- 1. Tool-Enforced Quota Reset (First Used + 24h Rule) ---
        first_ts = None
        last_ts = None
        tool_unlock_time = None
        
        if email in cooldown_map:
            entry_data = cooldown_map[email]
            if isinstance(entry_data, dict):
                first_ts_raw = entry_data.get("first_used")
                last_ts_raw = entry_data.get("last_used")
            else:
                first_ts_raw = last_ts_raw = entry_data

            try:
                if first_ts_raw:
                    first_ts = datetime.datetime.fromisoformat(first_ts_raw)
                    if first_ts.tzinfo is None:
                        first_ts = first_ts.replace(tzinfo=datetime.timezone.utc)
                    first_ts = first_ts.astimezone()
                    # Quota Reset is 24h from FIRST use
                    tool_unlock_time = first_ts + datetime.timedelta(hours=COOLDOWN_HOURS)
                
                if last_ts_raw:
                    last_ts = datetime.datetime.fromisoformat(last_ts_raw)
                    if last_ts.tzinfo is None:
                        last_ts = last_ts.replace(tzinfo=datetime.timezone.utc)
                    last_ts = last_ts.astimezone()
            except ValueError:
                pass

        # --- 2. Hard Resets (Captured from Gemini) ---
        manual_reset_dt = None
        auto_reset_dt = None
        
        my_resets = []
        for r in resets_list:
            if r.get("email", "").lower() == email:
                try:
                    r_ts = datetime.datetime.fromisoformat(r["reset_ist"])
                    if r_ts.tzinfo is None:
                         r_ts = r_ts.astimezone()
                    else:
                         r_ts = r_ts.astimezone() # Ensure local
                    
                    is_auto = "Auto-detected" in r.get("saved_string", "")
                    my_resets.append((r_ts, is_auto))
                except Exception:
                    pass
        
        my_resets.sort(key=lambda x: x[0])
        for r_ts, auto in my_resets:
            if r_ts > now:
                if auto:
                    if not auto_reset_dt: auto_reset_dt = r_ts
                else:
                    if not manual_reset_dt: manual_reset_dt = r_ts

        # --- 3. Calculate Availability ---
        # Rule: Max(FirstUsed+24h, ManualReset)
        # We ignore auto_reset_dt for availability calculation because it's 
        # redundant with tool_unlock_time (and often less accurate for old data).
        final_unlock_time = tool_unlock_time
        if manual_reset_dt:
            if not final_unlock_time or manual_reset_dt > final_unlock_time:
                final_unlock_time = manual_reset_dt
        
        # Fallback: if somehow we have NO tool_unlock_time but have an auto_reset, use it.
        if not final_unlock_time and auto_reset_dt:
            final_unlock_time = auto_reset_dt

        availability_str = "Now"
        avail_style = "[bold green]Now[/]"
        is_locked = False

        if final_unlock_time and final_unlock_time > now:
            is_locked = True
            delta = final_unlock_time - now
            availability_str = format_delta(delta)
            avail_style = "[red]" + availability_str + "[/]"

        # --- 4. Format Display Columns ---
        first_used_str = first_ts.astimezone().strftime('%I:%M %p') if first_ts else "-"
        last_used_str = format_ago(now - last_ts) if last_ts else "-"

        # Next Scheduled Reset Column: Show both if they exist
        parts = []
        if manual_reset_dt:
            diff = manual_reset_dt - now
            parts.append(f"[magenta]{format_delta(diff)} (M)[/]")
        if auto_reset_dt:
            # Only show auto if it differs significantly from manual or tool_unlock
            diff = auto_reset_dt - now
            # If it's close to tool_unlock, it's just the 'system' cooldown
            parts.append(f"[dim]{format_delta(diff)} (A)[/]")
        
        next_reset_str = " / ".join(parts) if parts else "-"

        # Determine Status
        if is_locked:
            if manual_reset_dt and manual_reset_dt >= (tool_unlock_time or manual_reset_dt):
                status = "[bold yellow]🟡 SCHEDULED[/]"
            else:
                status = "[bold red]🔴 COOLDOWN[/]"
        else:
            status = "[bold green]🟢 READY[/]"

        table.add_row(email, status, avail_style, first_used_str, last_used_str, next_reset_str)

    console.print("\n[bold white]📊 Account Dashboard[/]")
    console.print(f"[dim]Current Local Time: {now.strftime('%I:%M %p')}[/]\n")
    console.print(table)
    console.print()


def parse_usage(usage_str: str):
    import re
    if not usage_str or usage_str == "N/A":
        return None
    res = {}
    pct_match = re.search(r"(\d+)%", usage_str)
    if pct_match:
        res["percent"] = int(pct_match.group(1))
    delta_match = re.search(r"\(\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*\)", usage_str)
    if delta_match:
        hours = int(delta_match.group(1)) if delta_match.group(1) else 0
        minutes = int(delta_match.group(2)) if delta_match.group(2) else 0
        res["reset_delta_seconds"] = hours * 3600 + minutes * 60
    return res

def update_cooldown_from_status(status_data: dict):
    from .reset_helpers import _load_store, _save_store
    import uuid
    import datetime

    email = status_data.get("email")
    if not email or email == "N/A":
        return

    now = datetime.datetime.now().astimezone()
    models = ["flash", "flash_lite", "pro"]
    max_reset_dt = None

    for model in models:
        usage = parse_usage(status_data.get(model, ""))
        if usage and "reset_delta_seconds" in usage:
            reset_dt = now + datetime.timedelta(seconds=usage["reset_delta_seconds"])
            # For model resets, we want the shortest cooldown to track when *any* model becomes available, or the longest? The prompt says "so we can detect accurately when this account will be available". Usually if any model resets, it becomes somewhat available, but let's track the longest reset time to be fully safe, or simply store it.
            if not max_reset_dt or reset_dt > max_reset_dt:
                max_reset_dt = reset_dt

    if max_reset_dt:
        entry = {
            "id": str(uuid.uuid4())[:8],
            "email": email,
            "saved_string": "Model usage reset detected",
            "reset_ist": max_reset_dt.isoformat(),
            "saved_at": now.isoformat()
        }

        entries = _load_store()
        # Keep existing manual or auto resets if they are further in future?
        # Let's clean older auto-detected ones for this email and add this one.
        new_entries = []
        for e in entries:
            if e.get("email") == email and ("Model usage reset detected" in e.get("saved_string", "") or "Auto-detected" in e.get("saved_string", "")):
                continue
            new_entries.append(e)
        new_entries.append(entry)
        _save_store(new_entries)
