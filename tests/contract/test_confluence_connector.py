"""Confluence connector contract tests (TASK-014).

Covers the full test strategy from docs/spec/04_CONNECTORS.md §8: fake
client, fixture data, pagination, incremental sync, retry and permission
errors. The acceptance criteria are that fixtures simulate 1,000 pages and
that unchanged pages are skipped.
"""

from collections.abc import AsyncIterator

import httpx
import pytest

from harness.application.services.sync import SourceSyncService
from harness.domain.artifacts.fetching import FetchedArtifact
from harness.domain.processing.models import (
    PermanentProcessingError,
    TransientProcessingError,
)
from harness.domain.sources.models import ArtifactType, DiscoveredArtifact
from harness.infrastructure.connectors.confluence import ConfluenceConnector
from tests.contract.fake_confluence import DEFAULT_PAGE_COUNT, FakeConfluence


def build_connector(
    fake: FakeConfluence, **kwargs: object
) -> tuple[ConfluenceConnector, httpx.AsyncClient]:
    client = httpx.AsyncClient(
        base_url="https://wiki.example.com",
        transport=fake.transport(),
        headers={"Authorization": "Bearer test-token"},
    )
    kwargs.setdefault("retry_base_delay", 0.0)
    return ConfluenceConnector(client, **kwargs), client  # type: ignore[arg-type]


async def collect(iterator: AsyncIterator[DiscoveredArtifact]) -> list[DiscoveredArtifact]:
    return [item async for item in iterator]


class TestConnection:
    async def test_reports_ok(self) -> None:
        connector, client = build_connector(FakeConfluence(page_count=1))
        async with client:
            result = await connector.test_connection()
        assert result.ok


class TestPagination:
    async def test_discovers_all_thousand_pages(self) -> None:
        fake = FakeConfluence()  # 1,000 synthetic pages
        connector, client = build_connector(fake, page_size=50, include_attachments=False)
        async with client:
            discovered = await collect(connector.discover(None))

        assert len(discovered) == DEFAULT_PAGE_COUNT == 1000
        assert {a.external_id for a in discovered} == set(fake.page_ids)
        # 1,000 pages at 50 per batch must take 20 list requests, proving
        # the connector paginated rather than reading one oversized page.
        list_requests = [p for p in fake.request_paths if p == "/rest/api/content"]
        assert len(list_requests) == 20

    async def test_cursor_resumes_after_offset(self) -> None:
        fake = FakeConfluence(page_count=120)
        connector, client = build_connector(fake, page_size=50, include_attachments=False)
        async with client:
            resumed = await collect(connector.discover("100"))
        assert len(resumed) == 20
        assert resumed[0].external_id == "101"


class TestCapturedFields:
    async def test_page_captures_spec_required_metadata(self) -> None:
        fake = FakeConfluence(page_count=2)
        connector, client = build_connector(fake, include_attachments=False)
        async with client:
            discovered = await collect(connector.discover(None))

        page = discovered[1]
        assert page.artifact_type == ArtifactType.PAGE
        assert page.title == "Page 2"
        assert page.version == "1"
        assert page.metadata["space"] == "ENG"
        assert page.metadata["labels"] == ["architecture"]
        assert page.metadata["author"] == "Bruno Souza"
        assert page.parent_external_id == "root"  # hierarchy
        assert page.created_at is not None and page.modified_at is not None
        assert page.source_uri == "https://wiki.example.com/spaces/ENG/pages/2"

    async def test_fetch_returns_body_html(self) -> None:
        fake = FakeConfluence(page_count=1)
        connector, client = build_connector(fake, include_attachments=False)
        async with client:
            (page,) = await collect(connector.discover(None))
            fetched = await connector.fetch(page)

        assert isinstance(fetched, FetchedArtifact)
        assert b"<h1>Page 1</h1>" in fetched.content
        assert fetched.filename == "1.html"


class TestAttachments:
    async def test_attachments_are_independent_artifacts_linked_to_parent(self) -> None:
        fake = FakeConfluence(page_count=2, attachments_for={"2"})
        connector, client = build_connector(fake)
        async with client:
            discovered = await collect(connector.discover(None))

        attachments = [a for a in discovered if a.artifact_type == ArtifactType.ATTACHMENT]
        assert len(attachments) == 1
        attachment = attachments[0]
        assert attachment.external_id == "att-2"
        assert attachment.parent_external_id == "2"
        assert attachment.metadata["parent_page_id"] == "2"
        assert attachment.metadata["parent_page_version"] == "1"
        assert attachment.mime_type == "image/png"

    async def test_attachment_content_is_downloaded(self) -> None:
        fake = FakeConfluence(page_count=1, attachments_for={"1"})
        connector, client = build_connector(fake)
        async with client:
            discovered = await collect(connector.discover(None))
            attachment = next(
                a for a in discovered if a.artifact_type == ArtifactType.ATTACHMENT
            )
            fetched = await connector.fetch(attachment)
        assert fetched.content == b"attachment-bytes"


class TestFailureHandling:
    async def test_transient_status_is_retried_then_succeeds(self) -> None:
        fake = FakeConfluence(page_count=1)
        fake.inject_failures("/rest/api/content", [429, 503])
        connector, client = build_connector(fake, include_attachments=False, max_attempts=3)
        async with client:
            discovered = await collect(connector.discover(None))
        assert len(discovered) == 1

    async def test_transient_failure_beyond_attempts_propagates(self) -> None:
        fake = FakeConfluence(page_count=1)
        fake.inject_failures("/rest/api/content", [503, 503, 503])
        connector, client = build_connector(fake, include_attachments=False, max_attempts=2)
        async with client:
            with pytest.raises(TransientProcessingError):
                await collect(connector.discover(None))

    async def test_permission_error_is_permanent_and_not_retried(self) -> None:
        fake = FakeConfluence(page_count=1)
        fake.inject_failures("/rest/api/content", [403, 200])
        connector, client = build_connector(fake, include_attachments=False, max_attempts=3)
        async with client:
            with pytest.raises(PermanentProcessingError):
                await collect(connector.discover(None))
        # Exactly one attempt: a permanent error must not consume retries.
        assert fake.request_paths.count("/rest/api/content") == 1


class TestIncrementalSync:
    async def test_unchanged_pages_are_skipped_on_second_sync(self) -> None:
        fake = FakeConfluence(page_count=DEFAULT_PAGE_COUNT)
        connector, client = build_connector(fake, page_size=100, include_attachments=False)

        known: dict[str, str] = {}

        async def handle(
            discovered: DiscoveredArtifact, fetched: FetchedArtifact
        ) -> None:
            known[discovered.external_id] = discovered.version or ""

        service = SourceSyncService(
            connector, known_version=known.get, handle=handle
        )

        async with client:
            first = await service.run()
            assert first.discovered == 1000
            assert first.fetched == 1000
            assert first.skipped == 0

            fake.content_fetches.clear()

            # Nothing changed between passes.
            second = await service.run()
            assert second.discovered == 1000
            assert second.fetched == 0
            assert second.skipped == 1000
            assert fake.content_fetches == []  # zero content downloads

            # One page gets a new version; only that page is re-fetched.
            fake.bump_version("42")
            third = await service.run()
            assert third.fetched == 1
            assert third.skipped == 999
            assert fake.content_fetches == ["42"]
