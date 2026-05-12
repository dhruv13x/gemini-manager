#!/usr/bin/env python3
# src/gemini_manager/cli.py


import sys
from .ui import print_rich_help
from .args import get_parser
from .banner import print_logo
from .login import do_login
from .logout import do_logout
from .session import do_session
from .cooldown import do_cooldown_list, do_remove_account, do_reset_all
from .settings_cli import do_config
from .doctor import do_doctor
from .prune import do_prune
from .update import do_update, do_check_update
from .recommend import do_recommend
from .stats import do_stats
from .status import get_gemini_status
from .cooldown import parse_usage, update_cooldown_from_status
from .reset_helpers import sync_resets_with_cloud
from .cloud_factory import get_cloud_provider
from .reset_helpers import handle_resets_command
from .profile import do_profile
from .config import (
    DEFAULT_GEMINI_HOME,
    CHAT_HISTORY_BACKUP_PATH
)
from .backup import perform_backup
from .restore import perform_restore
from .integrity import perform_integrity_check
from .list_backups import perform_list_backups
from .check_b2 import perform_check_b2
from .sync import perform_sync
from .chat import backup_chat_history, restore_chat_history, cleanup_chat_history, resume_chat

def main():
    print_logo()
    # Handle main help manually to use Rich if no args or explicit help on main
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] in ["-h", "--help"]):
        print_rich_help()

    parser = get_parser()
    args = parser.parse_args()

    if args.command == "backup":
        perform_backup(args)
    elif args.command == "restore":
        perform_restore(args)
    elif args.command == "chat":
        if args.chat_command == "backup":
            backup_chat_history(CHAT_HISTORY_BACKUP_PATH, DEFAULT_GEMINI_HOME)
        elif args.chat_command == "restore":
            restore_chat_history(CHAT_HISTORY_BACKUP_PATH, DEFAULT_GEMINI_HOME)
        elif args.chat_command == "cleanup":
            cleanup_chat_history(args.dry_run, args.force, DEFAULT_GEMINI_HOME)
        elif args.chat_command == "resume":
            resume_chat()
    elif args.command == "check-integrity":
        perform_integrity_check(args)
    elif args.command == "list-backups":
        perform_list_backups(args)
    elif args.command == "check-b2":
        perform_check_b2(args)
    elif args.command == "sync":
        if args.sync_direction:
            perform_sync(args.sync_direction, args)
        else:
            # No subcommand provided
            parser.parse_args(["sync", "--help"])
    elif args.command == "config":
        do_config(args)
    elif args.command == "doctor":
        do_doctor()
    elif args.command == "prune":
        do_prune(args)
    elif args.command == "profile":
        do_profile(args)
    elif args.command == "cooldown":
        if args.reset_all:
            do_reset_all(args)
        elif args.remove:
            do_remove_account(args.remove[0], args)
        else:
            do_cooldown_list(args)
    elif args.command == "recommend" or args.command == "next":
        do_recommend(args)
    elif args.command == "stats" or args.command == "usage":
        do_stats(args)
    elif args.command == "status":
        from .status import get_gemini_status
        from .cooldown import update_cooldown_from_status, do_cooldown_list
        from .reset_helpers import sync_resets_with_cloud
        from .cloud_factory import get_cloud_provider
        from .ui import cprint, NEON_CYAN, NEON_YELLOW
        import json

        cprint(NEON_CYAN, "Fetching Gemini status...")
        status_data = get_gemini_status()
        if "error" in status_data:
            cprint(NEON_YELLOW, f"Error: {status_data['error']}")
        else:
            print("Email :", status_data['email'])
            print("Flash :", status_data['flash'])
            print("Flash Lite :", status_data['flash_lite'])
            print("Pro :", status_data['pro'])
            update_cooldown_from_status(status_data)

            if args.cloud:
                cprint(NEON_CYAN, "Syncing to cloud...")
                provider = get_cloud_provider(args)
                if provider:
                    sync_resets_with_cloud(provider)
            do_cooldown_list(args)
    elif args.command == "resets":
        if not handle_resets_command(args):
            # We need to print help for the resets command.
            # Since we don't have direct access to resets_parser here (it's inside get_parser),
            # we can trigger it by re-parsing with help, or just print a custom message,
            # or better: we can make get_parser return subparsers too or find the subparser.
            # Easiest way using argparse:
            parser.parse_args(["resets", "--help"])
    elif args.login:
        do_login()
    elif args.logout:
        do_logout()
    elif args.session:
        do_session()
    elif args.update:
        do_update()
    elif args.check_update:
        do_check_update()
    else:
        print_rich_help()


if __name__ == "__main__":
    main()
