from rich.prompt import Prompt
from gemini_manager.settings import set_setting
from gemini_manager.ui import cprint
from gemini_manager.config import NEON_CYAN, NEON_GREEN, NEON_YELLOW, NEON_RED, DEFAULT_BACKUP_DIR
import os

def run_wizard():
    """
    Runs the interactive configuration wizard.
    """
    cprint(NEON_CYAN, "Welcome to the Gemini CLI Configuration Wizard!")
    cprint(NEON_GREEN, "We will set up your Cloud Backups (B2).")

    b2_id = Prompt.ask(f"[{NEON_YELLOW}]Enter B2 Key ID[/{NEON_YELLOW}]")
    b2_key = Prompt.ask(f"[{NEON_YELLOW}]Enter B2 App Key[/{NEON_YELLOW}]")
    bucket = Prompt.ask(f"[{NEON_YELLOW}]Enter B2 Bucket Name[/{NEON_YELLOW}]")

    # We could ask for backup dir, but we have a default.
    # Let's ask if they want to change it.
    backup_dir = Prompt.ask(f"[{NEON_YELLOW}]Enter Local Backup Directory (default: {DEFAULT_BACKUP_DIR})[/{NEON_YELLOW}]", default=DEFAULT_BACKUP_DIR)

    if b2_id:
        set_setting("GEMINI_B2_KEY_ID", b2_id)
    if b2_key:
        set_setting("GEMINI_B2_APP_KEY", b2_key)
    if bucket:
        set_setting("GEMINI_B2_BUCKET", bucket)
    
    # Save backup_dir if it's different from the default or explicitly set
    if backup_dir and backup_dir != DEFAULT_BACKUP_DIR:
        set_setting("GEMINI_BACKUP_DIR", backup_dir)
    elif backup_dir == DEFAULT_BACKUP_DIR:
        # Even if it's the default, explicitly save it for clarity in settings
        set_setting("GEMINI_BACKUP_DIR", backup_dir)

    cprint(NEON_GREEN, "Configuration saved successfully!")
