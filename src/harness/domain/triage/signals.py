"""Deterministic triage signals (docs/spec/06_DEDUP_TRIAGE.md §2).

Every signal here is computed without an LLM. They feed the relevance
policy, which decides whether expensive AI enrichment is justified —
so computing them must stay cheap.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from harness.domain.artifacts.parsing import ParsedDocument, PartType

_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def unique_token_ratio(text: str) -> float:
    """Lexical diversity: 1.0 means every token is distinct.

    Low ratios flag padded or highly repetitive content.
    """
    tokens = tokenize(text)
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)


def repeated_block_ratio(blocks: list[str]) -> float:
    """Fraction of blocks that are duplicates of an earlier block."""
    if not blocks:
        return 0.0
    normalized = [normalize_block(block) for block in blocks]
    seen: set[str] = set()
    repeated = 0
    for block in normalized:
        if block in seen:
            repeated += 1
        else:
            seen.add(block)
    return repeated / len(normalized)


def normalize_block(text: str) -> str:
    return " ".join(text.lower().split())


@dataclass(slots=True)
class DeterministicSignals:
    text_length: int = 0
    unique_token_ratio: float = 0.0
    heading_count: int = 0
    image_count: int = 0
    attachment_count: int = 0
    link_count: int = 0
    repeated_block_ratio: float = 0.0
    hierarchy_depth: int = 0
    modification_age_days: float | None = None
    duplicate_hash_count: int = 0


def compute_signals(
    document: ParsedDocument,
    *,
    attachment_count: int = 0,
    hierarchy_depth: int = 0,
    modified_at: datetime | None = None,
    duplicate_hash_count: int = 0,
    now: datetime | None = None,
) -> DeterministicSignals:
    text_parts = document.text_parts
    full_text = "\n".join(part.text_content or "" for part in text_parts)
    link_count = sum(len(part.metadata.get("links", []) or []) for part in document.parts)
    heading_count = sum(
        1
        for part in document.parts
        if part.part_type == PartType.HEADING
        or (part.part_type == PartType.SECTION and part.metadata.get("heading"))
    )

    age_days: float | None = None
    if modified_at is not None:
        reference = now or datetime.now(UTC)
        age_days = max((reference - modified_at).total_seconds() / 86400.0, 0.0)

    return DeterministicSignals(
        text_length=len(full_text),
        unique_token_ratio=unique_token_ratio(full_text),
        heading_count=heading_count,
        image_count=len(document.image_parts),
        attachment_count=attachment_count,
        link_count=link_count,
        repeated_block_ratio=repeated_block_ratio(
            [part.text_content or "" for part in text_parts]
        ),
        hierarchy_depth=hierarchy_depth,
        modification_age_days=age_days,
        duplicate_hash_count=duplicate_hash_count,
    )
