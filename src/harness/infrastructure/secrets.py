"""Environment-backed secret resolution (docs/spec/04_CONNECTORS.md §7).

The database stores only a reference such as `secret://confluence/main`.
This resolver maps it to environment variables prefixed with the scope and
name, e.g. `SECRET_CONFLUENCE_MAIN_TOKEN=...` becomes `{"token": "..."}`.

Raw credential values are never written back to the database or logged.
"""

import os
import re

SECRET_SCHEME = "secret://"
_REFERENCE_PATTERN = re.compile(r"^secret://([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)$")


class SecretNotFoundError(LookupError):
    """Raised when a secret reference resolves to no configured values."""


class InvalidSecretReferenceError(ValueError):
    """Raised when a reference does not match `secret://scope/name`."""


def _env_prefix(scope: str, name: str) -> str:
    return f"SECRET_{scope.upper().replace('-', '_')}_{name.upper().replace('-', '_')}_"


class EnvSecretResolver:
    """Satisfies harness.domain.sources.ports.SecretResolver."""

    def __init__(self, environ: dict[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else dict(os.environ)

    def resolve(self, reference: str) -> dict[str, str]:
        match = _REFERENCE_PATTERN.match(reference)
        if match is None:
            raise InvalidSecretReferenceError(
                f"expected secret://scope/name, got {reference!r}"
            )
        prefix = _env_prefix(match.group(1), match.group(2))
        values = {
            key.removeprefix(prefix).lower(): value
            for key, value in self._environ.items()
            if key.startswith(prefix)
        }
        if not values:
            raise SecretNotFoundError(f"no environment values configured for {reference!r}")
        return values
