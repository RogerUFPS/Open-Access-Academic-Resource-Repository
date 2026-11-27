"""Operaciones de objetos sobre RustFS (S3 compatible)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config

from .config import StorageSettings

_DOWNLOAD_CHUNK_BYTES = 8 * 1024 * 1024


class SnapshotStorage:
    """Bucket de snapshots. Sube, lee y lista objetos; nunca borra."""

    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def from_settings(cls, settings: StorageSettings) -> "SnapshotStorage":
        settings.ensure_complete()
        client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint,
            region_name=settings.region,
            aws_access_key_id=settings.access_key,
            aws_secret_access_key=settings.secret_key,
            config=Config(
                s3={"addressing_style": "path"},
                # Las sumas CRC que boto3 añade por defecto no son obligatorias
                # en S3 compatible; la integridad la verificamos con SHA-256.
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        return cls(client, settings.bucket)

    def upload_file(self, path: Path, key: str) -> None:
        self._client.upload_file(str(path), self._bucket, key)

    def download_file(self, key: str, path: Path) -> None:
        self._client.download_file(self._bucket, key, str(path))

    def sha256(self, key: str) -> str:
        """SHA-256 del contenido almacenado, descargándolo por partes."""
        body = self._client.get_object(Bucket=self._bucket, Key=key)["Body"]
        digest = hashlib.sha256()
        for chunk in body.iter_chunks(_DOWNLOAD_CHUNK_BYTES):
            digest.update(chunk)
        return digest.hexdigest()

    def put_json(self, key: str, data: dict[str, Any]) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=json.dumps(data, indent=2, sort_keys=True).encode("utf-8"),
            ContentType="application/json",
        )

    def get_json(self, key: str) -> dict[str, Any]:
        body = self._client.get_object(Bucket=self._bucket, Key=key)["Body"]
        return json.loads(body.read())

    def list_keys(self, prefix: str) -> list[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        return [
            item["Key"]
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix)
            for item in page.get("Contents", [])
        ]
