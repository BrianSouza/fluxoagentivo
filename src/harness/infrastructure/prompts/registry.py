"""Loads prompt templates from the prompts/ directory (spec §11)."""

from pathlib import Path
from typing import Any

import yaml

from harness.domain.prompts.models import PromptTemplate

PROMPTS_ROOT = Path("prompts")

_REQUIRED_KEYS = ("name", "version", "template")


class PromptNotFoundError(LookupError):
    """Raised when a prompt name is not present in the registry."""


class InvalidPromptFileError(ValueError):
    """Raised when a prompt manifest is missing required fields."""


def load_prompt_file(path: Path) -> PromptTemplate:
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise InvalidPromptFileError(f"{path} does not contain a YAML mapping")
    missing = [key for key in _REQUIRED_KEYS if not raw.get(key)]
    if missing:
        raise InvalidPromptFileError(f"{path} is missing required keys: {missing}")
    return PromptTemplate(
        name=str(raw["name"]),
        version=str(raw["version"]),
        template=str(raw["template"]),
        system=str(raw["system"]) if raw.get("system") else None,
        json_schema=raw.get("json_schema"),
        description=str(raw.get("description", "")).strip(),
        variables=tuple(raw.get("variables", ())),
    )


class PromptRegistry:
    def __init__(self, prompts: dict[str, PromptTemplate]) -> None:
        self._prompts = prompts

    @classmethod
    def from_directory(cls, root: Path = PROMPTS_ROOT) -> "PromptRegistry":
        prompts: dict[str, PromptTemplate] = {}
        for path in sorted(root.rglob("*.yaml")):
            prompt = load_prompt_file(path)
            existing = prompts.get(prompt.name)
            if existing is not None and existing.version != prompt.version:
                raise InvalidPromptFileError(
                    f"prompt {prompt.name!r} defined twice with different versions "
                    f"({existing.version} and {prompt.version})"
                )
            prompts[prompt.name] = prompt
        return cls(prompts)

    def get(self, name: str) -> PromptTemplate:
        try:
            return self._prompts[name]
        except KeyError as exc:
            raise PromptNotFoundError(
                f"unknown prompt {name!r}; available: {sorted(self._prompts)}"
            ) from exc

    def names(self) -> list[str]:
        return sorted(self._prompts)
