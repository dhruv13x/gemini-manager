import os
from .b2 import B2Manager
from .cloud_s3 import S3Provider
from .ui import console
from .credentials import resolve_credentials # <--- ADD THIS IMPORT

def get_cloud_provider(args):
    """
    Factory to return the appropriate cloud provider based on args/config.
    """
    # S3
    s3_key = os.environ.get("GEMINI_AWS_ACCESS_KEY_ID")
    s3_secret = os.environ.get("GEMINI_AWS_SECRET_ACCESS_KEY")
    s3_bucket = os.environ.get("GEMINI_S3_BUCKET")
    s3_region = os.environ.get("GEMINI_S3_REGION", "us-east-1")

    # Resolve B2 credentials using the comprehensive resolve_credentials function
    b2_id, b2_key, b2_bucket = resolve_credentials(args, allow_fail=True) # allow_fail=True so it doesn't sys.exit here

    # If B2 credentials were resolved, return B2Manager
    if b2_id and b2_key and b2_bucket:
        return B2Manager(b2_id, b2_key, b2_bucket)

    # If S3 env vars exist -> S3 (keeping this logic for now)
    if s3_key and s3_secret and s3_bucket:
        return S3Provider(s3_bucket, s3_key, s3_secret, s3_region)

    console.print("[yellow]No valid cloud credentials found. Please configure B2 or S3.[/]")
    return None
