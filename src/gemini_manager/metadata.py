from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from typing import Any, Optional

from .config import DEFAULT_BACKUP_DIR


def metadata_path_for_archive(archive_path: str) -> str:
    """
    Generate the metadata file path for a given backup archive.
    Example: 
      backup.tar.gz -> backup.metadata.json
      backup.tar.gz.gpg -> backup.metadata.json
    """
    base = archive_path[:-4] if archive_path.endswith(".gpg") else archive_path
    if base.endswith(".tar.gz"):
        base = base[:-7]
    return f"{base}.metadata.json"


def _safe_email(email: str) -> str:
    """Sanitize email for use in filenames by replacing separators and spaces."""
    return str(email).replace(os.path.sep, "_").replace(" ", "_")


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
    metadata_only: bool = False,
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


def write_metadata(path: str, metadata: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)


def create_backup_metadata(
    *,
    archive_path: str,
    active_email: str | None,
    status: dict[str, Any] | None = None,
) -> Optional[str]:
    if not active_email:
        return None

    metadata_path = metadata_path_for_archive(archive_path)
    status = status or {"email": active_email, "models": {}}
    metadata = build_status_metadata(
        status,
        archive_name=os.path.basename(archive_path),
        archive_path=archive_path,
        metadata_only=False,
    )
    write_metadata(metadata_path, metadata)
    return metadata_path


def _metadata_paths_for_email(backup_dir: str, email: str) -> list[str]:
    if not os.path.isdir(backup_dir):
        return []
    return sorted(
        [
            os.path.join(backup_dir, name)
            for name in os.listdir(backup_dir)
            if name.endswith(".metadata.json") and _safe_email(email) in name
        ],
        reverse=True,
    )


def patch_status_metadata(status: dict[str, Any], args: Any = None) -> Optional[str]:
    email = status.get("email")
    if not email:
        return None

    backup_dir = os.path.abspath(os.path.expanduser(getattr(args, "backup_dir", DEFAULT_BACKUP_DIR)))
    paths = _metadata_paths_for_email(backup_dir, email)
    metadata_path = paths[0] if paths else os.path.join(
        backup_dir,
        f"{time.strftime('%Y-%m-%d_%H%M%S')}-{_safe_email(email)}.gemini-manager.metadata.json",
    )

    existing = {}
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as fh:
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
    write_metadata(metadata_path, metadata)

    if args and getattr(args, "cloud", False):
        try:
            from .cloud_factory import get_cloud_provider

            provider = get_cloud_provider(args)
            if provider:
                provider.upload_file(metadata_path, os.path.basename(metadata_path))
        except Exception:
            pass

    return metadata_path


def load_local_metadata(backup_dir: str = DEFAULT_BACKUP_DIR) -> list[dict[str, Any]]:
    backup_dir = os.path.abspath(os.path.expanduser(backup_dir))
    if not os.path.isdir(backup_dir):
        return []

    records = []
    for name in sorted(os.listdir(backup_dir)):
        if not name.endswith(".metadata.json"):
            continue
        path = os.path.join(backup_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            data["_metadata_name"] = name
            records.append(data)
        except Exception:
            continue
    return records


def load_cloud_metadata(provider) -> list[dict[str, Any]]:
    records = []
    with tempfile.TemporaryDirectory(prefix="gm-metadata-") as tmp:
        for item in provider.list_files():
            name = getattr(item, "name", "")
            if not name.endswith(".metadata.json"):
                continue
            local_path = os.path.join(tmp, os.path.basename(name))
            try:
                provider.download_file(name, local_path)
                with open(local_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                data["_metadata_name"] = name
                records.append(data)
            except Exception:
                continue
    return records


def latest_metadata_by_email(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    Find the most recent metadata record for each unique email address,
    prioritizing records that contain detailed model quota information.
    """
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        email = record.get("email")
        if not email:
            continue
        key = email.lower()
        current = latest.get(key)

        # Priority: updated_at > captured_at > saved_at > created_at
        record_time = (
            record.get("updated_at") or 
            record.get("captured_at") or 
            record.get("saved_at") or 
            record.get("created_at") or 
            ""
        )
        
        has_models = bool(record.get("models"))
        
        if current is None:
            latest[key] = record
            continue

        current_time = (
            current.get("updated_at") or 
            current.get("captured_at") or 
            current.get("saved_at") or 
            current.get("created_at") or 
            ""
        )
        current_has_models = bool(current.get("models"))

        # Selection Logic:
        # 1. Prefer records with models over those without.
        # 2. If model-presence is equal, prefer the newer timestamp.
        if has_models and not current_has_models:
            latest[key] = record
        elif has_models == current_has_models:
            if record_time > current_time:
                latest[key] = record
                
    return latest
