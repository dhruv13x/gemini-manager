
import pytest
import sys
from unittest.mock import MagicMock, patch
from gemini_manager.project_config import load_project_config, normalize_config_keys

def test_normalize_config_keys():
    config = {
        "backup-dir": "/tmp",
        "verbose-mode": True,
        "simple_key": 1
    }
    normalized = normalize_config_keys(config)
    assert normalized["backup_dir"] == "/tmp"
    assert normalized["verbose_mode"] is True
    assert normalized["simple_key"] == 1

def test_load_project_config_no_files(fs):
    # fs is empty
    assert load_project_config() == {}

def test_load_project_config_gemini_toml_tool_section(fs):
    toml_content = """
    [tool.gm]
    backup-dir = "val1"
    """
    fs.create_file("gemini-manager.toml", contents=toml_content)
    config = load_project_config()
    assert config == {"backup-dir": "val1"}

def test_load_project_config_gemini_toml_root(fs):
    toml_content = """
    backup-dir = "val2"
    """
    fs.create_file("gemini-manager.toml", contents=toml_content)
    config = load_project_config()
    assert config == {"backup-dir": "val2"}

def test_load_project_config_gemini_toml_error(fs):
    # Invalid TOML
    toml_content = "invalid toml ["
    fs.create_file("gemini-manager.toml", contents=toml_content)
    config = load_project_config()
    assert config == {}

def test_load_project_config_pyproject_toml(fs):
    toml_content = """
    [tool.gm]
    option = "val3"
    """
    fs.create_file("pyproject.toml", contents=toml_content)
    config = load_project_config()
    assert config == {"option": "val3"}

def test_load_project_config_pyproject_toml_no_section(fs):
    toml_content = """
    [tool.other]
    option = "val4"
    """
    fs.create_file("pyproject.toml", contents=toml_content)
    config = load_project_config()
    assert config == {}

def test_load_project_config_pyproject_toml_error(fs):
    fs.create_file("pyproject.toml", contents="[")
    config = load_project_config()
    assert config == {}

def test_load_project_config_gemini_toml_open_fail(fs):
    fs.create_file("gemini-manager.toml", contents="")
    # Simulate open fail using patch since pyfakefs doesn't easily simulate generic IOError on open
    # but allows file permissions
    with patch("builtins.open", side_effect=OSError("Read error")):
        config = load_project_config()

    assert config == {}

def test_tomllib_import_fallback(mocker):
    # Test the safety check if tomllib is missing
    with patch("gemini_manager.project_config.tomllib", None):
        assert load_project_config() == {}
