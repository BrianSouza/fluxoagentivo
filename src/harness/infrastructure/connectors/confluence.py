"""Confluence connector (TASK-014, docs/spec/04_CONNECTORS.md §2-§4, §7).

Discovery pages through the REST API and captures everything the spec
requires: space, page ID, title, hierarchy, version, labels, author,
created/modified timestamps, HTML body, attachments and page URL.

Attachments are emitted as independent artifacts that retain their parent
page ID and version, so provenance survives (§4).

Credentials are resolved at runtime from a `secret://` reference and are
never persisted or logged (§7).
"""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx

from harness.domain.artifacts.fetching import FetchedArtifact
from harness.domain.processing.models import PermanentProcessingError
from harness.domain.sources.models import (
    ArtifactType,
    ConnectionResult,
    DiscoveredArtifact,
)
from harness.domain.sources.ports import SecretResolver
from harness.infrastructure.connectors.errors import raise_for_status, with_retry

DEFAULT_PAGE_SIZE = 50
_EXPANSIONS = "body.storage,version,space,ancestors,metadata.labels,history"


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_client(
    base_url: str,
    credentials: dict[str, str],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = 30.0,
) -> httpx.AsyncClient:
    """Build an authenticated client. Supports API token or bearer token."""
    headers = {"Accept": "application/json"}
    auth: httpx.Auth | None = None
    if "token" in credentials and "email" in credentials:
        auth = httpx.BasicAuth(credentials["email"], credentials["token"])
    elif "token" in credentials:
        headers["Authorization"] = f"Bearer {credentials['token']}"
    elif "username" in credentials and "password" in credentials:
        auth = httpx.BasicAuth(credentials["username"], credentials["password"])
    else:
        raise PermanentProcessingError(
            "confluence credentials must provide token, email+token or username+password"
        )
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        headers=headers,
        auth=auth,
        timeout=timeout,
        transport=transport,
    )


