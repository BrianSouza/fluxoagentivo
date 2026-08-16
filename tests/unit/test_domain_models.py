from datetime import UTC, datetime
from uuid import uuid4

import pytest

from harness.domain.artifacts.models import Artifact, ArtifactPart
from harness.domain.evidence.models import Enrichment, Evidence
from harness.domain.knowledge.models import KnowledgeUnit, Relationship

NOW = datetime(2026, 8, 16, tzinfo=UTC)
SHA = "a" * 64


def make_artifact(**overrides: object) -> Artifact:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "source_id": uuid4(),
        "external_id": "PAGE-1",
        "artifact_type": "page",
        "source_uri": "https://wiki.example/PAGE-1",
        "checksum_sha256": SHA,
        "discovered_at": NOW,
    }
    defaults.update(overrides)
    return Artifact(**defaults)  # type: ignore[arg-type]


class TestArtifact:
    def test_valid_artifact(self) -> None:
        artifact = make_artifact(title="Checkout flow", size_bytes=1024)
        assert artifact.metadata == {}
        assert artifact.parent_artifact_id is None

    @pytest.mark.parametrize("checksum", ["", "abc", "Z" * 64, "A" * 64])
    def test_rejects_invalid_checksum(self, checksum: str) -> None:
        with pytest.raises(ValueError, match="checksum_sha256"):
            make_artifact(checksum_sha256=checksum)

    def test_rejects_negative_size(self) -> None:
        with pytest.raises(ValueError, match="size_bytes"):
            make_artifact(size_bytes=-1)

    def test_rejects_empty_external_id(self) -> None:
        with pytest.raises(ValueError, match="external_id"):
            make_artifact(external_id="")


class TestArtifactPart:
    def test_valid_part(self) -> None:
        part = ArtifactPart(id=uuid4(), artifact_id=uuid4(), part_type="section", ordinal=0)
        assert part.location == {}

    def test_rejects_negative_ordinal(self) -> None:
        with pytest.raises(ValueError, match="ordinal"):
            ArtifactPart(id=uuid4(), artifact_id=uuid4(), part_type="section", ordinal=-1)

    def test_optional_checksum_is_validated_when_present(self) -> None:
        with pytest.raises(ValueError, match="checksum_sha256"):
            ArtifactPart(
                id=uuid4(),
                artifact_id=uuid4(),
                part_type="image",
                ordinal=0,
                checksum_sha256="nothex",
            )


class TestEvidence:
    def test_valid_evidence(self) -> None:
        evidence = Evidence(
            id=uuid4(),
            artifact_id=uuid4(),
            artifact_part_id=uuid4(),
            modality="text",
            content="The checkout uses a WebView.",
            content_hash=SHA,
            extraction_method="pymupdf",
            created_at=NOW,
            confidence=0.9,
        )
        assert evidence.confidence == 0.9

    @pytest.mark.parametrize("confidence", [-0.1, 1.1])
    def test_rejects_out_of_range_confidence(self, confidence: float) -> None:
        with pytest.raises(ValueError, match="confidence"):
            Evidence(
                id=uuid4(),
                artifact_id=uuid4(),
                artifact_part_id=uuid4(),
                modality="text",
                content="x",
                content_hash=SHA,
                extraction_method="pymupdf",
                created_at=NOW,
                confidence=confidence,
            )

    def test_rejects_empty_content(self) -> None:
        with pytest.raises(ValueError, match="content"):
            Evidence(
                id=uuid4(),
                artifact_id=uuid4(),
                artifact_part_id=uuid4(),
                modality="text",
                content="",
                content_hash=SHA,
                extraction_method="pymupdf",
                created_at=NOW,
            )


class TestEnrichment:
    def test_valid_enrichment_records_provenance(self) -> None:
        enrichment = Enrichment(
            id=uuid4(),
            evidence_id=uuid4(),
            enrichment_type="image_description",
            content={"description": "Login screen"},
            created_at=NOW,
            provider="ollama",
            model="llava",
            prompt_version="1.0.0",
            input_tokens=100,
            output_tokens=50,
        )
        assert enrichment.provider == "ollama"

    def test_rejects_negative_tokens(self) -> None:
        with pytest.raises(ValueError, match="input_tokens"):
            Enrichment(
                id=uuid4(),
                evidence_id=uuid4(),
                enrichment_type="x",
                content={},
                created_at=NOW,
                input_tokens=-1,
            )


class TestKnowledgeUnit:
    def test_valid_unit(self) -> None:
        unit = KnowledgeUnit(
            id=uuid4(),
            title="Checkout flow",
            summary="The mobile checkout runs in a WebView.",
            version=1,
            status="active",
            created_at=NOW,
            updated_at=NOW,
            evidence_ids=[uuid4()],
        )
        assert unit.version == 1

    def test_rejects_version_below_one(self) -> None:
        with pytest.raises(ValueError, match="version"):
            KnowledgeUnit(
                id=uuid4(),
                title="t",
                summary="s",
                version=0,
                status="draft",
                created_at=NOW,
                updated_at=NOW,
            )


class TestRelationship:
    def test_valid_relationship(self) -> None:
        relationship = Relationship(
            id=uuid4(),
            subject_type="knowledge_unit",
            subject_id=uuid4(),
            predicate="describes",
            object_type="artifact",
            object_id=uuid4(),
            created_at=NOW,
            confidence=0.8,
        )
        assert relationship.predicate == "describes"

    def test_rejects_empty_predicate(self) -> None:
        with pytest.raises(ValueError, match="predicate"):
            Relationship(
                id=uuid4(),
                subject_type="a",
                subject_id=uuid4(),
                predicate="",
                object_type="b",
                object_id=uuid4(),
                created_at=NOW,
            )
