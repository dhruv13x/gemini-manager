#!/usr/bin/env python3
# src/gemini_manager/reset_helpers.py

"""
reset_helpers.py

Features:
 - Auto-capture reset times (flexible parsing) and optional email tag
 - Persist multiple entries to ~/.gemini_resets.json
 - Automatically expire/remove entries whose reset time has passed
 - List entries and show next reset (global or per-account)
 - Flexible capture: accepts piped text, argument text, or interactive paste

Usage (examples):
  gm --capture-reset "Access resets at 11:53 AM UTC dhruv13x@gmail.com"
  echo "Access resets at 11:53 AM UTC" | gm --capture-reset
  gm --list-resets
  gm --next-reset               # shows next upcoming reset across all accounts
  gm --next-reset dhruv@gmail.com
"""

from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional, List, Dict, Any
import json
import os
import re
import sys
import uuid
import subprocess

from .ui import banner, cprint
from .config import NEON_CYAN, NEON_YELLOW, NEON_GREEN, NEON_RED, RESETS_FILE

# Keep ISO timestamps in UTC for exact comparisons

# -------------------------
# run_cmd_safe (auto-capture)
# -------------------------
def run_cmd_safe(cmd: str, timeout: int = 30, capture: bool = True, detect_reset_time: bool = True) -> Tuple[int, str, str]:
    """
    Run shell command with timeout. Returns (rc, stdout, stderr).
    Automatically detects Gemini rate-limit messages and saves reset time.
    """
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=capture, text=True, timeout=timeout)
        out = proc.stdout or ""
        err = proc.stderr or ""

        # Auto-detect and save reset time from combined output
        if detect_reset_time:
            try:
                save_reset_time_from_output(out + err)
            except Exception:
                # never fail the caller because of our detection
                pass

        return proc.returncode, out, err

    except subprocess.TimeoutExpired as e:
        out = getattr(e, "output", "") or ""
        err = getattr(e, "stderr", "") or f"Timeout after {timeout}s"
        if isinstance(out, bytes):
            out = out.decode(errors="ignore")
        if isinstance(err, bytes):
            err = err.decode(errors="ignore")

        # try to capture reset time even on timeout
        if detect_reset_time:
            try:
                save_reset_time_from_output(out + err)
            except Exception:
                pass

        return 124, out, err

    except Exception as e:
        # capture exception text as well
        if detect_reset_time:
            try:
                save_reset_time_from_output(str(e))
            except Exception:
                pass
        return 1, "", str(e)

# ------------------------
# Helpers: storage & I/O
# ------------------------
def get_all_resets() -> List[Dict[str, Any]]:
    """Public accessor for reset entries."""
    return _load_store()

