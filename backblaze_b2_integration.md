This is a great upgrade. Integrating Backblaze B2 will solve your cross-platform issues by decoupling the backup storage from the local filesystem (no more relying on `/sdcard` or specific `/root` paths).

Here is the implementation plan. You will need to create **1 new file** and modify **4 existing files**.

### **1. New File: `src/gemini_manager/b2.py`**

Create this file to handle all Backblaze B2 interactions (authentication, uploading, downloading). We will use the official `b2sdk` library.

```python
#!/usr/bin/env python3
import os
import sys
from .ui import cprint, NEON_GREEN, NEON_RED, NEON_YELLOW

try:
    from b2sdk.v2 import InMemoryAccountInfo, B2Api
except ImportError:
    B2Api = None

class B2Manager:
    def __init__(self, key_id, app_key, bucket_name):
        if not B2Api:
            cprint(NEON_RED, "[ERROR] 'b2sdk' is not installed. Please run: pip install b2sdk")
            sys.exit(1)
        
        self.info = InMemoryAccountInfo()
        self.b2_api = B2Api(self.info)
        self.bucket_name = bucket_name
        
        try:
            cprint(NEON_YELLOW, "[CLOUD] Authenticating with Backblaze B2...")
            self.b2_api.authorize_account("production", key_id, app_key)
            self.bucket = self.b2_api.get_bucket_by_name(bucket_name)
            cprint(NEON_GREEN, f"[CLOUD] Connected to bucket: {bucket_name}")
        except Exception as e:
            cprint(NEON_RED, f"[CLOUD] Authentication failed: {e}")
            sys.exit(1)

    def upload(self, local_path, remote_name=None):
        if not remote_name:
            remote_name = os.path.basename(local_path)
        
        cprint(NEON_YELLOW, f"[CLOUD] Uploading {local_path} -> {remote_name}...")
        try:
            self.bucket.upload_local_file(
                local_file=local_path,
                file_name=remote_name
            )
            cprint(NEON_GREEN, "[CLOUD] Upload successful!")
        except Exception as e:
            cprint(NEON_RED, f"[CLOUD] Upload failed: {e}")

    def list_backups(self):
        """Returns a list of file objects (id, file_name, upload_timestamp)."""
        return self.bucket.ls(recursive=True)

    def download(self, remote_name, local_path):
        cprint(NEON_YELLOW, f"[CLOUD] Downloading {remote_name} -> {local_path}...")
        try:
            download_dest = self.bucket.download_file_by_name(remote_name)
            download_dest.save_to(local_path)
            cprint(NEON_GREEN, "[CLOUD] Download successful!")
        except Exception as e:
            cprint(NEON_RED, f"[CLOUD] Download failed: {e}")
            sys.exit(1)
```

-----

### **2. Modify: `pyproject.toml`**

Add `b2sdk` to your project dependencies so it installs automatically.

```toml
# In [project] section, find dependencies = [] and change to:
dependencies = [
    "b2sdk>=1.18.0"
]
```

-----

### **3. Modify: `src/gemini_manager/cli.py`**

Update the argument parser to accept B2 credentials and pass them to the sub-commands.

**Changes:**

1.  Add new arguments (`--cloud`, `--b2-id`, `--b2-key`, `--bucket`) to the `backup` and `restore` subparsers.
2.  Update the `if args.command == ...` blocks to pass these new flags into `sys.argv`.

**Modified Code Snippet (Focusing on the changes):**

```python
# ... inside main(): ...

    # --- UPDATED BACKUP PARSER ---
    backup_parser = subparsers.add_parser("backup", help="Backup GM configuration.")
    # ... existing args ...
    backup_parser.add_argument("--cloud", action="store_true", help="Upload backup to Cloud (B2)")
    backup_parser.add_argument("--bucket", help="B2 Bucket Name")
    backup_parser.add_argument("--b2-id", help="B2 Key ID (or set env B2_APPLICATION_KEY_ID)")
    backup_parser.add_argument("--b2-key", help="B2 App Key (or set env B2_APPLICATION_KEY)")

    # --- UPDATED RESTORE PARSER ---
    restore_parser = subparsers.add_parser("restore", help="Restore GM configuration.")
    # ... existing args ...
    restore_parser.add_argument("--cloud", action="store_true", help="Restore from Cloud (B2)")
    restore_parser.add_argument("--bucket", help="B2 Bucket Name")
    restore_parser.add_argument("--b2-id", help="B2 Key ID")
    restore_parser.add_argument("--b2-key", help="B2 App Key")

    # ... inside args parsing block ...

    if args.command == "backup":
        sys.argv = ["gm-backup"]
        # ... existing arg extensions ...
        if args.cloud: sys.argv.append("--cloud")
        if args.bucket: sys.argv.extend(["--bucket", args.bucket])
        if args.b2_id: sys.argv.extend(["--b2-id", args.b2_id])
        if args.b2_key: sys.argv.extend(["--b2-key", args.b2_key])
        backup_main()

    elif args.command == "restore":
        sys.argv = ["gm-restore"]
        # ... existing arg extensions ...
        if args.cloud: sys.argv.append("--cloud")
        if args.bucket: sys.argv.extend(["--bucket", args.bucket])
        if args.b2_id: sys.argv.extend(["--b2-id", args.b2_id])
        if args.b2_key: sys.argv.extend(["--b2-key", args.b2_key])
        restore_main()
```

