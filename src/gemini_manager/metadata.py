from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TypedDict, Union


class ModelState(TypedDict, total=False):
    percent: int
    percent_used: int
    percent_left: int
    extra: str
    reset_h: int
    reset_m: int
    reset_at: str


class SnapshotRecord(TypedDict, total=False):
    schema_version: int
    product: str
    email: str
    archive_name: str
    archive_path: str
    created_at: str
    captured_at: str
    reset_at: str
    models: Dict[str, ModelState]
    _metadata_name: str
    _entity_type: str


class AccountState(TypedDict, total=False):
    schema_version: int
    product: str
    email: str
    updated_at: str
    captured_at: str
    next_available_at: str
    models: Dict[str, ModelState]
    status_source: str
    metadata_only: bool
    _metadata_name: str
    _entity_type: str


class ResetRecord(TypedDict, total=False):
    schema_version: int
    id: str
    email: str
    saved_string: str
    reset_ist: str
    saved_at: str
    models: Optional[Dict[str, Any]]
    _entity_type: str


# Trust-based ranking priority
# Higher is more authoritative
ENTITY_PRIORITY = {
    "state": 300,
    "snapshot": 200,
    "reset": 100,
}
CURRENT_SCHEMA_VERSION = 2

from .config import DEFAULT_BACKUP_DIR, ACCOUNTS_DIR
from .cloud_storage import CloudFile


def snapshot_path_for_archive(archive_path: str) -> str:
    """
    Generate the immutable snapshot metadata path for a backup archive.
    Example: 
      backup.tar.gz -> backup.snapshot.json
    """
    base = archive_path[:-4] if archive_path.endswith(".gpg") else archive_path
    if base.endswith(".tar.gz"):
        base = base[:-7]
    return f"{base}.snapshot.json"


def get_account_state_path(email: str, accounts_dir: str = ACCOUNTS_DIR) -> str:
    """
    Generate the unique, mutable state path for an account's live health.
    Example: accounts/drdoom13x@gmail.com.state.json
    """
    accounts_dir = os.path.abspath(os.path.expanduser(accounts_dir))
    return os.path.join(accounts_dir, f"{_safe_email(email)}.state.json")


def _safe_email(email: str) -> str:
    """Sanitize email for use in filenames by replacing separators, spaces and '@'."""
    return str(email).replace(os.path.sep, "_").replace(" ", "_").replace("@", "_at_")


def _now() -> datetime:
    return datetime.now().astimezone()


def _model_reset_at(captured_at: datetime, info: dict[str, Any]) -> Optional[str]:
    h = info.get("reset_h")
    m = info.get("reset_m")
    if h is None or m is None:
        return None
    try:
        return (captured_at + timedelta(hours=int(h), minutes=int(m))).isoformat()
    except Exception:
        return None


def build_status_metadata(
    status: dict[str, Any],
    *,
    archive_name: str | None = None,
    archive_path: str | None = None,
    metadata_only: bool = True,
) -> dict[str, Any]:
    captured_at = _now()
    models = status.get("models", {}) or {}
    model_resets = []
    enriched_models = {}

    for name, info in models.items():
        model_info = dict(info)
        reset_at = _model_reset_at(captured_at, model_info)
        if reset_at:
            model_info["reset_at"] = reset_at
            model_resets.append(datetime.fromisoformat(reset_at))
        enriched_models[name] = model_info

    next_available_at = max(model_resets).isoformat() if model_resets else captured_at.isoformat()

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "product": "gemini",
        "email": status.get("email"),
        "archive_name": archive_name,
        "archive_path": archive_path,
        "created_at": captured_at.isoformat(),
        "updated_at": captured_at.isoformat(),
        "captured_at": captured_at.isoformat(),
        "next_available_at": next_available_at,
        "reset_at": next_available_at,
        "models": enriched_models,
        "status_source": "live_gemini_status",
        "metadata_only": metadata_only,
    }


