
import pytest
from unittest.mock import MagicMock, patch, mock_open
import os
import zipfile
from pathlib import Path
from rich.prompt import Confirm
from gemini_manager.profile import do_profile, perform_export, perform_import
from gemini_manager.config import DEFAULT_GEMINI_HOME

# Fixture for common mocks
@pytest.fixture
def mock_profile_deps(fs, mocker):
    mock_console_print = mocker.patch("gemini_manager.profile.console.print") # Mock console output
    mocker.patch("gemini_manager.profile.Confirm.ask", return_value=True) # Default to 'yes' for prompts
    
    # Setup default GEMINI_HOME for tests
    fs.create_dir(DEFAULT_GEMINI_HOME)
    yield mock_console_print # Yield the mock object for console.print

# --- do_profile tests ---
def test_do_profile_export_dispatch(mock_profile_deps, mocker):
    mock_export = mocker.patch("gemini_manager.profile.perform_export")
    args = MagicMock(profile_command="export", file="test.zip")
    do_profile(args)
    mock_export.assert_called_once_with(args)

def test_do_profile_import_dispatch(mock_profile_deps, mocker):
    mock_import = mocker.patch("gemini_manager.profile.perform_import")
    args = MagicMock(profile_command="import", file="test.zip")
    do_profile(args)
    mock_import.assert_called_once_with(args)

def test_do_profile_invalid_command(mock_profile_deps, mocker):
    args = MagicMock(profile_command="invalid", file="test.zip")
    do_profile(args)
    mock_profile_deps.assert_called_with("[red]Invalid profile command.[/]") # Use mock_profile_deps directly

# --- perform_export tests ---
@pytest.fixture
def create_test_profile_files(fs):
    # Create dummy files for export
    fs.create_file(os.path.join(os.getcwd(), "gemini-manager.toml"), contents="[tool.gemini]\nkey='value'")
    fs.create_file(os.path.expanduser("~/.gm-cooldown.json"), contents="{}")
    fs.create_file(os.path.expanduser("~/.gemini_history.json"), contents="[]")
    fs.create_file(os.path.expanduser("~/.gemini_resets.json"), contents="[]")

def test_perform_export_success_cwd_config(mock_profile_deps, create_test_profile_files, fs):
    args = MagicMock(file="export_test.zip")
    perform_export(args)

    output_path = Path("export_test.zip")
    assert output_path.exists()
    
    with zipfile.ZipFile(output_path, "r") as zf:
        namelist = zf.namelist()
        assert "gemini-manager.toml" in namelist
        assert ".gm-cooldown.json" in namelist
        assert ".gemini_history.json" in namelist
        assert ".gemini_resets.json" in namelist

def test_perform_export_success_gemini_home_config(mock_profile_deps, fs):
    # Ensure no config in CWD, create in DEFAULT_GEMINI_HOME
    # DEFAULT_GEMINI_HOME is already created by mock_profile_deps fixture
    fs.create_file(os.path.join(DEFAULT_GEMINI_HOME, "gemini-manager.toml"), contents="[tool.gemini]\nkey='value'")
    fs.create_file(os.path.expanduser("~/.gm-cooldown.json"), contents="{}")
    fs.create_file(os.path.expanduser("~/.gemini_history.json"), contents="[]")
    fs.create_file(os.path.expanduser("~/.gemini_resets.json"), contents="[]")

    args = MagicMock(file="export_test.zip")
    perform_export(args)

    output_path = Path("export_test.zip")
    assert output_path.exists()
    
    with zipfile.ZipFile(output_path, "r") as zf:
        namelist = zf.namelist()
        assert "gemini-manager.toml" in namelist
        assert ".gm-cooldown.json" in namelist
        assert ".gemini_history.json" in namelist
        assert ".gemini_resets.json" in namelist

def test_perform_export_no_config_file(mock_profile_deps, fs):
    # Only create cooldown, history, resets
    fs.create_file(os.path.expanduser("~/.gm-cooldown.json"), contents="{}")
    fs.create_file(os.path.expanduser("~/.gemini_history.json"), contents="[]")
    fs.create_file(os.path.expanduser("~/.gemini_resets.json"), contents="[]")
    
    args = MagicMock(file="export_test_no_config.zip")
    perform_export(args)

    output_path = Path("export_test_no_config.zip")
    assert output_path.exists()

    with zipfile.ZipFile(output_path, "r") as zf:
        namelist = zf.namelist()
        assert "gemini-manager.toml" not in namelist
        assert ".gm-cooldown.json" in namelist
        assert ".gemini_history.json" in namelist
        assert ".gemini_resets.json" in namelist
    mock_profile_deps.assert_any_call("[yellow]No gemini-manager.toml found to export. Only history will be saved.[/]") # Use mock_profile_deps directly

def test_perform_export_missing_some_files(mock_profile_deps, fs):
    fs.create_file(os.path.join(os.getcwd(), "gemini-manager.toml"), contents="[tool.gemini]\nkey='value'")
    fs.create_file(os.path.expanduser("~/.gm-cooldown.json"), contents="{}")
    # history.json and resets.json are missing
    
    args = MagicMock(file="export_missing_files.zip")
    perform_export(args)

    output_path = Path("export_missing_files.zip")
    assert output_path.exists()

    with zipfile.ZipFile(output_path, "r") as zf:
        namelist = zf.namelist()
        assert "gemini-manager.toml" in namelist
        assert ".gm-cooldown.json" in namelist
        assert ".gemini_history.json" not in namelist
        assert ".gemini_resets.json" not in namelist

