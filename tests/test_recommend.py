import pytest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from freezegun import freeze_time

from gemini_manager.recommend import get_recommendation, AccountStatus

# Constants matching implementation
COOLDOWN_HOURS = 24

@pytest.fixture
def mock_data_sources():
    with patch("gemini_manager.recommend.get_cooldown_data") as mock_cd, \
         patch("gemini_manager.recommend.get_all_resets") as mock_resets:
        yield mock_cd, mock_resets

@freeze_time("2025-01-01 12:00:00")
def test_recommend_no_accounts(mock_data_sources):
    mock_cd, mock_resets = mock_data_sources
    mock_cd.return_value = {}
    mock_resets.return_value = []

    rec = get_recommendation()
    assert rec is None

@freeze_time("2025-01-01 12:00:00")
def test_recommend_one_ready_account(mock_data_sources):
    mock_cd, mock_resets = mock_data_sources

    # Now is 2025-01-01 12:00:00 UTC
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Account A: Used 30 hours ago (Ready)
    # Account B: Used 1 hour ago (Cooldown)
    t_ready = (now - timedelta(hours=30)).isoformat()
    t_locked = (now - timedelta(hours=1)).isoformat()

    mock_cd.return_value = {
        "ready@test.com": t_ready,
        "locked@test.com": t_locked
    }
    mock_resets.return_value = []

    rec = get_recommendation()
    assert rec is not None
    assert rec.email == "ready@test.com"
    assert rec.status == AccountStatus.READY

@freeze_time("2025-01-01 12:00:00")
def test_recommend_lru_logic(mock_data_sources):
    mock_cd, mock_resets = mock_data_sources
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Both Ready
    # Account A: Used 30 hours ago
    # Account B: Used 100 hours ago (should be preferred as "more rested")

    t_recent = (now - timedelta(hours=30)).isoformat()
    t_old = (now - timedelta(hours=100)).isoformat()

    mock_cd.return_value = {
        "recent@test.com": t_recent,
        "old@test.com": t_old
    }
    # "unused@test.com" exists in resets (known account) but not in cooldowns (never switched to)
    mock_resets.return_value = [{"email": "unused@test.com", "reset_ist": "2025-01-01T00:00:00"}]

    rec = get_recommendation()
    # Logic: Unused (Never) > Oldest Used > ...
    assert rec.email == "unused@test.com"

    # Remove unused, test between recent and old
    mock_resets.return_value = []
    rec = get_recommendation()
    assert rec.email == "old@test.com"

@freeze_time("2025-01-01 12:00:00")
def test_recommend_scheduled_logic(mock_data_sources):
    mock_cd, mock_resets = mock_data_sources
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Account A: Ready (Last used long ago)
    t_ready = (now - timedelta(hours=30)).isoformat()

    mock_cd.return_value = {
        "ready@test.com": t_ready,
        "scheduled@test.com": (now - timedelta(hours=30)).isoformat()
    }

    # Scheduled reset 1 hour in future
    future_reset = (now + timedelta(hours=1)).isoformat()
    mock_resets.return_value = [
        {"email": "scheduled@test.com", "reset_ist": future_reset}
    ]

    rec = get_recommendation()
    assert rec.email == "ready@test.com"
    assert rec.status == AccountStatus.READY

@freeze_time("2025-01-01 12:00:00")
def test_recommend_all_locked(mock_data_sources):
    mock_cd, mock_resets = mock_data_sources
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # All locked
    t_locked = (now - timedelta(hours=1)).isoformat()
    mock_cd.return_value = {"locked@test.com": t_locked}
    mock_resets.return_value = []

    rec = get_recommendation()
    assert rec is None
import pytest
import json
import os
from unittest.mock import patch, MagicMock
from gemini_manager.recommend import get_recommendation, do_recommend, AccountStatus
from gemini_manager.config import COOLDOWN_FILE

def test_get_recommendation_no_data(fs):
    """Test when no data exists."""
    if not os.path.exists(os.path.expanduser("~")):
        fs.create_dir(os.path.expanduser("~"))
    with patch("gemini_manager.recommend.get_all_resets", return_value=[]):
        rec = get_recommendation()
        assert rec is None

