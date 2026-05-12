#!/usr/bin/env python3
# src/gemini_manager/login.py


import re
import time

from .ui import banner, cprint
from .utils import read_file
from .config import LOGIN_URL_PATH, NEON_YELLOW, NEON_CYAN, NEON_MAGENTA, NEON_GREEN, NEON_RED, RESET
from .reset_helpers import run_cmd_safe

# Improved do_login
def do_login(retries: int = 2, wait_between: float = 0.8):
    """
    Robust login flow:
     - Runs gm, attempts to extract an auth URL or verification code via regex.
     - If first-run menu appears, auto-select Browser Login by sending an ENTER.
     - Writes to LOGIN_URL_PATH (from config) and shows a safe preview to user.
    """
    banner()
    cprint(NEON_YELLOW, "[INFO] Starting Gemini login flow...")
    cprint(NEON_YELLOW, f"[INFO] Saving output to: {NEON_CYAN}{LOGIN_URL_PATH}{RESET}")

    # Helper to parse URLs and possible verification codes
    url_regex = re.compile(r"https?://[^\s'\"<>]+")
    code_regex = re.compile(r"(?i)verification code[:\s]*([A-Za-z0-9\-_=]{4,})")

    # First attempt: run gm capturing stderr (where gm prints)
    for attempt in range(1, retries + 1):
        cprint(NEON_YELLOW, f"[INFO] Running gm (attempt {attempt}/{retries})...")
        rc, out, err = run_cmd_safe(f"gm 2> {LOGIN_URL_PATH}", timeout=30, capture=True)
        # read file if exists
        try:
            raw = read_file(LOGIN_URL_PATH)
        except Exception:
            raw = (err or "") + (out or "")
        text = (raw or "").strip()

        # quick search for obvious signs
        found_urls = url_regex.findall(text)
        found_codes = code_regex.findall(text)

        if found_urls or found_codes:
            # Success — at least we have something to show
            cprint(NEON_GREEN, "[OK] Authentication output captured.")
            break

        # If output does not contain URL/code, check for first-run menu hint and try the ENTER trick
        lower = text.lower()
        if ("choose a login method" in lower) or ("browser login" in lower) or ("press enter" in lower) or ("choose an option" in lower):
            cprint(NEON_MAGENTA, "[INFO] FIRST RUN / interactive menu detected — selecting Browser Login (send ENTER).")
            rc2, out2, err2 = run_cmd_safe(f'printf "\\n" | gm 2> {LOGIN_URL_PATH}', timeout=15, capture=True)
            # after selecting, run gm again to capture the URL
            time.sleep(wait_between)
            _, out3, err3 = run_cmd_safe(f"gm 2> {LOGIN_URL_PATH}", timeout=30, capture=True)
            try:
                text = read_file(LOGIN_URL_PATH)
            except Exception:
                text = (err3 or "") + (out3 or "")
            found_urls = url_regex.findall(text)
            found_codes = code_regex.findall(text)
            if found_urls or found_codes:
                break

        # If nothing found and not last attempt, wait & retry
        if attempt < retries:
            time.sleep(wait_between)
        else:
            cprint(NEON_RED, "[ERROR] Could not extract login URL or verification code from gm output.")
            cprint(NEON_YELLOW, f"[INFO] Show file preview (first 15 lines) from {LOGIN_URL_PATH} if present.")
            try:
                raw = read_file(LOGIN_URL_PATH)
            except Exception:
                raw = None
            preview = ("\n".join((raw or "").splitlines()[:15])) if raw else "(no file)"
            cprint(NEON_MAGENTA, "Preview:")
            print(preview + "\n")
            return

    # At this point `text` contains the latest file contents
    # Extract and print a safe preview and show instructions
    preview = "\n".join(text.splitlines()[:15])
    cprint(NEON_MAGENTA, "Preview:")
    print(preview + "\n")

    # If we have a URL, show it clearly
    if found_urls:
        cprint(NEON_GREEN, "[OK] Found URL(s):")
        for u in found_urls:
            cprint(NEON_CYAN, f"  {u}")
    if found_codes:
        cprint(NEON_GREEN, "[OK] Found verification code(s):")
        for code in found_codes:
            cprint(NEON_CYAN, f"  {code}")

    cprint(NEON_YELLOW, "✔ Open the URL in your browser")
    cprint(NEON_YELLOW, "✔ Complete the login")
    cprint(NEON_YELLOW, "✔ Copy the verification code shown in the browser")
    cprint(NEON_YELLOW, "✔ Paste the code into the Gemini CLI when prompted\n")

    cprint(NEON_CYAN, "[INFO] Full file (not printed here for safety):")
    cprint(NEON_MAGENTA, f"  cat {LOGIN_URL_PATH}\n")
