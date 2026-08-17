import os
import boto3
import requests
from urllib.parse import urlparse
from botocore.config import Config

def parse_s3_url(url: str) -> tuple[str | None, str | None]:
    """
    Parses an S3 HTTP(S) or s3:// URL into (bucket, key).
    Supports:
      - s3://bucket/key/path
      - https://s3.us-east-1.amazonaws.com/bucket/key/path
      - https://s3.amazonaws.com/bucket/key/path
      - https://bucket.s3.us-east-1.amazonaws.com/key/path
      - https://bucket.s3.amazonaws.com/key/path
    """
    if not url:
        return None, None
    try:
        parsed = urlparse(url)
        if parsed.scheme == "s3":
            return parsed.netloc, parsed.path.lstrip("/")
        
        host = parsed.netloc.lower()
        if "amazonaws.com" not in host:
            return None, None
            
        # Path-style: s3.amazonaws.com/bucket/key or s3.<region>.amazonaws.com/bucket/key
        if host == "s3.amazonaws.com" or host.startswith("s3.") or host.startswith("s3-"):
            parts = parsed.path.lstrip("/").split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
            return bucket, key
            
        # Virtual-hosted style: <bucket>.s3...
        if ".s3" in host:
            bucket = host.split(".s3")[0]
            key = parsed.path.lstrip("/")
            return bucket, key
            
        return None, None
    except Exception:
        return None, None

def get_s3_client():
    region = os.getenv("AWS_REGION") or os.getenv("REMOTION_AWS_REGION") or "us-east-1"
    return boto3.client(
        "s3",
        region_name=region,
        config=Config(region_name=region, s3={"addressing_style": "virtual"}),
    )

def download_s3_or_http_file(url: str, output_path: str) -> bool:
    """
    Downloads file using boto3 if it is an S3 URL (works for private buckets like Remotion),
    falling back to requests for public HTTP URLs.
    """
    bucket, key = parse_s3_url(url)
    if bucket and key:
        try:
            s3 = get_s3_client()
            s3.download_file(bucket, key, output_path)
            return True
        except Exception as e:
            print(f"boto3 download failed for s3://{bucket}/{key}: {e}. Falling back to HTTP...")

    try:
        r = requests.get(url, stream=True, timeout=120)
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"Failed to download video from {url}: {e}")
        return False

def delete_s3_file_by_url(url: str) -> bool:
    """
    Deletes an S3 object based on its URL, automatically identifying bucket and key.
    """
    bucket, key = parse_s3_url(url)
    if not bucket or not key:
        # Fallback to BUCKET_NAME if path-only
        bucket = os.getenv("BUCKET_NAME")
        try:
            key = urlparse(url).path.lstrip("/")
        except:
            return False
            
    if not bucket or not key:
        return False
        
    try:
        s3 = get_s3_client()
        s3.delete_object(Bucket=bucket, Key=key)
        return True
    except Exception as e:
        print(f"Failed to delete S3 object {bucket}/{key}: {e}")
        return False

def get_presigned_s3_url(url: str, expires_in: int = 7200) -> str:
    """
    Generates a pre-signed S3 URL if the URL points to an S3 object.
    Allows services like Instagram / Facebook / Meta to fetch private video assets.
    """
    bucket, key = parse_s3_url(url)
    if bucket and key:
        try:
            s3 = get_s3_client()
            return s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in
            )
        except Exception as e:
            print(f"Failed to generate presigned S3 URL for {bucket}/{key}: {e}")
    return url
