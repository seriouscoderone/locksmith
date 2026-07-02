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

    def upload_release(
        self,
        *,
        bucket: str,
        kel: bytes,
        anchors: dict[str, bytes],
        appcast: bytes,
        appcast_key: str,
    ) -> None:
        """Upload the publisher KEL, anchor events, and the appcast in one shot.

        Layout (mirrors the verifier's expected URLs):

          ``<bucket>/publisher/v1/kel.cesr``            — the publisher KEL stream
          ``<bucket>/publisher/v1/anchors/<said>.cesr`` — one per anchor event
          ``<bucket>/<appcast_key>``                    — the built appcast JSON

        ``anchors`` maps each anchor SAID to its CESR-encoded event bytes.
        Reuses ``put_object``; no network in tests when ``self.client`` is a mock.
        """
        self.put_object(
            bucket=bucket,
            key="publisher/v1/kel.cesr",
            data=kel,
            content_type="application/cesr",
        )
        for said, event in anchors.items():
            self.put_object(
                bucket=bucket,
                key=f"publisher/v1/anchors/{said}.cesr",
                data=event,
                content_type="application/cesr",
            )
        self.put_object(
            bucket=bucket,
            key=appcast_key,
            data=appcast,
            content_type="application/json",
        )

    def list_release_versions(self, *, bucket: str, prefix: str = "releases") -> list[str]:
        """Enumerate ``X.Y.Z`` directories under ``<prefix>/`` in S3."""
        paginator = self.client.get_paginator("list_objects_v2")
        versions: set[str] = set()
        depth = len(prefix.split("/"))  # index of the X.Y.Z segment after prefix
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/"):
            for obj in page.get("Contents", []):
                parts = obj["Key"].split("/")
                if len(parts) > depth and "/".join(parts[:depth]) == prefix:
                    versions.add(parts[depth])
        return sorted(versions)
