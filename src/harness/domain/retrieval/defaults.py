"""Default port implementations usable without any extra wiring."""

from uuid import UUID

from harness.domain.common.values import validate_confidence


class IdentityCanonicalLookup:
    """Satisfies CanonicalArtifactLookup: every artifact is its own group.

    The safe default when no dedup relationships have been computed yet —
    suppression becomes a no-op rather than an error.
    """

    def canonical_for(self, artifact_id: UUID) -> UUID:
        return artifact_id


class ConfigurableSourceAuthority:
    """Satisfies SourceAuthorityLookup (spec §9: configurable by source)."""

    def __init__(
        self,
        authority_by_source: dict[UUID, float] | None = None,
        *,
        default: float = 0.5,
    ) -> None:
        for value in (authority_by_source or {}).values():
            validate_confidence(value, field="authority")
        validate_confidence(default, field="default")
        self._authority_by_source = dict(authority_by_source or {})
        self._default = default

    def authority_for(self, source_id: UUID | None) -> float:
        if source_id is None:
            return self._default
        return self._authority_by_source.get(source_id, self._default)
