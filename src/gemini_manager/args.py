#!/usr/bin/env python3
# src/gemini_manager/args.py

import argparse
import sys
from rich.table import Table
from rich.panel import Panel
from .ui import console, print_rich_help
from .config import (
    DEFAULT_BACKUP_DIR,
    OLD_CONFIGS_DIR,
    DEFAULT_GEMINI_HOME
)
from .project_config import load_project_config, normalize_config_keys

class RichHelpParser(argparse.ArgumentParser):
    """
    Custom parser that overrides print_help to display a Rich-based help screen
    for subcommands (and the main command if accessed via standard flow).
    """
    def error(self, message):
        console.print(f"[bold red]Error:[/ {message}")
        # Only print full help if really needed, or just hint
        console.print("[dim]Use --help for usage information.[/]")
        sys.exit(2)

    def print_help(self, file=None):
        """
        Dynamically generates Rich help for ANY parser (main or subcommand).
        """
        # If this is the main parser (checking by prog name usually, or description),
        # we might want to use the specialized print_rich_help() for the fancy banner.
        # However, implementing a generic one is better for subcommands.

        if self.description and "Gemini AI Automation Tool" in self.description:
             # This is likely the main parser
             print_rich_help()
             return

        # For Subcommands (e.g., 'gm backup')
        console.print(f"[bold cyan]Command:[/ ] [bold magenta]{self.prog}[/]\n")
        if self.description:
            console.print(f"[italic]{self.description}[/]\n")

        # Usage
        console.print(f"[bold white]Usage:[/ ] [dim]{self.format_usage().strip().replace('usage: ', '')}[/]\n")

        # Arguments
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Option", style="bold yellow", width=30)
        table.add_column("Description", style="white")

        for action in self._actions:
            # Skip help if we want, but usually good to show
            opts = ", ".join(action.option_strings)
            if not opts:
                opts = action.dest # Positional arg

            help_text = action.help or ""
            # Handle default values
            if action.default != argparse.SUPPRESS and action.default is not None:
                # help_text += f" [dim](default: {action.default})[/]"
                pass # argparse puts default in help usually, check formatting

            table.add_row(opts, help_text)

        console.print(Panel(table, title="[bold green]Arguments & Options[/]", border_style="cyan"))

