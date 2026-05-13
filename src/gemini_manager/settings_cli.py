#!/usr/bin/env python3
# src/gemini_manager/settings_cli.py


import sys
from .settings import (
    set_setting,
    get_setting,
    list_settings,
    remove_setting,
    CONFIG_FILE,
)
from .ui import cprint
from .config import NEON_CYAN, NEON_GREEN, NEON_YELLOW, NEON_RED, RESET
from .wizard import run_wizard


def do_config(args):
    """
    Handle config command.
    args.config_action: 'set', 'get', 'list', 'unset', 'init'
    args.key: key (optional for list)
    args.value: value (optional for get/list/unset)
    args.force: boolean (optional)
    """
    action = args.config_action

    if args.init or action == "init":
        run_wizard()
        return

    if action == "list":
        s = list_settings()
        if not s:
            cprint(NEON_YELLOW, "No settings configured.")
        else:
            cprint(NEON_CYAN, "Current Configuration:")
            for k, v in s.items():
                # Mask sensitive keys in output
                display_val = v
                if (
                    "key" in k.lower()
                    or "secret" in k.lower()
                    or "password" in k.lower()
                    or "id" in k.lower()
                ):
                    if isinstance(v, str) and len(v) > 4:
                        display_val = v[:2] + "*" * (len(v) - 4) + v[-2:]
                    else:
                        display_val = "*****"
                print(f"  {NEON_GREEN}{k}{RESET}: {display_val}")
        return

    if not args.key:
        cprint(NEON_RED, "[ERROR] Key required for set/get/unset.")
        return

    if action == "set":
        if not args.value:
            cprint(NEON_RED, "[ERROR] Value required for set.")
            return

        # --- Safety Layer ---
        key_lower = args.key.lower()
        # "id" is included because Account IDs (like B2 Key ID) are sensitive identifiers
        is_sensitive = any(
            x in key_lower for x in ["key", "secret", "token", "password", "id"]
        )
        force = getattr(args, "force", False)

        if is_sensitive and not force:
            # Check if we are in an interactive terminal
            is_interactive = sys.stdin.isatty()

            if is_interactive:
                cprint(
                    NEON_YELLOW,
                    f"⚠️  Security Warning: You are about to save a sensitive key ('{args.key}') to disk.",
                )
                cprint(NEON_YELLOW, f"   Location: {CONFIG_FILE}")

                try:
                    response = (
                        input(
                            f"{NEON_CYAN}   Save locally for convenience? [y/N] {RESET}"
                        )
                        .strip()
                        .lower()
                    )
                except EOFError:
                    response = "n"

                if response != "y":
                    cprint(
                        NEON_RED,
                        "❌ Aborted. (Tip: Use 'export GEMINI_B2_KEY_ID=...' for temporary usage)",
                    )
                    return
            else:
                # Non-interactive (Automation/Script) -> BLOCK
                cprint(
                    NEON_RED,
                    "❌ Error: Refusing to write secrets in non-interactive mode.",
                )
                cprint(
                    NEON_RED,
                    "   Solution 1: Use Environment Variables (Recommended for CI/CD).",
                )
                cprint(NEON_RED, "   Solution 2: Use --force to override.")
                sys.exit(1)
        # --------------------

        set_setting(args.key, args.value)
        cprint(NEON_GREEN, f"[OK] Set {args.key} = {args.value}")

    elif action == "get":
        val = get_setting(args.key)
        if val is not None:
            cprint(NEON_GREEN, f"{val}")
        else:
            cprint(NEON_YELLOW, "(not set)")

    elif action == "unset":
        if remove_setting(args.key):
            cprint(NEON_GREEN, f"[OK] Removed {args.key}")
        else:
            cprint(NEON_YELLOW, f"[WARN] Key {args.key} not found.")
