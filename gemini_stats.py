# gemini_stats.py

import re
import subprocess
import time
import sys

SESSION = "gemini_capture"
COLS, ROWS = 120, 40


# ── SHELL ─────────────────────────────────────────────────────────────────────
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


# ── READY DETECTION ───────────────────────────────────────────────────────────
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


# ── COMMAND SENDER ────────────────────────────────────────────────────────────
def send_cmd(cmd: str):
    sh(f"tmux send-keys -t {SESSION} C-u")
    time.sleep(0.1)

    sh(f"tmux send-keys -t {SESSION} '{cmd}'")
    time.sleep(0.15)

    sh(f"tmux send-keys -t {SESSION} Enter")
    time.sleep(0.1)
    sh(f"tmux send-keys -t {SESSION} Enter")


# ── WAIT ──────────────────────────────────────────────────────────────────────
def wait_for(cond, timeout=20):
    start = time.time()

    while True:
        out = capture()

        if cond(out):
            return out

        if time.time() - start > timeout:
            return out

        time.sleep(0.5)


# ── RETRY EXECUTION ───────────────────────────────────────────────────────────
def run_and_wait(cmd, condition):
    for _ in range(3):
        send_cmd(cmd)
        time.sleep(0.5)

        out = capture()

        # detect help menu (command not executed)
        if "Usage: /stats" in out or "stats    Check session stats" in out:
            continue

        out = wait_for(condition)

        if condition(out):
            return out

        time.sleep(1)

    return out


# ── EMAIL EXTRACTION ──────────────────────────────────────────────────────────
def extract_email(text: str):
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return m.group(0) if m else None


# ── START ─────────────────────────────────────────────────────────────────────
sh(f"tmux kill-session -t {SESSION}", check=False)
sh(f"tmux new-session -d -s {SESSION} -x {COLS} -y {ROWS} 'gemini'")

if SESSION not in sh_out("tmux ls || true"):
    sys.exit(1)

wait_ready()

# ── EMAIL ─────────────────────────────────────────────────────────────────────
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


# ── MODEL USAGE ───────────────────────────────────────────────────────────────
output_model = run_and_wait("/model", lambda o: "Model usage" in o)

flash_match = re.search(r"Flash\s+.*?(\d+)%\s+(.*)", output_model)
flash_lite_match = re.search(r"Flash Lite\s+.*?(\d+)%\s+(.*)", output_model)
pro_match = re.search(r"Pro\s+.*?(\d+)%\s+(.*)", output_model)

flash = f"{flash_match.group(1)}% {flash_match.group(2).strip()}" if flash_match else "N/A"
flash_lite = f"{flash_lite_match.group(1)}% {flash_lite_match.group(2).strip()}" if flash_lite_match else "N/A"
pro = f"{pro_match.group(1)}% {pro_match.group(2).strip().rstrip('│')}" if pro_match else "N/A"


# ── CLEANUP ───────────────────────────────────────────────────────────────────
sh(f"tmux kill-session -t {SESSION}", check=False)


# ── OUTPUT ────────────────────────────────────────────────────────────────────
print("Email :", email)
print("Flash :", flash)
print("Flash Lite :", flash_lite)
print("Pro :", pro)

if email == "N/A":
    sys.exit(2)
