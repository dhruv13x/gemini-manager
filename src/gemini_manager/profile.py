import os
import zipfile
import shutil
import argparse
from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm
from .config import DEFAULT_GEMINI_HOME

console = Console()

def do_profile(args: argparse.Namespace):
    """
    Dispatcher for profile commands.
    """
    if args.profile_command == "export":
        perform_export(args)
    elif args.profile_command == "import":
        perform_import(args)
    else:
        console.print("[red]Invalid profile command.[/]")

def perform_export(args: argparse.Namespace):
    """
    Exports configuration and history to a zip archive.
    """
    output_path = Path(args.file)
    if not output_path.name.endswith(".zip"):
        output_path = output_path.with_suffix(".zip")

    console.print(f"[bold cyan]Exporting profile to {output_path}...[/]")

    # Identify config file: prioritize gemini-manager.toml in CWD, then ~/.gemini-manager/gemini-manager.toml
    config_file = "gemini-manager.toml"
    if not os.path.exists(config_file):
        possible_path = os.path.join(DEFAULT_GEMINI_HOME, "gemini-manager.toml")
        if os.path.exists(possible_path):
            config_file = possible_path
        else:
            config_file = None

    files_to_export = [
        os.path.expanduser("~/.gm-cooldown.json"),
        os.path.expanduser("~/.gemini_history.json"),
        os.path.expanduser("~/.gemini_resets.json")
    ]

    if config_file:
        files_to_export.insert(0, config_file)
    else:
        console.print("[yellow]No gemini-manager.toml found to export. Only history will be saved.[/]")

    try:
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for filepath in files_to_export:
                if os.path.exists(filepath):
                    # Store file with its basename in the archive
                    zf.write(filepath, arcname=os.path.basename(filepath))
                    console.print(f"  [green]Added[/] {filepath}")
                else:
                    console.print(f"  [yellow]Skipped (not found)[/] {filepath}")
        console.print(f"[bold green]Profile exported successfully to {output_path}[/]")
    except Exception as e:
        console.print(f"[bold red]Export failed:[/ {e}")

def perform_import(args: argparse.Namespace):
    """
    Imports configuration and history from a zip archive.
    """
    input_path = Path(args.file)
    if not input_path.exists():
        console.print(f"[bold red]Error: File {input_path} not found.[/]")
        return

    console.print(f"[bold cyan]Importing profile from {input_path}...[/]")

    try:
        with zipfile.ZipFile(input_path, "r") as zf:
            namelist = zf.namelist()

            # Map filenames to their destination paths
            destinations = {
                "gemini-manager.toml": "gemini-manager.toml", # Restores to CWD by default
                ".gm-cooldown.json": os.path.expanduser("~/.gm-cooldown.json"),
                ".gemini_history.json": os.path.expanduser("~/.gemini_history.json"),
                ".gemini_resets.json": os.path.expanduser("~/.gemini_resets.json")
            }

            # If gemini-manager.toml is in the archive
            if "gemini-manager.toml" in namelist:
                # If no gemini-manager.toml in CWD, prioritize DEFAULT_GEMINI_HOME
                if not os.path.exists("gemini-manager.toml"):
                    destinations["gemini-manager.toml"] = os.path.join(DEFAULT_GEMINI_HOME, "gemini-manager.toml")
                # Else, it defaults to CWD already as set above

            for filename in namelist:
                if filename in destinations:
                    dest = destinations[filename]
                    if os.path.exists(dest) and not args.force:
                        if not Confirm.ask(f"File {dest} already exists. Overwrite?"):
                            console.print(f"  [yellow]Skipped[/] {filename}")
                            continue

                    # Ensure directory exists for destination
                    dest_dir = os.path.dirname(dest)
                    if dest_dir and not os.path.exists(dest_dir):
                        os.makedirs(dest_dir, exist_ok=True)

                    # Extract to temporary location or read bytes and write
                    with zf.open(filename) as source, open(dest, "wb") as target:
                        shutil.copyfileobj(source, target)
                    console.print(f"  [green]Restored[/] {dest}")
                else:
                    console.print(f"  [dim]Ignored unknown file in archive: {filename}[/]")

        console.print("[bold green]Profile imported successfully.[/]")

    except zipfile.BadZipFile:
        console.print("[bold red]Error: Invalid zip file.[/]")
    except Exception as e:
        console.print(f"[bold red]Import failed:[/ {e}")