def test_perform_export_zip_error(mock_profile_deps, mocker):
    mocker.patch("zipfile.ZipFile", side_effect=Exception("Zip error"))
    args = MagicMock(file="bad_export.zip")
    perform_export(args)
    mock_profile_deps.assert_any_call("[bold red]Export failed:[/ Zip error") # Use mock_profile_deps directly


# --- perform_import tests ---
@pytest.fixture
def create_zip_for_import(fs):
    zip_path = Path("import_test.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("gemini-manager.toml", "[tool.gemini]\nkey='imported_value'")
        zf.writestr(".gm-cooldown.json", '{"email": "test@example.com"}')
        zf.writestr(".gemini_history.json", '[{"event": "test"}]')
        zf.writestr(".gemini_resets.json", '[{"id": "123"}]')
        zf.writestr("unknown_file.txt", "content")
    return zip_path

def test_perform_import_file_not_found(mock_profile_deps, mocker):
    args = MagicMock(file="non_existent.zip", force=False)
    perform_import(args)
    mock_profile_deps.assert_called_with("[bold red]Error: File non_existent.zip not found.[/]") # Use mock_profile_deps directly

def test_perform_import_success_no_overwrite(mock_profile_deps, create_zip_for_import, fs, mocker):
    args = MagicMock(file=str(create_zip_for_import), force=False)
    mocker.patch("gemini_manager.profile.Confirm.ask", return_value=True) # Confirm overwrite
    
    # Pre-create files to trigger overwrite prompt
    fs.create_file(os.path.join(os.getcwd(), "gemini-manager.toml"), contents="old_config")
    fs.create_file(os.path.expanduser("~/.gm-cooldown.json"), contents="old_cooldown")

    perform_import(args)

    assert Path(os.path.join(os.getcwd(), "gemini-manager.toml")).read_text() == "[tool.gemini]\nkey='imported_value'"
    assert Path(os.path.expanduser("~/.gm-cooldown.json")).read_text() == '{"email": "test@example.com"}'
    assert Path(os.path.expanduser("~/.gemini_history.json")).read_text() == '[{"event": "test"}]'
    assert Path(os.path.expanduser("~/.gemini_resets.json")).read_text() == '[{"id": "123"}]'
    
    mock_profile_deps.assert_any_call("  [green]Restored[/] gemini-manager.toml")
    mock_profile_deps.assert_any_call(f"  [green]Restored[/] {os.path.expanduser('~/.gm-cooldown.json')}") # Use mock_profile_deps directly

def test_perform_import_success_force_overwrite(mock_profile_deps, create_zip_for_import, fs):
    args = MagicMock(file=str(create_zip_for_import), force=True)
    
    # Pre-create files to check force overwrite
    fs.create_file(os.path.join(os.getcwd(), "gemini-manager.toml"), contents="old_config")
    fs.create_file(os.path.expanduser("~/.gm-cooldown.json"), contents="old_cooldown")

    perform_import(args)

    assert Path(os.path.join(os.getcwd(), "gemini-manager.toml")).read_text() == "[tool.gemini]\nkey='imported_value'"
    assert Path(os.path.expanduser("~/.gm-cooldown.json")).read_text() == '{"email": "test@example.com"}'

def test_perform_import_bad_zip_file(mock_profile_deps, fs):
    bad_zip_path = Path("bad.zip")
    fs.create_file(bad_zip_path, contents="not a zip")
    args = MagicMock(file=str(bad_zip_path), force=False)
    perform_import(args)
    mock_profile_deps.assert_any_call("[bold red]Error: Invalid zip file.[/]") # Use mock_profile_deps directly

def test_perform_import_general_exception(mock_profile_deps, create_zip_for_import, fs, mocker):
    mocker.patch("shutil.copyfileobj", side_effect=Exception("Copy error"))
    args = MagicMock(file=str(create_zip_for_import), force=True)
    perform_import(args)
    mock_profile_deps.assert_any_call("[bold red]Import failed:[/ Copy error") # Use mock_profile_deps directly

def test_perform_import_gemini_home_config_detection(mock_profile_deps, fs, mocker):
    # Setup: no gemini-manager.toml in CWD, but one in DEFAULT_GEMINI_HOME
    # DEFAULT_GEMINI_HOME is already created by mock_profile_deps fixture
    zip_path = Path("import_home.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("gemini-manager.toml", "[tool.gemini]\nkey='home_config'")
    
    args = MagicMock(file=str(zip_path), force=False)
    mocker.patch("gemini_manager.profile.Confirm.ask", return_value=True) # Confirm overwrite if necessary

    perform_import(args)

    # Assert that it was restored to DEFAULT_GEMINI_HOME
    assert Path(os.path.join(DEFAULT_GEMINI_HOME, "gemini-manager.toml")).read_text() == "[tool.gemini]\nkey='home_config'"
    assert not Path(os.path.join(os.getcwd(), "gemini-manager.toml")).exists()
