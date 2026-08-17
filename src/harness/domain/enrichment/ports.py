"""Ports for OCR and enrichment caching."""

from typing import Protocol

from harness.domain.enrichment.models import OcrResult


class OcrEngine(Protocol):
    """Pluggable OCR (TASK-025).

    Implementations must be safe to call on any image bytes and should
    return an empty result rather than raising when they find no text.
    """

    name: str

    def extract_text(self, image: bytes) -> OcrResult: ...


class EnrichmentCache(Protocol):
    """Caches enrichment keyed by the spec §9 image cache key."""

    def get(self, key: str) -> dict[str, object] | None: ...

    def set(self, key: str, value: dict[str, object]) -> None: ...
