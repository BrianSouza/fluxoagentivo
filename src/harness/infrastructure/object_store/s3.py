"""S3/MinIO adapter implementing the ObjectStore port."""

from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import ClientError

from harness.config.settings import Settings, get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client


class ObjectNotFoundError(KeyError):
    """Raised when a requested object key does not exist in the bucket."""


class S3ObjectStore:
    """Stores binaries in an S3-compatible bucket (MinIO locally).

    Satisfies harness.domain.common.ports.ObjectStore.
    """

    def __init__(self, client: "S3Client", bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "S3ObjectStore":
        settings = settings or get_settings()
        client: S3Client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        )
        return cls(client, settings.s3_bucket)

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)

    def put_object(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        extra: dict[str, str] = {"ContentType": content_type} if content_type else {}
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, **extra)  # type: ignore[arg-type]

    def get_object(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                raise ObjectNotFoundError(key) from exc
            raise
        return response["Body"].read()

    def object_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return False
            raise
        return True

    def delete_object(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
