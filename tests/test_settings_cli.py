# tests/test_settings_cli.py

import pytest
from unittest.mock import patch, MagicMock
from gemini_manager.settings_cli import do_config
import sys

def mock_args(action="list", key=None, value=None, force=False):
    m = MagicMock(config_action=action, key=key, value=value, force=force)
    m.init = False # Explicitly set init to False to avoid MagicMock evaluating to True
    return m

@patch("gemini_manager.settings_cli.list_settings")
@patch("gemini_manager.settings_cli.cprint")
def test_do_config_list(mock_cprint, mock_list):
    mock_list.return_value = {"my_key": "my_value", "secret_key": "secret12345"}

    with patch("builtins.print") as mock_print:
        do_config(mock_args(action="list"))

        found_masked = False
        for call in mock_print.call_args_list:
            if "se*******45" in str(call):
                 found_masked = True
        assert found_masked

@patch("gemini_manager.settings_cli.list_settings")
@patch("gemini_manager.settings_cli.cprint")
def test_do_config_list_empty(mock_cprint, mock_list):
    mock_list.return_value = {}
    do_config(mock_args(action="list"))
    assert any("No settings configured" in str(c) for c in mock_cprint.call_args_list)

@patch("gemini_manager.settings_cli.cprint")
def test_do_config_no_key(mock_cprint):
    do_config(mock_args(action="set", key=None))
    assert any("Key required" in str(c) for c in mock_cprint.call_args_list)

@patch("gemini_manager.settings_cli.set_setting")
@patch("gemini_manager.settings_cli.cprint")
def test_do_config_set(mock_cprint, mock_set):
    # Non-sensitive key, should just work
    do_config(mock_args(action="set", key="k", value="v"))
    mock_set.assert_called_with("k", "v")
    assert any("Set k = v" in str(c) for c in mock_cprint.call_args_list)

@patch("gemini_manager.settings_cli.set_setting")
@patch("gemini_manager.settings_cli.cprint")
def test_do_config_set_sensitive_interactive_yes(mock_cprint, mock_set):
    # Sensitive key, Interactive, User says Yes
    with patch("sys.stdin.isatty", return_value=True):
        with patch("builtins.input", return_value="y"):
            do_config(mock_args(action="set", key="b2_key", value="secret"))
            mock_set.assert_called_with("b2_key", "secret")

@patch("gemini_manager.settings_cli.set_setting")
@patch("gemini_manager.settings_cli.cprint")
def test_do_config_set_sensitive_interactive_no(mock_cprint, mock_set):
    # Sensitive key, Interactive, User says No
    with patch("sys.stdin.isatty", return_value=True):
        with patch("builtins.input", return_value="n"):
            do_config(mock_args(action="set", key="b2_key", value="secret"))
            mock_set.assert_not_called()
            assert any("Aborted" in str(c) for c in mock_cprint.call_args_list)

@patch("gemini_manager.settings_cli.set_setting")
@patch("gemini_manager.settings_cli.cprint")
def test_do_config_set_sensitive_non_interactive_no_force(mock_cprint, mock_set):
    # Sensitive key, Non-Interactive, No Force -> Fail
    with patch("sys.stdin.isatty", return_value=False):
        with pytest.raises(SystemExit) as e:
            do_config(mock_args(action="set", key="b2_key", value="secret", force=False))
        assert e.value.code == 1
        mock_set.assert_not_called()

@patch("gemini_manager.settings_cli.set_setting")
@patch("gemini_manager.settings_cli.cprint")
def test_do_config_set_sensitive_non_interactive_with_force(mock_cprint, mock_set):
    # Sensitive key, Non-Interactive, With Force -> Success
    with patch("sys.stdin.isatty", return_value=False):
        do_config(mock_args(action="set", key="b2_key", value="secret", force=True))
        mock_set.assert_called_with("b2_key", "secret")

@patch("gemini_manager.settings_cli.cprint")
def test_do_config_set_no_value(mock_cprint):
    do_config(mock_args(action="set", key="k", value=None))
    assert any("Value required" in str(c) for c in mock_cprint.call_args_list)

@patch("gemini_manager.settings_cli.get_setting")
@patch("gemini_manager.settings_cli.cprint")
def test_do_config_get(mock_cprint, mock_get):
    mock_get.return_value = "my_val"
    do_config(mock_args(action="get", key="k"))
    assert any("my_val" in str(c) for c in mock_cprint.call_args_list)

@patch("gemini_manager.settings_cli.get_setting")
@patch("gemini_manager.settings_cli.cprint")
def test_do_config_get_none(mock_cprint, mock_get):
    mock_get.return_value = None
    do_config(mock_args(action="get", key="k"))
    assert any("(not set)" in str(c) for c in mock_cprint.call_args_list)

@patch("gemini_manager.settings_cli.remove_setting")
@patch("gemini_manager.settings_cli.cprint")
def test_do_config_unset(mock_cprint, mock_remove):
    mock_remove.return_value = True
    do_config(mock_args(action="unset", key="k"))
    assert any("Removed k" in str(c) for c in mock_cprint.call_args_list)

@patch("gemini_manager.settings_cli.remove_setting")
@patch("gemini_manager.settings_cli.cprint")
def test_do_config_unset_fail(mock_cprint, mock_remove):
    mock_remove.return_value = False
    do_config(mock_args(action="unset", key="k"))
    assert any("Key k not found" in str(c) for c in mock_cprint.call_args_list)

@patch("gemini_manager.settings_cli.list_settings")
@patch("builtins.print")
def test_do_config_list_masking_short_value(mock_print, mock_list):
    mock_list.return_value = {"secret_key": "123"}
    do_config(mock_args(action="list"))
    # Values too short for partial masking should be fully masked.
    assert any("*****" in str(c) for c in mock_print.call_args_list)