def get_parser() -> argparse.ArgumentParser:
    """
    Builds and returns the argument parser.
    """
    # Use RichHelpParser for the main parser
    parser = RichHelpParser(description="Gemini AI Automation Tool", add_help=False)

    # 0. Check for --profile in args manually before full parsing
    profile = None
    if "--profile" in sys.argv:
        try:
            idx = sys.argv.index("--profile")
            if idx + 1 < len(sys.argv):
                profile = sys.argv[idx + 1]
        except ValueError:
            pass

    # Load project config (pyproject.toml / gemini-manager.toml)
    project_defaults = load_project_config(profile=profile)
    if project_defaults:
        # Normalize keys (kebab-case -> snake_case)
        project_defaults = normalize_config_keys(project_defaults)
        parser.set_defaults(**project_defaults)

    subparsers = parser.add_subparsers(dest="command", help="Available commands", parser_class=RichHelpParser)

    # Keep existing top-level arguments
    parser.add_argument("--login", action="store_true", help="Login to Gemini CLI")
    parser.add_argument("--logout", action="store_true", help="Logout from Gemini CLI")
    parser.add_argument("--session", action="store_true", help="Show current active session")
    parser.add_argument("--update", action="store_true", help="Reinstall / update Gemini CLI")
    parser.add_argument("--check-update", action="store_true", help="Check for updates")
    parser.add_argument("--version", "-v", action="store_true", help="Show version information")
    parser.add_argument("--profile", help="Specify a configuration profile to use (e.g., work, personal)")

    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Backup Gemini configuration and chats (local or Backblaze B2 cloud).")
    backup_parser.add_argument("--src", default="~/.gemini-manager", help="Source gemini-manager dir (default ~/.gemini-manager)")
    backup_parser.add_argument("--archive-dir", default=DEFAULT_BACKUP_DIR, help="Directory to store tar.gz archives (default: ~/.gemini-manager/backups)")
    backup_parser.add_argument("--dest-dir-parent", default=OLD_CONFIGS_DIR, help="Parent directory where timestamped directory backups are stored")
    backup_parser.add_argument("--dry-run", action="store_true", help="Do not perform destructive actions")
    backup_parser.add_argument("--cloud", action="store_true", help="Create local backup AND upload to Cloud (B2)")
    backup_parser.add_argument("--bucket", help="B2 Bucket Name")
    backup_parser.add_argument("--b2-id", help="B2 Key ID (or set env GEMINI_B2_KEY_ID)")
    backup_parser.add_argument("--b2-key", help="B2 App Key (or set env GEMINI_B2_APP_KEY)")

    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore Gemini configuration from a backup (local or Backblaze B2 cloud).")
    restore_parser.add_argument("--from-dir", help="Directory backup to restore from (preferred)")
    restore_parser.add_argument("--from-archive", help="Tar.gz archive to restore from")
    restore_parser.add_argument("--email", help="Restore the latest backup for this email")
    restore_parser.add_argument("--search-dir", default=DEFAULT_BACKUP_DIR, help="Directory to search for backup archives (*.gemini-manager.tar.gz) when no --from-dir (default: ~/.gemini-manager/backups)")
    restore_parser.add_argument("--dest", default=DEFAULT_GEMINI_HOME, help=f"Destination (default {DEFAULT_GEMINI_HOME})")
    restore_parser.add_argument("--force", action="store_true", help="Allow destructive replace without keeping .bak")
    restore_parser.add_argument("--dry-run", action="store_true", help="Do a dry run without destructive actions")
    restore_mode = restore_parser.add_mutually_exclusive_group()
    restore_mode.add_argument("--auth-only", action="store_true", help="Restore only Gemini identity files and preserve current sessions (default)")
    restore_mode.add_argument("--full", action="store_true", help="Replace the whole Gemini state directory")
    restore_parser.add_argument("--cloud", action="store_true", help="Restore from Cloud (B2)")
    restore_parser.add_argument("--bucket", help="B2 Bucket Name")
    restore_parser.add_argument("--b2-id", help="B2 Key ID")
    restore_parser.add_argument("--b2-key", help="B2 App Key")
    restore_parser.add_argument("--auto", action="store_true", help="Automatically restore the best available account")

    # Chat command
    chat_parser = subparsers.add_parser("chat", help="Manage chat history.")
    chat_subparsers = chat_parser.add_subparsers(dest="chat_command", help="Chat commands")
    chat_backup_parser = chat_subparsers.add_parser("backup", help="Backup chat history.")
    chat_restore_parser = chat_subparsers.add_parser("restore", help="Restore chat history.")
    chat_cleanup_parser = chat_subparsers.add_parser("cleanup", help="Clear temporary chat history and logs.")
    chat_cleanup_parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without doing it")
    chat_cleanup_parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    chat_resume_parser = chat_subparsers.add_parser("resume", help="Resume the last chat session.")

    # Integrity check command
    integrity_parser = subparsers.add_parser("check-integrity", help="Check integrity of current configuration against the latest backup.")
    integrity_parser.add_argument("--src", default="~/.gemini-manager", help="Source directory for integrity check (default: ~/.gemini-manager)")


    # List backups command
    list_backups_parser = subparsers.add_parser("list-backups", help="List available backups (local or Backblaze B2 cloud).")
    list_backups_parser.add_argument("--search-dir", default=DEFAULT_BACKUP_DIR, help="Directory to search for backup archives (default: ~/.gemini-manager/backups)")
    list_backups_parser.add_argument("--all", action="store_true", help="Show every archive instead of only the latest backup per email")
    list_backups_parser.add_argument("--show-dirs", action="store_true", help="Also show legacy directory backups from ~/.gemini-manager-old")
    list_backups_parser.add_argument("--cloud", action="store_true", help="List backups from Cloud (B2)")
    list_backups_parser.add_argument("--bucket", help="B2 Bucket Name")
    list_backups_parser.add_argument("--b2-id", help="B2 Key ID")
    list_backups_parser.add_argument("--b2-key", help="B2 App Key")

    # Check B2 command
    check_b2_parser = subparsers.add_parser("check-b2", help="Verify Backblaze B2 credentials.")
    check_b2_parser.add_argument("--b2-id", help="B2 Key ID (or set env GEMINI_B2_KEY_ID)")
    check_b2_parser.add_argument("--b2-key", help="B2 App Key (or set env GEMINI_B2_APP_KEY)")
    check_b2_parser.add_argument("--bucket", help="B2 Bucket Name (or set env GEMINI_B2_BUCKET)")

    # Sync command (Unified Push/Pull)
    sync_parser = subparsers.add_parser("sync", help="Sync backups with Cloud (B2).")
    sync_subparsers = sync_parser.add_subparsers(dest="sync_direction", help="Sync direction")

    # Sync Push (Local -> Cloud)
    push_parser = sync_subparsers.add_parser("push", help="Upload missing local backups to Cloud.")
    push_parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR, help="Local backup directory (default: ~/.gemini-manager/backups)")
    push_parser.add_argument("--bucket", help="B2 Bucket Name")
    push_parser.add_argument("--b2-id", help="B2 Key ID")
    push_parser.add_argument("--b2-key", help="B2 App Key")

    # Sync Pull (Cloud -> Local)
    pull_parser = sync_subparsers.add_parser("pull", help="Download missing Cloud backups to local.")
    pull_parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR, help="Local backup directory (default: ~/.gemini-manager/backups)")
    pull_parser.add_argument("--bucket", help="B2 Bucket Name")
    pull_parser.add_argument("--b2-id", help="B2 Key ID")
    pull_parser.add_argument("--b2-key", help="B2 App Key")

    # Config command
    config_parser = subparsers.add_parser("config", help="Manage persistent configuration.")
    config_parser.add_argument("config_action", choices=["set", "get", "list", "unset", "init"], nargs="?", help="Action to perform")
    config_parser.add_argument("key", nargs="?", help="Setting key")
    config_parser.add_argument("value", nargs="?", help="Setting value")
    config_parser.add_argument("--force", action="store_true", help="Force save sensitive keys without confirmation (automation mode)")
    config_parser.add_argument("--init", action="store_true", help="Run the interactive configuration wizard")

    # Resets command (New subcommand for reset management)
    resets_parser = subparsers.add_parser("resets", help="Manage Gemini free tier reset schedules.")
    resets_parser.add_argument("--list", action="store_true", help="List saved schedules")
    resets_parser.add_argument("--next", nargs="?", const="*ALL*", help="Show next usage time. Optionally pass email or id.")
    resets_parser.add_argument("--add", nargs="?", const="", help="Add time manually. Example: --add '01:00 PM user@example.com'")
    resets_parser.add_argument("--remove", nargs=1, help="Remove saved entry by id or email.")

    # Doctor command
    subparsers.add_parser("doctor", help="Run system diagnostic check.")

    # Prune command
    prune_parser = subparsers.add_parser("prune", help="Prune old backups.")
    prune_parser.add_argument("--keep", type=int, default=5, help="Number of recent backups to keep (default: 5)")
    prune_parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR, help="Local backup directory (default: ~/.gemini-manager/backups)")
    prune_parser.add_argument("--cloud", action="store_true", help="Prune both local AND cloud backups")
    prune_parser.add_argument("--cloud-only", action="store_true", help="Only prune cloud backups")
    prune_parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without doing it")
    prune_parser.add_argument("--bucket", help="B2 Bucket Name")
    prune_parser.add_argument("--b2-id", help="B2 Key ID")
    prune_parser.add_argument("--b2-key", help="B2 App Key")

    # Cooldown command
    cooldown_parser = subparsers.add_parser("cooldown", help="Show account cooldown status, with optional cloud sync.")
    cooldown_parser.add_argument("--cloud", action="store_true", help="Sync cooldown status from the cloud.")
    cooldown_parser.add_argument("--bucket", help="B2 Bucket Name")
    cooldown_parser.add_argument("--b2-id", help="B2 Key ID")
    cooldown_parser.add_argument("--b2-key", help="B2 App Key")
    cooldown_parser.add_argument("--remove", nargs=1, help="Remove an account from the dashboard (both cooldown and resets).")
    cooldown_parser.add_argument("--reset-all", action="store_true", help="⚠️ Clear ALL account activity and reset data (Local & Cloud).")

    # Recommend command
    recommend_parser = subparsers.add_parser("recommend", aliases=["next"], help="Suggest the next best account (Green & Least Recently Used).")
    recommend_parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR, help="Directory containing backup archives and metadata")
    recommend_parser.add_argument("--cloud", action="store_true", help="Recommend from Cloud metadata")
    recommend_parser.add_argument("--use", action="store_true", help="Immediately switch to the recommended account (auth-only)")
    recommend_parser.add_argument("--restore", action="store_true", help="Immediately full-restore the recommended account")
    recommend_parser.add_argument("--dest", default=DEFAULT_GEMINI_HOME, help=f"Gemini home directory to restore into (default {DEFAULT_GEMINI_HOME})")
    recommend_parser.add_argument("--dry-run", action="store_true", help="Show what would happen without switching")
    recommend_parser.add_argument("--force", action="store_true", help="Allow destructive replacement for --restore")
    recommend_parser.add_argument("--bucket", help="B2 Bucket Name")
    recommend_parser.add_argument("--b2-id", help="B2 Key ID")
    recommend_parser.add_argument("--b2-key", help="B2 App Key")

    # Stats command
    stats_parser = subparsers.add_parser("stats", aliases=["usage"], help="Show usage statistics (last 7 days).")

    # Profile command
    profile_parser = subparsers.add_parser("profile", help="Manage configuration profiles.")
    profile_subparsers = profile_parser.add_subparsers(dest="profile_command", help="Profile commands")

    # Profile Export
    profile_export = profile_subparsers.add_parser("export", help="Export profile to a zip file.")
    profile_export.add_argument("file", help="Output zip filename")

    # Profile Import
    profile_import = profile_subparsers.add_parser("import", help="Import profile from a zip file.")
    profile_import.add_argument("file", help="Input zip filename")
    profile_import.add_argument("--force", action="store_true", help="Overwrite existing files without confirmation")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show current Gemini status (live capture).")
    status_parser.add_argument("--cloud", action="store_true", help="Sync status with the cloud.")
    status_parser.add_argument("--bucket", help="B2 Bucket Name")
    status_parser.add_argument("--b2-id", help="B2 Key ID")
    status_parser.add_argument("--b2-key", help="B2 App Key")

    return parser
