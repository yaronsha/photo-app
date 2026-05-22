from __future__ import annotations

from typing import BinaryIO, Iterator

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .base import KeyNotFound, Storage


# S3-compatible "object missing" indicators. HeadObject responses have no
# body, so botocore can populate the Code field as "" with HTTPStatusCode=404
# — always check both.
_MISSING_CODES = {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}


def _is_not_found(exc: ClientError) -> bool:
    code = exc.response.get("Error", {}).get("Code", "")
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return status == 404 or code in _MISSING_CODES


class R2Storage(Storage):
    def __init__(self, account_id: str, access_key: str, secret_key: str, bucket: str) -> None:
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    def read_bytes(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            if _is_not_found(exc):
                raise KeyNotFound(key) from exc
            raise

    def open_stream(self, key: str) -> BinaryIO:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]  # type: ignore[return-value]
        except ClientError as exc:
            if _is_not_found(exc):
                raise KeyNotFound(key) from exc
            raise

    def write_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if _is_not_found(exc):
                return False
            raise

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def iter_prefix(self, prefix: str) -> Iterator[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                yield obj["Key"]

    def presign_get(self, key: str, expires: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires,
        )
