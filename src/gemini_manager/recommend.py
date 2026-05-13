from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional
import datetime
from .ui import console, NEON_RED
from .cooldown import get_cooldown_data, COOLDOWN_HOURS
from .reset_helpers import get_all_resets

class AccountStatus(Enum):
    READY = auto()
    SCHEDULED = auto()
    COOLDOWN = auto()

@dataclass
class Recommendation:
    email: str
    status: AccountStatus
    last_used: Optional[datetime.datetime]
    next_reset: Optional[datetime.datetime]

def get_recommendation() -> Optional[Recommendation]:
    """
    Identifies the "Next Best Account" based on:
    1. Status: READY > SCHEDULED > COOLDOWN (we only return READY usually, or best available?)
       Actually, strictly speaking, if an account is in Cooldown, it's not ready.
       If it has a Scheduled reset in the future, it might be effectively in cooldown until then.
       So we prioritize READY accounts.
    2. LRU: Among READY accounts, pick the one with oldest last_used timestamp (or None).
    """

    # 1. Gather Data
    cooldown_map = get_cooldown_data() # {email: iso_str}
    resets_list = get_all_resets()     # [{email: ..., reset_ist: ...}]

    # 2. Identify all known accounts
    all_emails = set(cooldown_map.keys())
    for r in resets_list:
        if r.get("email"):
            all_emails.add(r["email"].lower())

    if not all_emails:
        return None

    candidates = []
    now = datetime.datetime.now().astimezone()

    for email in all_emails:
        # Determine First/Last timestamps
        first_used_dt = None
        last_used_dt = None
        if email in cooldown_map:
            entry_data = cooldown_map[email]
            if isinstance(entry_data, dict):
                first_ts_raw = entry_data.get("first_used")
                last_ts_raw = entry_data.get("last_used")
            else:
                first_ts_raw = last_ts_raw = entry_data

            try:
                if first_ts_raw:
                    first_used_dt = datetime.datetime.fromisoformat(first_ts_raw)
                    if first_used_dt.tzinfo is None:
                        first_used_dt = first_used_dt.replace(tzinfo=datetime.timezone.utc)
                if last_ts_raw:
                    last_used_dt = datetime.datetime.fromisoformat(last_ts_raw)
                    if last_used_dt.tzinfo is None:
                        last_used_dt = last_used_dt.replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                pass

        # Determine Cooldown Status (24h from FIRST use)
        is_locked = False
        if first_used_dt:
            unlock_time = first_used_dt + datetime.timedelta(hours=COOLDOWN_HOURS)
            if unlock_time > now:
                is_locked = True

        # Determine Scheduled Status
        next_reset_dt = None
        has_future_reset = False

        my_resets = []
        for r in resets_list:
            if r.get("email", "").lower() == email:
                try:
                    # Ignore "Auto-detected" resets in recommendation logic because
                    # they are redundant with 'is_locked' and might be less accurate
                    if "Auto-detected" in r.get("saved_string", ""):
                        continue
                        
                    r_ts = datetime.datetime.fromisoformat(r["reset_ist"])
                    if r_ts.tzinfo is None:
                        r_ts = r_ts.astimezone()
                    my_resets.append(r_ts)
                except Exception:
                    pass

        for r_ts in sorted(my_resets):
            if r_ts > now:
                next_reset_dt = r_ts
                has_future_reset = True
                break

        # Assign Status
        if is_locked or (has_future_reset and next_reset_dt > now):
            # If it's tool-locked or gm-locked
            if is_locked:
                status = AccountStatus.COOLDOWN
            else:
                status = AccountStatus.SCHEDULED
        else:
            status = AccountStatus.READY

        candidates.append(Recommendation(
            email=email,
            status=status,
            last_used=last_used_dt,
            next_reset=next_reset_dt
        ))

    # 3. Filter and Sort
    # We want:
    #  Priority 1: READY
    #  Priority 2: LRU (Least Recently Used) -> Oldest last_used first. None (never used) is oldest.

    ready_accounts = [c for c in candidates if c.status == AccountStatus.READY]

    if not ready_accounts:
        # No ready accounts. Return None?
        # Or should we return the one that becomes ready soonest?
        # Requirement says "suggest the most rested account (Green & Least Recently Used)".
        # "Green" implies Ready. So if none are green, maybe we shouldn't recommend any to *use* now.
        return None

    # Sort ready accounts by last_used (ascending). None comes first?
    # sorted key needs to handle None.
    # We want None (never used) to be treated as "very old" (small timestamp).

    # Helper for sorting
    def sort_key(rec):
        if rec.last_used is None:
            # Min aware datetime
            return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
        return rec.last_used

    ready_accounts.sort(key=sort_key)

    return ready_accounts[0]

def do_recommend(args=None):
    """
    CLI command to print the recommendation.
    """
    rec = get_recommendation()

    console.print()
    console.print("[bold white]🤖 Smart Account Recommendation[/]")

    if not rec:
        console.print(f"[{NEON_RED}]No 'Green' (Ready) accounts available right now.[/]")
        console.print("Check [bold]gm resets[/] to see when accounts will become available.")
        return

    # It's Green/Ready
    console.print(f"The next best account is: [bold green]{rec.email}[/]")

    if rec.last_used:
        # formatting
        diff = datetime.datetime.now().astimezone() - rec.last_used
        days = diff.days
        hours = diff.seconds // 3600
        console.print(f"Last used: [dim]{days}d {hours}h ago[/]")
    else:
        console.print("Last used: [bold]Never / Unknown[/] (Most Rested)")

    console.print("[green]✓ Account is Ready to use[/]")
    console.print()
