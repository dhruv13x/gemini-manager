
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from gemini_manager.cloud_s3 import S3Provider
import boto3 # Import boto3 to access its exceptions for mocking
from botocore.exceptions import ClientError # Import ClientError for mocking boto3 exceptions
from gemini_manager.cloud_storage import CloudFile
import sys

# Patch boto3.client at the module level where it's used in cloud_s3.py
@pytest.fixture
def mock_s3_client():
    """Fixture to mock boto3 S3 client."""
    with patch("gemini_manager.cloud_s3.boto3.client") as mock_boto_client:
        mock_client_instance = MagicMock()
        mock_boto_client.return_value = mock_client_instance
        yield mock_client_instance

@pytest.fixture
def s3_provider(mock_s3_client):
    """Fixture to create an S3Provider instance."""
    # Ensure S3Provider uses the mocked client from mock_s3_client
    return S3Provider("test-bucket", "test-key-id", "test-secret-key", "us-west-1")

def test_s3_provider_init():
    """Test S3Provider initialization."""
    # Patch boto3.client specifically for this test to ensure it's called once
    with patch("gemini_manager.cloud_s3.boto3.client") as mock_boto_client:
        mock_client_instance = MagicMock()
        mock_boto_client.return_value = mock_client_instance
        provider = S3Provider("init-bucket", "init-key", "init-secret", "eu-central-1")
        mock_boto_client.assert_called_once_with(
            "s3",
            aws_access_key_id="init-key",
            aws_secret_access_key="init-secret",
            region_name="eu-central-1"
        )
        assert provider.bucket_name == "init-bucket"


def test_upload_file_success(s3_provider, mock_s3_client, capsys):
    """Test successful file upload."""
    s3_provider.upload_file("local/path/file.txt", "remote/path/file.txt")
    mock_s3_client.upload_file.assert_called_once_with(
        "local/path/file.txt", "test-bucket", "remote/path/file.txt"
    )
    captured = capsys.readouterr()
    assert "Upload successful." in captured.out

def test_upload_file_failure(s3_provider, mock_s3_client, capsys):
    """Test file upload failure."""
    mock_s3_client.upload_file.side_effect = Exception("Upload failed")
    with pytest.raises(Exception, match="Upload failed"):
        s3_provider.upload_file("local/path/file.txt", "remote/path/file.txt")
    captured = capsys.readouterr()
    assert "S3 Upload Error" in captured.out

def test_download_file_success(s3_provider, mock_s3_client, capsys):
    """Test successful file download."""
    s3_provider.download_file("remote/path/file.txt", "local/path/file.txt")
    mock_s3_client.download_file.assert_called_once_with(
        "test-bucket", "remote/path/file.txt", "local/path/file.txt"
    )
    captured = capsys.readouterr()
    assert "Download successful." in captured.out

def test_download_file_failure(s3_provider, mock_s3_client, capsys):
    """Test file download failure."""
    mock_s3_client.download_file.side_effect = Exception("Download failed")
    with pytest.raises(Exception, match="Download failed"):
        s3_provider.download_file("remote/path/file.txt", "local/path/file.txt")
    captured = capsys.readouterr()
    assert "S3 Download Error" in captured.out

def test_list_files_success(s3_provider, mock_s3_client):
    """Test successful listing of files."""
    mock_s3_client.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": "file1.txt",
                "Size": 100,
                "LastModified": datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            },
            {
                "Key": "folder/file2.txt",
                "Size": 200,
                "LastModified": datetime(2023, 1, 2, 13, 0, 0, tzinfo=timezone.utc)
            },
        ]
    }
    files = s3_provider.list_files("prefix/")
    assert len(files) == 2
    assert files[0].name == "file1.txt"
    assert files[0].size == 100
    assert files[0].last_modified == datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    assert files[1].name == "folder/file2.txt"
    assert files[1].last_modified == datetime(2023, 1, 2, 13, 0, 0, tzinfo=timezone.utc).timestamp()

def test_list_files_no_contents(s3_provider, mock_s3_client):
    """Test listing files when 'Contents' key is missing."""
    mock_s3_client.list_objects_v2.return_value = {}
    files = s3_provider.list_files("prefix/")
    assert len(files) == 0

def test_list_files_failure(s3_provider, mock_s3_client, capsys):
    """Test listing files failure."""
    mock_s3_client.list_objects_v2.side_effect = Exception("List failed")
    files = s3_provider.list_files("prefix/")
    assert len(files) == 0
    captured = capsys.readouterr()
    assert "S3 List Error" in captured.out

def test_delete_file_success(s3_provider, mock_s3_client, capsys):
    """Test successful file deletion."""
    s3_provider.delete_file("remote/path/file.txt")
    mock_s3_client.delete_object.assert_called_once_with(
        Bucket="test-bucket", Key="remote/path/file.txt"
    )
    captured = capsys.readouterr()
    assert "Deleted remote/path/file.txt from S3." in captured.out

def test_delete_file_failure(s3_provider, mock_s3_client, capsys):
    """Test file deletion failure."""
    mock_s3_client.delete_object.side_effect = Exception("Delete failed")
    with pytest.raises(Exception, match="Delete failed"):
        s3_provider.delete_file("remote/path/file.txt")
    captured = capsys.readouterr()
    assert "S3 Delete Error" in captured.out

def test_upload_string_success(s3_provider, mock_s3_client, capsys):
    """Test successful string upload."""
    test_data = "Hello, S3!"
    remote_path = "data.txt"
    s3_provider.upload_string(test_data, remote_path)
    mock_s3_client.put_object.assert_called_once_with(
        Bucket="test-bucket", Key=remote_path, Body=test_data.encode("utf-8")
    )
    captured = capsys.readouterr()
    assert "Upload successful." in captured.out

def test_upload_string_failure(s3_provider, mock_s3_client, capsys):
    """Test string upload failure."""
    mock_s3_client.put_object.side_effect = Exception("Upload string failed")
    with pytest.raises(Exception, match="Upload string failed"):
        s3_provider.upload_string("test", "data.txt")
    captured = capsys.readouterr()
    assert "S3 Upload String Error" in captured.out

def test_download_to_string_success(s3_provider, mock_s3_client):
    """Test successful string download."""
    mock_response_body = MagicMock()
    mock_response_body.read.return_value = b"Downloaded string data"
    mock_s3_client.get_object.return_value = {"Body": mock_response_body}
    
    result = s3_provider.download_to_string("remote/string.txt")
    assert result == "Downloaded string data"
    mock_s3_client.get_object.assert_called_once_with(
        Bucket="test-bucket", Key="remote/string.txt"
    )

def test_download_to_string_no_such_key(s3_provider, mock_s3_client):
    """Test string download when key does not exist."""
    mock_s3_client.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
        "GetObject"
    )
    result = s3_provider.download_to_string("nonexistent.txt")
    assert result is None

def test_download_to_string_other_failure(s3_provider, mock_s3_client, capsys):
    """Test string download for other failures."""
    mock_s3_client.get_object.side_effect = ClientError(
        {"Error": {"Code": "SomeOtherError", "Message": "Some other S3 error."}},
        "GetObject"
    )
    with pytest.raises(ClientError, match="SomeOtherError"):
        s3_provider.download_to_string("remote/string.txt")
    captured = capsys.readouterr()
    assert "S3 Download String Error" in captured.out