def load_latest_status_for_email(email: str, resets: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    candidates = [
        entry for entry in resets
        if entry.get("email") == email and isinstance(entry.get("models"), dict)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda entry: entry.get("saved_at") or entry.get("reset_ist") or "", reverse=True)
    latest = candidates[0]
    return {"email": email, "models": latest.get("models", {})}


def write_snapshot(path: str, metadata: dict[str, Any]) -> None:
    """
    Writes immutable snapshot metadata.
    Does not perform change detection as snapshots are unique/timestamped.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, sort_keys=True)


def write_state(path: str, metadata: dict[str, Any]) -> bool:
    """
    Writes mutable account state metadata if content has changed.
    Returns True if written, False if skipped.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    new_data = json.dumps(metadata, indent=2, sort_keys=True)
    
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                old_metadata = json.load(fh)
                # Ignore volatile fields when comparing to prevent redundant churn
                comparison_old = {k: v for k, v in old_metadata.items() if k not in ("updated_at", "captured_at")}
                comparison_new = {k: v for k, v in metadata.items() if k not in ("updated_at", "captured_at")}
                
                if comparison_old == comparison_new:
                    return False
        except Exception:
            pass

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new_data)
    return True


def create_backup_snapshot(
    *,
    archive_path: str,
    active_email: str | None,
    status: dict[str, Any] | None = None,
) -> Optional[str]:
    if not active_email:
        return None

    # 1. Create Immutable Snapshot (Archive Sidecar)
    snapshot_path = snapshot_path_for_archive(archive_path)
    status = status or {"email": active_email, "models": {}}
    metadata = build_status_metadata(
        status,
        archive_name=os.path.basename(archive_path),
        archive_path=archive_path,
        metadata_only=False,
    )
    write_snapshot(snapshot_path, metadata)
    return snapshot_path


def _historical_snapshot_paths(backup_dir: str, email: str) -> list[str]:
    if not os.path.isdir(backup_dir):
        return []
    safe = _safe_email(email)
    return sorted(
        [
            os.path.join(backup_dir, name)
            for name in os.listdir(backup_dir)
            if (name.endswith(".snapshot.json") or name.endswith(".metadata.json")) and safe in name
        ],
        reverse=True,
    )


# Union type for all entity records
EntityRecord = Union[SnapshotRecord, AccountState]


def patch_status_metadata(status: dict[str, Any], args: Any = None) -> Optional[str]:
    email = status.get("email")
    if not email:
        return None

    accounts_dir = os.path.abspath(os.path.expanduser(getattr(args, "accounts_dir", ACCOUNTS_DIR)))
    state_path = get_account_state_path(email, accounts_dir)

    existing: AccountState = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
        except Exception:
            existing = {}

    metadata = build_status_metadata(
        status,
        archive_name=existing.get("archive_name"),
        archive_path=existing.get("archive_path"),
        metadata_only=not bool(existing.get("archive_name")),
    )
    if existing.get("created_at"):
        metadata["created_at"] = existing["created_at"]
    
    was_written = write_state(state_path, metadata)

    if was_written:
        # Update Layer 2 Index (Registry)
        try:
            from .registry import get_registry
            get_registry().update_account(email, metadata)
        except Exception:
            pass

    if was_written and args and getattr(args, "cloud", False):
        try:
            from .cloud_factory import get_cloud_provider

            provider = get_cloud_provider(args)
            if provider:
                # Still upload individual state for decentralization/multi-machine reconstructability
                provider.upload_file(state_path, f"accounts/{os.path.basename(state_path)}")
                # Also sync the Registry for dashboard speed
                from .registry import sync_registry_with_cloud
                sync_registry_with_cloud(provider, direction="push")
        except Exception:
            pass

    return state_path