-----

### **4. Modify: `src/gemini_manager/backup.py`**

Update it to initialize the `B2Manager` and upload the file after the tarball is created.

**Changes:**

1.  Import `B2Manager`.
2.  Add arguments to `argparse`.
3.  After the archive creation step, trigger the upload.

**Modified Code Snippet:**

```python
# ... imports ...
from .b2 import B2Manager  # <--- Import the new module

def main():
    p = argparse.ArgumentParser(...)
    # ... existing args ...
    p.add_argument("--cloud", action="store_true")
    p.add_argument("--bucket")
    p.add_argument("--b2-id")
    p.add_argument("--b2-key")
    args = p.parse_args()

    # ... [Existing code: timestamp generation, archive creation] ...
    
    # ... [Existing code: Archive saved at: archive_path] ...
    
    # --- NEW CODE BLOCK: CLOUD UPLOAD ---
    if args.cloud:
        # Resolve credentials (CLI arg > Env Var)
        key_id = args.b2_id or os.environ.get("B2_APPLICATION_KEY_ID")
        app_key = args.b2_key or os.environ.get("B2_APPLICATION_KEY")
        bucket = args.bucket or os.environ.get("B2_BUCKET_NAME")

        if not (key_id and app_key and bucket):
            print("[ERROR] Cloud upload requested but credentials missing.")
            print("Provide --b2-id, --b2-key, --bucket OR set env vars.")
        else:
            b2 = B2Manager(key_id, app_key, bucket)
            # Upload the tar.gz we just created
            b2.upload(archive_path, remote_name=os.path.basename(archive_path))
    # ------------------------------------

    print("Backup complete.")
```

-----

### **5. Modify: `src/gemini_manager/restore.py`**

Update it to download the backup from the cloud to a temporary path before restoring.

**Changes:**

1.  Import `B2Manager`.
2.  Add logic to `main()`: if `--cloud` is used, don't search local dir; instead, list B2 files, pick the oldest/latest, and download it.

**Modified Code Snippet:**

```python
# ... imports ...
from .b2 import B2Manager # <--- Import

def main():
    p = argparse.ArgumentParser(...)
    # ... existing args ...
    p.add_argument("--cloud", action="store_true")
    p.add_argument("--bucket")
    p.add_argument("--b2-id")
    p.add_argument("--b2-key")
    args = p.parse_args()

    # ... existing variables setup ...
    from_archive = None

    # --- NEW CODE BLOCK: CLOUD DISCOVERY ---
    if args.cloud:
        key_id = args.b2_id or os.environ.get("B2_APPLICATION_KEY_ID")
        app_key = args.b2_key or os.environ.get("B2_APPLICATION_KEY")
        bucket_name = args.bucket or os.environ.get("B2_BUCKET_NAME")

        if not (key_id and app_key and bucket_name):
            print("[ERROR] Cloud restore requested but credentials missing.")
            sys.exit(1)

        b2 = B2Manager(key_id, app_key, bucket_name)
        
        # 1. List backups
        print("Fetching file list from B2...")
        # b2sdk ls returns a generator of (file_version, folder_name) tuples usually
        # We need to simplify this logic for the snippet:
        all_files = []
        for file_version, _ in b2.list_backups():
            if file_version.file_name.endswith(".gemini-manager.tar.gz"):
                ts = parse_timestamp_from_name(file_version.file_name)
                if ts:
                    all_files.append((ts, file_version.file_name))
        
        if not all_files:
            print("No valid backups found in B2 bucket.")
            sys.exit(1)

        # 2. Auto-select oldest (matches existing logic) or latest
        # Sorting by timestamp (earliest first)
        all_files.sort(key=lambda x: time.mktime(x[0]))
        target_file_name = all_files[0][1]
        print(f"Auto-selected oldest cloud backup: {target_file_name}")

        # 3. Download to a temporary file
        temp_download = os.path.join(tempfile.gettempdir(), target_file_name)
        b2.download(target_file_name, temp_download)
        
        from_archive = temp_download
    # ---------------------------------------

    # ... [Rest of the existing logic: elif args.from_dir ... else auto-discover local] ...
    # The existing logic checks 'if args.from_dir' first. 
    # You must insert the 'if args.cloud' block BEFORE the 'else' block 
    # or ensure 'from_archive' is set so the script knows what to do.

    # ... [Existing Restore Process (extract, verify, swap)] ...
```