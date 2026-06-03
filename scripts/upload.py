"""Upload an artifact to AWS S3.

Credentials are picked up from the environment by boto3 (AWS_ACCESS_KEY_ID,
AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN, AWS_REGION). In CI these are
populated by aws-actions/configure-aws-credentials@v4 via GitHub Actions
OIDC; no long-lived secrets are needed.
"""
from __future__ import annotations

import argparse
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def upload(bucket: str, object_key: str, file: str, region: str | None = None) -> None:
    s3 = boto3.client("s3", region_name=region) if region else boto3.client("s3")
    s3.upload_file(file, bucket, object_key)
    print(f"uploaded s3://{bucket}/{object_key}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Upload a file to AWS S3.")
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--object-key", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--region", default=None, help="optional override; default from env")
    args = ap.parse_args()
    try:
        upload(args.bucket, args.object_key, args.file, args.region)
    except (BotoCoreError, ClientError) as exc:
        print(f"upload failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
