#!/usr/bin/env python3
# src/gemini_manager/doctor.py


import os
import shutil
import urllib.request
import argparse
from rich.console import Console
from rich.table import Table
from .b2 import B2Manager
from .ui import banner
from .config import DEFAULT_BACKUP_DIR
from .credentials import resolve_credentials

console = Console()


def do_doctor():
    banner()
    console.print("[bold cyan]🩺  Running System Diagnostic...[/]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Component", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Details", style="dim")

    # Tools
    tools = ["gm", "tar", "diff", "npm", "gpg"]
    for tool in tools:
        path = shutil.which(tool)
        if path:
            table.add_row(f"Tool: {tool}", "[bold green]OK[/]", path)
        else:
            table.add_row(f"Tool: {tool}", "[bold red]MISSING[/]", "Not found in PATH")

    # Directories
    dirs = [("~/.gemini-manager", "Config Dir"), (DEFAULT_BACKUP_DIR, "Backup Dir")]
    for d, desc in dirs:
        path = os.path.expanduser(d)
        if os.path.isdir(path):
            if os.access(path, os.W_OK):
                table.add_row(f"Dir: {desc}", "[bold green]OK[/]", f"Writable: {path}")
            else:
                table.add_row(
                    f"Dir: {desc}", "[bold red]READ-ONLY[/]", f"Exists: {path}"
                )
        else:
            table.add_row(
                f"Dir: {desc}", "[bold yellow]MISSING[/]", f"Not found: {path}"
            )

    # Internet
    try:
        urllib.request.urlopen("https://www.google.com", timeout=3)
        table.add_row("Network", "[bold green]OK[/]", "Internet accessible")
    except:
        table.add_row("Network", "[bold red]FAIL[/]", "No internet connection")

    # B2
    # Mock args for resolve_credentials (none passed via CLI for doctor usually)
    dummy_args = argparse.Namespace(b2_id=None, b2_key=None, bucket=None)
    key_id, app_key, bucket = resolve_credentials(dummy_args, allow_fail=True)

    if key_id and app_key and bucket:
        try:
            B2Manager(key_id, app_key, bucket)
            table.add_row("Cloud (B2)", "[bold green]OK[/]", "Authenticated")
        except Exception as e:
            table.add_row("Cloud (B2)", "[bold red]FAIL[/]", str(e))
    else:
        table.add_row("Cloud (B2)", "[yellow]SKIPPED[/]", "Credentials not set")

    console.print(table)
    console.print("[bold green]Diagnostic Complete.[/]")