def test_get_recommendation_all_locked(fs):
    """Test when all accounts are locked (Cooldown)."""
    if not os.path.exists(os.path.expanduser("~")):
        fs.create_dir(os.path.expanduser("~"))
    cooldown_path = os.path.expanduser(COOLDOWN_FILE)
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(hours=1)).isoformat()

    fs.create_file(cooldown_path, contents=json.dumps({"locked@test.com": recent}))

    with patch("gemini_manager.recommend.get_all_resets", return_value=[]):
        rec = get_recommendation()
        assert rec is None

def test_get_recommendation_ready_sort_lru(fs):
    """Test picking the LRU ready account."""
    if not os.path.exists(os.path.expanduser("~")):
        fs.create_dir(os.path.expanduser("~"))
    cooldown_path = os.path.expanduser(COOLDOWN_FILE)
    now = datetime.now(timezone.utc)

    # old1 used 10 days ago
    old1 = (now - timedelta(days=10)).isoformat()
    # old2 used 5 days ago
    old2 = (now - timedelta(days=5)).isoformat()

    fs.create_file(cooldown_path, contents=json.dumps({
        "newer@test.com": old2,
        "older@test.com": old1
    }))

    with patch("gemini_manager.recommend.get_all_resets", return_value=[]):
        rec = get_recommendation()
        assert rec.email == "older@test.com"
        assert rec.status == AccountStatus.READY

def test_get_recommendation_never_used_first(fs):
    """Test that never used accounts come before used ones."""
    if not os.path.exists(os.path.expanduser("~")):
        fs.create_dir(os.path.expanduser("~"))
    cooldown_path = os.path.expanduser(COOLDOWN_FILE)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=10)).isoformat()

    # "new@test.com" is not in cooldown file, so last_used is None
    # "used@test.com" is in cooldown file
    fs.create_file(cooldown_path, contents=json.dumps({"used@test.com": old}))

    # We need to make sure "new@test.com" is known.
    # It must be in resets list or cooldown list.
    resets = [{"email": "new@test.com", "reset_ist": (now - timedelta(hours=1)).isoformat()}]

    with patch("gemini_manager.recommend.get_all_resets", return_value=resets):
        rec = get_recommendation()
        assert rec.email == "new@test.com"

def test_get_recommendation_scheduled_ignored(fs):
    """Test that scheduled accounts (even if not recently used) are ignored if logic dictates."""
    # Logic: Status: READY > SCHEDULED > COOLDOWN.
    # Candidates with Status SCHEDULED are filtered out in step 3 (only READY kept).

    if not os.path.exists(os.path.expanduser("~")):
        fs.create_dir(os.path.expanduser("~"))
    now = datetime.now(timezone.utc)
    future = (now + timedelta(hours=10)).isoformat()

    # This email has a future reset, so it should be SCHEDULED
    resets = [{"email": "scheduled@test.com", "reset_ist": future}]

    with patch("gemini_manager.recommend.get_all_resets", return_value=resets):
        rec = get_recommendation()
        assert rec is None

def test_do_recommend_success(fs, capsys):
    """Test CLI output for successful recommendation."""
    rec = MagicMock()
    rec.email = "best@test.com"
    rec.last_used = datetime.now(timezone.utc) - timedelta(days=2)

    # Patch colors to be valid rich styles or empty
    with patch("gemini_manager.recommend.NEON_RED", "red"), \
         patch("gemini_manager.recommend.get_recommendation", return_value=rec):
        do_recommend()

    captured = capsys.readouterr()
    assert "best@test.com" in captured.out
    assert "2d" in captured.out
    assert "Account is Ready" in captured.out

def test_do_recommend_none(fs, capsys):
    """Test CLI output when no recommendation found."""
    with patch("gemini_manager.recommend.NEON_RED", "red"), \
         patch("gemini_manager.recommend.get_recommendation", return_value=None):
        do_recommend()

    captured = capsys.readouterr()
    assert "No 'Green' (Ready) accounts" in captured.out

