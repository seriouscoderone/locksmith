"""Thin boto3 wrapper for the publisher CLI.

Credentials are picked up from the ambient environment (operator's
``AWS_PROFILE`` or default chain). The publisher CLI runs on the operator's
laptop, NOT in CI — there is no OIDC role assumption here.

Memory rule: this is an AWS shop (project_aws_infrastructure); never mix
DigitalOcean wrappers into this module.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3


@dataclass
class S3:
    client: Any  # boto3 client — not strongly typed by boto3 itself

    @classmethod
    def default(cls) -> "S3":
        return cls(client=boto3.client("s3"))

    def get_object(self, *, bucket: str, key: str) -> bytes:
        resp = self.client.get_object(Bucket=bucket, Key=key)
        return resp["Body"].read()

    def get_json(self, *, bucket: str, key: str) -> dict:
        return json.loads(self.get_object(bucket=bucket, key=key))

    def head_object_size(self, *, bucket: str, key: str) -> int:
        resp = self.client.head_object(Bucket=bucket, Key=key)
        return int(resp["ContentLength"])

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        self.client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    def put_file(
        self,
        *,
        bucket: str,
        key: str,
        path: Path,
        content_type: str = "application/octet-stream",
    ) -> None:
        self.put_object(
            bucket=bucket,
            key=key,
            data=path.read_bytes(),
            content_type=content_type,
        )

    def list_release_versions(self, *, bucket: str) -> list[str]:
        """Enumerate ``X.Y.Z`` directories under ``releases/`` in S3."""
        paginator = self.client.get_paginator("list_objects_v2")
        versions: set[str] = set()
        for page in paginator.paginate(Bucket=bucket, Prefix="releases/"):
            for obj in page.get("Contents", []):
                parts = obj["Key"].split("/")
                if len(parts) >= 2 and parts[0] == "releases":
                    versions.add(parts[1])
        return sorted(versions)
