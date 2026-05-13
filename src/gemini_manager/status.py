import re
import subprocess
import time
from typing import Dict, Optional

SESSION = "gemini_capture_status"
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
    while True:
        out = capture()
        ready = (">" in out or "›" in out) and "Waiting for authentication" not in out
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

def get_live_status() -> Optional[Dict]:
    sh(f"tmux kill-session -t {SESSION}", check=False)
    sh(f"tmux new-session -d -s {SESSION} -x {COLS} -y {ROWS} 'gemini'")

    if SESSION not in sh_out("tmux ls || true"):
        return None

    wait_ready()

    output_stats = run_and_wait("/stats", lambda o: "Session Stats" in o or "Auth Method" in o)
    email = extract_email(output_stats)
    if not email:
        email = extract_email(capture())
    if not email:
        output_stats_model = run_and_wait("/stats model", lambda o: "Auth Method" in o or "No API calls" in o)
        email = extract_email(output_stats_model)

    if not email:
        sh(f"tmux kill-session -t {SESSION}", check=False)
        return None

    output_model = run_and_wait("/model", lambda o: "Model usage" in o)

    flash_match = re.search(r"Flash\s+.*?(\d+)%\s+(.*)", output_model)
    flash_lite_match = re.search(r"Flash Lite\s+.*?(\d+)%\s+(.*)", output_model)
    pro_match = re.search(r"Pro\s+.*?(\d+)%\s+(.*)", output_model)

    def parse_resets(extra_str):
        # Extract "21h 3m"
        m = re.search(r"\((\d+)h\s*(\d+)m\)", extra_str)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None, None

    result = {
        "email": email,
        "models": {}
    }

    if flash_match:
        percent = int(flash_match.group(1))
        extra = flash_match.group(2).strip()
        h, m = parse_resets(extra)
        result["models"]["Flash"] = {"percent": percent, "extra": extra, "reset_h": h, "reset_m": m}

    if flash_lite_match:
        percent = int(flash_lite_match.group(1))
        extra = flash_lite_match.group(2).strip()
        h, m = parse_resets(extra)
        result["models"]["Flash Lite"] = {"percent": percent, "extra": extra, "reset_h": h, "reset_m": m}

    if pro_match:
        percent = int(pro_match.group(1))
        extra = pro_match.group(2).strip().rstrip('│')
        h, m = parse_resets(extra)
        result["models"]["Pro"] = {"percent": percent, "extra": extra, "reset_h": h, "reset_m": m}

    sh(f"tmux kill-session -t {SESSION}", check=False)
    return result

from .ui import cprint, console, Table
from .config import NEON_CYAN, NEON_GREEN, NEON_RED

def do_status(args=None):
    from .cloud_factory import get_cloud_provider
    from .reset_helpers import sync_resets_with_cloud, save_live_status_to_resets
    from .metadata import patch_status_metadata

    if args and getattr(args, 'cloud', False):
        provider = get_cloud_provider(args)
        if provider:
            sync_resets_with_cloud(provider)
            cprint(NEON_CYAN, "Cloud sync (pre-fetch) complete.")

    cprint(NEON_CYAN, "Fetching live status from Gemini...")
    try:
        status = get_live_status()
    except Exception as e:
        cprint(NEON_RED, f"Failed to get live status: {e}")
        return

    if not status:
        cprint(NEON_RED, "Could not retrieve status. Is the Gemini CLI working?")
        return

    # Save to local store
    save_live_status_to_resets(status)
    metadata_path = patch_status_metadata(status, args)
    if metadata_path:
        cprint(NEON_CYAN, f"Metadata updated: {metadata_path}")

    # Sync to cloud if requested
    if args and getattr(args, 'cloud', False):
        provider = get_cloud_provider(args)
        if provider:
            sync_resets_with_cloud(provider)
            cprint(NEON_CYAN, "Cloud sync (post-fetch) complete.")

    cprint(NEON_GREEN, f"Email : {status['email']}")

    table = Table(show_header=True, header_style="bold white", border_style="blue")
    table.add_column("Model", style="cyan")
    table.add_column("Remaining", justify="right", style="green")
    table.add_column("Extra/Resets", style="yellow")

    for model, data in status['models'].items():
        table.add_row(model, f"{data['percent']}%", data['extra'])

    console.print(table)
