#!/usr/bin/env python3
# src/gemini_manager/update.py


import os
import re
import time
from typing import Tuple
import subprocess        # <<<< ADDED
import shutil           # <<<< ADDED

from .ui import banner, cprint
from .utils import run, read_file
from .config import *
from .reset_helpers import run_cmd_safe

# Improved do_update (standardized on run_cmd_safe)
def do_update():
    banner()
    cprint(NEON_YELLOW, "[INFO] Updating Gemini CLI...")

    # Remove old symlink (ignore errors)
    run_cmd_safe("rm -f /usr/bin/gm", timeout=5, detect_reset_time=False)

    # Query npm global root
    rc, npm_root, npm_err = run_cmd_safe("npm root -g", timeout=8, capture=True, detect_reset_time=False)
    npm_root = (npm_root or "").strip()
    if rc != 0 or not npm_root:
        cprint(NEON_YELLOW, f"[WARN] Could not determine npm global root (rc={rc}). Falling back to /usr/lib/node_modules")
        npm_root = "/usr/lib/node_modules"

#     google_pkg_dir = os.path.join(npm_root, "@google") # umcomment if current version is not working
    google_pkg_dir = os.path.join(npm_root, "@google", "gm-cli")
    if os.path.exists(google_pkg_dir):
        cprint(NEON_YELLOW, f"[INFO] Removing existing {google_pkg_dir} ...")
        try:
            shutil.rmtree(google_pkg_dir)
            cprint(NEON_GREEN, f"[OK] Removed {google_pkg_dir}")
        except Exception as e:
            cprint(NEON_RED, f"[ERROR] Failed to remove {google_pkg_dir}: {e}")
    else:
        cprint(NEON_GREEN, f"[OK] {google_pkg_dir} does not exist — nothing to remove.")

    # Show npm root contents for debugging — non-fatal
    if os.path.exists(npm_root):
        rc_ls, ls_out, ls_err = run_cmd_safe(f"ls -la {npm_root}", timeout=6, capture=True, detect_reset_time=False)
        if rc_ls == 0:
            cprint(NEON_GREEN, f"[INFO] npm root contents:\n{ls_out}")
        else:
            cprint(NEON_YELLOW, f"[WARN] ls returned rc={rc_ls}\n{ls_err or ''}")

    # Install / update gm CLI
    cprint(NEON_YELLOW, "[INFO] Running npm install -g @google/gm-cli ...")
    rc_install, out_install, err_install = run_cmd_safe("npm install -g @google/gm-cli", timeout=300, capture=True, detect_reset_time=False)
    
    if rc_install == 0:
        cprint(NEON_GREEN, "\n[OK] Update complete. Installed version (npm output snippet):")
        snippet = "\n".join((out_install or "").splitlines()[-6:])
        cprint(NEON_GREEN, snippet)

    else:
        cprint(NEON_RED, f"\n[ERROR] npm install failed (rc={rc_install}).")
        cprint(NEON_RED, (err_install or out_install or "No output."))

        cprint(NEON_YELLOW, "[INFO] Trying with --force ...")
        rc_force, out_force, err_force = run_cmd_safe("npm install -g @google/gm-cli --force", timeout=300, capture=True, detect_reset_time=False)

        if rc_force == 0:
            cprint(NEON_GREEN, "\n[OK] Update complete with --force.")
            snippet = "\n".join((out_force or "").splitlines()[-6:])
            cprint(NEON_GREEN, snippet)
        else:
            cprint(NEON_RED, f"[ERROR] npm install --force failed (rc={rc_force}).")
            cprint(NEON_RED, (err_force or out_force or "No output."))
            cprint(NEON_YELLOW, "[INFO] Trying with --unsafe-perm ...")
            rc2, out2, err2 = run_cmd_safe("npm install -g --unsafe-perm @google/gm-cli", timeout=300, capture=True, detect_reset_time=False)
            if rc2 == 0:
                cprint(NEON_GREEN, "[OK] Update succeeded with --unsafe-perm.")
            else:
                cprint(NEON_RED, "[ERROR] Update failed even with --unsafe-perm.")
                cprint(NEON_RED, (err2 or out2 or "No additional output."))
                # diagnostic: show npm bin and suggest symlink
                rc_bin, npm_bin, _ = run_cmd_safe("npm bin -g", timeout=6, capture=True, detect_reset_time=False)
                npm_bin = (npm_bin or "").strip()
                if npm_bin:
                    cprint(NEON_YELLOW, f"[INFO] npm global bin: {npm_bin}")
                    cprint(NEON_YELLOW, f"[TIP] If gm is installed here, you can symlink: ln -sf {npm_bin}/gm /usr/bin/gm")
    # done


def do_check_update():
    banner()
    cprint(NEON_YELLOW, "[INFO] Checking Gemini CLI version...")

    # Quick check: is gm on PATH?
    rc_path, gem_path, _ = run_cmd_safe("command -v gm", timeout=3, capture=True, detect_reset_time=False)
    gem_path = (gem_path or "").strip()
    if rc_path != 0 or not gem_path:
        cprint(NEON_RED, "[ERROR] 'gm' not found on PATH. Is it installed?")
        cprint(NEON_YELLOW, "Try: npm install -g @google/gm-cli  or check your PATH.")
        return

    cprint(NEON_CYAN, f"[INFO] Found gm at: {NEON_GREEN}{gem_path}")

    # Run version with stdin redirected from /dev/null to avoid interactive hangs,
    # and give it a generous timeout for slow environments.
    rc_inst, installed, err_inst = run_cmd_safe("gm --version < /dev/null", timeout=30, capture=True, detect_reset_time=False)
    installed = (installed or "").strip()
    if rc_inst != 0 or not installed:
        cprint(NEON_RED, "[ERROR] Gemini is installed but `gm --version` failed or timed out.")
        cprint(NEON_YELLOW, f"[DEBUG] gm --version rc={rc_inst} stderr: {err_inst}")
        cprint(NEON_YELLOW, "You can try running `gm --version` manually to see interactive prompts.")
        return

    # Get latest package version from npm
    rc_latest, latest, err_latest = run_cmd_safe("npm view @google/gm-cli version", timeout=10, capture=True, detect_reset_time=False)
    latest = (latest or "").strip()
    if rc_latest != 0 or not latest:
        cprint(NEON_YELLOW, "[WARN] Could not determine latest version via npm view.")
        cprint(NEON_YELLOW, f"[DEBUG] stderr: {err_latest}")
        cprint(NEON_CYAN, "Try: npm view @google/gm-cli version --json")
        latest = "(unknown)"

    cprint(NEON_CYAN, f"Installed version: {NEON_GREEN}{installed}")
    cprint(NEON_CYAN, f"Latest version:    {NEON_GREEN}{latest}")

    if latest != "(unknown)" and installed == latest:
        cprint(NEON_GREEN, "\n[OK] You already have the latest version!")
        return

    cprint(NEON_MAGENTA, "\n⚡ Update available!")
    choice = input(NEON_YELLOW + "Do you want to update? (y/n): " + RESET).strip().lower()
    if choice == "y":
        do_update()
    else:
        cprint(NEON_CYAN, "Update cancelled.\n")
