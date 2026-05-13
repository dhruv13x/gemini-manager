#!/usr/bin/env python3
import re
import subprocess
import sys
import time

SESSION = "gemini_capture"
COLS, ROWS = 120, 40


# ── SHELL / TMUX ───────────────────────────────────────────────────────────────

def run(cmd, check=True):
    r = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
    )

    if check and r.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n"
            f"stdout:\n{r.stdout}\n"
            f"stderr:\n{r.stderr}"
        )

    return r


def sh_out(cmd_list) -> str:
    return run(cmd_list).stdout


def tmux(*args, check=True):
    return run(["tmux", *args], check=check)


def capture() -> str:
    try:
        return sh_out(["tmux", "capture-pane", "-t", SESSION, "-p"])
    except Exception:
        return ""


# ── READY DETECTION ───────────────────────────────────────────────────────────

def wait_ready(timeout=30):
    start = time.time()
    stable = 0

    while True:
        out = capture()

        ready = (
            (">" in out or "›" in out)
            and "Waiting for authentication" not in out
        )

        stable = stable + 1 if ready else 0

        if stable >= 3:
            return out

        if time.time() - start > timeout:
            return out

        time.sleep(0.5)


# ── COMMAND SENDER ────────────────────────────────────────────────────────────

def send_cmd(cmd: str):
    tmux("send-keys", "-t", SESSION, "C-u")
    time.sleep(0.1)

    tmux("send-keys", "-t", SESSION, "-l", cmd)
    time.sleep(0.15)

    tmux("send-keys", "-t", SESSION, "Enter")
    time.sleep(0.1)

    # Your Gemini CLI setup appears to need this second Enter
    tmux("send-keys", "-t", SESSION, "Enter")


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
    out = ""

    for _ in range(3):
        send_cmd(cmd)
        time.sleep(0.5)

        out = capture()

        if (
            "Usage: /stats" in out
            or "stats    Check session stats" in out
            or "Usage: /model" in out
        ):
            continue

        out = wait_for(condition)

        if condition(out):
            return out

        time.sleep(1)

    return out


# ── EXTRACTION ────────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)


def extract_email(text: str):
    m = EMAIL_RE.search(text)
    return m.group(0) if m else None


def extract_model_info(label: str, text: str):
    """
    Parses lines like:
      │ Flash       ... 0%   Resets: 8:59 AM (24h)
      │ Flash Lite  ... 0%   Resets: 8:57 AM (23h 59m)
      │ Pro         ... 28%  Resets: 10:15 PM (13h 16m)

    Returns:
      "0% Resets: 8:59 AM (24h)"
    """
    pattern = rf"(?m)^\s*[│┃]?\s*{re.escape(label)}\s+.*?(\d+)%\s+Resets:\s*(.+?)\s*[│┃]?\s*$"
    m = re.search(pattern, text)

    if m:
        pct = m.group(1).strip()
        reset = m.group(2).strip()
        reset = re.sub(r"\s+[│┃]\s*$", "", reset)
        return f"{pct}% Resets: {reset}"

    return "N/A"


# ── START ─────────────────────────────────────────────────────────────────────

tmux("kill-session", "-t", SESSION, check=False)

tmux(
    "new-session",
    "-d",
    "-s",
    SESSION,
    "-x",
    str(COLS),
    "-y",
    str(ROWS),
    "gemini",
)

if SESSION not in sh_out(["tmux", "ls"]):
    sys.exit(1)

wait_ready()


# ── EMAIL ─────────────────────────────────────────────────────────────────────

output_stats = run_and_wait(
    "/stats",
    lambda o: (
        "Session Stats" in o
        or "Auth Method" in o
    ),
)

email = extract_email(output_stats)

if not email:
    email = extract_email(capture())

if not email:
    output_stats_model = run_and_wait(
        "/stats model",
        lambda o: (
            "Auth Method" in o
            or "No API calls" in o
        ),
    )
    email = extract_email(output_stats_model)

email = email if email else "N/A"


# ── MODEL USAGE ───────────────────────────────────────────────────────────────

output_model = run_and_wait(
    "/model",
    lambda o: "Model usage" in o or "Flash" in o or "Pro" in o,
)

flash = extract_model_info("Flash", output_model)
flash_lite = extract_model_info("Flash Lite", output_model)
pro = extract_model_info("Pro", output_model)


# ── CLEANUP ───────────────────────────────────────────────────────────────────

tmux("kill-session", "-t", SESSION, check=False)


# ── OUTPUT ────────────────────────────────────────────────────────────────────

print("Email :", email)
print("Flash :", flash)
print("Flash Lite :", flash_lite)
print("Pro :", pro)

if email == "N/A":
    sys.exit(2)
