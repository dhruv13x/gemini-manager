import re
import subprocess
import time
import os
import json
import uuid
import datetime
from typing import Optional, Tuple

from .ui import console, cprint, NEON_CYAN, NEON_GREEN, NEON_YELLOW, NEON_RED
from .config import COOLDOWN_FILE
from .reset_helpers import (
    _load_store,
    _save_store,
    _now_local,
    add_24h_cooldown_for_email,
)

SESSION = "gemini_capture"
COLS, ROWS = 120, 40


def sh(cmd: str, check=True):
    r = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}")
    return r


def sh_out(cmd: str) -> str:
    return sh(cmd).stdout


def capture() -> str:
    try:
        return sh_out(f"tmux capture-pane -t {SESSION} -p")
    except Exception:
        return ""


def wait_ready(timeout=30):
    start = time.time()
    stable = 0
    with console.status("[cyan]Waiting for Gemini prompt...[/cyan]", spinner="dots"):
        while True:
            out = capture()
            ready = (
                ">" in out or "›" in out
            ) and "Waiting for authentication" not in out
            stable = stable + 1 if ready else 0
            if stable >= 3:
                return out
            if time.time() - start > timeout:
                return out
            time.sleep(0.5)


def send_cmd(cmd: str):
    sh(f"tmux send-keys -t {SESSION} C-u")
    time.sleep(0.1)
    sh(f"tmux send-keys -t {SESSION} '{cmd}'")
    time.sleep(0.15)
    sh(f"tmux send-keys -t {SESSION} Enter")
    time.sleep(0.1)
    sh(f"tmux send-keys -t {SESSION} Enter")


def wait_for(cond, timeout=20):
    start = time.time()
    while True:
        out = capture()
        if cond(out):
            return out
        if time.time() - start > timeout:
            return out
        time.sleep(0.5)


def run_and_wait(cmd, condition):
    with console.status(f"[cyan]Running {cmd}...[/cyan]", spinner="dots"):
        for _ in range(3):
            send_cmd(cmd)
            time.sleep(0.5)
            out = capture()
            if "Usage: /stats" in out or "stats    Check session stats" in out:
                continue
            out = wait_for(condition)
            if condition(out):
                return out
            time.sleep(1)
        return out


def extract_email(text: str):
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return m.group(0) if m else None


