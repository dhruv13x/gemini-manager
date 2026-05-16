
import pytest
from unittest.mock import patch, MagicMock
import os
import shutil
from gemini_manager.prune import do_prune
from gemini_manager.config import DEFAULT_GEMINI_HOME

def test_do_prune_workspace(fs):
    gemini_home = "/tmp/gemini"
    os.makedirs(gemini_home, exist_ok=True)
    
    # Files to prune
    fs.create_file(os.path.join(gemini_home, "logs.json"))
    fs.create_file(os.path.join(gemini_home, "history.jsonl"))
    
    # Directories to prune
    os.makedirs(os.path.join(gemini_home, "tmp"), exist_ok=True)
    fs.create_file(os.path.join(gemini_home, "tmp/file.txt"))
    
    os.makedirs(os.path.join(gemini_home, "history"), exist_ok=True)
    fs.create_file(os.path.join(gemini_home, "history/session.json"))
    
    # Files to preserve
    fs.create_file(os.path.join(gemini_home, "google_accounts.json"))
    fs.create_file(os.path.join(gemini_home, "settings.json"))

    args = MagicMock(src=gemini_home, dry_run=False)
    
    do_prune(args)
    
    # Verify pruned
    assert not os.path.exists(os.path.join(gemini_home, "logs.json"))
    assert not os.path.exists(os.path.join(gemini_home, "history.jsonl"))
    assert not os.path.exists(os.path.join(gemini_home, "tmp/file.txt"))
    assert not os.path.exists(os.path.join(gemini_home, "history"))
    
    # Verify preserved
    assert os.path.exists(os.path.join(gemini_home, "google_accounts.json"))
    assert os.path.exists(os.path.join(gemini_home, "settings.json"))

def test_do_prune_workspace_preserve_bin(fs):
    gemini_home = "/tmp/gemini"
    os.makedirs(gemini_home, exist_ok=True)
    
    os.makedirs(os.path.join(gemini_home, "tmp/bin"), exist_ok=True)
    fs.create_file(os.path.join(gemini_home, "tmp/bin/helper"))
    fs.create_file(os.path.join(gemini_home, "tmp/other.txt"))

    args = MagicMock(src=gemini_home, dry_run=False)
    do_prune(args)
    
    assert os.path.exists(os.path.join(gemini_home, "tmp/bin/helper"))
    assert not os.path.exists(os.path.join(gemini_home, "tmp/other.txt"))
