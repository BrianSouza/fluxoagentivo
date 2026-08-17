"""Image enrichment cache key (docs/spec/05_PARSERS_AND_MULTIMODAL.md §9).

`sha256(image_bytes + processor_version + prompt_version + model_profile)`

Every input that can change the result is part of the key, so bumping a
prompt version or switching model profile invalidates the cache instead of
silently serving stale interpretations.
"""

import hashlib

PROCESSOR_VERSION = "1.0.0"


def image_cache_key(
    image: bytes,
    *,
    processor_version: str = PROCESSOR_VERSION,
    prompt_version: str,
    model_profile: str,
) -> str:
    hasher = hashlib.sha256()
    hasher.update(image)
    for part in (processor_version, prompt_version, model_profile):
        hasher.update(b"\x00")
        hasher.update(part.encode("utf-8"))
    return hasher.hexdigest()


class InMemoryEnrichmentCache:
    """Satisfies harness.domain.enrichment.ports.EnrichmentCache."""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, object]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> dict[str, object] | None:
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        self.hits += 1
        return dict(entry)

    def set(self, key: str, value: dict[str, object]) -> None:
        self._entries[key] = dict(value)
