"""Ports for source connectors and credential resolution."""

from collections.abc import AsyncIterator
from typing import Protocol

from harness.domain.artifacts.fetching import FetchedArtifact
from harness.domain.sources.models import ConnectionResult, DiscoveredArtifact


class SourceConnector(Protocol):
    """Interface from docs/spec/04_CONNECTORS.md section 1."""

    async def test_connection(self) -> ConnectionResult: ...

    def discover(self, cursor: str | None) -> AsyncIterator[DiscoveredArtifact]: ...

    async def fetch(self, artifact: DiscoveredArtifact) -> FetchedArtifact: ...

    async def get_version(self, artifact: DiscoveredArtifact) -> str: ...


class SecretResolver(Protocol):
    """Resolves `secret://scope/name` references to credential values.

    Connectors receive credentials at runtime only. Raw credentials are
    never persisted in the database (spec section 7).
    """

    def resolve(self, reference: str) -> dict[str, str]: ...
