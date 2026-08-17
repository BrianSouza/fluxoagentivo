"""Shared time-decay helper for freshness-style scoring.

Used by both the triage relevance policy (06_DEDUP_TRIAGE.md §3) and
hybrid retrieval scoring (07_RETRIEVAL.md §3), so the two freshness
signals behave identically for the same age.
"""


def exponential_decay(
    age_days: float | None,
    *,
    half_life_days: float,
    neutral: float = 0.5,
) -> float:
    """1.0 for age 0, decaying toward 0 as age grows; unknown age is neutral.

    Unknown age must not read as "stale" — a missing modification date is
    absence of a signal, not evidence of one.
    """
    if age_days is None:
        return neutral
    decayed = 1.0 / (1.0 + max(age_days, 0.0) / half_life_days)
    return max(0.0, min(1.0, decayed))
