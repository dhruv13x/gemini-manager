#!/usr/bin/env python3
# src/gemini_manager/registry.py

import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime

from .config import REGISTRY_FILE, ACCOUNTS_DIR
from .metadata import AccountState, SnapshotRecord, ResetRecord, latest_entity_by_email, load_local_states, load_local_snapshots
from .ui import cprint, NEON_GREEN, NEON_RED, NEON_YELLOW

class RegistryManager:
    """
    Manages the 'Layer 2' Derived Index (registry.json).
    This index provides fast lookups for fleet health but is derived from 
    authoritative States and Snapshots.
    """
    
    def __init__(self, path: str = REGISTRY_FILE):
        self.path = os.path.abspath(os.path.expanduser(path))
        self._data: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            self._data = {}
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self._data = data
                else:
                    self._data = {}
        except Exception:
            self._data = {}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)

    def update_account(self, email: str, record: Dict[str, Any]) -> None:
        """Update the index with new data for an account."""
        email = email.lower()
        # Merge or replace? For a derived index, we use the authoritative 'latest_entity' logic
        existing = self._data.get(email, {})
        
        # Compose and pick the best
        candidates = [existing, record]
        refined = latest_entity_by_email([c for c in candidates if c])
        
        if email in refined:
            self._data[email] = refined[email]
            self.save()

    def get_all(self) -> List[Dict[str, Any]]:
        return list(self._data.values())

    def get_for_email(self, email: str) -> Optional[Dict[str, Any]]:
        return self._data.get(email.lower())

    def reconstruct(self) -> None:
        """
        Authoritative reconstruction: rebuild index from decentralized state/snapshot files.
        This fulfills the 'Layered Authority' mandate for reconstructability.
        """
        cprint(NEON_YELLOW, "[REGISTRY] Reconstructing index from authoritative files...")
        
        # 1. Load decentralized states
        states = load_local_states()
        
        # 2. Load historical snapshots
        snapshots = load_local_snapshots()
        
        # 3. Aggregate using authoritative ranking logic
        all_records = states + snapshots
        self._data = latest_entity_by_email(all_records)
        self.save()
        cprint(NEON_GREEN, f"[REGISTRY] Index rebuilt with {len(self._data)} accounts.")

def get_registry() -> RegistryManager:
    return RegistryManager()

def sync_registry_with_cloud(provider, direction: str = "push") -> None:
    """Synchronize the derived index with cloud storage."""
    reg = get_registry()
    remote_name = "gm-registry.json"
    
    if direction == "push":
        reg.save() # Ensure latest local is saved
        provider.upload_file(reg.path, remote_name)
    else:
        # Pull and Merge
        cloud_data_str = provider.download_to_string(remote_name)
        if cloud_data_str:
            try:
                cloud_data = json.loads(cloud_data_str)
                # Merge logic: latest entity wins
                local_list = reg.get_all()
                cloud_list = list(cloud_data.values())
                merged = latest_entity_by_email(local_list + cloud_list)
                reg._data = merged
                reg.save()
            except Exception as e:
                cprint(NEON_RED, f"[REGISTRY] Failed to merge cloud index: {e}")
