#!/usr/bin/env python3
# src/gemini_manager/logout.py


import os
import re
import time
from typing import Tuple
import subprocess        # <<<< ADDED
import shutil           # <<<< ADDED

from .ui import banner, cprint
from .utils import run, read_file
from .config import *


def do_logout():
    banner()

    gemini_dir = os.path.expanduser("~/.gemini-manager")

    cprint(NEON_YELLOW, "[INFO] Logging out from Gemini CLI...")
    cprint(NEON_YELLOW, f"[INFO] Removing: {NEON_CYAN}{gemini_dir}{RESET}")

    if os.path.exists(gemini_dir):
        run(f"rm -rf {gemini_dir}")
        cprint(NEON_GREEN, "[OK] Directory removed.")
    else:
        cprint(NEON_GREEN, "[OK] Already logged out (directory missing).")

    cprint(NEON_YELLOW, "\n[INFO] Confirming logout status:")
    run("ls -d ~/.gemini-manager || echo '[OK] Logout complete.'")

