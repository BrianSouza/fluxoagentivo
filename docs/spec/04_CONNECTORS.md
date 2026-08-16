# 04 --- Connector Architecture

## 1. Connector interface

``` python
class SourceConnector(Protocol):
    async def test_connection(self) -> ConnectionResult: ...
    async def discover(self, cursor: str | None) -> AsyncIterator[DiscoveredArtifact]: ...
    async def fetch(self, artifact: DiscoveredArtifact) -> FetchedArtifact: ...
    async def get_version(self, artifact: DiscoveredArtifact) -> str: ...
```

## 2. Confluence

Use Confluence REST APIs through `httpx`.

Connector MUST capture: - space - page ID - title - hierarchy -
version - labels - author - created/modified timestamps - HTML body -
attachments - page URL

## 3. Incremental synchronization

Preferred sequence: 1. discover changed objects using connector-native
update/version metadata; 2. compare external version/checksum; 3. fetch
only changed artifacts; 4. process changed artifacts; 5. preserve
previous versions.

## 4. Attachments

Attachment objects are independent artifacts but retain: - parent page
ID - parent page version when available - attachment relationship

## 5. Local filesystem connector

Required for development and test fixtures.

It MUST recursively discover configured extensions and produce
deterministic external IDs.

## 6. Generic uploaded-file connector

Accept one or more files and assign a generated source boundary.

## 7. Connector security

Credentials are referenced by secret ID. Connectors MUST NOT persist raw
credentials in the database.

## 8. Connector test strategy

Every connector MUST provide: - fake client - contract tests - fixture
data - retry test - pagination test - incremental sync test -
permission/error test
