"""S3ObjectStore adapter tests against an in-process fake S3 (moto)."""

from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws

from harness.domain.common.ports import ObjectStore
from harness.infrastructure.object_store.s3 import ObjectNotFoundError, S3ObjectStore


@pytest.fixture
def store() -> Iterator[S3ObjectStore]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        adapter = S3ObjectStore(client, "harness")
        adapter.ensure_bucket()
        yield adapter


def test_satisfies_object_store_port(store: S3ObjectStore) -> None:
    port: ObjectStore = store
    assert port is store


def test_put_and_get_roundtrip(store: S3ObjectStore) -> None:
    store.put_object("artifacts/a/original.pdf", b"%PDF-1.7", content_type="application/pdf")
    assert store.get_object("artifacts/a/original.pdf") == b"%PDF-1.7"


def test_object_exists(store: S3ObjectStore) -> None:
    assert not store.object_exists("missing")
    store.put_object("present", b"data")
    assert store.object_exists("present")


def test_get_missing_object_raises(store: S3ObjectStore) -> None:
    with pytest.raises(ObjectNotFoundError):
        store.get_object("missing")


def test_delete_object(store: S3ObjectStore) -> None:
    store.put_object("victim", b"data")
    store.delete_object("victim")
    assert not store.object_exists("victim")


def test_ensure_bucket_is_idempotent(store: S3ObjectStore) -> None:
    store.ensure_bucket()
    store.ensure_bucket()
    store.put_object("k", b"v")
    assert store.object_exists("k")
