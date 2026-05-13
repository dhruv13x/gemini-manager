from unittest.mock import patch

from gemini_manager.project_config import (
    load_project_config,
    normalize_config_keys,
)


def test_load_config_no_toml_support(monkeypatch):
    monkeypatch.setattr("gemini_manager.project_config.tomllib", None)

    assert load_project_config() == {}


def test_load_profile_config_tool_gm(fs):
    fs.create_file(
        "gemini-manager-work.toml",
        contents="""
[tool.gm]
backup-dir = "/profile/backups"
max-files = 5
""",
    )

    result = load_project_config(profile="work")

    assert result == {
        "backup-dir": "/profile/backups",
        "max-files": 5,
    }


def test_load_profile_config_root_keys(fs):
    fs.create_file(
        "gemini-manager-work.toml",
        contents="""
backup-dir = "/profile/root"
threads = 4
""",
    )

    result = load_project_config(profile="work")

    assert result == {
        "backup-dir": "/profile/root",
        "threads": 4,
    }


def test_invalid_profile_toml_returns_empty(fs):
    fs.create_file(
        "gemini-manager-work.toml",
        contents="invalid = [",
    )

    result = load_project_config(profile="work")

    assert result == {}


def test_load_gemini_manager_toml_tool_gm(fs):
    fs.create_file(
        "gemini-manager.toml",
        contents="""
[tool.gm]
backup-dir = "/gm/backups"
auto-sync = true
""",
    )

    result = load_project_config()

    assert result == {
        "backup-dir": "/gm/backups",
        "auto-sync": True,
    }


def test_load_gemini_manager_toml_root_keys(fs):
    fs.create_file(
        "gemini-manager.toml",
        contents="""
backup-dir = "/root/backups"
workers = 8
""",
    )

    result = load_project_config()

    assert result == {
        "backup-dir": "/root/backups",
        "workers": 8,
    }


def test_invalid_gemini_manager_toml_returns_empty(fs):
    fs.create_file(
        "gemini-manager.toml",
        contents="[invalid TOML",
    )

    result = load_project_config()

    assert result == {}


def test_load_pyproject_tool_gm(fs):
    fs.create_file(
        "pyproject.toml",
        contents="""
[tool.gm]
backup-dir = "/pyproject/backups"
timeout = 30
""",
    )

    result = load_project_config()

    assert result == {
        "backup-dir": "/pyproject/backups",
        "timeout": 30,
    }


def test_pyproject_without_gm_section_returns_empty(fs):
    fs.create_file(
        "pyproject.toml",
        contents="""
[tool.other]
value = "test"
""",
    )

    result = load_project_config()

    assert result == {}


def test_invalid_pyproject_returns_empty(fs):
    fs.create_file(
        "pyproject.toml",
        contents="[tool.gm",
    )

    result = load_project_config()

    assert result == {}


def test_profile_has_priority_over_main_config(fs):
    fs.create_file(
        "gemini-manager-work.toml",
        contents="""
[tool.gm]
backup-dir = "/profile"
""",
    )

    fs.create_file(
        "gemini-manager.toml",
        contents="""
[tool.gm]
backup-dir = "/main"
""",
    )

    result = load_project_config(profile="work")

    assert result["backup-dir"] == "/profile"


def test_gemini_manager_has_priority_over_pyproject(fs):
    fs.create_file(
        "gemini-manager.toml",
        contents="""
[tool.gm]
backup-dir = "/gm"
""",
    )

    fs.create_file(
        "pyproject.toml",
        contents="""
[tool.gm]
backup-dir = "/pyproject"
""",
    )

    result = load_project_config()

    assert result["backup-dir"] == "/gm"


def test_open_failure_returns_empty(fs):
    fs.create_file(
        "gemini-manager.toml",
        contents="",
    )

    with patch("builtins.open", side_effect=OSError("read error")):
        result = load_project_config()

    assert result == {}


def test_returns_empty_when_no_config_exists(fs):
    result = load_project_config()

    assert result == {}


def test_normalize_config_keys():
    config = {
        "backup-dir": "/tmp/backups",
        "max-files": 10,
        "plain_key": True,
    }

    result = normalize_config_keys(config)

    assert result == {
        "backup_dir": "/tmp/backups",
        "max_files": 10,
        "plain_key": True,
    }
