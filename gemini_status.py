# gemini_stats.py

import re
import subprocess
import sys

MODEL = "gemini-3.1-flash-lite-preview"


# ── ANSI CLEANUP ──────────────────────────────────────────────────────────────
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def clean(text: str) -> str:
    text = ANSI_RE.sub("", text)
    text = text.replace("\r", "")
    return text


# ── RUN GEMINI COMMAND ────────────────────────────────────────────────────────
def run_gemini(command: str) -> str:
    cmd = f"script -qec 'gemini --model {MODEL} {command}' /dev/null"

    result = subprocess.run(
        cmd,
        shell=True,
        text=True,
        capture_output=True,
    )

    return clean(result.stdout + result.stderr)


# ── EMAIL EXTRACTION ──────────────────────────────────────────────────────────
def extract_email(text: str):
    m = re.search(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        text,
    )
    return m.group(0) if m else None


# ── QUOTA EXTRACTION ──────────────────────────────────────────────────────────
def extract_usage(name: str, text: str):
    pattern = rf"{re.escape(name)}\s+.*?(\d+)%\s*(.*)"

    m = re.search(pattern, text)

    if not m:
        return "N/A"

    percent = m.group(1).strip()
    extra = m.group(2).strip()

    extra = extra.rstrip("│").strip()

    return f"{percent}% {extra}".strip()


# ── FETCH STATS ───────────────────────────────────────────────────────────────
stats_output = run_gemini("/stats")

email = extract_email(stats_output) or "N/A"


# ── FETCH MODEL USAGE ─────────────────────────────────────────────────────────
model_output = run_gemini("/model")

flash = extract_usage("Flash", model_output)
flash_lite = extract_usage("Flash Lite", model_output)
pro = extract_usage("Pro", model_output)


# ── OUTPUT ────────────────────────────────────────────────────────────────────
print("Email :", email)
print("Flash :", flash)
print("Flash Lite :", flash_lite)
print("Pro :", pro)


# ── EXIT CODE ─────────────────────────────────────────────────────────────────
if email == "N/A":
    sys.exit(2)
