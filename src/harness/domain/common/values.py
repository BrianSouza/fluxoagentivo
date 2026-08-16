"""Validation helpers shared by domain entities."""

import string

_HEX_DIGITS = set(string.hexdigits.lower())

SHA256_LENGTH = 64


def validate_sha256(value: str, *, field: str) -> str:
    if len(value) != SHA256_LENGTH or not set(value) <= _HEX_DIGITS:
        raise ValueError(f"{field} must be a lowercase hex SHA-256 digest, got {value!r}")
    return value


def validate_confidence(value: float | None, *, field: str) -> float | None:
    if value is not None and not 0.0 <= value <= 1.0:
        raise ValueError(f"{field} must be between 0.0 and 1.0, got {value!r}")
    return value


def validate_non_negative(value: int | None, *, field: str) -> int | None:
    if value is not None and value < 0:
        raise ValueError(f"{field} must be non-negative, got {value!r}")
    return value
