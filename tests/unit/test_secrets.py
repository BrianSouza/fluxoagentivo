"""Secret reference resolution (docs/spec/04_CONNECTORS.md §7)."""

import pytest

from harness.infrastructure.secrets import (
    EnvSecretResolver,
    InvalidSecretReferenceError,
    SecretNotFoundError,
)


def test_resolves_prefixed_environment_values() -> None:
    resolver = EnvSecretResolver(
        {
            "SECRET_CONFLUENCE_MAIN_TOKEN": "t0ken",
            "SECRET_CONFLUENCE_MAIN_EMAIL": "bot@example.com",
            "SECRET_OTHER_THING_TOKEN": "unrelated",
            "PATH": "/usr/bin",
        }
    )
    assert resolver.resolve("secret://confluence/main") == {
        "token": "t0ken",
        "email": "bot@example.com",
    }


def test_scope_and_name_with_dashes() -> None:
    resolver = EnvSecretResolver({"SECRET_MY_WIKI_READ_ONLY_TOKEN": "x"})
    assert resolver.resolve("secret://my-wiki/read-only") == {"token": "x"}


@pytest.mark.parametrize(
    "reference",
    ["confluence/main", "secret://confluence", "secret://a/b/c", "https://x/y", ""],
)
def test_rejects_malformed_references(reference: str) -> None:
    with pytest.raises(InvalidSecretReferenceError):
        EnvSecretResolver({}).resolve(reference)


def test_unknown_reference_raises() -> None:
    with pytest.raises(SecretNotFoundError):
        EnvSecretResolver({}).resolve("secret://confluence/main")
