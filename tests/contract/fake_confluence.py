"""In-memory fake Confluence server (docs/spec/04_CONNECTORS.md §8).

Backs contract tests with synthetic fixture data — by default a corpus of
1,000 pages, which is the scale the TASK-014 acceptance criteria call for.
Supports pagination, per-page version bumps for incremental-sync tests and
injected failures for retry / permission tests.
"""

import json
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

DEFAULT_PAGE_COUNT = 1000


class FakeConfluence:
    def __init__(
        self,
        page_count: int = DEFAULT_PAGE_COUNT,
        *,
        attachments_for: set[str] | None = None,
    ) -> None:
        self.versions: dict[str, int] = {
            str(index): 1 for index in range(1, page_count + 1)
        }
        self.attachments_for = attachments_for or set()
        self.request_paths: list[str] = []
        self.content_fetches: list[str] = []
        # Failures injected per path prefix: a list of status codes to
        # return before the request finally succeeds.
        self.injected_failures: dict[str, list[int]] = {}

    # ---------------------------------------------------------------- setup

    def bump_version(self, page_id: str) -> None:
        self.versions[page_id] += 1

    def inject_failures(self, path_prefix: str, statuses: list[int]) -> None:
        self.injected_failures[path_prefix] = list(statuses)

    @property
    def page_ids(self) -> list[str]:
        return list(self.versions)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    # -------------------------------------------------------------- handler

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.request_paths.append(path)

        for prefix, statuses in self.injected_failures.items():
            if path.startswith(prefix) and statuses:
                return httpx.Response(statuses.pop(0), json={"message": "injected"})

        query = parse_qs(urlparse(str(request.url)).query)
        if path == "/rest/api/space":
            return httpx.Response(200, json={"results": [{"key": "ENG"}]})
        if path == "/rest/api/content":
            return self._content_list(query)
        if path.endswith("/child/attachment"):
            page_id = path.split("/")[4]
            return self._attachment_list(page_id, query)
        if path.startswith("/download/"):
            return httpx.Response(200, content=b"attachment-bytes")
        if path.startswith("/rest/api/content/"):
            page_id = path.rsplit("/", 1)[-1]
            self.content_fetches.append(page_id)
            return self._single_page(page_id)
        return httpx.Response(404, json={"message": "not found"})

    # ------------------------------------------------------------- payloads

    def _content_list(self, query: dict[str, list[str]]) -> httpx.Response:
        start = int(query.get("start", ["0"])[0])
        limit = int(query.get("limit", ["50"])[0])
        page_ids = self.page_ids[start : start + limit]
        results = [self._page_payload(page_id) for page_id in page_ids]
        has_next = start + limit < len(self.versions)
        return httpx.Response(
            200,
            json={
                "results": results,
                "start": start,
                "limit": limit,
                "size": len(results),
                "_links": {"next": "/rest/api/content?start=next" if has_next else None},
            },
        )

    def _single_page(self, page_id: str) -> httpx.Response:
        if page_id not in self.versions:
            return httpx.Response(404, json={"message": "no such page"})
        return httpx.Response(200, json=self._page_payload(page_id))

    def _attachment_list(self, page_id: str, query: dict[str, list[str]]) -> httpx.Response:
        if page_id not in self.attachments_for:
            return httpx.Response(200, json={"results": [], "_links": {"next": None}})
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": f"att-{page_id}",
                        "title": f"diagram-{page_id}.png",
                        "version": {"number": 1, "when": "2026-08-01T10:00:00.000Z"},
                        "extensions": {"mediaType": "image/png", "fileSize": 2048},
                        "_links": {"download": f"/download/att-{page_id}.png"},
                    }
                ],
                "_links": {"next": None},
            },
        )

    def _page_payload(self, page_id: str) -> dict[str, Any]:
        version = self.versions[page_id]
        return {
            "id": page_id,
            "title": f"Page {page_id}",
            "space": {"key": "ENG"},
            "version": {
                "number": version,
                "when": "2026-08-10T12:00:00.000Z",
                "by": {"displayName": "Ana Lima"},
            },
            "ancestors": [{"id": "root"}] if page_id != "1" else [],
            "metadata": {"labels": {"results": [{"name": "architecture"}]}},
            "history": {
                "createdDate": "2026-01-05T09:30:00.000Z",
                "createdBy": {"displayName": "Bruno Souza"},
            },
            "body": {
                "storage": {
                    "value": f"<h1>Page {page_id}</h1><p>Version {version}</p>",
                }
            },
            "_links": {"webui": f"/spaces/ENG/pages/{page_id}"},
        }


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload)
