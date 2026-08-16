"""HTTP failure classification and bounded retry.

Maps transport/status failures onto the taxonomy from
docs/spec/01_ARCHITECTURE.md section 8: 429, 5xx and network timeouts are
transient and retried with exponential backoff; authentication,
authorization and not-found failures are permanent and never retried.
"""

import asyncio
from collections.abc import Awaitable, Callable

import httpx

from harness.domain.processing.models import (
    PermanentProcessingError,
    TransientProcessingError,
)

TRANSIENT_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
PERMANENT_STATUS_CODES = frozenset({400, 401, 403, 404, 405, 409, 422})


def raise_for_status(response: httpx.Response) -> httpx.Response:
    """Convert an error response into the domain error taxonomy."""
    status = response.status_code
    if status < 400:
        return response
    detail = f"HTTP {status} for {response.request.method} {response.request.url}"
    if status in TRANSIENT_STATUS_CODES or status >= 500:
        raise TransientProcessingError(detail)
    raise PermanentProcessingError(detail)


async def with_retry[T](
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Retry transient failures with exponential backoff.

    PermanentProcessingError propagates immediately — retrying it wastes
    quota and never succeeds.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await operation()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = TransientProcessingError(str(exc))
        except TransientProcessingError as exc:
            last_error = exc
        if attempt < max_attempts - 1:
            await sleep(base_delay * (2**attempt))
    assert last_error is not None
    raise last_error
