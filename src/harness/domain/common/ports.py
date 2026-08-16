"""Ports implemented by the infrastructure layer."""

from typing import Protocol


class ObjectStore(Protocol):
    """S3-compatible binary storage for original artifacts and derived files.

    Large binaries live here; PostgreSQL keeps only object keys
    (docs/spec/01_ARCHITECTURE.md, section 6).
    """

    def put_object(self, key: str, data: bytes, *, content_type: str | None = None) -> None: ...

    def get_object(self, key: str) -> bytes: ...

    def object_exists(self, key: str) -> bool: ...

    def delete_object(self, key: str) -> None: ...