def load_local_snapshots(backup_dir: str = DEFAULT_BACKUP_DIR) -> List[SnapshotRecord]:
    """Loads all archival snapshots from the backup directory."""
    backup_dir = os.path.abspath(os.path.expanduser(backup_dir))
    records: List[SnapshotRecord] = []
    if os.path.isdir(backup_dir):
        for name in sorted(os.listdir(backup_dir)):
            # Support both new .snapshot.json and legacy .metadata.json
            if not (name.endswith(".snapshot.json") or name.endswith(".metadata.json")):
                continue
            path = os.path.join(backup_dir, name)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data: SnapshotRecord = json.load(fh)
                data["_metadata_name"] = name
                data["_entity_type"] = "snapshot"
                records.append(data)
            except Exception:
                continue
    return records


def load_local_states(accounts_dir: str = ACCOUNTS_DIR) -> List[AccountState]:
    """Loads all mutable account state files from the accounts directory."""
    accounts_dir = os.path.abspath(os.path.expanduser(accounts_dir))
    records: List[AccountState] = []
    if os.path.isdir(accounts_dir):
        for name in sorted(os.listdir(accounts_dir)):
            if not name.endswith(".state.json"):
                continue
            path = os.path.join(accounts_dir, name)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data: AccountState = json.load(fh)
                data["_metadata_name"] = name
                data["_entity_type"] = "state"
                records.append(data)
            except Exception:
                continue
    return records


def parse_cloud_summary(cloud_file: CloudFile) -> Optional[dict[str, Any]]:
    """
    Attempts to reconstruct a basic record from cloud metadata headers.
    Returns None if essential headers (email) are missing.
    """
    m = cloud_file.metadata
    email = m.get("gm-email")
    if not email:
        return None
        
    record = {
        "email": email,
        "_entity_type": m.get("gm-entity-type", "unknown"),
        "captured_at": m.get("gm-captured-at"),
        "next_available_at": m.get("gm-reset-at"),
        "reset_at": m.get("gm-reset-at"),
        "models": {},
        "_metadata_name": os.path.basename(cloud_file.name),
        "_is_cloud_summary": True
    }
    
    # Parse models (gm-q-flash -> models['Flash']['percent'])
    for k, v in m.items():
        if k.startswith("gm-q-"):
            model_name = k[5:].capitalize()
            try:
                record["models"][model_name] = {"percent": int(v)}
            except (ValueError, TypeError):
                pass
                
    return record


def load_cloud_snapshots(provider) -> List[SnapshotRecord]:
    """
    Loads all archival snapshots from the cloud provider.
    Uses 'Shadow Metadata' (B2 File Info) to avoid downloads where possible.
    """
    records: List[SnapshotRecord] = []
    
    cloud_files = provider.list_files()
    
    # Optimization: We can't use prefix reliably with B2Manager list_files yet if it doesn't support it,
    # but B2Manager list_files (Bucket.ls) is recursive anyway.
    
    with tempfile.TemporaryDirectory(prefix="gm-snapshots-") as tmp:
        for item in cloud_files:
            name = item.name
            if not (name.endswith(".snapshot.json") or name.endswith(".metadata.json")):
                continue
                
            # 1. Attempt to use Shadow Metadata
            summary = parse_cloud_summary(item)
            if summary:
                records.append(summary)
                continue
                
            # 2. Fallback to download if metadata headers are missing
            local_path = os.path.join(tmp, os.path.basename(name))
            try:
                provider.download_file(name, local_path)
                with open(local_path, "r", encoding="utf-8") as fh:
                    data: SnapshotRecord = json.load(fh)
                data["_metadata_name"] = os.path.basename(name)
                data["_entity_type"] = "snapshot"
                records.append(data)
            except Exception:
                continue
    return records