def capture_live_status() -> Tuple[str, str, str, str]:
    """
    Captures live status from the gemini CLI.
    Returns: (email, flash, flash_lite, pro)
    """
    try:
        subprocess.run(["tmux", "-V"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        cprint(
            NEON_YELLOW,
            "tmux is not installed or not in PATH. Required for live status capture.",
        )
        return "N/A", "N/A", "N/A", "N/A"

    sh(f"tmux kill-session -t {SESSION}", check=False)

    try:
        sh(f"tmux new-session -d -s {SESSION} -x {COLS} -y {ROWS} 'gemini'")
    except RuntimeError as e:
        cprint(NEON_RED, f"Failed to start gemini in tmux: {e}")
        return "N/A", "N/A", "N/A", "N/A"

    if SESSION not in sh_out("tmux ls || true"):
        cprint(NEON_RED, "Failed to find tmux session.")
        return "N/A", "N/A", "N/A", "N/A"

    try:
        wait_ready()

        output_stats = run_and_wait(
            "/stats", lambda o: "Session Stats" in o or "Auth Method" in o
        )
        email = extract_email(output_stats)
        if not email:
            email = extract_email(capture())
        if not email:
            output_stats_model = run_and_wait(
                "/stats model", lambda o: "Auth Method" in o or "No API calls" in o
            )
            email = extract_email(output_stats_model)
        email = email if email else "N/A"

        output_model = run_and_wait("/model", lambda o: "Model usage" in o)
        flash_match = re.search(r"Flash\s+.*?(\d+)%\s+(.*)", output_model)
        flash_lite_match = re.search(r"Flash Lite\s+.*?(\d+)%\s+(.*)", output_model)
        pro_match = re.search(r"Pro\s+.*?(\d+)%\s+(.*)", output_model)

        flash = (
            f"{flash_match.group(1)}% {flash_match.group(2).strip()}"
            if flash_match
            else "N/A"
        )
        flash_lite = (
            f"{flash_lite_match.group(1)}% {flash_lite_match.group(2).strip()}"
            if flash_lite_match
            else "N/A"
        )
        pro = (
            f"{pro_match.group(1)}% {pro_match.group(2).strip().rstrip('│')}"
            if pro_match
            else "N/A"
        )

    finally:
        sh(f"tmux kill-session -t {SESSION}", check=False)

    return email, flash, flash_lite, pro


def _parse_reset_time_from_model_string(model_str: str) -> Optional[datetime.datetime]:
    # e.g. "0% Resets: 1:12 PM (24h)"
    m = re.search(r"Resets:\s*(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)", model_str)
    if m:
        time_str = m.group(1)
        now = _now_local()
        try:
            parsed_time = datetime.datetime.strptime(time_str.upper(), "%I:%M %p")
            reset_dt = now.replace(
                hour=parsed_time.hour,
                minute=parsed_time.minute,
                second=0,
                microsecond=0,
            )
            if reset_dt < now:
                reset_dt += datetime.timedelta(days=1)
            return reset_dt
        except ValueError:
            return None
    return None


def capture_live_status_and_update(
    expected_email: Optional[str] = None, fallback_24h: bool = False, args=None
) -> None:
    """
    Captures live status, extracts accurate reset times, updates resets.json and cooldown.json.
    """
    email, flash, flash_lite, pro = capture_live_status()

    # If the captured email is N/A or empty, or doesn't match the expected outgoing email (if we are switching out)
    if email == "N/A" or not email:
        email = expected_email

    if not email:
        cprint(NEON_RED, "Could not determine email for live status update.")
        return

    cprint(NEON_CYAN, f"Updating live status for {email}...")

    if email == "N/A" or (flash == "N/A" and flash_lite == "N/A" and pro == "N/A"):
        cprint(NEON_YELLOW, f"Live status capture failed for {email}.")
        if fallback_24h:
            cprint(NEON_YELLOW, "Falling back to 24h assumption model.")
            add_24h_cooldown_for_email(email)
        return

    # Extract best reset time from models
    best_reset_dt = None
    for m_str in [flash, flash_lite, pro]:
        if m_str != "N/A":
            rt = _parse_reset_time_from_model_string(m_str)
            if rt:
                if not best_reset_dt or rt > best_reset_dt:
                    best_reset_dt = rt

    now = _now_local()

    # Save to resets.json
    if best_reset_dt:
        entry = {
            "id": str(uuid.uuid4())[:8],
            "email": email,
            "saved_string": "Auto-detected from live model status",
            "reset_ist": best_reset_dt.isoformat(),
            "saved_at": now.isoformat(),
        }
        entries = _load_store()
        entries = [e for e in entries if e.get("email") != email]
        entries.append(entry)
        _save_store(entries)
        cprint(
            NEON_GREEN,
            f"[INFO] Accurate reset time found for {email}: {best_reset_dt.strftime('%d %b %I:%M %p')}",
        )
    else:
        if fallback_24h:
            cprint(
                NEON_YELLOW,
                "No accurate reset time found. Falling back to 24h assumption model.",
            )
            add_24h_cooldown_for_email(email)

    # Save model percentages to cooldown.json
    path = os.path.expanduser(COOLDOWN_FILE)
    cooldown_data = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    cooldown_data = data
        except (json.JSONDecodeError, IOError):
            pass

    existing = cooldown_data.get(email, {})
    if isinstance(existing, str):
        existing = {"first_used": existing, "last_used": now.isoformat()}

    existing["models"] = {"flash": flash, "flash_lite": flash_lite, "pro": pro}

    cooldown_data[email] = existing

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(cooldown_data, f, indent=4)
    except IOError as e:
        cprint(
            NEON_RED, f"Error: Could not write to local cooldown file at {path}: {e}"
        )

    # Optional cloud sync could happen here if args says so
    if args and getattr(args, "cloud", False):
        from .cooldown import _sync_cooldown_file
        from .reset_helpers import sync_resets_with_cloud
        from .credentials import resolve_credentials
        from .b2 import B2Manager

        _sync_cooldown_file(direction="upload", args=args)

        try:
            key_id, app_key, bucket_name = resolve_credentials(args)
            if key_id and app_key and bucket_name:
                b2 = B2Manager(key_id, app_key, bucket_name)
                sync_resets_with_cloud(b2)
        except Exception as e:
            cprint(NEON_RED, f"[WARN] Failed to sync resets: {e}")


def handle_status(args):
    """
    Handle the 'gm status' command.
    """
    capture_live_status_and_update(args=args)
    # Then display the dashboard
    from .cooldown import do_cooldown_list

    do_cooldown_list(args)
