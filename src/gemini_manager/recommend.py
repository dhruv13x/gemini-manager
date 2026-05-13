from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional
import datetime
import argparse
from .ui import console, NEON_RED
from .cooldown import get_cooldown_data, COOLDOWN_HOURS
from .reset_helpers import get_all_resets
from .metadata import load_cloud_metadata, load_local_metadata, latest_metadata_by_email

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
    quota_percent_left: Optional[int] = None
    flash_percent_left: Optional[int] = None
    source: str = "legacy"


def _parse_dt(value) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.timezone.utc).astimezone()
        return dt.astimezone()
    except Exception:
        return None


def _last_used_for(email: str, cooldown_map) -> Optional[datetime.datetime]:
    if email not in cooldown_map:
        return None
    entry_data = cooldown_map[email]
    if isinstance(entry_data, dict):
        raw = entry_data.get("last_used") or entry_data.get("first_used")
    else:
        raw = entry_data
    return _parse_dt(raw)


def _first_used_for(email: str, cooldown_map) -> Optional[datetime.datetime]:
    if email not in cooldown_map:
        return None
    entry_data = cooldown_map[email]
    raw = entry_data.get("first_used") if isinstance(entry_data, dict) else entry_data
    return _parse_dt(raw)


def _metadata_recommendation(args=None) -> Optional[Recommendation]:
    records = []
    if args and getattr(args, "cloud", False):
        try:
            from .cloud_factory import get_cloud_provider

            provider = get_cloud_provider(args)
            if provider:
                records.extend(load_cloud_metadata(provider))
        except Exception:
            pass

    backup_dir = getattr(args, "backup_dir", None)
    records.extend(load_local_metadata(backup_dir) if backup_dir else load_local_metadata())
    by_email = latest_metadata_by_email(records)
    if not by_email:
        return None

    cooldown_map = get_cooldown_data()
    now = datetime.datetime.now().astimezone()
    candidates = []

    for email, meta in by_email.items():
        first_used = _first_used_for(email, cooldown_map)
        last_used = _last_used_for(email, cooldown_map)
        tool_locked_until = first_used + datetime.timedelta(hours=COOLDOWN_HOURS) if first_used else None
        next_reset = _parse_dt(meta.get("next_available_at") or meta.get("reset_at"))

        models = meta.get("models", {}) or {}
        flash_info = models.get("Flash") if isinstance(models.get("Flash"), dict) else {}
        flash_percent = None
        if flash_info.get("percent") is not None:
            try:
                flash_percent = int(flash_info.get("percent"))
            except Exception:
                flash_percent = None

        quota_values = [
            int(info.get("percent", 0))
            for info in models.values()
            if isinstance(info, dict) and info.get("percent") is not None
        ]
        # Treat percentages as 'used'. An account has quota if at least one model is < 100% used.
        min_used = min(quota_values) if quota_values else None
        has_model_quota = min_used is not None and min_used < 100

        status = AccountStatus.READY
        if tool_locked_until and tool_locked_until > now:
            status = AccountStatus.COOLDOWN
            if not next_reset or tool_locked_until > next_reset:
                next_reset = tool_locked_until
        elif not has_model_quota and next_reset and next_reset > now:
            status = AccountStatus.COOLDOWN

        candidates.append(Recommendation(
            email=email,
            status=status,
            last_used=last_used,
            next_reset=next_reset,
            quota_percent_left=min_used, # This is now actually 'min_used'
            flash_percent_left=flash_percent, # This is 'flash_used'
            source="metadata",
        ))

    ready = [c for c in candidates if c.status == AccountStatus.READY]
    pool = ready if ready else candidates

    def sort_key(rec):
        last_used = rec.last_used or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
        next_reset = rec.next_reset or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
        flash_rank = rec.flash_percent_left if rec.flash_percent_left is not None else 101
        return (
            rec.status != AccountStatus.READY,
            flash_rank,
            next_reset if rec.status != AccountStatus.READY else last_used,
            rec.email,
        )

    pool.sort(key=sort_key)
    return pool[0]

def get_recommendation(args=None) -> Optional[Recommendation]:
    """
    Identifies the "Next Best Account" based on:
    1. Status: READY > SCHEDULED > COOLDOWN (we only return READY usually, or best available?)
       Actually, strictly speaking, if an account is in Cooldown, it's not ready.
       If it has a Scheduled reset in the future, it might be effectively in cooldown until then.
       So we prioritize READY accounts.
    2. LRU: Among READY accounts, pick the one with oldest last_used timestamp (or None).
    """

    metadata_rec = _metadata_recommendation(args)
    if metadata_rec:
        return metadata_rec

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

def _format_remaining(dt: Optional[datetime.datetime]) -> str:
    if not dt:
        return "unknown"
    delta = dt - datetime.datetime.now().astimezone()
    seconds = int(delta.total_seconds())
    if seconds <= 0:
        return "now"
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h {minutes}m"
    return f"{hours}h {minutes}m"


def do_recommend(args=None):
    """
    CLI command to print the recommendation.
    """
    rec = get_recommendation(args)

    console.print()
    console.print("[bold white]🤖 Smart Account Recommendation[/]")

    if not rec:
        console.print(f"[{NEON_RED}]No 'Green' (Ready) accounts available right now.[/]")
        console.print("Check [bold]gm resets[/] to see when accounts will become available.")
        return

    console.print(f"The next best account is: [bold green]{rec.email}[/]")
    rec_status = rec.status if isinstance(rec.status, AccountStatus) else AccountStatus.READY
    console.print(f"Status: [bold]{rec_status.name}[/]")
    if isinstance(rec.quota_percent_left, int):
        console.print(f"Lowest usage (any model): [bold]{rec.quota_percent_left}% used[/]")
    if isinstance(rec.flash_percent_left, int):
        console.print(f"Flash usage: [bold]{rec.flash_percent_left}% used[/]")
    if isinstance(rec.next_reset, datetime.datetime):
        console.print(f"Available in: [bold]{_format_remaining(rec.next_reset)}[/]")
    source = rec.source if isinstance(rec.source, str) else "legacy"
    console.print(f"Source: [dim]{source}[/]")

    if rec.last_used:
        # formatting
        diff = datetime.datetime.now().astimezone() - rec.last_used
        days = diff.days
        hours = diff.seconds // 3600
        console.print(f"Last used: [dim]{days}d {hours}h ago[/]")
    else:
        console.print("Last used: [bold]Never / Unknown[/] (Most Rested)")

    if rec_status == AccountStatus.READY:
        console.print("[green]✓ Account is Ready to use[/]")
    else:
        console.print("[yellow]No account is fully ready. This account becomes available soonest.[/]")
    console.print()

    if args and (getattr(args, "use", False) or getattr(args, "restore", False)):
        restore_args = argparse.Namespace(
            email=rec.email,
            cloud=getattr(args, "cloud", False),
            dest=getattr(args, "dest", None),
            search_dir=getattr(args, "backup_dir", None),
            from_dir=None,
            from_archive=None,
            dry_run=getattr(args, "dry_run", False),
            force=getattr(args, "force", False),
            full=getattr(args, "restore", False),
            auth_only=not getattr(args, "restore", False),
            bucket=getattr(args, "bucket", None),
            b2_id=getattr(args, "b2_id", None),
            b2_key=getattr(args, "b2_key", None),
            auto=False,
        )
        from .restore import perform_restore

        perform_restore(restore_args)