class ConfluenceConnector:
    """Satisfies harness.domain.sources.ports.SourceConnector."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        space_key: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        include_attachments: bool = True,
        max_attempts: int = 3,
        retry_base_delay: float = 0.5,
    ) -> None:
        self._client = client
        self._space_key = space_key
        self._page_size = page_size
        self._include_attachments = include_attachments
        self._max_attempts = max_attempts
        self._retry_base_delay = retry_base_delay

    @classmethod
    def from_secret(
        cls,
        base_url: str,
        config_ref: str,
        resolver: SecretResolver,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        **kwargs: Any,
    ) -> "ConfluenceConnector":
        credentials = resolver.resolve(config_ref)
        return cls(build_client(base_url, credentials, transport=transport), **kwargs)

    async def test_connection(self) -> ConnectionResult:
        try:
            payload = await self._get_json("/rest/api/space", params={"limit": 1})
        except PermanentProcessingError as exc:
            return ConnectionResult(ok=False, message=str(exc))
        return ConnectionResult(
            ok=True, message="ok", detail={"spaces": len(payload.get("results", []))}
        )

    async def discover(self, cursor: str | None = None) -> AsyncIterator[DiscoveredArtifact]:
        """Page through content, yielding pages and their attachments.

        The cursor is the `start` offset of the next batch, so an
        interrupted sync resumes without re-reading earlier batches.
        """
        start = int(cursor) if cursor else 0
        while True:
            params: dict[str, Any] = {
                "limit": self._page_size,
                "start": start,
                "expand": _EXPANSIONS,
            }
            if self._space_key:
                params["spaceKey"] = self._space_key
            payload = await self._get_json("/rest/api/content", params=params)
            results = payload.get("results", [])
            for page in results:
                discovered = self._to_page_artifact(page)
                yield discovered
                if self._include_attachments:
                    async for attachment in self._discover_attachments(discovered):
                        yield attachment
            if not results or payload.get("_links", {}).get("next") is None:
                return
            start += len(results)

    async def _discover_attachments(
        self, page: DiscoveredArtifact
    ) -> AsyncIterator[DiscoveredArtifact]:
        start = 0
        while True:
            payload = await self._get_json(
                f"/rest/api/content/{page.external_id}/child/attachment",
                params={"limit": self._page_size, "start": start},
            )
            results = payload.get("results", [])
            for item in results:
                yield self._to_attachment_artifact(item, page)
            if not results or payload.get("_links", {}).get("next") is None:
                return
            start += len(results)

    async def fetch(self, artifact: DiscoveredArtifact) -> FetchedArtifact:
        if artifact.artifact_type == ArtifactType.ATTACHMENT:
            download_path = artifact.metadata.get("download_path")
            if not download_path:
                raise PermanentProcessingError(
                    f"attachment {artifact.external_id} has no download path"
                )
            response = await self._request("GET", str(download_path))
            content = response.content
            filename = artifact.title or artifact.external_id
        else:
            payload = await self._get_json(
                f"/rest/api/content/{artifact.external_id}", params={"expand": _EXPANSIONS}
            )
            content = self._body_html(payload).encode("utf-8")
            filename = f"{artifact.external_id}.html"
        return FetchedArtifact(
            external_id=artifact.external_id,
            source_uri=artifact.source_uri,
            filename=filename,
            content=content,
            mime_type=artifact.mime_type,
            version=artifact.version,
            metadata=dict(artifact.metadata),
        )

    async def get_version(self, artifact: DiscoveredArtifact) -> str:
        payload = await self._get_json(
            f"/rest/api/content/{artifact.external_id}", params={"expand": "version"}
        )
        return str(payload.get("version", {}).get("number", ""))

    def _to_page_artifact(self, page: dict[str, Any]) -> DiscoveredArtifact:
        page_id = str(page["id"])
        links = page.get("_links", {})
        history = page.get("history", {})
        ancestors = [str(a.get("id")) for a in page.get("ancestors", [])]
        labels = [
            label.get("name")
            for label in page.get("metadata", {}).get("labels", {}).get("results", [])
        ]
        return DiscoveredArtifact(
            external_id=page_id,
            source_uri=self._page_url(links),
            artifact_type=ArtifactType.PAGE,
            title=page.get("title"),
            version=str(page.get("version", {}).get("number", "")),
            parent_external_id=ancestors[-1] if ancestors else None,
            mime_type="text/html",
            created_at=_parse_timestamp(history.get("createdDate")),
            modified_at=_parse_timestamp(page.get("version", {}).get("when")),
            metadata={
                "space": page.get("space", {}).get("key"),
                "labels": labels,
                "ancestors": ancestors,
                "author": history.get("createdBy", {}).get("displayName"),
                "last_modifier": page.get("version", {}).get("by", {}).get("displayName"),
                "page_url": self._page_url(links),
            },
        )

    def _to_attachment_artifact(
        self, attachment: dict[str, Any], page: DiscoveredArtifact
    ) -> DiscoveredArtifact:
        attachment_id = str(attachment["id"])
        extensions = attachment.get("extensions", {})
        links = attachment.get("_links", {})
        return DiscoveredArtifact(
            external_id=attachment_id,
            source_uri=self._page_url(links) or page.source_uri,
            artifact_type=ArtifactType.ATTACHMENT,
            title=attachment.get("title"),
            version=str(attachment.get("version", {}).get("number", "")),
            parent_external_id=page.external_id,
            mime_type=extensions.get("mediaType"),
            size_bytes=extensions.get("fileSize"),
            modified_at=_parse_timestamp(attachment.get("version", {}).get("when")),
            metadata={
                "parent_page_id": page.external_id,
                "parent_page_version": page.version,
                "download_path": links.get("download"),
                "space": page.metadata.get("space"),
            },
        )

    def _page_url(self, links: dict[str, Any]) -> str:
        webui = links.get("webui") or ""
        base = str(self._client.base_url).rstrip("/")
        if not webui:
            return base
        return f"{base}{webui}" if webui.startswith("/") else f"{base}/{webui}"

    @staticmethod
    def _body_html(payload: dict[str, Any]) -> str:
        return str(payload.get("body", {}).get("storage", {}).get("value", ""))

    async def _get_json(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        response = await self._request("GET", path, params=params)
        data: dict[str, Any] = response.json()
        return data

    async def _request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        async def call() -> httpx.Response:
            response = await self._client.request(method, path, params=params)
            return raise_for_status(response)

        return await with_retry(
            call, max_attempts=self._max_attempts, base_delay=self._retry_base_delay
        )