def _load_store() -> List[Dict[str, Any]]:
    try:
        if not os.path.exists(RESETS_FILE):
            return []
        with open(RESETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                return []
            # Convert keys: ensure reset_ist is parseable
            cleaned = []
            for e in data:
                if "reset_ist" in e:
                    try:
                        # parse; leave as string in the dict
                        datetime.fromisoformat(e["reset_ist"])
                        cleaned.append(e)
                    except Exception:
                        # skip invalid entry
                        continue
            return cleaned
    except Exception:
        return []

def _save_store(entries: List[Dict[str, Any]]):
    try:
        os.makedirs(os.path.dirname(RESETS_FILE), exist_ok=True)
        with open(RESETS_FILE, "w", encoding="utf-8", newline="\n") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except Exception as e:
        # non-fatal: just print a message
        cprint(NEON_YELLOW, f"[WARN] Failed to write store: {e}")

IST = timezone(timedelta(hours=5, minutes=30))

def _now_local() -> datetime:
    return datetime.now().astimezone()

# ------------------------
# Parsing helpers
# ------------------------
TIME_PATTERNS = [
    # 12-hour with AM/PM: 11:53 AM or 1:05PM
    r"(?P<h>\d{1,2}):(?P<m>\d{1,2})\s*(?P<ampm>AM|PM)",
    # 24-hour (or no AM/PM) 11:53 or 1:05
    r"(?P<h2>\d{1,2}):(?P<m2>\d{1,2})"
]

EMAIL_RE = re.compile(r"(?P<email>[\w.+-]+@[\w-]+\.[\w.-]+)")

def _parse_time_from_text(text: str) -> Optional[Tuple[int, int, Optional[str]]]:
    """
    Return (hour, minute, ampm_string) where ampm_string is "AM", "PM", or None.
    None indicates AM/PM was not explicitly provided in the input text.
    """
    txt = text.upper()
    # Try explicit AM/PM first
    m = re.search(r"(\d{1,2}):(\d{1,2})\s*(AM|PM)", txt)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        ampm = m.group(3)
        return (h, mi, ampm)
    # Fallback: bare hh:mm (no AM/PM)
    m2 = re.search(r"(\d{1,2}):(\d{1,2})", txt)
    if m2:
        h = int(m2.group(1))
        mi = int(m2.group(2))
        return (h, mi, None) # AM/PM not provided
    return None

def _normalize_minutes(m: int) -> int:
    # clamp minutes to 0-59
    if m < 0:
        return 0
    if m > 59:
        return 59
    return m

def _parse_email_from_text(text: str) -> Optional[str]:
    m = EMAIL_RE.search(text)
    if m:
        return m.group("email").strip().lower()
    return None

# ------------------------
# Entry creation & cleanup
# ------------------------
def _compute_next_local_for_time(hour: int, minute: int, ampm: Optional[str]=None) -> datetime:
    """
    Interpret hour/minute possibly with AM/PM. Return the next local datetime for that time.
    Times will be parsed and treated as local machine time.
    If AM/PM provided, convert to 24-hour, else assume given hour is already 0-23.
    Then build a datetime for today at that local time; if <= now, add 1 day.
    """
    now = _now_local()
    hour24 = hour
    if ampm: # Only apply AM/PM logic if ampm is explicitly given
        ampm = ampm.upper()
        if ampm == "AM":
            if hour == 12: # 12 AM is 00 in 24-hour
                hour24 = 0
            else:
                hour24 = hour % 12
        else:  # PM
            if hour == 12: # 12 PM is 12 in 24-hour
                hour24 = 12
            else:
                hour24 = (hour % 12) + 12
    # If ampm is None, assume hour is already in 24-hour format (0-23)
    
    minute = _normalize_minutes(minute)
    reset_dt = now.replace(hour=hour24, minute=minute, second=0, microsecond=0)
    if reset_dt <= now:
        reset_dt = reset_dt + timedelta(days=1)
    return reset_dt

def add_reset_entry(time_str_raw: str, email: Optional[str]=None, provided_ampm: Optional[str]=None) -> Dict[str,Any]:
    """
    time_str_raw: original captured string like "11:53 AM" or "11:5"
    email: optional email string
    provided_ampm: "AM", "PM" if interactively provided
    Returns the created entry.
    """
    parsed = _parse_time_from_text(time_str_raw)
    if not parsed:
        raise ValueError("Could not parse time from input")
    hour, minute, initial_ampm = parsed # Use initial_ampm from parsed text
    
    # Use provided_ampm if available, otherwise fall back to initial_ampm
    final_ampm = provided_ampm if provided_ampm else initial_ampm

    # if minutes were single-digit like 5 -> 05
    minute = _normalize_minutes(int(minute))
    reset_dt = _compute_next_local_for_time(int(hour), int(minute), final_ampm) # Pass final_ampm
    entry = {
        "id": str(uuid.uuid4())[:8],
        "email": email,
        "saved_string": time_str_raw.strip(),
        "reset_ist": reset_dt.isoformat(), # Keep key name for compat, but it stores local ISO
        "saved_at": _now_local().isoformat()
    }
    entries = _load_store()
    entries.append(entry)
    _save_store(entries)
    return entry

def cleanup_expired() -> List[Dict[str,Any]]:
    """
    Remove entries whose reset_ist <= now and rewrite store.
    Return list of removed entries.
    """
    entries = _load_store()
    now = _now_local()
    keep = []
    removed = []
    for e in entries:
        try:
            t = datetime.fromisoformat(e["reset_ist"])
            if t <= now:
                removed.append(e)
            else:
                keep.append(e)
        except Exception:
            # malformed entry -> remove
            removed.append(e)
    _save_store(keep)
    return removed

# ------------------------
# Public capture function (enhanced)
# ------------------------
def save_reset_time_from_output(text: str) -> bool:
    if not text or not text.strip():
        return False

    email = _parse_email_from_text(text)

    # First, try to parse the time from the text
    parsed = _parse_time_from_text(text)
    if not parsed:
        cprint(NEON_RED, "Could not find a valid time in the provided text.")
        return False

    hour, minute, ampm_from_text = parsed
    time_str_raw = f"{hour}:{minute:02d}" # Raw time string for add_reset_entry and prompt if needed

    final_ampm = ampm_from_text # Start with AM/PM found in text

    if not ampm_from_text: # AM/PM not explicitly provided in the text
        # If hour is between 1 and 12, it's ambiguous, so prompt
        if 1 <= hour <= 12:
            cprint(NEON_YELLOW, f"Ambiguous time '{time_str_raw}'. Please specify AM or PM (e.g., 'AM' or 'PM'):")
            user_ampm = input().strip().upper()
            if user_ampm in ("AM", "PM"):
                final_ampm = user_ampm
            else:
                cprint(NEON_RED, "Invalid AM/PM specified. Cannot record entry.")
                return False
        # If hour > 12 (e.g., 13-23), it's unambiguous 24-hour, no prompt needed.
        # final_ampm remains None, and _compute_next_local_for_time will handle it as 24h.

    try:
        entry = add_reset_entry(time_str_raw, email, final_ampm) # Pass final_ampm to add_reset_entry
        cprint(NEON_GREEN, f"[OK] Saved reset for {entry.get('email') or '<no-email>'} at {entry['reset_ist']}")
        return True
    except Exception as e:
        cprint(NEON_RED, f"[ERROR] Failed to save reset: {e}")
        return False

# ------------------------
# Listing & next-reset utilities
# ------------------------
def _load_and_cleanup_store() -> List[Dict[str,Any]]:
    # load then cleanup expired entries (auto expiry)
    removed = cleanup_expired()
    if removed:
        cprint(NEON_YELLOW, f"[INFO] Removed {len(removed)} expired reset entries.")
    return _load_store()

def do_list_resets():
    banner()
    entries = _load_and_cleanup_store()
    if not entries:
        cprint(NEON_YELLOW, "No reset schedules saved.")
        return
    cprint(NEON_CYAN, f"Saved reset entries ({len(entries)}):")
    now = _now_local() # Get current time once for efficiency
    for e in entries:
        id_ = e.get("id")
        email = e.get("email") or "<no-email>"
        # saved_at = e.get("saved_at") # This is an unused variable reported by vulture, I will remove it.
        reset_at_str = e.get("reset_ist")
        
        remaining_str = "Expired"
        try:
            reset_dt = datetime.fromisoformat(reset_at_str)
            # Display in local time format
            reset_at_display = reset_dt.strftime("%I:%M %p")
            
            delta = reset_dt - now
            if delta.total_seconds() > 0:
                total_seconds = int(delta.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                remaining_str = f"In {hours}h {minutes}m"
            
        except Exception:
            reset_at_display = reset_at_str # Fallback if parsing fails
            
        print(f"  {id_:8}  {email:25}  {reset_at_display:14}  {remaining_str:15}") # Removed IST suffix
    print()

def do_next_reset(identifier: Optional[str] = None):
    """
    If identifier is None -> show next upcoming reset across all entries.
    If identifier looks like an email or id, try to filter to that account.
    """
    banner()
    entries = _load_and_cleanup_store()
    if not entries:
        cprint(NEON_YELLOW, "No reset schedules saved.")
        return

    now = _now_local()

    # filter
    filtered = entries
    if identifier:
        ident = identifier.lower()
        # match by email or id prefix
        filtered = [e for e in entries if (e.get("email") and e["email"].lower() == ident) or e.get("id","").startswith(ident)]
        if not filtered:
            cprint(NEON_RED, f"[ERROR] No entries matching '{identifier}'")
            return

    # find next upcoming (min reset_ist)
    upcoming = []
    for e in filtered:
        try:
            t = datetime.fromisoformat(e["reset_ist"])
            upcoming.append((t, e))
        except Exception:
            continue
    if not upcoming:
        cprint(NEON_YELLOW, "No valid upcoming resets.")
        return
    upcoming.sort(key=lambda x: x[0])
    next_dt, next_entry = upcoming[0]

    # compute remaining
    delta = next_dt - now
    if delta.total_seconds() <= 0:
        cprint(NEON_YELLOW, "Next reset already passed; it has been expired and removed.")
        cleanup_expired()
        return

    total_seconds = int(delta.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60

    email = next_entry.get("email") or "<no-email>"
    id_ = next_entry.get("id")

    cprint(NEON_GREEN, f"\nNext reset for {email} (id={id_}): {hours} hours {minutes} minutes")
    cprint(NEON_CYAN, f"Reset time:         {next_dt.strftime('%I:%M %p')}")
    print()

def do_capture_reset(pasted_text: str = None):
    """
    Save a reset time from either an argument or stdin.
    Usage:
      gm --capture-reset "Access resets at 11:53 AM UTC."
      echo "Access resets at 11:53 AM UTC." | gm --capture-reset
    """
    banner()

    # Read argument or stdin
    if pasted_text:
        text = pasted_text
    else:
        # try reading from stdin if piped
        if not sys.stdin.isatty():
            text = sys.stdin.read()
        else:
            # interactive prompt fallback
            cprint(NEON_YELLOW, "Paste the 'Access resets at ... UTC' line and press Enter:")
            try:
                text = input().strip()
            except EOFError:
                text = ""

    if not text:
        cprint(NEON_RED, "[ERROR] No input provided.")
        return

    saved = save_reset_time_from_output(text)
    if saved:
        cprint(NEON_GREEN, "[OK] Reset time saved.")
    else:
        cprint(NEON_RED, "[ERROR] Could not parse reset time. Make sure the text contains 'Access resets at HH:MM AM/PM UTC'.")

# ------------------------
# Small utilities: remove by id/email
# ------------------------
def remove_entry_by_id(id_or_email: str) -> bool:
    entries = _load_store()
    lowered = id_or_email.lower()
    keep = []
    removed = False
    for e in entries:
        if (e.get("id","").startswith(id_or_email)) or (e.get("email") and e.get("email").lower() == lowered):
            removed = True
            continue
        keep.append(e)
    _save_store(keep)
    return removed

# ------------------------
# Automated Cooldown & Cloud Sync
# ------------------------
def add_24h_cooldown_for_email(email: str) -> Dict[str, Any]:
    """
    Adds a cooldown for the given email.
    It primarily tries to fetch accurate model reset times via get_live_status().
    If that fails, it falls back to 24h calculation (first_used + 24h or now + 24h).
    """
    now = _now_local()
    reset_dt = None
    saved_string = "Auto-detected 24h cooldown on account switch"

    try:
        from .status import get_live_status
        status = get_live_status()
        if status and status.get("email") == email:
            max_timedelta = None
            for m_data in status["models"].values():
                h, m = m_data.get("reset_h"), m_data.get("reset_m")
                if h is not None and m is not None:
                    td = timedelta(hours=h, minutes=m)
                    if max_timedelta is None or td > max_timedelta:
                        max_timedelta = td

            if max_timedelta is not None:
                reset_dt = now + max_timedelta
                saved_string = "Accurate live cooldown detected"
    except Exception:
        pass

    if reset_dt is None:
        reset_dt = now + timedelta(hours=24)

        # Try to honor the 24h rolling window from the FIRST use of the session
        try:
            # Local import to avoid circular dependency with cooldown.py
            from .cooldown import get_cooldown_data
            cd_data = get_cooldown_data()
            if email in cd_data:
                entry = cd_data[email]
                first_used_str = entry.get("first_used") if isinstance(entry, dict) else entry
                if first_used_str:
                    first_ts = datetime.fromisoformat(first_used_str)
                    if first_ts.tzinfo is None:
                        first_ts = first_ts.astimezone()

                    candidate_reset = first_ts + timedelta(hours=24)
                    # If the 24h window from first_used is still in the future, use it.
                    # If it's already passed, it means the session exceeded 24h or first_used is stale,
                    # so we fall back to the default now + 24h to ensure the account is locked after switch-out.
                    if candidate_reset > now:
                        reset_dt = candidate_reset
        except Exception:
            pass

    entry = {
        "id": str(uuid.uuid4())[:8],
        "email": email,
        "saved_string": saved_string,
        "reset_ist": reset_dt.isoformat(),
        "saved_at": now.isoformat()
    }
    
    entries = _load_store()
    # Remove existing entries for this email to avoid duplicates, 
    # assuming the new 24h cooldown is the most relevant authority.
    # actually, let's just append. The list/merge logic handles duplicates by 'latest' usually.
    # But to be clean, let's remove old ones for this email locally first.
    entries = [e for e in entries if e.get("email") != email]
    entries.append(entry)
    
    _save_store(entries)
    cprint(NEON_GREEN, f"[INFO] Started 24h cooldown for {email} (until {reset_dt.strftime('%d %b %I:%M %p')})")
    return entry

def save_live_status_to_resets(status: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Saves a live status dict (from get_live_status) to the resets store.
    """
    email = status.get("email")
    if not email:
        return None

    now = _now_local()
    
    # Prioritize 'Flash' for the main reset_ist, fallback to max of others
    target_timedelta = None
    models = status.get("models", {})
    
    if "Flash" in models:
        m_info = models["Flash"]
        h, m = m_info.get("reset_h"), m_info.get("reset_m")
        if h is not None and m is not None:
            target_timedelta = timedelta(hours=h, minutes=m)
    
    if target_timedelta is None:
        # Fallback to max of any available model
        for m_data in models.values():
            h, m = m_data.get("reset_h"), m_data.get("reset_m")
            if h is not None and m is not None:
                td = timedelta(hours=h, minutes=m)
                if target_timedelta is None or td > target_timedelta:
                    target_timedelta = td

    if target_timedelta is None:
        return None

    reset_dt = now + target_timedelta
    
    entry = {
        "id": str(uuid.uuid4())[:8],
        "email": email,
        "saved_string": "Live status capture",
        "reset_ist": reset_dt.isoformat(),
        "saved_at": now.isoformat(),
        "models": status.get("models", {})  # Store full model status
    }
    
    entries = _load_store()
    # Replace existing for this email
    entries = [e for e in entries if e.get("email") != email]
    entries.append(entry)
    _save_store(entries)
    return entry

def merge_resets(local: List[Dict], remote: List[Dict]) -> List[Dict]:
    """
    Merges two lists of resets.
    Strategy:
     - Use 'id' as the primary key for exact de-duplication.
     - For the same email, we allow multiple entries (e.g., Manual and Auto).
    """
    merged_map = {}
    
    for e in local + remote:
        eid = e.get("id")
        if not eid:
            # Fallback if ID is missing (shouldn't happen with new entries)
            eid = f"{e.get('email')}-{e.get('reset_ist')}"
            
        # If we have a collision on ID, we just keep the existing one (or latest).
        # Since local usually comes first in local+remote, local wins on ID collision.
        if eid not in merged_map:
            merged_map[eid] = e
            
    return list(merged_map.values())

def sync_resets_with_cloud(provider):
    """
    Downloads cloud cooldowns, merges with local, and pushes back.
    """
    CLOUD_FILE = "gm-resets.json"
    
    cprint(NEON_CYAN, "Syncing cooldowns with cloud...")
    
    # 1. Download
    remote_json_str = provider.download_to_string(CLOUD_FILE)
    remote_entries = []
    if remote_json_str:
        try:
            remote_entries = json.loads(remote_json_str)
            # Ensure it is a list, otherwise ignore it (e.g. if it was a dict from another tool)
            if not isinstance(remote_entries, list):
                cprint(NEON_YELLOW, "[WARN] Cloud file format mismatch (expected list). Ignoring remote data.")
                remote_entries = []
        except json.JSONDecodeError:
            cprint(NEON_YELLOW, "[WARN] Cloud cooldown file was corrupt. Overwriting.")
    
    # 2. Merge
    local_entries = _load_store()
    merged = merge_resets(local_entries, remote_entries)
    
    # 3. Save Local
    _save_store(merged)
    
    # 4. Upload
    try:
        merged_json_str = json.dumps(merged, ensure_ascii=False, indent=2)
        provider.upload_string(merged_json_str, CLOUD_FILE)
    except Exception as e:
        cprint(NEON_RED, f"[ERROR] Failed to upload cooldowns: {e}")

def handle_resets_command(args) -> bool:
    """
    Handles the 'resets' subcommand.
    Returns True if an action was taken, False if help should be shown.
    """
    if args.list:
        do_list_resets()
        return True
    elif args.remove is not None:
        key = args.remove[0]
        ok = remove_entry_by_id(key)
        if ok:
            cprint(NEON_CYAN, f"[OK] Removed entries matching: {key}")
        else:
            cprint(NEON_YELLOW, f"[WARN] No entries matched: {key}")
        return True
    elif args.next is not None:
        ident = args.next
        if ident == "*ALL*":
            ident = None
        do_next_reset(ident)
        return True
    elif args.add is not None:
        do_capture_reset(args.add)
        return True

    return False

# ------------------------
# End of file
# ------------------------
