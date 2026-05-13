import os
import shutil
import subprocess

from .ui import cprint
from .config import NEON_GREEN, NEON_RED, NEON_YELLOW, NEON_CYAN

def backup_chat_history(backup_path: str, gemini_home_dir: str):
    """Backup the chat history from the current user's Gemini directory."""
    source_path = os.path.join(gemini_home_dir, "tmp")

    if not os.path.exists(source_path):
        cprint(NEON_RED, "Gemini chat history directory not found.")
        return

    backup_dir = os.path.join(backup_path, "tmp")

    # Ensure only one latest backup exists
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)
    os.makedirs(backup_dir, exist_ok=True)

    try:
        items = [os.path.join(source_path, i) for i in os.listdir(source_path)]
        if not items:
            cprint(NEON_YELLOW, "No chat history found to backup.")
            return

        # Process each project directory separately (latest chat per project)
        for item in items:
            name = os.path.basename(item)

            # Skip helper binary directory
            if name == "bin":
                continue
            # Skip Gemini runtime hash directories
            if len(name) == 64:
                try:
                    int(name, 16)
                    continue
                except ValueError:
                    pass

            dest_path = os.path.join(backup_dir, name)

            if os.path.islink(item) or os.path.isfile(item):
                shutil.copy(item, dest_path)

            elif os.path.isdir(item):
                shutil.copytree(item, dest_path, dirs_exist_ok=True)

                # Keep only the latest chat session inside chats/ directories
                try:
                    for root, dirs, files in os.walk(dest_path):
                        if os.path.basename(root) == "chats":
                            sessions = [
                                os.path.join(root, f)
                                for f in os.listdir(root)
                                if f.startswith("session-") and f.endswith(".json")
                            ]

                            if len(sessions) > 1:
                                latest_session = max(
                                    sessions,
                                    key=lambda p: os.path.basename(p)
                                )

                                for s in sessions:
                                    if s != latest_session:
                                        os.remove(s)
                except Exception:
                    pass
        cprint(NEON_GREEN, f"Chat history successfully backed up to {backup_dir}")
    except Exception as e:
        cprint(NEON_RED, f"Failed to backup chat history: {e}")


def restore_chat_history(backup_path: str, gemini_home_dir: str):
    """Restore the chat history to the current user's Gemini directory."""
    destination_path = os.path.join(gemini_home_dir, "tmp")
    backup_dir = os.path.join(backup_path, "tmp")

    if not os.path.exists(backup_dir):
        cprint(NEON_RED, "Chat history backup directory not found.")
        return

    os.makedirs(destination_path, exist_ok=True)

    try:
        # Clean destination first (except bin if present)
        for item in os.listdir(destination_path):
            if item == "bin":
                continue
            path = os.path.join(destination_path, item)
            if os.path.isfile(path) or os.path.islink(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)

        items = [os.path.join(backup_dir, i) for i in os.listdir(backup_dir)]
        if not items:
            cprint(NEON_YELLOW, "No chat backup found to restore.")
            return

        # Restore all project backups (each already contains only its latest session)
        for item in items:
            name = os.path.basename(item)
            dest_path = os.path.join(destination_path, name)

            if os.path.islink(item) or os.path.isfile(item):
                shutil.copy(item, dest_path)
            elif os.path.isdir(item):
                shutil.copytree(item, dest_path, dirs_exist_ok=True)

                # Safety check: ensure only one latest session remains
                try:
                    for root, dirs, files in os.walk(dest_path):
                        if os.path.basename(root) == "chats":
                            sessions = [
                                os.path.join(root, f)
                                for f in os.listdir(root)
                                if f.startswith("session-") and f.endswith(".json")
                            ]

                            if len(sessions) > 1:
                                latest_session = max(
                                    sessions,
                                    key=lambda p: os.path.basename(p)
                                )
                                for s in sessions:
                                    if s != latest_session:
                                        os.remove(s)
                except Exception:
                    pass
        cprint(NEON_GREEN, "Chat history successfully restored.")
    except Exception as e:
        cprint(NEON_RED, f"Failed to restore chat history: {e}")


def cleanup_chat_history(dry_run: bool, force: bool, gemini_home_dir: str):
    """Clear temporary chat history and logs."""
    target_dir = os.path.join(gemini_home_dir, "tmp")
    
    if not os.path.exists(target_dir):
        cprint(NEON_YELLOW, f"[INFO] Nothing to clean. Directory not found: {target_dir}")
        return

    # Get list of items to be removed (excluding 'bin')
    try:
        all_items = os.listdir(target_dir)
    except Exception as e:
        cprint(NEON_RED, f"[ERROR] Could not list directory {target_dir}: {e}")
        return

    items_to_remove = [item for item in all_items if item != "bin"]

    if not items_to_remove:
        cprint(NEON_GREEN, "[OK] Directory is already clean (only preserved items remain).")
        return

    cprint(NEON_CYAN, f"Found {len(items_to_remove)} items to clean in {target_dir}")
    
    if not force and not dry_run:
        choice = input(f"{NEON_YELLOW}Are you sure you want to proceed? (y/N): ").strip().lower()
        if choice != 'y':
            cprint(NEON_CYAN, "Cleanup cancelled.")
            return

    cprint(NEON_YELLOW, "[INFO] Cleaning up...")
    
    cleaned_count = 0
    
    for item in items_to_remove:
        item_path = os.path.join(target_dir, item)
        
        if dry_run:
            cprint(NEON_YELLOW, f"[DRY-RUN] Would delete: {item}")
            cleaned_count += 1
            continue
        
        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)
                cleaned_count += 1
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
                cleaned_count += 1
        except Exception as e:
            cprint(NEON_RED, f"[ERROR] Failed to delete {item}: {e}")

    if dry_run:
        cprint(NEON_GREEN, f"[OK] Cleanup dry run finished. Would remove {cleaned_count} items.")
    else:
        cprint(NEON_GREEN, f"[OK] Cleanup finished. Removed {cleaned_count} items.")


def resume_chat():
    """Resume the last chat session."""
    try:
        subprocess.run(["gm", "--model", "pro", "--resume"])
    except FileNotFoundError:
        cprint(NEON_RED, "The 'gm' command was not found. Make sure it is in your PATH.")
    except Exception as e:
        cprint(NEON_RED, f"Failed to resume chat: {e}")
