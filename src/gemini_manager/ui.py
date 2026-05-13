#!/usr/bin/env python3
# src/gemini_manager/ui.py


import sys
from rich.console import Console
from rich.panel import Panel
from rich.align import Align
from rich.text import Text
from rich.table import Table

from .config import RESET

# Export console for use in other modules
console = Console()

def cprint(color, text):
    """
    Legacy cprint wrapper using rich.
    concatenates color (ANSI) + text + RESET and renders it using Text.from_ansi
    to ensure ANSI codes are displayed correctly.
    """
    # Check if color or text is None to prevent TypeError
    color = str(color) if color is not None else ""
    text = str(text) if text is not None else ""

    # Check if color is an ANSI string.
    # If it is an ANSI string, Text.from_ansi will parse it.

    full_text = color + text + RESET

    try:
        # Use simple print if we suspect Text.from_ansi is causing issues with nested styles in Rich
        # Or just strip ANSI codes if we want to be safe, but we want colors.

        # The error seems to be deeper in Rich when it encounters a Style object where it expects a string.
        # This might be because we are feeding it something that it tries to parse as a style name but fails.
        # However, we are passing a Text object to console.print()

        # Let's try to just print the text with the color style if 'color' argument matches known styles.
        # But 'color' here is an ANSI code string.

        console.print(Text.from_ansi(full_text))
    except AttributeError:
        # Fallback to standard print if Rich fails
        print(full_text)

def banner():
    """
    Displays the GA banner using a Rich Panel.
    """
    title = "[bold cyan]🚀  GM (GEMINI MANAGER)  🚀[/]"
    panel = Panel(Align.center(title), style="bold magenta", expand=False)
    console.print(panel)
    console.print("") # Newline

def print_rich_help():
    """Prints a beautiful Rich-formatted help screen for the MAIN command."""
    # Note: Avoid importing print_logo here to prevent circular imports if possible,
    # or import inside function.

    console.print("[bold white]Usage:[/] [bold cyan]gm[/] [dim][OPTIONS][/] [bold magenta]COMMAND[/] [dim][ARGS]...[/]\n")

    # Commands Table
    cmd_table = Table(show_header=False, box=None, padding=(0, 2))
    cmd_table.add_column("Command", style="bold cyan", width=20)
    cmd_table.add_column("Description", style="white")

    commands = [
        ("backup", "Backup GM configuration and chats"),
        ("restore", "Restore GM configuration from a backup"),
        ("chat", "Manage chat history"),
        ("check-integrity", "Check integrity of current configuration"),
        ("list-backups", "List available backups"),
        ("prune", "Prune old backups (local or cloud)"),
        ("check-b2", "Verify Backblaze B2 credentials"),
        ("sync", "Sync backups with Cloud (push/pull)"),
        ("config", "Manage persistent configuration"),
        ("doctor", "Run system diagnostic check"),
        ("resets", "Manage GM free tier reset schedules"),
        ("cooldown", "Show account cooldown status"),
        ("recommend", "Get the next best account recommendation"),
        ("stats", "Show usage statistics (last 7 days)"),
    ]

    for cmd, desc in commands:
        cmd_table.add_row(cmd, desc)

    console.print(Panel(cmd_table, title="[bold magenta]Available Commands[/]", border_style="cyan"))

    # Options Table
    opt_table = Table(show_header=False, box=None, padding=(0, 2))
    opt_table.add_column("Option", style="bold yellow", width=20)
    opt_table.add_column("Description", style="white")

    options = [
        ("--login", "Login to GM CLI"),
        ("--logout", "Logout from GM CLI"),
        ("--session", "Show current active session"),
        ("--update", "Reinstall / update GM CLI"),
        ("--check-update", "Check for updates"),
        ("--help, -h", "Show this message and exit"),
    ]

    for opt, desc in options:
        opt_table.add_row(opt, desc)

    console.print(Panel(opt_table, title="[bold yellow]Options[/]", border_style="green"))
    sys.exit(0)
