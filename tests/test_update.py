# tests/test_update.py

import pytest
from unittest.mock import patch, MagicMock
from gemini_manager.update import do_update, do_check_update

@patch("gemini_manager.update.run_cmd_safe")
@patch("gemini_manager.update.shutil.rmtree")
@patch("gemini_manager.update.os.path.exists")
@patch("gemini_manager.update.cprint")
@patch("subprocess.run") # Safety net
def test_do_update_success(mock_sub_run, mock_cprint, mock_exists, mock_rmtree, mock_run):
    # Mock sequence for run_cmd_safe:
    # 1. rm symlink (returns 0)
    # 2. npm root (returns "/usr/lib/node_modules")
    # 3. ls (returns 0, list, err)
    # 4. npm install (returns 0, "success", "")

    mock_run.side_effect = [
        (0, "", ""),
        (0, "/usr/lib/node_modules", ""),
        (0, "gm-cli", ""),
        (0, "Successfully installed", "")
    ]

    mock_exists.return_value = True # gm-cli dir exists

    do_update()

    mock_rmtree.assert_called()
    assert mock_run.call_count == 4
    # Check success message
    found_success = any("Update complete" in str(args) for args in mock_cprint.call_args_list)
    assert found_success

@patch("gemini_manager.update.run_cmd_safe")
@patch("gemini_manager.update.shutil.rmtree")
@patch("gemini_manager.update.os.path.exists")
@patch("gemini_manager.update.cprint")
@patch("subprocess.run") # Safety net
def test_do_update_fail_then_success(mock_sub_run, mock_cprint, mock_exists, mock_rmtree, mock_run):
    # Mock sequence:
    # 1. rm symlink
    # 2. npm root -> fail
    # 3. ls -> success. Note: The code checks os.path.exists(npm_root).
    #    If npm root failed, npm_root defaults to /usr/lib/node_modules.
    #    If os.path.exists returns False (mocked below), ls is skipped.
    # 4. npm install -> fail
    # 5. npm install --force -> fail
    # 6. npm install unsafe -> success

    mock_run.side_effect = [
        (0, "", ""), # rm
        (1, "", "error"), # npm root
        # ls might be skipped if os.path.exists returns False.
        # But let's verify logic in update.py:
        # npm_root = "/usr/lib/node_modules"
        # if os.path.exists(npm_root): ...

        # We want to test the full fallback path.
        # Let's say os.path.exists returns True for npm_root check.

        (0, "contents", ""), # ls
        (1, "", "EACCESS"), # first install
        (1, "", "EACCESS"), # force install
        (0, "Success unsafe", "") # second install (unsafe)
    ]

    # os.path.exists is called for:
    # 1. google_pkg_dir removal check
    # 2. npm_root ls check

    # We want 1 to be False (skip removal)
    # We want 2 to be True (do ls)

    mock_exists.side_effect = [False, True]

    do_update()

    assert mock_run.call_count == 6
    found_unsafe = any("Update succeeded with --unsafe-perm" in str(args) for args in mock_cprint.call_args_list)
    assert found_unsafe

@patch("gemini_manager.update.run_cmd_safe")
@patch("gemini_manager.update.cprint")
def test_do_check_update_not_installed(mock_cprint, mock_run):
    # 1. command -v gm -> fail
    mock_run.return_value = (1, "", "")

    do_check_update()

    assert any("not found on PATH" in str(args) for args in mock_cprint.call_args_list)

@patch("gemini_manager.update.run_cmd_safe")
@patch("gemini_manager.update.cprint")
def test_do_check_update_up_to_date(mock_cprint, mock_run):
    # 1. command -v gm -> ok
    # 2. gm --version -> 1.0.0
    # 3. npm view -> 1.0.0

    mock_run.side_effect = [
        (0, "/bin/gm", ""),
        (0, "1.0.0", ""),
        (0, "1.0.0", "")
    ]

    do_check_update()

    assert any("You already have the latest version" in str(args) for args in mock_cprint.call_args_list)

@patch("gemini_manager.update.run_cmd_safe")
@patch("builtins.input", return_value="n")
@patch("gemini_manager.update.cprint")
def test_do_check_update_available_no(mock_cprint, mock_input, mock_run):
    # 1. command -v gm -> ok
    # 2. gm --version -> 1.0.0
    # 3. npm view -> 2.0.0

    mock_run.side_effect = [
        (0, "/bin/gm", ""),
        (0, "1.0.0", ""),
        (0, "2.0.0", "")
    ]

    do_check_update()

    assert any("Update available" in str(args) for args in mock_cprint.call_args_list)
    assert any("Update cancelled" in str(args) for args in mock_cprint.call_args_list)

