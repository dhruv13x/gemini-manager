#!/usr/bin/env python3
# src/gemini_manager/cooldown.py

import os
import json
import datetime
from typing import Dict, Any

from .ui import cprint, console, NEON_CYAN, NEON_GREEN, NEON_YELLOW, NEON_RED, style_quota_percent
from .b2 import B2Manager
from .credentials import resolve_credentials
from .session import get_active_session
from .reset_helpers import get_all_resets, remove_entry_by_id, sync_resets_with_cloud
from .metadata import load_cloud_snapshots, load_cloud_states, load_local_snapshots, load_local_states, latest_entity_by_email
from . import history
from .config import NEON_CYAN, NEON_YELLOW, NEON_GREEN, NEON_RED, COOLDOWN_FILE

from rich.prompt import Confirm
from rich.table import Table
from rich.panel import Panel
from rich.align import Align

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
    except Exception:
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


# File to store cooldown data
CLOUD_COOLDOWN_FILENAME = "gm-cooldown.json"
COOLDOWN_HOURS = 24


def merge_cooldowns(local: Dict[str, Any], remote: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merges two cooldown maps. For each email, it keeps the one with the later 'last_used'.
    """
    merged = dict(local)
    for email, remote_entry in remote.items():
        if email not in merged:
            merged[email] = remote_entry
            continue
            
        local_entry = merged[email]
        
        # Helper to get timestamp for comparison
        def get_last_used(e):
            if isinstance(e, dict):
                return e.get("last_used") or e.get("first_used") or ""
            return e or "" # Legacy string format

        if get_last_used(remote_entry) > get_last_used(local_entry):
            merged[email] = remote_entry
            
    return merged

def sync_cooldown_with_cloud(args):
    """
    Bi-directional sync: Downloads cloud cooldowns, merges with local, and pushes back.
    """
    try:
        key_id, app_key, bucket_name = resolve_credentials(args)
        if not all([key_id, app_key, bucket_name]):
            return

        b2 = B2Manager(key_id, app_key, bucket_name)
        local_path = os.path.expanduser(COOLDOWN_FILE)

        cprint(NEON_CYAN, "Syncing cooldowns with cloud...")
        
        # 1. Download
        remote_content = b2.download_to_string(CLOUD_COOLDOWN_FILENAME)
        remote_data = {}
        if remote_content:
            try:
                remote_data = json.loads(remote_content)
            except json.JSONDecodeError:
                cprint(NEON_YELLOW, "[WARN] Cloud cooldown file was corrupt.")

        # 2. Merge
        local_data = get_cooldown_data()
        merged_data = merge_cooldowns(local_data, remote_data)

        # 3. Save Local
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "w") as f:
            json.dump(merged_data, f, indent=4)

        # 4. Upload
        try:
            b2.upload_string(json.dumps(merged_data), CLOUD_COOLDOWN_FILENAME)
            cprint(NEON_GREEN, "[OK] Cooldowns synced successfully!")
        except Exception as e:
            cprint(NEON_RED, f"[ERROR] Failed to upload cooldowns: {e}")

    except Exception as e:
        cprint(NEON_RED, f"Unexpected error during cooldown sync: {e}")

def _sync_cooldown_file(direction: str, args):
    """
    DEPRECATED: Use sync_cooldown_with_cloud for bi-directional sync.
    Private helper to sync the cooldown file with B2 cloud storage.
    """
    if direction == "download":
        sync_cooldown_with_cloud(args)
        return
    
    # Fallback for explicit upload if needed by some legacy calls
    try:
        key_id, app_key, bucket_name = resolve_credentials(args)
        if not all([key_id, app_key, bucket_name]): return
        b2 = B2Manager(key_id, app_key, bucket_name)
        local_path = os.path.expanduser(COOLDOWN_FILE)
        if os.path.exists(local_path):
            b2.upload(local_path, CLOUD_COOLDOWN_FILENAME)
    except Exception:
        pass


def get_cooldown_data() -> Dict[str, Any]:
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
        sync_cooldown_with_cloud(args)
        
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
        # Use explicit upload or unified sync
        try:
            key_id, app_key, bucket_name = resolve_credentials(args)
            if key_id and app_key and bucket_name:
                b2 = B2Manager(key_id, app_key, bucket_name)
                b2.upload_string(json.dumps(data), CLOUD_COOLDOWN_FILENAME)
        except Exception:
            pass

def do_cooldown_list(args=None):
    """
    Displays the Master Dashboard: merged view of Cooldowns (Switch events) and Scheduled Resets.
    """
    # 1. Sync if requested
    if args and getattr(args, 'cloud', False):
        sync_cooldown_with_cloud(args)
        
        # Also sync registry and resets
        try:
            key_id, app_key, bucket_name = resolve_credentials(args)
            if key_id and app_key and bucket_name:
                b2 = B2Manager(key_id, app_key, bucket_name)
                sync_resets_with_cloud(b2)
                
                # Layer 2: Sync Registry (Aggregated state)
                from .registry import sync_registry_with_cloud
                sync_registry_with_cloud(b2, direction="pull")
        except Exception:
             pass

    # 2. Composition of entities following Layered Authority hierarchy
    from .registry import get_registry
    registry_records = get_registry().get_all()
    
    local_states = load_local_states()
    local_snapshots = load_local_snapshots()
    
    # Authoritative ranking: Index > State > Snapshot
    all_records = list(registry_records)
    all_records.extend(local_states)
    all_records.extend(local_snapshots)
    
    metadata_by_email = latest_entity_by_email(all_records)

    # 2. Load Data
    cooldown_map = get_cooldown_data() # {email: last_switch_iso}
    resets_list = get_all_resets()     # [{email:..., reset_ist:...}, ...]

    all_emails = set(cooldown_map.keys())
    for entry in resets_list:
        if entry.get("email"):
            all_emails.add(entry["email"].lower())
    all_emails.update(metadata_by_email.keys())

    if not all_emails:
        cprint(NEON_YELLOW, "No account data found (switches or resets).")
        return

    # 3. Build Table
    table = Table(show_header=True, header_style="bold white", border_style="blue", padding=(0, 1))
    table.add_column("Account", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Usage", style="white")
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
    active_email = get_active_session()

    for email in sorted_emails:
        # --- 1. Tool-Enforced Quota Reset (First Used + 24h Rule) ---
        first_ts = None
        last_ts = None
        tool_unlock_time = None
        is_active = (active_email and active_email.lower() == email.lower())
        
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
        metadata_entry = metadata_by_email.get(email)
        metadata_reset_dt = None
        
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

        if metadata_entry:
            try:
                raw_reset = metadata_entry.get("next_available_at") or metadata_entry.get("reset_at")
                if raw_reset:
                    metadata_reset_dt = datetime.datetime.fromisoformat(raw_reset)
                    if metadata_reset_dt.tzinfo is None:
                        metadata_reset_dt = metadata_reset_dt.astimezone()
                    else:
                        metadata_reset_dt = metadata_reset_dt.astimezone()
            except Exception:
                metadata_reset_dt = None

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
        if metadata_reset_dt and (not final_unlock_time or metadata_reset_dt > final_unlock_time):
            final_unlock_time = metadata_reset_dt

        availability_str = "Now"
        avail_style = "[bold green]Now[/]"
        is_locked = False

        if final_unlock_time and final_unlock_time > now:
            is_locked = True
            delta = final_unlock_time - now
            availability_str = format_delta(delta)

            avail_style = "[white]" + availability_str + "[/]"

        live_entry = metadata_entry or next((r for r in resets_list if r.get("email", "").lower() == email and r.get("models")), None)
        has_model_quota = True # Assume quota unless explicitly exhausted
        
        if live_entry:
            model_lines = []
            captured_raw = live_entry.get("captured_at") or live_entry.get("saved_at")
            captured_dt = None
            if captured_raw:
                try:
                    captured_dt = datetime.datetime.fromisoformat(captured_raw)
                    captured_dt = captured_dt.astimezone() if captured_dt.tzinfo else captured_dt.astimezone()
                except Exception:
                    captured_dt = None

            exhausted_models = 0
            total_models = 0
            
            for m_name, m_info in live_entry.get("models", {}).items():
                p = m_info.get("percent", 0)
                total_models += 1
                if p >= 100: exhausted_models += 1
                
                p_styled = style_quota_percent(p, is_usage=True)
                m_short = m_name.replace("Flash Lite", "Lite").replace("Flash", "Flsh")

                m_reset_dt = None
                if m_info.get("reset_at"):
                    try:
                        m_reset_dt = datetime.datetime.fromisoformat(m_info["reset_at"]).astimezone()
                    except Exception:
                        m_reset_dt = None
                elif captured_dt is not None:
                    m_h, m_m = m_info.get("reset_h"), m_info.get("reset_m")
                    if m_h is not None and m_m is not None:
                        m_reset_dt = captured_dt + datetime.timedelta(hours=m_h, minutes=m_m)

                if m_reset_dt:
                    if m_reset_dt > now:
                        m_rem = format_delta(m_reset_dt - now)
                        model_lines.append(f"{m_short}:{p_styled} ({m_rem})")
                    else:
                        model_lines.append(f"{m_short}:{p_styled} (Ready)")
                else:
                    # Special case for Pro model on Free Tier accounts
                    if m_name == "Pro" and p >= 100:
                        model_lines.append(f"{m_short}:{p_styled} [dim](Limited)[/]")
                    else:
                        model_lines.append(f"{m_short}:{p_styled}")

            if total_models > 0 and exhausted_models == total_models:
                has_model_quota = False

            if model_lines:
                availability_str = "\n".join(model_lines)
                avail_style = "[white]" + availability_str + "[/]"

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
        if metadata_reset_dt and metadata_reset_dt > now:
            diff = metadata_reset_dt - now
            parts.append(f"[cyan]{format_delta(diff)} (Q)[/]")
        
        next_reset_str = " / ".join(parts) if parts else "-"

        # Determine Status
        if is_active:
            # If active, we only show COOLDOWN if it's REALLY exhausted (hard resets)
            # or if it's 100% used on all models.
            is_hard_locked = (manual_reset_dt and manual_reset_dt > now) or \
                             (metadata_reset_dt and metadata_reset_dt > now) or \
                             (not has_model_quota)
            
            if is_hard_locked:
                status = "[bold red]🔴 ACTIVE (Locked)[/]"
            else:
                status = "[bold green]🟢 ACTIVE[/]"
        elif is_locked:
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
