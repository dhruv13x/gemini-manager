import os
import boto3
from botocore.exceptions import ClientError # Import ClientError
from .cloud_storage import CloudStorageProvider, CloudFile
from .ui import console

class S3Provider(CloudStorageProvider):
    def __init__(self, bucket_name: str, aws_access_key_id: str, aws_secret_access_key: str, region_name: str = "us-east-1"):
        self.bucket_name = bucket_name
        self.client = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name
        )

    def upload_file(self, local_path: str, remote_path: str):
        try:
            console.print(f"[cyan]Uploading {local_path} to S3://{self.bucket_name}/{remote_path}...[/]")
            self.client.upload_file(local_path, self.bucket_name, remote_path)
            console.print(f"[green]Upload successful.[/]")
        except Exception as e:
            console.print(f"[bold red]S3 Upload Error:[/ {e}")
            raise

    def download_file(self, remote_path: str, local_path: str):
        try:
            console.print(f"[cyan]Downloading S3://{self.bucket_name}/{remote_path} to {local_path}...[/]")
            self.client.download_file(self.bucket_name, remote_path, local_path)
            console.print(f"[green]Download successful.[/]")
        except Exception as e:
            console.print(f"[bold red]S3 Download Error:[/ {e}")
            raise

    def list_files(self, prefix: str = "") -> list[CloudFile]:
        try:
            response = self.client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
            files = []
            if "Contents" in response:
                for obj in response["Contents"]:
                    files.append(CloudFile(
                        name=obj["Key"],
                        size=obj["Size"],
                        last_modified=obj["LastModified"]
                    ))
            return files
        except Exception as e:
            console.print(f"[bold red]S3 List Error:[/ {e}")
            return []

    def delete_file(self, remote_path: str):
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=remote_path)
            console.print(f"[green]Deleted {remote_path} from S3.[/]")
        except Exception as e:
            console.print(f"[bold red]S3 Delete Error:[/ {e}")
            raise

    def upload_string(self, data_str: str, remote_path: str):
        try:
            console.print(f"[cyan]Syncing string data to S3://{self.bucket_name}/{remote_path}...[/]")
            self.client.put_object(Bucket=self.bucket_name, Key=remote_path, Body=data_str.encode("utf-8"))
            console.print(f"[green]Upload successful.[/]")
        except Exception as e:
            console.print(f"[bold red]S3 Upload String Error:[/ {e}")
            raise

    def download_to_string(self, remote_path: str) -> str | None:
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=remote_path)
            return response["Body"].read().decode("utf-8")
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            else:
                console.print(f"[bold red]S3 Download String Error:[/ {e}")
                raise # Re-raise other ClientErrors
        except Exception as e:
            console.print(f"[bold red]S3 Download String Error:[/ {e}")
            return None