@patch("gemini_manager.update.do_update")
@patch("gemini_manager.update.run_cmd_safe")
@patch("builtins.input", return_value="y")
@patch("gemini_manager.update.cprint")
def test_do_check_update_available_yes(mock_cprint, mock_input, mock_run, mock_do_update):
    # 1. command -v gm -> ok
    # 2. gm --version -> 1.0.0
    # 3. npm view -> 2.0.0

    mock_run.side_effect = [
        (0, "/bin/gm", ""),
        (0, "1.0.0", ""),
        (0, "2.0.0", "")
    ]

    do_check_update()

    mock_do_update.assert_called_once()

# NEW TESTS

@patch("gemini_manager.update.run_cmd_safe")
@patch("gemini_manager.update.shutil.rmtree")
@patch("gemini_manager.update.os.path.exists")
@patch("gemini_manager.update.cprint")
@patch("subprocess.run") # Safety net
def test_do_update_rmtree_fail(mock_sub_run, mock_cprint, mock_exists, mock_rmtree, mock_run):
    # Test lines 37-38: Exception during shutil.rmtree

    mock_run.side_effect = [
        (0, "", ""), # rm symlink
        (0, "/usr/lib/node_modules", ""), # npm root
        (0, "contents", ""), # ls
        (0, "Success", "") # npm install
    ]

    mock_exists.return_value = True
    mock_rmtree.side_effect = Exception("Permission denied")

    do_update()

    assert any("Failed to remove" in str(args) for args in mock_cprint.call_args_list)


@patch("gemini_manager.update.run_cmd_safe")
@patch("gemini_manager.update.shutil.rmtree")
@patch("gemini_manager.update.os.path.exists")
@patch("gemini_manager.update.cprint")
@patch("subprocess.run") # Safety net
def test_do_update_ls_fail(mock_sub_run, mock_cprint, mock_exists, mock_rmtree, mock_run):
    # Test line 48: ls returned rc!=0

    mock_run.side_effect = [
        (0, "", ""), # rm symlink
        (0, "/usr/lib/node_modules", ""), # npm root
        (1, "", "ls error"), # ls fails
        (0, "Success", "") # npm install
    ]

    mock_exists.return_value = True # ensure we enter the if block

    do_update()

    assert any("ls returned rc=1" in str(args) for args in mock_cprint.call_args_list)


@patch("gemini_manager.update.run_cmd_safe")
@patch("gemini_manager.update.shutil.rmtree")
@patch("gemini_manager.update.os.path.exists")
@patch("gemini_manager.update.cprint")
@patch("subprocess.run") # Safety net
def test_do_update_all_installs_fail(mock_sub_run, mock_cprint, mock_exists, mock_rmtree, mock_run):
    # Test lines 67-74: Update failed even with --unsafe-perm, and npm bin logic

    mock_run.side_effect = [
        (0, "", ""), # rm symlink
        (0, "/usr/lib/node_modules", ""), # npm root
        (0, "contents", ""), # ls
        (1, "", "install error"), # npm install fail
        (1, "", "force error"), # force install fail
        (1, "", "unsafe error"), # unsafe install fail
        (0, "/usr/bin/npm-bin", "") # npm bin
    ]

    mock_exists.return_value = True

    do_update()

    assert mock_run.call_count == 7
    assert any("Update failed even with --unsafe-perm" in str(args) for args in mock_cprint.call_args_list)
    assert any("If gm is installed here" in str(args) for args in mock_cprint.call_args_list)


@patch("gemini_manager.update.run_cmd_safe")
@patch("gemini_manager.update.cprint")
def test_do_check_update_version_fail(mock_cprint, mock_run):
    # Test lines 97-100: gm --version failed

    mock_run.side_effect = [
        (0, "/bin/gm", ""), # command -v
        (1, "", "version error") # gm --version
    ]

    do_check_update()

    assert any("Gemini is installed but `gm --version` failed" in str(args) for args in mock_cprint.call_args_list)


@patch("gemini_manager.update.run_cmd_safe")
@patch("builtins.input", return_value="n")
@patch("gemini_manager.update.cprint")
def test_do_check_update_npm_view_fail(mock_cprint, mock_input, mock_run):
    # Test lines 106-109: npm view failed

    mock_run.side_effect = [
        (0, "/bin/gm", ""), # command -v
        (0, "1.0.0", ""), # gm --version
        (1, "", "npm view error") # npm view
    ]

    do_check_update()

    assert any("Could not determine latest version" in str(args) for args in mock_cprint.call_args_list)
    # Just check if (unknown) appears in arguments
    assert any("(unknown)" in str(args) for args in mock_cprint.call_args_list)