def load_cloud_states(provider) -> List[AccountState]:
    """
    Loads all account state files from the cloud provider.
    Uses 'Shadow Metadata' (B2 File Info) to avoid downloads where possible.
    """
    records: List[AccountState] = []
    
    # States are stored under accounts/ prefix in cloud
    cloud_files = provider.list_files(prefix="accounts/")
    
    with tempfile.TemporaryDirectory(prefix="gm-states-") as tmp:
        for item in cloud_files:
            name = item.name
            if not name.endswith(".state.json"):
                continue
            
            # 1. Attempt to use Shadow Metadata
            summary = parse_cloud_summary(item)
            if summary:
                records.append(summary)
                continue

            # 2. Fallback to download
            local_path = os.path.join(tmp, os.path.basename(name))
            try:
                provider.download_file(name, local_path)
                with open(local_path, "r", encoding="utf-8") as fh:
                    data: AccountState = json.load(fh)
                data["_metadata_name"] = os.path.basename(name)
                data["_entity_type"] = "state"
                records.append(data)
            except Exception:
                continue
    return records


def get_cloud_summary(entity: Union[EntityRecord, ResetRecord]) -> Dict[str, str]:
    """
    Extract a compact summary for cloud metadata headers.
    Headers must be strings.
    """
    summary = {
        "gm-email": entity.get("email", "unknown"),
        "gm-entity-type": entity.get("_entity_type", "unknown"),
        "gm-captured-at": entity.get("captured_at") or entity.get("saved_at") or "",
        "gm-reset-at": entity.get("next_available_at") or entity.get("reset_at") or entity.get("reset_ist") or "",
    }
    
    models = entity.get("models")
    if isinstance(models, dict):
        for name, state in models.items():
            # Use short keys to stay within header limits (B2 has 10 limit usually)
            p = state.get("percent")
            if p is not None:
                summary[f"gm-q-{name.lower()}"] = str(p)
                
    return {k: v for k, v in summary.items() if v}


def latest_entity_by_email(
    records: List[Union[EntityRecord, ResetRecord, Dict[str, Any]]]
) -> Dict[str, Union[EntityRecord, ResetRecord]]:
    """
    Find the most recent entity record (snapshot or state) for each unique email address,
    prioritizing records that contain detailed model quota information.
    """
    latest: Dict[str, Union[EntityRecord, ResetRecord]] = {}
    for record in records:
        email = record.get("email")
        if not email:
            continue
        key = email.lower()
        current = latest.get(key)

        if current is None:
            latest[key] = record
            continue

        # 1. Compare Entity Class Priority
        rec_type = record.get("_entity_type", "reset")
        cur_type = current.get("_entity_type", "reset")
        rec_prio = ENTITY_PRIORITY.get(rec_type, 0)
        cur_prio = ENTITY_PRIORITY.get(cur_type, 0)

        # 2. Compare Model Richness
        rec_has_models = bool(record.get("models"))
        cur_has_models = bool(current.get("models"))

        # 3. Compare Timestamp Freshness
        # Priority: updated_at > captured_at > saved_at > created_at > reset_ist
        def get_time(r):
            return (
                r.get("updated_at") or 
                r.get("captured_at") or 
                r.get("saved_at") or 
                r.get("created_at") or 
                r.get("reset_ist") or
                ""
            )
        
        rec_time = get_time(record)
        cur_time = get_time(current)

        # Ranking Heuristic:
        # A. If priorities differ, take higher priority UNLESS lower priority has models and higher doesn't.
        # B. If priorities same, take model-rich one.
        # C. If model-status same, take newer one.

        better = False
        if rec_prio > cur_prio:
            # Current is lower priority. We take record UNLESS current has models and record doesn't.
            if cur_has_models and not rec_has_models:
                better = False
            else:
                better = True
        elif rec_prio < cur_prio:
            # Record is lower priority. We only take it if it has models and current doesn't.
            if rec_has_models and not cur_has_models:
                better = True
            else:
                better = False
        else:
            # Same priority
            if rec_has_models and not cur_has_models:
                better = True
            elif not rec_has_models and cur_has_models:
                better = False
            else:
                # Same richness, take newer
                better = rec_time > cur_time

        if better:
            latest[key] = record
                
    return latest
