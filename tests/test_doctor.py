# tests/test_doctor.py

from unittest.mock import patch
from gemini_manager.doctor import do_doctor


@patch("gemini_manager.doctor.shutil.which")
@patch("gemini_manager.doctor.os.path.isdir")
@patch("gemini_manager.doctor.os.access")
@patch("gemini_manager.doctor.urllib.request.urlopen")
@patch("gemini_manager.doctor.resolve_credentials")  # Updated: Mock resolve_credentials
@patch("gemini_manager.doctor.B2Manager")
@patch("gemini_manager.doctor.console.print")
def test_do_doctor(
    mock_print,
    mock_b2,
    mock_resolve_creds,
    mock_urlopen,
    mock_access,
    mock_isdir,
    mock_which,
):
    # Setup mocks
    mock_which.side_effect = lambda x: f"/usr/bin/{x}" if x != "missing_tool" else None
    mock_isdir.return_value = True
    mock_access.return_value = True
    # resolve_credentials returns tuple (id, key, bucket)
    mock_resolve_creds.return_value = ("test_id", "test_key", "test_bucket")

    do_doctor()

    # Assertions
    assert mock_print.call_count >= 2  # Header, Table, Footer
    mock_b2.assert_called_with("test_id", "test_key", "test_bucket")


@patch("gemini_manager.doctor.shutil.which")
@patch("gemini_manager.doctor.os.path.isdir")
@patch("gemini_manager.doctor.os.access")
@patch("gemini_manager.doctor.urllib.request.urlopen")
@patch("gemini_manager.doctor.resolve_credentials")  # Updated
@patch("gemini_manager.doctor.B2Manager")
@patch("gemini_manager.doctor.console.print")
def test_do_doctor_failures(
    mock_print,
    mock_b2,
    mock_resolve_creds,
    mock_urlopen,
    mock_access,
    mock_isdir,
    mock_which,
):
    # Setup mocks for failures
    mock_which.return_value = None  # No tools
    mock_isdir.return_value = False  # No dirs
    mock_urlopen.side_effect = Exception("No Internet")  # No internet
    # resolve_credentials returns None (SKIPPED)
    mock_resolve_creds.return_value = (None, None, None)

    do_doctor()

    assert mock_print.call_count >= 2
    mock_b2.assert_not_called()


@patch("gemini_manager.doctor.shutil.which")
@patch("gemini_manager.doctor.os.path.isdir")
@patch("gemini_manager.doctor.os.access")
@patch("gemini_manager.doctor.urllib.request.urlopen")
@patch("gemini_manager.doctor.resolve_credentials")  # Updated
@patch("gemini_manager.doctor.B2Manager")
@patch("gemini_manager.doctor.console.print")
def test_do_doctor_b2_fail(
    mock_print,
    mock_b2,
    mock_resolve_creds,
    mock_urlopen,
    mock_access,
    mock_isdir,
    mock_which,
):
    # Setup mocks for B2 fail
    mock_which.return_value = "/bin/tool"
    mock_isdir.return_value = True
    mock_access.return_value = False  # Read-only dir
    mock_urlopen.return_value = True
    mock_resolve_creds.return_value = ("test_id", "test_key", "test_bucket")
    mock_b2.side_effect = Exception("B2 Fail")

    do_doctor()

    assert mock_print.call_count >= 2
    mock_b2.assert_called()
