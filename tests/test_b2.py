# tests/test_b2.py

import pytest
from unittest.mock import patch, MagicMock
import sys
from gemini_manager import b2

# We don't need fs for B2 tests since they mock the B2Api/Bucket classes mostly.
# But conftest.py injects fs. That's fine.

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_init(mock_mem_info, mock_b2_api):
    mock_b2_api.return_value.get_bucket_by_name.return_value = MagicMock()
    b2_mgr = b2.B2Manager("id", "key", "bucket")
    assert b2_mgr.bucket is not None
    mock_b2_api.return_value.authorize_account.assert_called_with("production", "id", "key")

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_init_fail(mock_mem_info, mock_b2_api):
    mock_b2_api.return_value.authorize_account.side_effect = Exception("Auth fail")
    with pytest.raises(SystemExit):
        b2.B2Manager("id", "key", "bucket")

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_upload(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    b2_mgr.upload("local_file")
    mock_bucket.upload_local_file.assert_called()

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_upload_fail(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    mock_bucket.upload_local_file.side_effect = Exception("Upload fail")
    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    b2_mgr.upload("local_file") # Should handle exception and print error

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_download(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    b2_mgr.download("remote", "local")
    mock_bucket.download_file_by_name.assert_called()

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_download_fail(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    mock_bucket.download_file_by_name.side_effect = Exception("Download fail")
    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    with pytest.raises(Exception):
        b2_mgr.download("remote", "local")

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_list_backups(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    b2_mgr.list_backups()
    mock_bucket.ls.assert_called()

# Test import error handling
def test_b2_import_error():
    # We want to test the code path where B2Api is None
    # We can mock the module attribute directly on the already imported module
    original_b2api = b2.B2Api

    try:
        b2.B2Api = None
        with pytest.raises(SystemExit):
            b2.B2Manager("id", "key", "bucket")
    finally:
        b2.B2Api = original_b2api

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_upload_with_name(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    b2_mgr.upload("local_file", remote_name="remote_file")
    mock_bucket.upload_local_file.assert_called_with(local_file="local_file", file_name="remote_file")

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_upload_string_success(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    data = "some data"
    b2_mgr.upload_string(data, "remote_file")

    mock_bucket.upload_bytes.assert_called_with(
        data_bytes=data.encode('utf-8'),
        file_name="remote_file"
    )

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_upload_string_fail(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    mock_bucket.upload_bytes.side_effect = Exception("Upload bytes fail")
    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    with pytest.raises(Exception):
        b2_mgr.upload_string("data", "remote_file")

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_download_to_string_success(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    mock_download_dest = MagicMock()

    # Mock save behavior to write to the BytesIO buffer passed to it
    def side_effect_save(file_obj):
        file_obj.write(b"remote content")

    mock_download_dest.save.side_effect = side_effect_save
    mock_bucket.download_file_by_name.return_value = mock_download_dest

    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    result = b2_mgr.download_to_string("remote_file")
    assert result == "remote content"
    mock_bucket.download_file_by_name.assert_called_with("remote_file")

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_download_to_string_fail(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    mock_bucket.download_file_by_name.side_effect = Exception("Not found")
    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    result = b2_mgr.download_to_string("remote_file")
    assert result is None

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_upload_interface(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    b2_mgr.upload_file("local", "remote")
    mock_bucket.upload_local_file.assert_called_with(local_file="local", file_name="remote")

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_download_interface(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    b2_mgr.download_file("remote", "local")
    mock_bucket.download_file_by_name.assert_called()

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_list_files(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()

    # Mock generator return from ls
    file_ver = MagicMock()
    file_ver.file_name = "test.txt"
    file_ver.size = 100
    file_ver.upload_timestamp = 1000

    mock_bucket.ls.return_value = [(file_ver, None)]
    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    files = b2_mgr.list_files()
    assert len(files) == 1
    assert files[0].name == "test.txt"
    assert files[0].size == 100

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_list_files_fail(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    mock_bucket.ls.side_effect = Exception("List fail")
    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    files = b2_mgr.list_files()
    assert files == []

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_delete_file(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    file_ver = MagicMock()
    file_ver.id_ = "123"
    mock_bucket.get_file_info_by_name.return_value = file_ver

    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    b2_mgr.delete_file("remote")
    mock_bucket.delete_file_version.assert_called_with("123", "remote")

@patch("gemini_manager.b2.B2Api")
@patch("gemini_manager.b2.InMemoryAccountInfo")
def test_b2_manager_delete_file_fail(mock_mem_info, mock_b2_api):
    mock_bucket = MagicMock()
    mock_bucket.get_file_info_by_name.side_effect = Exception("Not found")

    mock_b2_api.return_value.get_bucket_by_name.return_value = mock_bucket
    b2_mgr = b2.B2Manager("id", "key", "bucket")

    b2_mgr.delete_file("remote")
    # Should print error but not crash
