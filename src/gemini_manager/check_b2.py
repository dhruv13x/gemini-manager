#!/usr/bin/env python3
# src/gemini_manager/check_b2.py

"""
check_b2.py

Verifies Backblaze B2 credentials and bucket access.
"""

import sys
import argparse
from .ui import cprint, NEON_GREEN, NEON_RED
from .b2 import B2Manager
from .credentials import resolve_credentials


def perform_check_b2(args: argparse.Namespace):
    # Resolve credentials (CLI arg > Doppler > Env Var > Config)
    key_id, app_key, bucket = resolve_credentials(args)

    try:
        B2Manager(key_id, app_key, bucket)
        cprint(
            NEON_GREEN,
            "[OK] Backblaze B2 credentials and bucket access are correctly configured.",
        )
    except SystemExit as e:
        # B2Manager calls sys.exit on failure, so we catch it to prevent a traceback
        # The error message is already printed by B2Manager's __init__
        sys.exit(e.code)
    except Exception as e:
        # Catch any other unexpected exceptions
        cprint(NEON_RED, f"[ERROR] An unexpected error occurred: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Verify Backblaze B2 credentials and bucket access."
    )
    parser.add_argument("--b2-id", help="B2 Key ID (or set env GEMINI_B2_KEY_ID)")
    parser.add_argument("--b2-key", help="B2 App Key (or set env GEMINI_B2_APP_KEY)")
    parser.add_argument("--bucket", help="B2 Bucket Name (or set env GEMINI_B2_BUCKET)")
    args = parser.parse_args()

    perform_check_b2(args)


if __name__ == "__main__":
    main()
