
import datetime
from typing import Dict, List
from collections import defaultdict
from . import history
from .ui import console, NEON_CYAN, NEON_GREEN, NEON_YELLOW, NEON_MAGENTA

def do_stats(args=None):
    """
    Displays usage statistics (switches) over the last 7 days.
    """
    days_to_show = 7
    events = history.get_events_last_n_days(days_to_show)

    if not events:
        console.print(f"[bold yellow]No usage history found for the last {days_to_show} days.[/]")
        return

    # Aggregate by day
    # We want to show 7 days up to today, even if count is 0
    now = datetime.datetime.now().astimezone()
    date_counts = defaultdict(int)

    for e in events:
        ts_str = e.get("timestamp")
        if not ts_str:
            continue
        try:
            ts = datetime.datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=datetime.timezone.utc)
            
            # Localize to machine time
            local_ts = ts.astimezone()
            date_key = local_ts.strftime("%Y-%m-%d")
            date_counts[date_key] += 1
        except ValueError:
            continue

    # Generate list of last 7 dates
    dates = []
    for i in range(days_to_show):
        d = now - datetime.timedelta(days=i)
        dates.append(d.strftime("%Y-%m-%d"))

    dates.reverse() # Oldest first

    console.print(f"\n[bold white]📈 Usage Statistics (Last {days_to_show} Days)[/]\n")

    max_count = max(date_counts.values()) if date_counts else 0

    # Simple normalization for bar width if counts are huge
    max_bar_width = 40

    for date_str in dates:
        count = date_counts[date_str]

        # Calculate bar length
        if max_count > 0:
            bar_len = int((count / max_count) * max_bar_width)
        else:
            bar_len = 0

        if count > 0:
            bar = "█" * bar_len
            if bar_len == 0: bar = "▏" # Tiny bar for non-zero count
            color = "bold green"
        else:
            bar = ""
            color = "dim"

        # Format: YYYY-MM-DD | ████ (4)
        # Shorten date to MM-DD for display
        display_date = date_str[5:] # Remove YYYY-

        console.print(f"  [cyan]{display_date}[/] | [{color}]{bar}[/] ({count})")

    console.print()
