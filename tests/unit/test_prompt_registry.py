"""Prompt registry and template contracts (spec 08 §11, 09 §6)."""

from pathlib import Path

import pytest

from harness.domain.prompts.models import MissingPromptVariableError, PromptTemplate
from harness.infrastructure.prompts.registry import (
    InvalidPromptFileError,
    PromptNotFoundError,
    PromptRegistry,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_PROMPTS = ("image_classification", "diagram_interpretation", "page_synthesis")


@pytest.fixture(scope="module")
def registry() -> PromptRegistry:
    return PromptRegistry.from_directory(REPO_ROOT / "prompts")


class TestTemplateInvariants:
    def test_version_must_be_semantic(self) -> None:
        with pytest.raises(ValueError, match="semantic version"):
            PromptTemplate(name="p", version="1", template="x")

    def test_empty_template_rejected(self) -> None:
        with pytest.raises(ValueError, match="empty template"):
            PromptTemplate(name="p", version="1.0.0", template="   ")

    def test_reference_identifies_name_and_version(self) -> None:
        prompt = PromptTemplate(name="p", version="2.1.0", template="x")
        assert prompt.reference == "p@2.1.0"

    def test_render_substitutes_declared_variables(self) -> None:
        prompt = PromptTemplate(
            name="p", version="1.0.0", template="Hello $who", variables=("who",)
        )
        assert prompt.render(who="world") == "Hello world"

    def test_render_requires_every_declared_variable(self) -> None:
        prompt = PromptTemplate(
            name="p", version="1.0.0", template="$a $b", variables=("a", "b")
        )
        with pytest.raises(MissingPromptVariableError, match=r"\['b'\]"):
            prompt.render(a="1")

    def test_undeclared_placeholder_is_reported(self) -> None:
        prompt = PromptTemplate(name="p", version="1.0.0", template="$ghost")
        with pytest.raises(MissingPromptVariableError, match="ghost"):
            prompt.render()


class TestShippedPrompts:
    def test_all_expected_prompts_load(self, registry: PromptRegistry) -> None:
        for name in SHIPPED_PROMPTS:
            assert name in registry.names()

    def test_structured_prompts_declare_a_schema(self, registry: PromptRegistry) -> None:
        for name in SHIPPED_PROMPTS:
            prompt = registry.get(name)
            assert prompt.json_schema is not None, name
            assert prompt.json_schema["type"] == "object"

    def test_prompts_render_with_their_declared_variables(
        self, registry: PromptRegistry
    ) -> None:
        for name in SHIPPED_PROMPTS:
            prompt = registry.get(name)
            rendered = prompt.render(**dict.fromkeys(prompt.variables, "value"))
            assert "$" not in rendered, name

    def test_diagram_prompt_forbids_inventing_details(
        self, registry: PromptRegistry
    ) -> None:
        # Spec §5: the enrichment must never claim invisible details as facts.
        system = registry.get("diagram_interpretation").system or ""
        assert "never claim invisible details" in system.lower()

    def test_classification_schema_covers_the_spec_categories(
        self, registry: PromptRegistry
    ) -> None:
        schema = registry.get("image_classification").json_schema or {}
        categories = schema["properties"]["categories"]["items"]["enum"]
        assert {"architecture_diagram", "ui_screenshot", "decorative", "unknown"} <= set(
            categories
        )

    def test_unknown_prompt_raises(self, registry: PromptRegistry) -> None:
        with pytest.raises(PromptNotFoundError, match="available"):
            registry.get("nope")


class TestRegistryLoading:
    def test_manifest_missing_keys_is_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "bad.yaml").write_text("name: x\nversion: 1.0.0\n")
        with pytest.raises(InvalidPromptFileError, match="missing required keys"):
            PromptRegistry.from_directory(tmp_path)

    def test_non_mapping_manifest_is_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "bad.yaml").write_text("- just\n- a list\n")
        with pytest.raises(InvalidPromptFileError, match="YAML mapping"):
            PromptRegistry.from_directory(tmp_path)

    def test_conflicting_versions_are_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "a.yaml").write_text("name: dup\nversion: 1.0.0\ntemplate: x\n")
        (tmp_path / "b.yaml").write_text("name: dup\nversion: 2.0.0\ntemplate: y\n")
        with pytest.raises(InvalidPromptFileError, match="defined twice"):
            PromptRegistry.from_directory(tmp_path)

    def test_empty_directory_yields_empty_registry(self, tmp_path: Path) -> None:
        assert PromptRegistry.from_directory(tmp_path).names() == []
