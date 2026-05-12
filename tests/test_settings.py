# tests/test_settings.py

import pytest
from unittest.mock import patch
import json
import os
from gemini_manager.settings import load_settings, save_settings, set_setting, get_setting, remove_setting, list_settings, CONFIG_FILE

CONFIG_CONTENT = '{"key1": "value1", "key2": "value2"}'
# Use the CONFIG_FILE path defined in gemini_manager.settings

def test_load_settings_exists(fs):
    # fs handles file creation
    fs.create_file(CONFIG_FILE, contents=CONFIG_CONTENT)
    settings = load_settings()
    assert settings["key1"] == "value1"

def test_load_settings_not_exists(fs):
    # File not created
    assert load_settings() == {}

def test_load_settings_malformed(fs):
    fs.create_file(CONFIG_FILE, contents='{invalid}')
    # Should handle malformed JSON gracefully and return empty dict (or log error)
    # The implementation likely catches JSONDecodeError
    assert load_settings() == {}

@patch("gemini_manager.settings.save_settings")
@patch("gemini_manager.settings.load_settings")
def test_set_setting(mock_load, mock_save):
    mock_load.return_value = {}
    set_setting("new_key", "new_val")
    mock_save.assert_called_with({"new_key": "new_val"})

@patch("gemini_manager.settings.load_settings")
def test_get_setting(mock_load):
    mock_load.return_value = {"key": "val"}
    assert get_setting("key") == "val"
    assert get_setting("missing", "default") == "default"

@patch("gemini_manager.settings.save_settings")
@patch("gemini_manager.settings.load_settings")
def test_remove_setting(mock_load, mock_save):
    mock_load.return_value = {"key": "val"}
    assert remove_setting("key") is True
    mock_save.assert_called_with({})

@patch("gemini_manager.settings.save_settings")
@patch("gemini_manager.settings.load_settings")
def test_remove_setting_not_found(mock_load, mock_save):
    mock_load.return_value = {}
    assert remove_setting("key") is False
    mock_save.assert_not_called()

@patch("gemini_manager.settings.load_settings")
def test_list_settings(mock_load):
    mock_load.return_value = {"a": 1}
    assert list_settings() == {"a": 1}

def test_save_settings(fs):
    # fs handles file creation
    save_settings({"a": 1})
    assert os.path.exists(CONFIG_FILE)
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)
    assert data == {"a": 1}