def test_do_recommend_never_used(fs, capsys):
    """Test CLI output for never used account."""
    rec = MagicMock()
    rec.email = "fresh@test.com"
    rec.last_used = None

    with patch("gemini_manager.recommend.NEON_RED", "red"), \
         patch("gemini_manager.recommend.get_recommendation", return_value=rec):
        do_recommend()

    captured = capsys.readouterr()
    assert "fresh@test.com" in captured.out
    assert "Never / Unknown" in captured.out


def test_get_recommendation_from_metadata(fs):
    backup_dir = os.path.expanduser("~/.gemini-manager/backups")
    fs.create_dir(backup_dir)
    fs.create_file(
        os.path.join(backup_dir, "2026-01-01_120000-meta@test.com.gemini-manager.metadata.json"),
        contents=json.dumps({
            "email": "meta@test.com",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "next_available_at": "2020-01-01T00:00:00+00:00",
            "models": {"Flash": {"percent": 42}},
        }),
    )

    rec = get_recommendation()

    assert rec.email == "meta@test.com"
    assert rec.status == AccountStatus.READY
    assert rec.quota_percent_left == 42
    assert rec.flash_percent_left == 42
    assert rec.source == "metadata"


def test_get_recommendation_prioritizes_lowest_flash_quota(fs):
    backup_dir = os.path.expanduser("~/.gemini-manager/backups")
    fs.create_dir(backup_dir)
    for email, flash_percent in [
        ("zero@test.com", 0),
        ("mid@test.com", 34),
        ("high@test.com", 64),
    ]:
        fs.create_file(
            os.path.join(backup_dir, f"2026-01-01_120000-{email}.gemini-manager.metadata.json"),
            contents=json.dumps({
                "email": email,
                "updated_at": "2026-01-01T00:00:00+00:00",
                "next_available_at": "2020-01-01T00:00:00+00:00",
                "models": {
                    "Flash": {"percent": flash_percent},
                    "Pro": {"percent": 100},
                },
            }),
        )

    rec = get_recommendation()

    assert rec.email == "zero@test.com"
    assert rec.flash_percent_left == 0


def test_get_recommendation_prioritizes_34_over_64_flash_when_no_zero(fs):
    backup_dir = os.path.expanduser("~/.gemini-manager/backups")
    fs.create_dir(backup_dir)
    for email, flash_percent in [
        ("mid@test.com", 34),
        ("high@test.com", 64),
    ]:
        fs.create_file(
            os.path.join(backup_dir, f"2026-01-01_120000-{email}.gemini-manager.metadata.json"),
            contents=json.dumps({
                "email": email,
                "updated_at": "2026-01-01T00:00:00+00:00",
                "next_available_at": "2020-01-01T00:00:00+00:00",
                "models": {"Flash": {"percent": flash_percent}},
            }),
        )

    rec = get_recommendation()

    assert rec.email == "mid@test.com"
    assert rec.flash_percent_left == 34


def test_do_recommend_use_calls_restore(fs):
    backup_dir = os.path.expanduser("~/.gemini-manager/backups")
    fs.create_dir(backup_dir)
    fs.create_file(
        os.path.join(backup_dir, "2026-01-01_120000-meta@test.com.gemini-manager.metadata.json"),
        contents=json.dumps({
            "email": "meta@test.com",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "next_available_at": "2020-01-01T00:00:00+00:00",
            "models": {"Flash": {"percent": 42}},
        }),
    )
    args = MagicMock()
    args.cloud = False
    args.use = True
    args.restore = False
    args.dest = os.path.expanduser("~/.gemini")
    args.backup_dir = backup_dir
    args.dry_run = True
    args.force = False
    args.bucket = None
    args.b2_id = None
    args.b2_key = None

    with patch("gemini_manager.restore.perform_restore") as mock_restore:
        do_recommend(args)

    restore_args = mock_restore.call_args.args[0]
    assert restore_args.email == "meta@test.com"
    assert restore_args.auth_only is True
    assert restore_args.full is False
